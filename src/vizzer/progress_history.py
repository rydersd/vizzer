"""Durable, deliberately narrow progress history for the constellation.

The history is generated from machine-readable story state and the active-work
checkpoint counters.  It never treats a Markdown body timestamp, a git commit
count, or a prose mention as delivery evidence.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config
from .model import Graph, Item
from .adapters.spec_tree import _body_deps


SCHEMA = 1
_ELIGIBLE_ROLES = {"ready", "active", "regression"}
_ELIGIBLE_STATUSES = {"ready", "building", "in-flight", "bug-gap"}
_MAX_EVENTS = 24
_STATUS_HEADER = re.compile(r"^>\s*Status:\s*([A-Za-z-]+)\s*$", re.MULTILINE)


@dataclass
class ProgressHistory:
    path: Path | None
    content: str | None
    warnings: list[str]


def _stamp(now: datetime | None = None) -> tuple[str, datetime]:
    value = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    value = value.replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z"), value


def _parse_stamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _safe_path(root: Path, configured: object) -> tuple[Path | None, str | None]:
    if not isinstance(configured, str) or not configured.strip():
        return None, None
    candidate = Path(configured)
    if candidate.is_absolute():
        return None, "progress history path must be relative to the project root"
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return None, "progress history path escapes the project root"
    return resolved, None


def _valid_history(payload: object) -> dict | None:
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return None
    items = payload.get("items")
    if not isinstance(items, dict):
        return None
    return payload


def _status_forward(cfg: Config, previous: str, current: str) -> bool:
    """Only a configured forward lifecycle transition is a progress event."""
    if previous == current:
        return False
    previous_meta = next((s for s in cfg.vocab["statuses"] if s.get("name") == previous), {})
    current_meta = next((s for s in cfg.vocab["statuses"] if s.get("name") == current), {})
    if not previous_meta or not current_meta:
        return False
    if current_meta.get("done") and not previous_meta.get("done"):
        return True
    if "next" in previous_meta:
        return current in previous_meta.get("next", []) and cfg.status_role(current) in _ELIGIBLE_ROLES
    # The bundled default vocabulary predates declared transitions. Its list order
    # is the only portable forward contract; parked/unknown never qualify.
    names = [status.get("name") for status in cfg.vocab["statuses"]]
    return (previous in names and current in names and names.index(current) > names.index(previous)
            and cfg.status_role(current) in _ELIGIBLE_ROLES)


def _eligible(item: Item, current_work: dict[str, int]) -> bool:
    """Eligibility is evidence work started, never a generic ready-ish role.

    Custom vocabularies frequently classify `idea` and `backlog` as a `ready`
    display bucket; treating that bucket as work-start evidence would turn the
    entire untouched backlog into accusations of stalling.
    """
    return item.status in _ELIGIBLE_STATUSES or bool(current_work)


def _work_snapshot(graph: Graph, item_id: str) -> dict[str, int]:
    snapshot = {}
    for work in graph.active_work:
        if work.story_id == item_id:
            snapshot[f"{work.agent}\u241f{work.task}"] = work.completed
    return snapshot


def _event(at: str, kind: str, source: str, detail: str) -> dict:
    return {"at": at, "kind": kind, "source": source, "detail": detail}


def _header_semantics(text: str, item_kind: str) -> tuple[str | None, set[str] | None]:
    """Read only exact machine-readable story headers from a historic blob."""
    status_match = _STATUS_HEADER.search(text)
    status = status_match.group(1) if status_match else None
    deps, error = _body_deps(text, item_kind)
    return status, (set(deps) if error is None and deps is not None else None)


def _git_backfill_events(root: Path, item: Item, cfg: Config,
                         since: datetime, now: datetime) -> list[dict]:
    """Return semantic header deltas in the configured one-time lookback.

    Commit dates only order and timestamp already-proven header changes. A prose
    edit, release-label change, or arbitrary commit to the same file is ignored.
    """
    relative = item.source.get("path")
    if item.source.get("adapter") != "spec_tree" or not isinstance(relative, str) or not relative:
        return []
    maximum = cfg.get("progress.backfill_max_commits_per_story", 48)
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "-c", "log.showSignature=false", "log",
             f"-n{maximum}", "--format=%H%x09%cI", "--", relative],
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return []
    commits: list[tuple[str, datetime]] = []
    for line in result.stdout.splitlines():
        sha, separator, raw_at = line.partition("\t")
        at = _parse_stamp(raw_at)
        if separator and re.fullmatch(r"[0-9a-f]{7,64}", sha) and at is not None:
            commits.append((sha, at))
    # Start at the first pre-window version when available, so a change at the
    # window boundary has a comparator. Git emits newest first.
    selected: list[tuple[str, datetime]] = []
    for commit in commits:
        selected.append(commit)
        if commit[1] < since:
            break
    selected.reverse()
    previous_status: str | None = None
    previous_deps: set[str] | None = None
    events: list[dict] = []
    kind = item.id.split(":", 1)[0]
    for sha, at in selected:
        try:
            blob = subprocess.run(
                ["git", "-C", str(root), "show", f"{sha}:{relative}"],
                check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        status, deps = _header_semantics(blob, kind)
        if at >= since and at <= now:
            source = f"git story headers {sha[:12]}"
            stamp = at.isoformat(timespec="seconds").replace("+00:00", "Z")
            if status is not None and previous_status is not None and _status_forward(cfg, previous_status, status):
                events.append(_event(stamp, "lifecycle", source, f"{previous_status} → {status}"))
            if deps is not None and previous_deps is not None:
                removed = previous_deps - deps
                if removed:
                    events.append(_event(stamp, "dependencies_resolved", source,
                                         f"{len(removed)} prerequisite{'s' if len(removed) != 1 else ''} removed"))
        if status is not None:
            previous_status = status
        if deps is not None:
            previous_deps = deps
    return events


def _active_checkpoint_backfill(graph: Graph, item_id: str, since: datetime,
                                now: datetime) -> list[dict]:
    events = []
    for work in graph.active_work:
        at = _parse_stamp(work.updated_at)
        if (work.story_id == item_id and work.completed > 0 and at is not None
                and since <= at <= now):
            events.append(_event(
                work.updated_at, "checkpoint", "active-work checkpoint timestamp",
                f"checkpoint count recorded at {work.completed}/{work.total}",
            ))
    return events


def _validated_events(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for event in raw:
        if not isinstance(event, dict):
            continue
        at = event.get("at")
        kind = event.get("kind")
        source = event.get("source")
        detail = event.get("detail")
        if (_parse_stamp(at) is not None and all(isinstance(value, str) and value
            for value in (kind, source, detail))):
            out.append({"at": at, "kind": kind, "source": source, "detail": detail})
    return sorted(out, key=lambda event: event["at"])[-_MAX_EVENTS:]


def _render_progress(record: dict, cfg: Config) -> dict:
    """Return stable render inputs; the browser owns wall-clock age.

    Serializing ``ageDays`` made an unchanged graph become stale as time passed.
    Event timestamps and eligibility anchors are durable evidence, while heat and
    marker size are presentation derived from ``Date.now()`` at view time.
    """
    events = list(reversed(_validated_events(record.get("events"))[-3:]))
    rendered: dict = {
        "events": events,
        "hotWindowDays": cfg.get("progress.hot_window_days", 7),
    }
    eligible_at = _parse_stamp(record.get("eligibleSince"))
    if eligible_at is None:
        return rendered
    latest = max((_parse_stamp(event["at"]) for event in events), default=None)
    since = max(filter(None, (eligible_at, latest)))
    rendered["stall"] = {
        "since": since.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": record.get("eligibleSource", "recorded eligible work state"),
        "afterDays": cfg.get("progress.stalled_after_days", 14),
        "maxDays": cfg.get("progress.stall_max_days", 90),
    }
    return rendered


def prepare_progress_history(graph: Graph, cfg: Config, root: Path,
                             now: datetime | None = None) -> ProgressHistory:
    """Attach render-safe trail/stall data and stage one history replacement.

    The first successful observation is a baseline, not a fake plus marker. A
    malformed history is retained intact and yields no progress/stall claims.
    """
    path, path_warning = _safe_path(root, cfg.get("progress.history_path", ""))
    if path_warning:
        graph.warnings = sorted(set(graph.warnings) | {path_warning})
        return ProgressHistory(None, None, [path_warning])
    if path is None:
        return ProgressHistory(None, None, [])
    stamp, moment = _stamp(now)
    if path.exists():
        try:
            previous = _valid_history(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError):
            previous = None
        if previous is None:
            warning = f"progress history {cfg.get('progress.history_path')} is malformed; preserved without claims"
            graph.warnings = sorted(set(graph.warnings) | {warning})
            return ProgressHistory(path, None, [warning])
    else:
        previous = {"schema": SCHEMA, "items": {}}

    old_items = previous.get("items", {})
    backfill_done = isinstance(previous.get("backfill"), dict)
    backfill_days = cfg.get("progress.backfill_days", 7)
    backfill_since = moment - timedelta(days=backfill_days)
    current_items: dict[str, dict] = {}
    for item in sorted(graph.items, key=lambda candidate: candidate.id):
        old = old_items.get(item.id)
        old = old if isinstance(old, dict) else None
        current_work = _work_snapshot(graph, item.id)
        eligible = _eligible(item, current_work)
        if old is None:
            events = []
            if not backfill_done:
                events.extend(_git_backfill_events(root, item, cfg, backfill_since, moment))
                events.extend(_active_checkpoint_backfill(graph, item.id, backfill_since, moment))
            record = {"status": item.status, "deps": sorted(set(item.deps)), "work": current_work,
                      "events": _validated_events(events)}
            if eligible:
                record.update({"eligibleSince": stamp, "eligibleSource": "initial eligible lifecycle observation"})
        else:
            events = _validated_events(old.get("events"))
            if not backfill_done:
                events.extend(_git_backfill_events(root, item, cfg, backfill_since, moment))
                events.extend(_active_checkpoint_backfill(graph, item.id, backfill_since, moment))
            old_status = old.get("status") if isinstance(old.get("status"), str) else "unknown"
            old_deps = set(value for value in old.get("deps", []) if isinstance(value, str))
            new_deps = set(item.deps)
            if _status_forward(cfg, old_status, item.status):
                events.append(_event(stamp, "lifecycle", "story lifecycle header",
                                     f"{old_status} → {item.status}"))
            removed = old_deps - new_deps
            if removed:
                events.append(_event(stamp, "dependencies_resolved", "story Deps header",
                                     f"{len(removed)} prerequisite{'s' if len(removed) != 1 else ''} removed"))
            old_work = old.get("work") if isinstance(old.get("work"), dict) else {}
            for key, completed in current_work.items():
                prior = old_work.get(key)
                if isinstance(prior, int) and completed > prior:
                    events.append(_event(stamp, "checkpoint", "active-work checkpoint",
                                         f"checkpoint count {prior} → {completed}"))
            record = {"status": item.status, "deps": sorted(new_deps), "work": current_work,
                      "events": _validated_events(events)}
            previous_eligible = _parse_stamp(old.get("eligibleSince"))
            if eligible:
                record["eligibleSince"] = (old.get("eligibleSince") if previous_eligible else stamp)
                record["eligibleSource"] = (old.get("eligibleSource") if previous_eligible else "recorded eligible lifecycle observation")
            # Ineligible stories intentionally drop prior eligibility. A prior
            # baseline written by an older engine must not leave a backlog item
            # with a future false stall marker.
        current_items[item.id] = record
        if eligible:
            item.progress = _render_progress(record, cfg)

    # A no-op refresh must not manufacture history churn.  The current wall clock
    # still drives derived stall age in the graph/view, but the durable ledger only
    # advances when its semantic snapshot advances.
    prior_items = previous.get("items", {})
    backfill = previous.get("backfill") if backfill_done else {
        "completedAt": stamp,
        "since": backfill_since.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "semantics": ["lifecycle", "dependencies_resolved", "checkpoint"],
    }
    unchanged = (prior_items == current_items and backfill_done
                 and isinstance(previous.get("updatedAt"), str))
    payload = {"schema": SCHEMA,
               "updatedAt": previous["updatedAt"] if unchanged else stamp,
               "items": current_items,
               "backfill": backfill}
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return ProgressHistory(path, content, [])
