"""Owner-authored planning overlay and course-change analysis.

The overlay is deliberately separate from story specs and target manifests.  It
changes uptake order; it never rewrites lifecycle, dependency, or release truth.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from .model import Graph


SCHEMA = 1
# codex-sequence-2026-08-08: planning is an audited overlay, never spec write-back.
MAX_ITEMS = 500
MAX_HISTORY = 100


class PlanningError(ValueError):
    """A planning request or overlay is invalid."""


class StaleRevisionError(PlanningError):
    """The caller analyzed an older overlay revision."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _overlay_path(cfg, root: Path) -> Path:
    raw = cfg.get("planning.overlay_path", "vizzer/planning-overlay.json")
    if not isinstance(raw, str) or not raw:
        raise PlanningError("planning.overlay_path must be a non-empty string")
    relative = Path(raw)
    if relative.is_absolute():
        raise PlanningError("planning overlay path must be relative")
    project_root = root.resolve()
    if ".." in relative.parts:
        raise PlanningError("planning overlay path escapes the project root")
    lexical = project_root / relative
    try:
        parent = lexical.parent.resolve()
        parent.relative_to(project_root)
    except (OSError, ValueError):
        raise PlanningError("planning overlay path escapes the project root") from None
    # Resolve the parent, not the leaf: resolving the leaf first erases the fact
    # that an in-project overlay path itself is a symlink.
    if lexical.is_symlink():
        raise PlanningError("planning overlay must be a regular file, not a symlink")
    return parent / lexical.name


def empty_state() -> dict:
    return {"promote": [], "defer": [], "order": []}


def _validate_ids(value, field: str, known: set[str] | None) -> list[str]:
    if not isinstance(value, list):
        raise PlanningError(f"planning {field} must be an array")
    if len(value) > MAX_ITEMS:
        raise PlanningError(f"planning {field} exceeds {MAX_ITEMS} items")
    if not all(isinstance(item_id, str) and item_id for item_id in value):
        raise PlanningError(f"planning {field} must contain non-empty item ids")
    if len(set(value)) != len(value):
        raise PlanningError(f"planning {field} contains duplicate item ids")
    if known is not None:
        unknown = sorted(set(value) - known)
        if unknown:
            raise PlanningError(f"unknown planning item: {unknown[0]}")
    return list(value)


def validate_state(value, graph: Graph | None = None) -> dict:
    if not isinstance(value, dict):
        raise PlanningError("planning state must be an object")
    allowed = {"promote", "defer", "order"}
    unknown_fields = sorted(set(value) - allowed)
    if unknown_fields:
        raise PlanningError(f"unknown planning field: {unknown_fields[0]}")
    known = set(graph.item_map()) if graph is not None else None
    state = {
        field: _validate_ids(value.get(field, []), field, known)
        for field in ("promote", "defer", "order")
    }
    conflict = sorted(set(state["promote"]) & set(state["defer"]))
    if conflict:
        raise PlanningError(f"item cannot be promoted and deferred: {conflict[0]}")
    return state


def _validate_overlay(data, graph: Graph | None = None) -> dict:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise PlanningError("planning overlay must be a schema-1 JSON object")
    revision = data.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise PlanningError("planning overlay revision must be a non-negative integer")
    state = validate_state(data.get("state", {}), graph)
    history = data.get("history", [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise PlanningError(f"planning overlay history must have at most {MAX_HISTORY} entries")
    previous = -1
    for entry in history:
        if not isinstance(entry, dict):
            raise PlanningError("planning history entries must be objects")
        entry_revision = entry.get("revision")
        if (isinstance(entry_revision, bool) or not isinstance(entry_revision, int)
                or entry_revision <= previous or entry_revision > revision):
            raise PlanningError("planning history revisions must increase through current revision")
        previous = entry_revision
        validate_state(entry.get("state", {}), graph)
    if history and history[-1].get("revision") != revision:
        raise PlanningError("planning history must end at the current revision")
    if revision > 0 and not history:
        raise PlanningError("planning overlay revisions require audit history")
    result = dict(data)
    result["state"] = state
    result["history"] = history
    return result


def read_overlay(cfg, root: Path, graph: Graph | None = None, *, strict: bool = True):
    """Return ``(overlay, warnings)``. Missing files are a valid revision zero."""
    try:
        path = _overlay_path(cfg, root)
        if not path.exists():
            return {
                "schema": SCHEMA, "revision": 0, "updatedAt": None,
                "author": "owner", "rationale": "", "state": empty_state(),
                "history": [],
            }, []
        if path.is_symlink() or not path.is_file():
            raise PlanningError("planning overlay must be a regular file, not a symlink")
        data = json.loads(path.read_text(encoding="utf-8"))
        return _validate_overlay(data, graph), []
    except (OSError, UnicodeError, json.JSONDecodeError, PlanningError) as exc:
        error = exc if isinstance(exc, PlanningError) else PlanningError(str(exc))
        if strict:
            raise error
        return None, [f"planning overlay ignored: {error}"]


def _incomplete_prerequisites(graph: Graph, target_ids: set[str], done: set[str]) -> set[str]:
    by_id = graph.item_map()
    result: set[str] = set()
    stack = list(target_ids)
    seen = set(stack)
    while stack:
        item_id = stack.pop()
        item = by_id.get(item_id)
        if item is None:
            continue
        for dep in item.deps:
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
            dependency = by_id.get(dep)
            if dependency is not None and dependency.status not in done:
                result.add(dep)
    return result


def _target_membership(graph: Graph) -> dict[str, list[str]]:
    membership: dict[str, list[str]] = {}
    for milestone in graph.milestones:
        for phase in milestone.phases:
            for item_id in phase.items:
                membership.setdefault(item_id, []).append(
                    f"{milestone.id}/{phase.name}"
                )
    return membership


def analyze_change(graph: Graph, cfg, root: Path, proposed_state: dict) -> dict:
    """Compare a proposed accepted course to the current accepted course."""
    from .priority import apply_priorities

    state = validate_state(proposed_state, graph)
    current_overlay, _ = read_overlay(cfg, root, graph)
    current_state = current_overlay["state"]

    current_graph = copy.deepcopy(graph)
    proposed_graph = copy.deepcopy(graph)
    apply_priorities(current_graph, cfg, root, overlay_state=current_state)
    apply_priorities(proposed_graph, cfg, root, overlay_state=state)
    current_meta = current_graph.priority
    proposed_meta = proposed_graph.priority
    current_targets = set(current_meta.get("effective_targets", []))
    proposed_targets = set(proposed_meta.get("effective_targets", []))
    base_targets = set(proposed_meta.get("base_targets", []))
    done = cfg.done_statuses()
    current_closure = _incomplete_prerequisites(graph, current_targets, done)
    proposed_closure = _incomplete_prerequisites(graph, proposed_targets, done)
    by_id = graph.item_map()

    changed_ids = set(current_state["promote"] + current_state["defer"])
    changed_ids.update(state["promote"] + state["defer"])
    readiness = []
    for item_id in sorted(changed_ids):
        item = by_id[item_id]
        unresolved = sorted(
            dep for dep in item.deps
            if dep in by_id and by_id[dep].status not in done
        )
        readiness.append({
            "item": item_id,
            "status": item.status,
            "ready": not unresolved and item.status not in done,
            "unresolvedPrerequisites": unresolved,
        })

    current_recs = current_meta.get("recommendations", [])
    proposed_recs = proposed_meta.get("recommendations", [])
    membership = _target_membership(graph)
    promoted = sorted(set(state["promote"]) - set(current_state["promote"]))
    deferred = sorted(set(state["defer"]) - set(current_state["defer"]))
    releases = sorted({
        by_id[item_id].release or "unassigned"
        for item_id in set(promoted + deferred)
    })
    milestone_changes = [
        {"item": item_id, "course": "promoted" if item_id in promoted else "deferred",
         "milestones": membership.get(item_id, [])}
        for item_id in sorted(set(promoted + deferred))
    ]
    displaced = sorted(base_targets & set(state["defer"]))
    dropped_recs = [item_id for item_id in current_recs if item_id not in proposed_recs]
    added_recs = [item_id for item_id in proposed_recs if item_id not in current_recs]
    warnings = []
    for item_id in displaced:
        warnings.append(f"defers current target {item_id}")
    for item_id in sorted(set(state["defer"]) & proposed_closure):
        warnings.append(f"{item_id} is deferred but remains an incomplete prerequisite")
    for item_id in state["promote"]:
        if by_id[item_id].status in done:
            warnings.append(f"{item_id} is already done and adds no uptake work")
    for item_id in state["order"]:
        if item_id not in proposed_targets:
            warnings.append(
                f"{item_id} is ordered but is not an effective target; promote it first"
            )

    return {
        "schema": SCHEMA,
        "generatedAt": _now(),
        "baseRevision": current_overlay["revision"],
        "proposal": state,
        "delta": {
            "promoted": promoted,
            "deferred": deferred,
            "newPrerequisites": sorted(proposed_closure - current_closure),
            "removedPrerequisites": sorted(current_closure - proposed_closure),
        },
        "readiness": readiness,
        "recommendations": {
            "before": current_recs,
            "after": proposed_recs,
            "added": added_recs,
            "displaced": dropped_recs,
        },
        "opportunityCost": {
            "displacedCurrentV1Targets": displaced,
            "recommendationsPushedOut": dropped_recs,
            "additionalIncompletePrerequisites": len(proposed_closure - current_closure),
        },
        "releaseImplications": {
            "affectedReleases": releases,
            "milestoneChanges": milestone_changes,
        },
        "warnings": warnings,
        "provenance": {
            "baseTargetTier": proposed_meta.get("target_tier", "none"),
            "baseTargetManifest": cfg.get("priority.target_manifest", ""),
            "overlayPath": cfg.get("planning.overlay_path", "vizzer/planning-overlay.json"),
        },
    }


def _write_overlay(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def restore_overlay(cfg, root: Path, overlay: dict) -> None:
    """Atomically restore a validated snapshot after a derived refresh fails."""
    normalized = _validate_overlay(overlay)
    _write_overlay(_overlay_path(cfg, root), normalized)


def apply_change(graph: Graph, cfg, root: Path, state: dict, *, expected_revision: int,
                 rationale: str, analysis: dict | None = None) -> dict:
    if not isinstance(rationale, str) or not rationale.strip():
        raise PlanningError("applying a course change requires a rationale")
    current, _ = read_overlay(cfg, root, graph)
    if expected_revision != current["revision"]:
        raise StaleRevisionError(
            f"stale planning revision {expected_revision}; current is {current['revision']}"
        )
    normalized = validate_state(state, graph)
    if analysis is None:
        analysis = analyze_change(graph, cfg, root, normalized)
    if analysis.get("baseRevision") != expected_revision:
        raise StaleRevisionError("analysis was produced from a stale planning revision")
    revision = current["revision"] + 1
    timestamp = _now()
    entry = {
        "revision": revision,
        "updatedAt": timestamp,
        "author": "owner",
        "rationale": rationale.strip(),
        "state": normalized,
        "analysis": analysis,
    }
    history = list(current.get("history", []))
    if not history:
        history.append({
            "revision": current["revision"],
            "updatedAt": current.get("updatedAt"),
            "author": current.get("author", "owner"),
            "rationale": current.get("rationale", "initial planning course"),
            "state": current["state"],
        })
    history.append(entry)
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    overlay = {
        "schema": SCHEMA,
        "revision": revision,
        "updatedAt": timestamp,
        "author": "owner",
        "rationale": rationale.strip(),
        "state": normalized,
        "history": history,
    }
    _write_overlay(_overlay_path(cfg, root), overlay)
    return overlay


def undo_change(graph: Graph, cfg, root: Path, *, expected_revision: int,
                rationale: str) -> dict:
    current, _ = read_overlay(cfg, root, graph)
    if expected_revision != current["revision"]:
        raise StaleRevisionError(
            f"stale planning revision {expected_revision}; current is {current['revision']}"
        )
    history = current.get("history", [])
    if len(history) < 2:
        raise PlanningError("planning overlay has no earlier revision to restore")
    return apply_change(
        graph, cfg, root, history[-2]["state"], expected_revision=expected_revision,
        rationale=rationale,
    )
