"""Validated, non-authoritative overlay describing live agent work.

The feed is intentionally separate from lifecycle and recommendation inputs: activity
answers "what is being touched now", not "what should we build next".  Its timestamped
records let a static constellation stop animating abandoned work without inventing a
percentage or mutating the source stories.
"""
# codex-sequence-2026-08-08: live agent work feed and staleness contract.
from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config
from .model import ActiveWork, Graph, OwnerDecision, owner_question_from_dict


_STATES = {"active", "blocked", "paused", "complete"}
GRANDFATHER_RELPATH = "vizzer/blocked-gate-grandfathered.json"


@dataclass(frozen=True)
class BlockerViolation:
    """One blocked activity record with no actionable or live handoff."""

    work: ActiveWork
    reasons: tuple[str, ...]
    grandfathered: bool = False

    @property
    def remedy(self) -> str:
        parts = []
        if "unlinked" in self.reasons:
            parts.append(
                f"add an owner question whose storyId is {self.work.story_id}, "
                "or name unfinished tracked work in this record's blockedBy"
            )
        if "expired-lease" in self.reasons:
            parts.append(
                "the lease expired; resolve the blocker or re-raise it with a "
                "current updatedAt and a live owner"
            )
        if "unknown-lease" in self.reasons:
            parts.append(
                "the feed has no as_of snapshot; repair the activity feed rather "
                "than treating an uncheckable lease as live"
            )
        return f"{self.work.story_id} ({self.work.agent}): " + "; ".join(parts)


def grandfather_key(entry: Mapping[str, object]) -> tuple[str, str, str, str]:
    """Pin an allowed legacy violation to the exact record revision."""
    return (
        str(entry.get("storyId", "")),
        str(entry.get("agent", "")),
        str(entry.get("task", "")),
        str(entry.get("updatedAt", "")),
    )


def _work_key(work: ActiveWork) -> tuple[str, str, str, str]:
    return (work.story_id, work.agent, work.task, work.updated_at)


def blocker_is_cleared(graph: Graph, story_id: str) -> bool:
    """All linked owner questions were answered and no current question remains."""
    has_decision = any(
        decision.question.story_id == story_id for decision in graph.owner_decisions
    )
    has_open = any(
        question.story_id == story_id for question in graph.owner_questions
    )
    return has_decision and not has_open


def answered_blocker_records(
    graph: Graph,
) -> list[tuple[ActiveWork, tuple[OwnerDecision, ...]]]:
    """Return activity records contradicted by fully answered owner questions."""
    decisions_by_story: dict[str, list[OwnerDecision]] = {}
    for decision in graph.owner_decisions:
        decisions_by_story.setdefault(decision.question.story_id, []).append(decision)
    open_stories = {question.story_id for question in graph.owner_questions}
    return [
        (
            work,
            tuple(sorted(
                decisions_by_story[work.story_id],
                key=lambda decision: decision.question.id,
            )),
        )
        for work in graph.active_work
        if work.state == "blocked"
        and work.story_id in decisions_by_story
        and work.story_id not in open_stories
    ]


def unresolved_blocker_records(
    graph: Graph,
    *,
    done_statuses: Collection[str],
    grandfathered: Collection[tuple[str, str, str, str]] = (),
) -> list[BlockerViolation]:
    """Find blocked records with no live question/dependency or expired lease."""
    done = set(done_statuses)
    by_id = graph.item_map()
    linked_stories = {question.story_id for question in graph.owner_questions}
    linked_stories.update(
        decision.question.story_id for decision in graph.owner_decisions
    )
    as_of = graph.activity.get("as_of")
    as_of = as_of if isinstance(as_of, str) and as_of else None
    allowlist = set(grandfathered)
    violations = []
    for work in graph.active_work:
        if work.state != "blocked":
            continue
        reasons = []
        linked = work.story_id in linked_stories or any(
            dependency in by_id and by_id[dependency].status not in done
            for dependency in work.blocked_by
        )
        if not linked:
            reasons.append("unlinked")
        if as_of is None:
            reasons.append("unknown-lease")
        elif work.stale_at < as_of:
            reasons.append("expired-lease")
        if reasons:
            violations.append(BlockerViolation(
                work=work,
                reasons=tuple(reasons),
                grandfathered=_work_key(work) in allowlist,
            ))
    return violations


def load_grandfathered_blockers(root: Path) -> tuple[set, list[str]]:
    """Load the exact-revision allowlist; absence grandfathers nothing."""
    path = root / GRANDFATHER_RELPATH
    if not path.exists():
        return set(), []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return set(), [f"{GRANDFATHER_RELPATH} is unreadable or malformed"]
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        return set(), [f"{GRANDFATHER_RELPATH} must be a schema-1 JSON object"]
    entries = payload.get("records")
    if not isinstance(entries, list):
        return set(), [f"{GRANDFATHER_RELPATH} records must be an array"]
    keys = set()
    warnings = []
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            warnings.append(
                f"{GRANDFATHER_RELPATH} record #{index} must be an object"
            )
            continue
        key = grandfather_key(entry)
        if not all(key):
            warnings.append(
                f"{GRANDFATHER_RELPATH} record #{index} needs storyId, agent, "
                "task, and updatedAt"
            )
            continue
        keys.add(key)
    return keys, warnings


class _DuplicateJSONKey(ValueError):
    """Reject ambiguous feed objects instead of accepting source-order truth."""


def _reject_duplicate_object_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(key)
        result[key] = value
    return result


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
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_object_keys,
        )
    except _DuplicateJSONKey as exc:
        return [
            f"activity feed {configured} contains duplicate JSON key {str(exc)!r} "
            "(feed ignored)"
        ]
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
        started_at = None
        if "startedAt" in raw:
            started_at, started = _utc_timestamp(raw.get("startedAt"))
            if started_at is None or started is None:
                warnings.append(
                    f"{label} startedAt must be an offset-aware ISO timestamp "
                    "(record dropped)"
                )
                continue
            if started > updated:
                warnings.append(
                    f"{label} startedAt must be <= updatedAt (record dropped)"
                )
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

        blocked_by = raw.get("blockedBy", [])
        if not isinstance(blocked_by, list) or not all(
            isinstance(value, str) and value.strip() for value in blocked_by
        ):
            warnings.append(
                f"{label} blockedBy must be an array of ids (record dropped)"
            )
            continue
        kept_blocked_by = []
        for dependency_id in dict.fromkeys(blocked_by):
            if dependency_id == story_id:
                warnings.append(
                    f"{label} cannot block {story_id} on itself (link dropped)"
                )
            elif dependency_id not in item_ids:
                warnings.append(
                    f"{label} blockedBy references unknown item {dependency_id} "
                    "(link dropped)"
                )
            else:
                kept_blocked_by.append(dependency_id)

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
            started_at=started_at,
            checkpoint=checkpoint.strip() if checkpoint is not None else None,
            related_story_ids=sorted(kept_related),
            blocked_by=sorted(kept_blocked_by),
        ))

    graph.active_work = sorted(
        parsed,
        key=lambda work: (work.story_id, work.agent, work.task),
    )
    raw_questions = payload.get("questions", [])
    parsed_questions = []
    seen_question_ids: set[str] = set()
    if not isinstance(raw_questions, list):
        warnings.append("activity feed questions must be an array (questions ignored)")
        raw_questions = []
    for index, raw in enumerate(raw_questions, 1):
        label = f"activity feed question #{index}"
        if not isinstance(raw, dict):
            warnings.append(f"{label} must be an object (question dropped)")
            continue
        try:
            recommendation = raw.get("recommendation")
            question = owner_question_from_dict({
                "id": raw.get("id"),
                "story_id": raw.get("storyId"),
                "owner": raw.get("owner"),
                "prompt": raw.get("prompt"),
                "options": raw.get("options"),
                "recommendation": {
                    "option_id": recommendation.get("optionId")
                    if isinstance(recommendation, dict) else None,
                    "rationale": recommendation.get("rationale")
                    if isinstance(recommendation, dict) else None,
                },
                "falsifier": raw.get("falsifier"),
                "evidence": raw.get("evidence"),
            })
        except ValueError as exc:
            warnings.append(f"{label} {exc} (question dropped)")
            continue
        if question.story_id not in item_ids:
            warnings.append(
                f"{label} references unknown item {question.story_id} (question dropped)"
            )
            continue
        if question.id in seen_question_ids:
            warnings.append(f"{label} duplicates {question.id} (question dropped)")
            continue
        seen_question_ids.add(question.id)
        parsed_questions.append(question)
    graph.owner_questions = sorted(parsed_questions, key=lambda question: question.id)
    graph.activity = {
        "source": str(configured),
        "stale_after_minutes": stale_minutes,
        # Deterministic snapshot time for static portfolio coordination. The
        # browser may compare to wall time for animation; generated work
        # selection must not change merely because refresh ran an hour later.
        "as_of": max((work.updated_at for work in graph.active_work), default=None),
    }
    return warnings
