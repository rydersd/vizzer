"""Shared deterministic lineage helpers for generated perspective views."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from ..gitmeta import GitMeta, collect


PATH_TOKEN = re.compile(
    r"`((?!/)(?![A-Za-z][A-Za-z0-9+.-]*:)(?:[A-Za-z0-9._-]+/)+[^`\n]+)`"
)


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def snapshot_time(graph) -> datetime:
    """Use newest persisted evidence, never refresh time, as the age anchor."""
    values: list[datetime] = []
    for item in graph.items:
        modified = parse_time(item.activity.get("modified"))
        if modified:
            values.append(modified)
        if item.completion:
            completed = parse_time(f"{item.completion.get('date')}T00:00:00Z")
            if completed:
                values.append(completed)
        for event in item.progress.get("events", []):
            at = parse_time(event.get("at")) if isinstance(event, dict) else None
            if at:
                values.append(at)
    values.extend(
        parsed for work in graph.active_work
        if (parsed := parse_time(work.updated_at)) is not None
    )
    values.extend(
        parsed for decision in graph.owner_decisions
        if (parsed := parse_time(decision.answered_at)) is not None
    )
    workstream_as_of = parse_time(graph.workstreams.get("asOf"))
    if workstream_as_of:
        values.append(workstream_as_of)
    return max(values) if values else datetime(1970, 1, 1, tzinfo=timezone.utc)


def age_days(value: object, anchor: datetime) -> int | None:
    parsed = value if isinstance(value, datetime) else parse_time(value)
    if parsed is None:
        return None
    return max(0, int((anchor - parsed).total_seconds() // 86_400))


def age_text(value: object, anchor: datetime, *, lower_bound: bool = False) -> str:
    days = age_days(value, anchor)
    if days is None:
        return "unknown"
    return f"{'≥' if lower_bound else ''}{days}d"


@lru_cache(maxsize=8)
def git_metadata(root_value: str) -> GitMeta:
    metadata, _warnings = collect(Path(root_value), [])
    return metadata


@lru_cache(maxsize=256)
def git_introduced(root_value: str, path: str, needle: str) -> str | None:
    """Return the first commit time that added an exact persisted identifier."""
    try:
        result = subprocess.run(
            [
                "git", "-C", root_value, "log", "--reverse", "-S", needle,
                "--format=%cI", "--", path,
            ],
            check=True, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), None)


def safe_source_text(root: Path, relpath: object) -> str:
    if not isinstance(relpath, str) or not relpath:
        return ""
    project = root.resolve()
    try:
        path = (project / relpath).resolve()
        path.relative_to(project)
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def capability_for(item, groups: dict) -> str:
    group_id = item.group
    seen: set[str] = set()
    while group_id and group_id not in seen:
        seen.add(group_id)
        group = groups.get(group_id)
        if group is None:
            break
        if group.kind == "capability":
            return group.id
        group_id = group.parent
    return "capability:unassigned"


def explicit_receipt_paths(text: str) -> list[str]:
    """Extract explicit receipt artifacts, not every test path in a story."""
    paths = set()
    for line in text.splitlines():
        if "receipt" not in line.casefold():
            continue
        for match in PATH_TOKEN.finditer(line):
            paths.add(match.group(1).rstrip(".,;:"))
    return sorted(paths)
