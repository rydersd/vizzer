"""Validated, non-authoritative overlay describing live agent work.

The feed is intentionally separate from lifecycle and recommendation inputs: activity
answers "what is being touched now", not "what should we build next".  Its timestamped
records let a static constellation stop animating abandoned work without inventing a
percentage or mutating the source stories.
"""
# codex-sequence-2026-08-08: live agent work feed and staleness contract.
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config
from .model import ActiveWork, Graph


_STATES = {"active", "blocked", "paused", "complete"}


def _utc_timestamp(value: object) -> tuple[str | None, datetime | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None, None
    if parsed.tzinfo is None:
        return None, None
    parsed = parsed.astimezone(timezone.utc)
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    return canonical, parsed


def _safe_feed_path(root: Path, configured: object) -> tuple[Path | None, str | None]:
    if not isinstance(configured, str) or not configured.strip():
        return None, None
    candidate = Path(configured)
    if candidate.is_absolute():
        return None, f"activity feed {configured} must be a relative in-project path"
    root_resolved = root.resolve()
    resolved = (root_resolved / candidate).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return None, f"activity feed {configured} escapes the project root (ignored)"
    return resolved, None


def load_active_work(graph: Graph, cfg: Config, root: Path) -> list[str]:
    """Load the configured activity overlay into ``graph`` and return warnings.

    Invalid records degrade independently: one agent typo must not erase every other
    live lane.  The feed never changes story status, dependency readiness, or priority.
    """
    configured = cfg.get("activity.path", "")
    path, path_warning = _safe_feed_path(root, configured)
    if path_warning:
        return [path_warning]
    if path is None:
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return [f"activity feed {configured} is unreadable or malformed"]
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        return [f"activity feed {configured} must be a schema-1 JSON object"]
    raw_work = payload.get("work")
    if not isinstance(raw_work, list):
        return [f"activity feed {configured} work must be an array"]

    stale_minutes = cfg.get("activity.stale_after_minutes", 120)
    if isinstance(stale_minutes, bool) or not isinstance(stale_minutes, int) \
            or stale_minutes <= 0:
        stale_minutes = 120
    item_ids = set(graph.item_map())
    warnings: list[str] = []
    parsed: list[ActiveWork] = []
    seen: set[tuple[str, str, str]] = set()

    for index, raw in enumerate(raw_work, 1):
        label = f"activity feed record #{index}"
        if not isinstance(raw, dict):
            warnings.append(f"{label} must be an object (record dropped)")
            continue
        story_id = raw.get("storyId")
        agent = raw.get("agent")
        task = raw.get("task")
        state = raw.get("state")
        if not all(isinstance(value, str) and value.strip()
                   for value in (story_id, agent, task, state)):
            warnings.append(
                f"{label} needs non-empty storyId, agent, task, and state (record dropped)"
            )
            continue
        if story_id not in item_ids:
            warnings.append(f"{label} references unknown item {story_id} (record dropped)")
            continue
        if state not in _STATES:
            warnings.append(
                f"{label} has unsupported state {state!r}; expected "
                f"{', '.join(sorted(_STATES))} (record dropped)"
            )
            continue
        updated_at, updated = _utc_timestamp(raw.get("updatedAt"))
        if updated_at is None or updated is None:
            warnings.append(f"{label} updatedAt must be an offset-aware ISO timestamp (record dropped)")
            continue

        checkpoints = raw.get("checkpoints")
        if not isinstance(checkpoints, dict):
            warnings.append(f"{label} checkpoints must be an object (record dropped)")
            continue
        completed = checkpoints.get("completed")
        total = checkpoints.get("total")
        if (isinstance(completed, bool) or not isinstance(completed, int)
                or isinstance(total, bool) or not isinstance(total, int)
                or completed < 0 or total < 0 or completed > total):
            warnings.append(
                f"{label} checkpoints require integers 0 <= completed <= total "
                "(record dropped)"
            )
            continue

        checkpoint = raw.get("checkpoint")
        if checkpoint is not None and (
            not isinstance(checkpoint, str) or not checkpoint.strip()
        ):
            warnings.append(f"{label} checkpoint must be a non-empty string (record dropped)")
            continue
        related = raw.get("relatedStoryIds", [])
        if not isinstance(related, list) or not all(
            isinstance(value, str) and value.strip() for value in related
        ):
            warnings.append(f"{label} relatedStoryIds must be an array of ids (record dropped)")
            continue
        kept_related: list[str] = []
        for related_id in dict.fromkeys(related):
            if related_id == story_id:
                warnings.append(f"{label} cannot link {story_id} to itself (link dropped)")
            elif related_id not in item_ids:
                warnings.append(
                    f"{label} references unknown related item {related_id} (link dropped)"
                )
            else:
                kept_related.append(related_id)

        key = (story_id, agent, task)
        if key in seen:
            warnings.append(
                f"{label} duplicates {story_id} / {agent} / {task} (record dropped)"
            )
            continue
        seen.add(key)
        stale_at = (updated + timedelta(minutes=stale_minutes)).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        parsed.append(ActiveWork(
            story_id=story_id,
            agent=agent.strip(),
            task=task.strip(),
            state=state,
            completed=completed,
            total=total,
            updated_at=updated_at,
            stale_at=stale_at,
            checkpoint=checkpoint.strip() if checkpoint is not None else None,
            related_story_ids=sorted(kept_related),
        ))

    graph.active_work = sorted(
        parsed,
        key=lambda work: (work.story_id, work.agent, work.task),
    )
    graph.activity = {
        "source": str(configured),
        "stale_after_minutes": stale_minutes,
    }
    return warnings
