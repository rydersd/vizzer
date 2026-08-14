"""Deterministic story uptake and defect-impact ranking.

The score deliberately ignores commits, mentions, and generic fan-out.  Those
measure attention, not V1 leverage.  Only hard dependency reachability into an
explicit/derived target set contributes graph leverage; typed lineage remains
visible but nonblocking and non-scoring for uptake.

Defect ranking is deliberately separate: a bug gap's known blast radius is the
hard-dependency reach of the shipped contract named by ``bug_against`` (or the
gap story itself when that lineage is absent).  It never pretends that graph
reach is severity, and it labels unlinked gaps so weak provenance stays visible.
"""
from __future__ import annotations

from collections import defaultdict
import heapq
import json
from pathlib import Path

from .model import Graph, Item


_DEFAULT_ROLE_BIAS = {"regression": 80, "active": 50, "ready": 0}
def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(entry for entry in value if isinstance(entry, str) and entry))


def _int_map(value, fallback: dict[str, int]) -> dict[str, int]:
    if not isinstance(value, dict):
        return dict(fallback)
    result = dict(fallback)
    for key, raw in value.items():
        if isinstance(key, str) and isinstance(raw, int) and not isinstance(raw, bool):
            result[key] = raw
    return result


def _incomplete(item: Item | None, done_statuses: set[str]) -> bool:
    return item is not None and item.status not in done_statuses


def _manifest_target_items(cfg, root: Path | None):
    configured = cfg.get("priority.target_manifest", "")
    if not isinstance(configured, str) or not configured:
        return None, [], None
    relpath = Path(configured)
    warnings = []
    if root is None:
        return [], [
            f"priority target manifest {configured} cannot be read without a project root"
        ], configured
    project_root = Path(root).resolve()
    try:
        path = (project_root / relpath).resolve()
        path.relative_to(project_root)
    except (OSError, ValueError):
        return [], [
            f"priority target manifest {configured} escapes the project root (ignored)"
        ], configured
    if relpath.is_absolute():
        return [], [
            f"priority target manifest {configured} must be a relative in-project path"
        ], configured
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        return [], [f"priority target manifest {configured} is unreadable or malformed"], configured
    if not isinstance(data, dict):
        return [], [f"priority target manifest {configured} must be a JSON object"], configured
    if "schema" in data and data["schema"] != 1:
        return [], [f"priority target manifest {configured} has unsupported schema"], configured
    raw_items = data.get("directTargetIds")
    if not isinstance(raw_items, list) or not all(isinstance(item, str) and item
                                                  for item in raw_items):
        return [], [
            f"priority target manifest {configured} directTargetIds must be strings"
        ], configured
    seen = set()
    items = []
    for item_id in raw_items:
        if item_id in seen:
            warnings.append(
                f"priority target manifest {configured} duplicates {item_id}"
            )
            continue
        seen.add(item_id)
        items.append(item_id)
    return items, warnings, configured


def _target_scope(graph: Graph, cfg, done_statuses: set[str], root: Path | None):
    """Return target ids and provenance using a narrowing fallback ladder.

    An authored-but-invalid tier never falls through to a broad release.  A typo
    should yield a warning and zero recommendations, not quietly reprioritize the
    project around hundreds of stories.
    """
    by_id = graph.item_map()
    milestone_by_id = {milestone.id: milestone for milestone in graph.milestones}
    manifest_items, manifest_warnings, manifest_path = _manifest_target_items(cfg, root)
    configured_items = _string_list(cfg.get("priority.target_items", []))
    configured_milestones = _string_list(cfg.get("priority.target_milestones", []))
    configured_releases = _string_list(cfg.get("priority.target_releases", []))
    warnings = list(manifest_warnings)
    provenance: dict[str, list[str]] = defaultdict(list)

    if manifest_items is not None:
        tier = "target-manifest"
        for item_id in manifest_items:
            if item_id not in by_id:
                warnings.append(f"priority target item {item_id} is unknown (target dropped)")
            elif _incomplete(by_id[item_id], done_statuses):
                provenance[item_id].append(f"manifest:{manifest_path}")
    elif configured_items:
        tier = "configured-items"
        for item_id in configured_items:
            if item_id not in by_id:
                warnings.append(f"priority target item {item_id} is unknown (target dropped)")
            elif _incomplete(by_id[item_id], done_statuses):
                provenance[item_id].append("configured-item")
    elif configured_milestones:
        tier = "configured-milestones"
        for milestone_id in configured_milestones:
            milestone = milestone_by_id.get(milestone_id)
            if milestone is None:
                warnings.append(
                    f"priority target milestone {milestone_id} is unknown (target dropped)"
                )
                continue
            for phase in milestone.phases:
                for item_id in phase.items:
                    if _incomplete(by_id.get(item_id), done_statuses):
                        provenance[item_id].append(f"milestone:{milestone_id}")
    elif configured_releases:
        tier = "configured-releases"
        for release in configured_releases:
            for item in graph.items:
                if item.release == release and _incomplete(item, done_statuses):
                    provenance[item.id].append(f"release:{release}")
    else:
        active_milestone = next((
            milestone for milestone in graph.milestones
            if any(
                _incomplete(by_id.get(item_id), done_statuses)
                for phase in milestone.phases
                for item_id in phase.items
            )
        ), None)
        if active_milestone is not None:
            tier = "active-milestone"
            for phase in active_milestone.phases:
                for item_id in phase.items:
                    if _incomplete(by_id.get(item_id), done_statuses):
                        provenance[item_id].append(f"milestone:{active_milestone.id}")
        else:
            releases = _string_list(cfg.get("render.releases", []))
            active_release = next((
                release for release in releases
                if any(item.release == release and _incomplete(item, done_statuses)
                       for item in graph.items)
            ), None)
            tier = "active-release" if active_release is not None else "none"
            if active_release is not None:
                for item in graph.items:
                    if item.release == active_release and _incomplete(item, done_statuses):
                        provenance[item.id].append(f"release:{active_release}")

    return set(provenance), {
        item_id: sorted(set(sources)) for item_id, sources in sorted(provenance.items())
    }, tier, warnings


def _condensed_dependents(graph: Graph):
    """Condense hard-dependency cycles into a DAG.

    Reachability counts unique target items, so a diamond is counted once; SCC
    condensation means walking a cycle cannot manufacture reach or path depth.
    """
    ids = sorted(item.id for item in graph.items)
    known = set(ids)
    forward = {item.id: sorted({dep for dep in item.deps if dep in known})
               for item in graph.items}
    # Iterative Kosaraju avoids Python's recursion limit on a legitimate long
    # release chain.  A prioritizer falling over at ~1,000 stories would be a
    # fairly embarrassing definition of "project leverage".
    visited = set()
    finish_order = []
    for item_id in ids:
        if item_id in visited:
            continue
        visited.add(item_id)
        stack = [(item_id, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                finish_order.append(node)
                continue
            stack.append((node, True))
            for target in reversed(forward[node]):
                if target not in visited:
                    visited.add(target)
                    stack.append((target, False))

    reverse: dict[str, list[str]] = {item_id: [] for item_id in ids}
    for source, targets in forward.items():
        for target in targets:
            reverse[target].append(source)
    for targets in reverse.values():
        targets.sort()

    components: list[list[str]] = []
    assigned = set()
    for item_id in reversed(finish_order):
        if item_id in assigned:
            continue
        component = []
        assigned.add(item_id)
        stack = [item_id]
        while stack:
            node = stack.pop()
            component.append(node)
            for target in reversed(reverse[node]):
                if target not in assigned:
                    assigned.add(target)
                    stack.append(target)
        components.append(sorted(component))

    component_of = {}
    for component_id, members in enumerate(components):
        for member in members:
            component_of[member] = component_id
    dependents: dict[int, set[int]] = {i: set() for i in range(len(components))}
    for item in graph.items:
        dependent_component = component_of[item.id]
        for dep in item.deps:
            dependency_component = component_of.get(dep)
            if dependency_component is not None and dependency_component != dependent_component:
                dependents[dependency_component].add(dependent_component)
    return components, component_of, dependents


def apply_priorities(graph: Graph, cfg, root: Path | None = None,
                     overlay_state: dict | None = None) -> None:
    """Annotate graph and items in-place when priority recommendations are enabled."""
    if not bool(cfg.get("priority.enabled", False)):
        return

    done_statuses = cfg.done_statuses()
    targets, provenance, target_tier, target_warnings = _target_scope(
        graph, cfg, done_statuses, root
    )
    base_targets = set(targets)
    course = {"promote": [], "defer": [], "order": []}
    overlay_revision = 0
    overlay_author = "owner"
    overlay_updated_at = None
    overlay_rationale = ""
    overlay_warnings = []
    if bool(cfg.get("planning.enabled", False)) and root is not None:
        from .planning import read_overlay, validate_state

        if overlay_state is None:
            overlay, overlay_warnings = read_overlay(
                cfg, root, graph, strict=False
            )
            if overlay is not None:
                course = overlay["state"]
                overlay_revision = overlay["revision"]
                overlay_author = overlay.get("author", "owner")
                overlay_updated_at = overlay.get("updatedAt")
                overlay_rationale = overlay.get("rationale", "")
        else:
            try:
                course = validate_state(overlay_state, graph)
                overlay_author = "proposal"
            except ValueError as exc:
                overlay_warnings = [f"planning proposal ignored: {exc}"]
    graph.warnings = sorted(set(graph.warnings).union(overlay_warnings))
    for item_id in course["promote"]:
        if _incomplete(graph.item_map().get(item_id), done_statuses):
            targets.add(item_id)
            provenance.setdefault(item_id, []).append("planning-overlay:promote")
        else:
            overlay_warnings.append(
                f"planning promotion {item_id} is already done (ignored for uptake)"
            )
    for item_id in course["defer"]:
        targets.discard(item_id)
        provenance.pop(item_id, None)
    order_by_target = {item_id: index for index, item_id in enumerate(course["order"])}
    graph.warnings = sorted(
        set(graph.warnings).union(target_warnings).union(overlay_warnings)
    )
    components, component_of, dependents = _condensed_dependents(graph)
    targets_by_component: dict[int, set[str]] = defaultdict(set)
    for item_id in targets:
        targets_by_component[component_of[item_id]].add(item_id)

    indegree = {component_id: 0 for component_id in dependents}
    for children in dependents.values():
        for child in children:
            indegree[child] += 1
    ready = sorted(component_id for component_id, degree in indegree.items() if degree == 0)
    heapq.heapify(ready)
    topo_order = []
    while ready:
        component_id = heapq.heappop(ready)
        topo_order.append(component_id)
        for child in sorted(dependents[component_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)

    reach_cache: dict[int, tuple[set[str], int]] = {}
    for component_id in reversed(topo_order):
        reached = set(targets_by_component.get(component_id, set()))
        max_depth = 0 if reached else -1
        for child in sorted(dependents[component_id]):
            child_targets, child_depth = reach_cache[child]
            reached.update(child_targets)
            if child_depth >= 0:
                max_depth = max(max_depth, child_depth + 1)
        reach_cache[component_id] = reached, max_depth

    # All-story downstream reach is a different question from target-scoped
    # uptake.  Keep it in a separate cache so a popular story can never leak
    # into the feature recommendation score merely because it has fan-out.
    downstream_cache: dict[int, set[str]] = {}
    direct_dependents: dict[int, set[str]] = {}
    for component_id in reversed(topo_order):
        direct = {
            member
            for child in dependents[component_id]
            for member in components[child]
        }
        reached = set(direct)
        for child in dependents[component_id]:
            reached.update(downstream_cache[child])
        direct_dependents[component_id] = direct
        downstream_cache[component_id] = reached

    role_bias = _int_map(cfg.get("priority.role_bias", {}), _DEFAULT_ROLE_BIAS)
    eligible_roles = set(_string_list(
        cfg.get("priority.eligible_roles", ["ready", "active", "regression"])
    ))
    excluded_flags = set(_string_list(
        cfg.get("priority.exclude_flags", ["blocked", "triage", "stale"])
    ))
    gates = cfg.gates()
    by_id = graph.item_map()
    scored = []

    # Milestone membership is a modest bias, never a substitute for target reach.
    incomplete_milestone_items = {
        item_id
        for milestone in graph.milestones
        for phase in milestone.phases
        for item_id in phase.items
        if _incomplete(by_id.get(item_id), done_statuses)
    }

    for item in sorted(graph.items, key=lambda entry: entry.id):
        role = cfg.status_role(item.status)
        reasons = []
        if item.status in done_statuses or role == "done":
            reasons.append("done")
        if role == "hold":
            reasons.append("held")
        if role not in eligible_roles:
            reasons.append(f"role:{role} not eligible")
        if item.id in gates:
            reasons.append("decision-gated")
        matching_flags = sorted(set(item.flags).intersection(excluded_flags))
        if matching_flags:
            reasons.append("excluded flags: " + ", ".join(matching_flags))
        if item.id in course["defer"]:
            reasons.append("deferred by planning overlay")
        unresolved_deps = sorted(
            dep for dep in item.deps
            if dep in by_id and by_id[dep].status not in done_statuses
        )
        if unresolved_deps:
            reasons.append("unready: " + ", ".join(unresolved_deps))

        reached, depth = reach_cache[component_of[item.id]]
        direct_target = int(item.id in targets)
        dependent_targets = sorted(reached - {item.id})
        ordered_targets = sorted(
            (order_by_target[target], target)
            for target in reached if target in order_by_target
        )
        course_order = ordered_targets[0][0] if ordered_targets else None
        if not reached:
            reasons.append("outside target dependency reach")
        values = {
            "direct_target": direct_target,
            "target_dependents": len(dependent_targets),
            "critical_path_depth": max(0, depth),
            "milestone_member": int(item.id in incomplete_milestone_items),
            "role_bias": role_bias.get(role, 0),
            "course_order": course_order,
        }
        score = (
            values["direct_target"] * 400
            + values["target_dependents"] * 500
            + values["critical_path_depth"] * 40
            + values["milestone_member"] * 100
            + values["role_bias"]
        )
        item.priority = {
            "eligible": not reasons,
            "score": score if not reasons else None,
            "rank": None,
            "components": values,
            "target_items": sorted(reached),
            "rationale": (
                f"{len(dependent_targets)} incomplete target dependent(s), "
                f"depth {max(0, depth)}, role {role}"
                if not reasons else "; ".join(reasons)
            ),
        }
        if not reasons:
            scored.append(item)

    scored.sort(key=lambda item: (
        item.priority["components"]["course_order"] is None,
        item.priority["components"]["course_order"]
        if item.priority["components"]["course_order"] is not None else 10 ** 9,
        -item.priority["score"],
        -item.priority["components"]["target_dependents"],
        -item.priority["components"]["critical_path_depth"],
        item.id,
    ))
    raw_limit = cfg.get("priority.limit", 10)
    limit = raw_limit if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) else 10
    limit = max(0, limit)
    for rank, item in enumerate(scored, 1):
        item.priority["rank"] = rank

    # Every bug gap receives a structural burn-down rank, even when it is
    # outside the current target set.  Explicit ``bug_against`` lineage lets a
    # narrow repair inherit the affected shipped contract's reach; without it
    # we rank only the gap story's own known graph reach and say so.
    defect_items = []
    for item in sorted(graph.items, key=lambda entry: entry.id):
        if item.status != "bug-gap":
            continue
        affected_contracts = sorted({
            relation.target
            for relation in item.relations
            if relation.kind == "bug_against" and relation.target in component_of
        })
        anchors = affected_contracts or [item.id]
        downstream: set[str] = set()
        direct: set[str] = set()
        for anchor in anchors:
            component_id = component_of[anchor]
            downstream.update(downstream_cache[component_id])
            direct.update(direct_dependents[component_id])
        downstream.difference_update(anchors)
        direct.difference_update(anchors)
        impacted_targets = sorted(targets.intersection(set(anchors) | downstream))
        incomplete_downstream = sorted(
            item_id for item_id in downstream
            if _incomplete(by_id.get(item_id), done_statuses)
        )
        lineage = "bug-against" if affected_contracts else "story-only"
        lineage_detail = (
            "bug against " + ", ".join(affected_contracts)
            if affected_contracts
            else "missing Bug against lineage; ranked from the gap story only"
        )
        defect = {
            "rank": None,
            "lineage": lineage,
            "affected_contracts": affected_contracts,
            "target_items": impacted_targets,
            "components": {
                "direct_target": int(any(anchor in targets for anchor in anchors)),
                "target_impact": len(impacted_targets),
                "direct_dependents": len(direct),
                "incomplete_dependents": len(incomplete_downstream),
                "total_dependents": len(downstream),
            },
            "rationale": (
                f"{len(impacted_targets)} V1 target(s), "
                f"{len(incomplete_downstream)} incomplete downstream, "
                f"{len(downstream)} total downstream; {lineage_detail}"
            ),
        }
        item.priority["defect"] = defect
        defect_items.append(item)

    defect_items.sort(key=lambda item: (
        -item.priority["defect"]["components"]["target_impact"],
        -item.priority["defect"]["components"]["direct_target"],
        -item.priority["defect"]["components"]["incomplete_dependents"],
        -item.priority["defect"]["components"]["total_dependents"],
        -item.priority["defect"]["components"]["direct_dependents"],
        item.priority["defect"]["lineage"] != "bug-against",
        item.id,
    ))
    for rank, item in enumerate(defect_items, 1):
        item.priority["defect"]["rank"] = rank

    graph.priority = {
        "method": "target-reach-v1",
        "target_tier": target_tier,
        "base_targets": sorted(base_targets),
        "effective_targets": sorted(targets),
        "planning": {
            "enabled": bool(cfg.get("planning.enabled", False)),
            "revision": overlay_revision,
            "author": overlay_author,
            "updatedAt": overlay_updated_at,
            "rationale": overlay_rationale,
            "promote": list(course["promote"]),
            "defer": list(course["defer"]),
            "order": list(course["order"]),
        },
        "targets": [
            {"item": item_id, "sources": provenance[item_id]}
            for item_id in sorted(targets)
        ],
        "recommendations": [item.id for item in scored[:limit]],
        "defects": [item.id for item in defect_items],
    }
