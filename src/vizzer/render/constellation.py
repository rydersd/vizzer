"""Interactive constellation: compose frontend sources and inject graph data."""
from __future__ import annotations

import html
import json
import re
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote

from .. import __version__
from ..config import Config
from ..model import Graph, owner_question_fingerprint
from .common import priority_items, source_link_prefix

FRONTEND_DIR = "constellation"
FRONTEND_RESOURCES = (
    ("__VIZZER_TOKENS_CSS__", "tokens.css"),
    ("__VIZZER_LAYOUT_CSS__", "layout.css"),
    ("__VIZZER_VIEWS_CSS__", "views.css"),
    ("__VIZZER_BOOT_JS__", "boot.js"),
    ("__VIZZER_STATE_JS__", "state.js"),
    ("__VIZZER_VIEWS_JS__", "views.js"),
    ("__VIZZER_FILTERS_JS__", "filters.js"),
    ("__VIZZER_QUESTIONS_JS__", "questions.js"),
    ("__VIZZER_PLANNING_JS__", "planning.js"),
    ("__VIZZER_DOSSIER_JS__", "dossier.js"),
    ("__VIZZER_WORK_NAVIGATION_JS__", "work_navigation.js"),
    ("__VIZZER_CANVAS_JS__", "canvas.js"),
    ("__VIZZER_BOOTSTRAP_JS__", "bootstrap.js"),
)


def _frontend_text(name: str) -> str:
    """Read one frontend source through importlib resources, including zipapps."""
    return (files(__package__) / FRONTEND_DIR / name).read_text(encoding="utf-8")


def _template_text() -> str:
    """Inline frontend sources into the shell without adding runtime dependencies."""
    shell = _frontend_text("shell.html")
    missing = [token for token, _ in FRONTEND_RESOURCES if token not in shell]
    if missing:
        raise RuntimeError(f"constellation shell is missing resource slots: {missing}")
    resources = {token: _frontend_text(name)
                 for token, name in FRONTEND_RESOURCES}
    composed = re.sub(
        "|".join(re.escape(token) for token in resources),
        lambda match: resources[match.group(0)],
        shell,
    )
    composed = composed.replace("__ENGINE_VERSION__", html.escape(__version__))
    unresolved = re.findall(r"__(?:VIZZER|ENGINE)_[A-Z_]+__", composed)
    if unresolved:
        raise RuntimeError(f"constellation shell has unresolved resources: {unresolved}")
    return composed

# Authored appetite fallback used only when assessment is disabled.
APPETITE_W = {"small": 1.0, "medium": 1.9, "large": 2.9}
ASSESSED_W = {"XS": 0.75, "S": 1.0, "M": 1.9, "L": 2.9, "XL": 3.6}
DEFAULT_W = 1.4
_SIZE_BANDS = {"XS", "S", "M", "L", "XL"}
_UNCERTAINTY = {"U0", "U1", "U2", "U3"}
_PROVENANCE = {"observed", "authored", "inferred", "unknown"}
_PARALLEL = {"candidate", "serial", "unknown"}


def _bounded_strings(value: object, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    return [entry[:500] for entry in value[:limit]
            if isinstance(entry, str) and entry]


def _assessment_profile(value: object) -> dict:
    """Constrain persisted assessment data before it reaches HTML/JavaScript."""
    if not isinstance(value, dict):
        return {}
    raw_size = value.get("size")
    raw_impact = value.get("impact")
    raw_parallel = value.get("parallelism")
    if not all(isinstance(entry, dict)
               for entry in (raw_size, raw_impact, raw_parallel)):
        return {}
    band = raw_size.get("assessed_band")
    band = band if band in _SIZE_BANDS else None
    plausible = raw_size.get("plausible_range", {})
    if not isinstance(plausible, dict):
        plausible = {}
    dimensions = {}
    raw_dimensions = raw_size.get("dimensions", {})
    if isinstance(raw_dimensions, dict):
        for name in ("implementation", "verification", "integration", "coordination"):
            entry = raw_dimensions.get(name)
            if not isinstance(entry, dict):
                continue
            dimension_band = entry.get("band")
            provenance = entry.get("provenance")
            dimensions[name] = {
                "band": dimension_band if dimension_band in _SIZE_BANDS else None,
                "provenance": provenance if provenance in _PROVENANCE else "unknown",
            }
    burden_established = all(
        dimensions.get(name, {}).get("band") in _SIZE_BANDS
        for name in ("implementation", "verification", "integration", "coordination")
    )
    appetite_band = raw_size.get("normalized_appetite")
    appetite_band = appetite_band if appetite_band in _SIZE_BANDS else None

    def count(name: str) -> int:
        value = raw_impact.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return min(max(value, 0), 1_000_000)

    uncertainty = raw_size.get("uncertainty")
    provenance = raw_size.get("provenance")
    parallel = raw_parallel.get("classification")
    raw_appetite = raw_size.get("raw_authored_appetite")
    return {
        "band": band if burden_established else None,
        "appetiteBand": appetite_band,
        "burdenEstablished": burden_established,
        "uncertainty": uncertainty if uncertainty in _UNCERTAINTY else "U3",
        "range": [
            plausible.get("min") if plausible.get("min") in _SIZE_BANDS else None,
            plausible.get("max") if plausible.get("max") in _SIZE_BANDS else None,
        ],
        "provenance": provenance if provenance in _PROVENANCE else "unknown",
        "rawAuthoredAppetite": raw_appetite[:200]
        if isinstance(raw_appetite, str) else None,
        "dimensions": dimensions,
        "evidence": _bounded_strings(raw_size.get("evidence")),
        "unknowns": _bounded_strings(raw_size.get("unknowns")),
        "targetReach": count("structural_target_reach"),
        "immediateUnlock": count("immediate_unlock"),
        "frontierReach": count("frontier_reach"),
        "impactProvenance": raw_impact.get("provenance")
        if raw_impact.get("provenance") in _PROVENANCE else "unknown",
        "parallel": parallel if parallel in _PARALLEL else "unknown",
        "parallelConflicts": _bounded_strings(raw_parallel.get("conflicts")),
    }


def _int(value) -> int:
    """Best-effort integer for a value that reached us from a hand-editable file."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _progress(value: object) -> dict:
    """Constrain hand-edited graph progress to the renderer's tiny data contract."""
    if not isinstance(value, dict):
        return {}
    events = []
    for event in value.get("events", []):
        if not isinstance(event, dict):
            continue
        if all(isinstance(event.get(field), str) for field in ("at", "kind", "source", "detail")):
            events.append({"at": event["at"], "kind": event["kind"],
                           "source": event["source"], "detail": event["detail"]})
    result = {"events": events[-3:]}
    hot_window = value.get("hotWindowDays")
    if (isinstance(hot_window, (int, float)) and not isinstance(hot_window, bool)
            and hot_window > 0):
        result["hotWindowDays"] = min(float(hot_window), 36500)
    stall = value.get("stall")
    if (isinstance(stall, dict) and isinstance(stall.get("since"), str)
            and isinstance(stall.get("source"), str)):
        after_days = stall.get("afterDays")
        max_days = stall.get("maxDays")
        if (isinstance(after_days, (int, float)) and not isinstance(after_days, bool)
                and after_days >= 0
                and isinstance(max_days, (int, float)) and not isinstance(max_days, bool)
                and max_days > 0):
            result["stall"] = {
                "since": stall["since"],
                "source": stall["source"],
                "afterDays": min(float(after_days), 36500),
                "maxDays": min(float(max_days), 36500),
            }
    return result


def _top_group(graph: Graph, group_id: str | None) -> tuple[str, str]:
    """(top-level group id tail, immediate group title) for a node."""
    by_id = {g.id: g for g in graph.groups}
    imm = by_id.get(group_id or "")
    cur = imm
    while cur is not None and cur.parent is not None:
        cur = by_id.get(cur.parent)
    top_tail = cur.id.split(":", 1)[1] if cur else ""
    return top_tail, (imm.title if imm else "")


def _group_search_text(graph: Graph, group_id: str | None) -> str:
    """Return every authored id/title in an item's group ancestry."""
    by_id = {group.id: group for group in graph.groups}
    terms = []
    seen: set[str] = set()
    current = group_id
    while current and current not in seen:
        seen.add(current)
        group = by_id.get(current)
        terms.append(current)
        if group is None:
            break
        terms.append(group.title)
        current = group.parent
    return " ".join(terms)


def _visual_group(cfg: Config, status: str) -> str:
    """Map configured lifecycle roles onto the constellation's visual grammar."""
    role = cfg.status_role(status)
    if role == "done":
        return "shipped"
    if role == "active":
        return "active"
    if role == "regression":
        return "buggap"
    if role == "hold":
        return "parked"
    if role == "ready":
        if status == "ready":
            return "ready"
        if status == "specced":
            return "specced"
        return "faint"
    return "specced"


def _source_href(root: Path, cfg: Config, source_path: object) -> str:
    """Return a portable path-escaped link only for sources inside the repo."""
    if not isinstance(source_path, str) or not source_path:
        return ""
    repo = root.resolve()
    source = (repo / source_path).resolve()
    try:
        source.relative_to(repo)
    except ValueError:
        return ""
    relative = source.relative_to(repo).as_posix()
    return quote(source_link_prefix(cfg, root) + relative, safe="/")


def _question_payload(entry, node_index: int) -> dict:
    """Serialize the complete authored packet used by either question state."""
    return {
        "id": entry.id,
        "n": node_index,
        "storyId": entry.story_id,
        "fingerprint": owner_question_fingerprint(entry),
        "owner": entry.owner,
        "prompt": entry.prompt,
        "options": [{
            "id": option.id,
            "label": option.label,
            "tradeoff": option.tradeoff,
        } for option in entry.options],
        "recommendation": {
            "optionId": entry.recommendation.option_id,
            "rationale": entry.recommendation.rationale,
        },
        "falsifier": entry.falsifier,
        "evidence": list(entry.evidence),
    }


def _question_search_text(entry) -> str:
    return " ".join((
        entry.id,
        entry.owner,
        entry.prompt,
        *(value for option in entry.options
          for value in (option.id, option.label, option.tradeoff)),
        entry.recommendation.option_id,
        entry.recommendation.rationale,
        entry.falsifier,
        *entry.evidence,
    ))


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    # Manual highlights remain supported; deterministic recommendations augment
    # them when the priority engine is enabled.
    recommended = set(cfg.get("render.recommended", []))
    recommended.update(item.id for item in priority_items(graph))
    assessment_items = graph.assessment.get("items", {})
    portfolio = graph.assessment.get("portfolio", {})
    portfolio_lane = {}
    if isinstance(portfolio, dict):
        for lane in ("small", "anchors", "defects", "questions", "occupied", "blocked"):
            for item_id in portfolio.get(lane, []):
                portfolio_lane.setdefault(item_id, lane)
    nodes, idx = [], {}
    items = sorted(graph.items, key=lambda i: i.id)
    for it in items:
        if it.id in idx:
            continue
        idx[it.id] = len(nodes)
        cap_tail, epic_title = _top_group(graph, it.group)
        raw_assessment = assessment_items.get(it.id, {}) \
            if isinstance(assessment_items, dict) else {}
        assessment = _assessment_profile(raw_assessment)
        assessed_band = assessment.get("band")
        if assessment:
            # Unknown assessed size must look unknown, not silently inherit an
            # M-ish default or the authored estimate that failed assessment.
            w = ASSESSED_W.get(assessed_band, ASSESSED_W["XS"])
        else:
            w = APPETITE_W.get(it.appetite or "", DEFAULT_W)
        node = {
            "id": it.id,
            "s": it.id.split(":", 1)[1].split("/")[-1],
            "t": it.title[:80],
            "summary": (it.one_liner or "")[:240],
            "st": it.status,
            # codex-sequence-2026-08-08: one lifecycle role map across views.
            "g": _visual_group(cfg, it.status),
            "c": cap_tail,
            "e": epic_title[:40],
            "r": it.release or "",
            "role": it.role,
            "tags": list(it.tags),
            "facets": {name: list(values) for name, values in it.facets.items()},
            # Keep structural ownership intact for hierarchy views. ``c`` and
            # ``e`` are compact display labels; neither can reconstruct a
            # deep or project-configured group tree after rendering.
            "group": it.group or "",
            "p": it.source.get("path", ""),
            # codex-sequence-2026-08-08: visible canonical on-drive story link.
            "h": _source_href(root, cfg, it.source.get("path")),
            "w": round(0.72 + 0.36 * w, 2),
            # Activity comes from a checked-in file a human may have edited, and these
            # values are interpolated into the page — coerce to ints, never pass through.
            "ac": _int(it.activity.get("commits")),
            "am": _int(it.activity.get("mentions")),
            "ts": _int(it.activity.get("last_touched")),
            # codex-sequence-2026-08-08: one portable, renderer-owned search
            # index covers authored item text and the full group ancestry. Live
            # activity is appended below after its graph records are resolved.
            "q": " ".join(str(value) for value in (
                it.title,
                it.id,
                it.one_liner or "",
                it.status,
                it.release or "",
                it.role,
                " ".join(it.tags),
                " ".join(
                    value for values in it.facets.values() for value in values
                ),
                _group_search_text(graph, it.group),
                it.source.get("path", ""),
            ) if value),
        }
        progress = _progress(it.progress)
        if progress:
            node["pg"] = progress
            node["q"] += " " + " ".join(
                event["detail"] + " " + event["source"]
                for event in progress.get("events", [])
            )
        if it.id in recommended:
            node["rec"] = 1
        if assessment:
            node["assess"] = dict(assessment, lane=portfolio_lane.get(it.id, ""))
        if it.priority:
            node["pr"] = it.priority.get("rank")
            node["ps"] = it.priority.get("score")
            node["pw"] = it.priority.get("rationale", "")
            node["pu"] = it.priority.get("components", {}).get(
                "target_dependents", 0
            )
            defect = it.priority.get("defect")
            if isinstance(defect, dict):
                components = defect.get("components", {})
                node["dr"] = defect.get("rank")
                node["dw"] = defect.get("rationale", "")
                node["dt"] = components.get("target_impact", 0)
                node["dd"] = components.get("total_dependents", 0)
                node["dl"] = defect.get("lineage", "story-only")
                node["q"] += " " + str(defect.get("rationale", ""))
        nodes.append(node)

    # codex-sequence-2026-08-08: Foundation groups are explicit non-work nodes.  They deliberately have
    # no status, activity, hard edges, or priority; their only purpose is to
    # make the DAG's declared structural-root relationships inspectable.
    foundations = sorted(
        (group for group in graph.groups if group.kind == "foundation"),
        key=lambda group: group.id,
    )
    for group in foundations:
        source = group.meta.get("source", {}) if isinstance(group.meta, dict) else {}
        source_path = source.get("path", "") if isinstance(source, dict) else ""
        summary = group.meta.get("summary", "") if isinstance(group.meta, dict) else ""
        idx[group.id] = len(nodes)
        nodes.append({
            "id": group.id,
            "s": group.id.split(":", 1)[1],
            "t": group.title[:80],
            "summary": str(summary)[:240],
            "st": "foundation",
            "g": "foundation",
            "c": "foundations",
            "e": "Structural root",
            "r": "",
            "role": "reference",
            "tags": [],
            "facets": {},
            "p": source_path,
            "h": _source_href(root, cfg, source_path) if source_path else "",
            "w": 1.35,
            "ac": 0,
            "am": 0,
            "ts": 0,
            "foundation": 1,
            "q": f"{group.id} {group.title} {summary} foundation Structural root",
        })

    edges = []
    for it in items:
        j = idx[it.id]
        for dep in it.deps:
            i = idx.get(dep)
            if i is not None:
                edges.append([i, j])

    # codex-sequence-2026-08-08: typed lineage is visible but deliberately not
    # included in DATA.edges, which remains the hard-prerequisite readiness graph.
    relations = []
    for it in items:
        source = idx[it.id]
        for relation in it.relations:
            target = idx.get(relation.target)
            if target is not None:
                relations.append([source, target, relation.kind])

    # codex-sequence-2026-08-08: activity stays a switchable overlay. Explicit
    # relatedStoryIds create work-link pulses; ordinary graph edges only receive
    # one/both-active emphasis and never claim that the relation itself is edited.
    work = []
    work_links = []
    for entry in sorted(
        graph.active_work,
        key=lambda value: (value.story_id, value.agent, value.task),
    ):
        node_index = idx.get(entry.story_id)
        if node_index is None:
            continue
        work_index = len(work)
        work.append({
            "n": node_index,
            "agent": entry.agent,
            "task": entry.task,
            "state": entry.state,
            "done": entry.completed,
            "total": entry.total,
            "updatedAt": entry.updated_at,
            "staleAt": entry.stale_at,
            "checkpoint": entry.checkpoint or "",
        })
        nodes[node_index].setdefault("aw", []).append(work_index)
        # codex-sequence-2026-08-08: activity is searchable without becoming
        # lifecycle or priority truth. Keep every human-facing text field.
        nodes[node_index]["q"] += " " + " ".join(filter(None, (
            entry.agent,
            entry.task,
            entry.state,
            entry.checkpoint or "",
            entry.updated_at,
            entry.stale_at,
        )))
        for related_id in entry.related_story_ids:
            related_index = idx.get(related_id)
            if related_index is not None:
                work_links.append([work_index, related_index])

    # Explicit checkpoint chronology is the only authority for an agent trail.
    # Dependency proximity and layout adjacency are intentionally ignored: a
    # pretty inferred route would be a fabricated work record.
    trail_limit = cfg.get("activity.trail_rounds", 5)
    activity_by_agent: dict[str, list] = {}
    for entry in graph.active_work:
        if entry.story_id in idx:
            activity_by_agent.setdefault(entry.agent, []).append(entry)
    agent_trails = []
    for agent, entries in sorted(activity_by_agent.items()):
        checkpoints = []
        for entry in sorted(
            entries,
            key=lambda value: (
                value.updated_at, value.story_id, value.task, value.state,
            ),
        ):
            point = {
                "n": idx[entry.story_id],
                "at": entry.updated_at,
                "state": entry.state,
                "task": entry.task,
            }
            if checkpoints and checkpoints[-1]["n"] == point["n"]:
                checkpoints[-1] = point
            else:
                checkpoints.append(point)
        checkpoints = checkpoints[-trail_limit:]
        if len(checkpoints) >= 2:
            agent_trails.append({"agent": agent, "points": checkpoints})

    # Questions are explicit researched decisions, not a spelling of "blocked".
    # Keeping them separate lets a question survive stale/completed work and lets
    # operational blockers remain honest.
    questions = []
    for entry in sorted(graph.owner_questions, key=lambda value: value.id):
        node_index = idx.get(entry.story_id)
        if node_index is None:
            continue
        question_index = len(questions)
        questions.append(_question_payload(entry, node_index))
        nodes[node_index].setdefault("oq", []).append(question_index)
        nodes[node_index]["q"] += " " + _question_search_text(entry)

    # Accepted decisions are repo-authoritative history, not open questions.
    # Keep the question snapshot in the static payload so a reader can judge an
    # answer without relying on a mutable activity feed that may have moved on.
    decisions = []
    for entry in sorted(
        graph.owner_decisions,
        key=lambda value: (value.question.id, value.revision),
    ):
        question = entry.question
        node_index = idx.get(question.story_id)
        if node_index is None:
            continue
        decision_index = len(decisions)
        serialized = _question_payload(question, node_index)
        serialized.update({
            "fingerprint": entry.fingerprint,
            "revision": entry.revision,
            "answeredAt": entry.answered_at,
            "answeredBy": entry.answered_by,
            "kind": entry.kind,
            "optionId": entry.option_id,
            "text": entry.text,
        })
        decisions.append(serialized)
        nodes[node_index].setdefault("od", []).append(decision_index)
        nodes[node_index]["q"] += " " + " ".join(filter(None, (
            _question_search_text(question),
            entry.fingerprint,
            str(entry.revision),
            entry.answered_at,
            entry.answered_by,
            entry.kind,
            entry.option_id,
            entry.text,
        )))

    caps: dict[str, dict] = {}
    done = cfg.done_statuses()
    for it in (item for item in items if item.role == "delivery"):
        cap_tail, _ = _top_group(graph, it.group)
        caps.setdefault(cap_tail, {"total": 0, "shipped": 0})
        caps[cap_tail]["total"] += 1
        if it.status in done:
            caps[cap_tail]["shipped"] += 1
    # codex-sequence-2026-08-08: foundation nodes are Structure-lens relation
    # targets, not deliverable capabilities with a fake 0/N progress bar.

    planning = dict(graph.priority.get("planning", {}))
    planning["baseTargets"] = graph.priority.get("base_targets", [])
    planning["effectiveTargets"] = graph.priority.get("effective_targets", [])
    rendered_groups = []
    for group in sorted(graph.groups, key=lambda value: value.id):
        entry = {
            "id": group.id,
            "kind": group.kind,
            "title": group.title,
            "parent": group.parent or "",
        }
        source = group.meta.get("source", {}) if isinstance(group.meta, dict) else {}
        source_path = source.get("path", "") if isinstance(source, dict) else ""
        if source_path:
            entry["p"] = source_path
            entry["h"] = _source_href(root, cfg, source_path)
        summary = group.meta.get("summary") if isinstance(group.meta, dict) else None
        if isinstance(summary, str) and summary:
            entry["summary"] = summary[:240]
        rendered_groups.append(entry)

    data = {
        "engineVersion": __version__,
        "nodes": nodes,
        "groups": rendered_groups,
        "edges": edges,
        "relations": relations,
        "work": work,
        "workLinks": work_links,
        "agentTrails": agent_trails,
        "questions": questions,
        "decisions": decisions,
        # Accepted owner planning course is inspectable in static mode. Writes
        # remain available only through the guarded loopback service.
        "planning": planning,
        "workstreams": graph.workstreams,
        "caps": caps,
        "areas": cfg.areas(),
        "sourceAreas": cfg.source_areas(),
        # deterministic "now": the newest activity in the graph, never wall clock
        "now": max((n["ts"] for n in nodes), default=0),
    }
    if graph.assessment:
        data["assessment"] = {
            "schema": graph.assessment.get("schema"),
            "method": graph.assessment.get("method"),
            "portfolio": portfolio if isinstance(portfolio, dict) else {},
        }
    # codex-sequence-2026-08-08: Default output is portable and root-free.
    # The documented Obsidian integration remains an explicit local-vault opt-in.
    if cfg.get("render.obsidian_links", False):
        data["root"] = str(root)
    repo_url = cfg.get("render.repo_url", "")
    if repo_url:
        data["repo"] = repo_url

    title = cfg.get("render.title", "") or f"{cfg.get('project.name', 'project')} — constellation"
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    payload = (
        payload.replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    # Substitute in ONE pass. Replacing sequentially lets the first substitution's
    # output be re-scanned by the second: a title containing the literal "__DATA__"
    # smuggled the whole JSON payload into the HTML body, outside the script element,
    # where node titles are not HTML-escaped.
    substitutions = {"__TITLE__": html.escape(title, quote=True), "__DATA__": payload}
    rendered = re.sub(
        "|".join(re.escape(token) for token in substitutions),
        lambda match: substitutions[match.group(0)],
        _template_text(),
    )
    return {"constellation.html": rendered}
