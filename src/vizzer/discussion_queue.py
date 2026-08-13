"""Audited provider lanes for owner-question discussions.

The queue chooses which harness should pick up a Story; it does not target a
particular chat session and it never changes question or answer authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from .model import Graph, owner_question_fingerprint


SCHEMA = 1
PROVIDERS = ("codex", "claude")
MAX_QUEUE_ITEMS = 500
MAX_HISTORY = 1000


class DiscussionQueueError(ValueError):
    pass


class DiscussionQueueConflict(DiscussionQueueError):
    pass


def _now(value: str | None = None) -> str:
    raw = value or datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise DiscussionQueueError("queuedAt must be offset-aware ISO-8601") from None
    if parsed.tzinfo is None:
        raise DiscussionQueueError("queuedAt must be offset-aware ISO-8601")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _queue_path(cfg, root: Path) -> Path:
    raw = cfg.get("discussions.queue_path", "vizzer/discussion-queue.json")
    if not isinstance(raw, str) or not raw.strip():
        raise DiscussionQueueError("discussions.queue_path must be non-empty")
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise DiscussionQueueError("discussion queue path must stay inside the project")
    project = root.resolve()
    lexical = project / relative
    try:
        parent = lexical.parent.resolve()
        parent.relative_to(project)
    except (OSError, ValueError):
        raise DiscussionQueueError("discussion queue path must stay inside the project") from None
    if lexical.is_symlink():
        raise DiscussionQueueError("discussion queue must not be a symlink")
    return parent / lexical.name


def empty_queue() -> dict:
    return {
        "schema": SCHEMA,
        "revision": 0,
        "updatedAt": None,
        "queues": {provider: [] for provider in PROVIDERS},
        "history": [],
    }


def _story_ids(value: object, provider: str, known: set[str] | None) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_QUEUE_ITEMS:
        raise DiscussionQueueError(
            f"{provider} discussion queue must be an array of at most {MAX_QUEUE_ITEMS} items"
        )
    if not all(isinstance(story_id, str) and story_id for story_id in value):
        raise DiscussionQueueError(f"{provider} discussion queue needs non-empty Story ids")
    if len(set(value)) != len(value):
        raise DiscussionQueueError(f"{provider} discussion queue contains duplicates")
    if known is not None:
        unknown = next((story_id for story_id in value if story_id not in known), None)
        if unknown:
            raise DiscussionQueueError(f"discussion queue references unknown Story {unknown}")
    return list(value)


def _validate(data: object, graph: Graph | None = None) -> dict:
    expected = {"schema", "revision", "updatedAt", "queues", "history"}
    if not isinstance(data, dict) or set(data) != expected or data.get("schema") != SCHEMA:
        raise DiscussionQueueError("discussion queue must be a schema-1 JSON object")
    revision = data.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise DiscussionQueueError("discussion queue revision must be non-negative")
    if revision == 0:
        if data.get("updatedAt") is not None:
            raise DiscussionQueueError("revision-zero discussion queue cannot be updated")
    else:
        _now(data.get("updatedAt"))
    queues = data.get("queues")
    if not isinstance(queues, dict) or set(queues) != set(PROVIDERS):
        raise DiscussionQueueError("discussion queue needs codex and claude lanes")
    known = set(graph.item_map()) if graph is not None else None
    normalized = {
        provider: _story_ids(queues[provider], provider, known)
        for provider in PROVIDERS
    }
    overlap = set(normalized["codex"]) & set(normalized["claude"])
    if overlap:
        raise DiscussionQueueError(
            f"Story cannot be queued to two providers: {sorted(overlap)[0]}"
        )
    history = data.get("history")
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise DiscussionQueueError(
            f"discussion queue history must have at most {MAX_HISTORY} entries"
        )
    previous = 0
    normalized_history = []
    history_fields = {"revision", "queuedAt", "provider", "storyId", "questionIds"}
    for index, entry in enumerate(history, 1):
        if not isinstance(entry, dict) or set(entry) != history_fields:
            raise DiscussionQueueError(f"discussion queue history entry #{index} is malformed")
        entry_revision = entry["revision"]
        if (isinstance(entry_revision, bool) or not isinstance(entry_revision, int)
                or entry_revision <= previous or entry_revision > revision):
            raise DiscussionQueueError("discussion queue history revisions must increase")
        previous = entry_revision
        provider = entry["provider"]
        if provider not in PROVIDERS:
            raise DiscussionQueueError(f"unsupported discussion provider {provider!r}")
        story_id = entry["storyId"]
        if not isinstance(story_id, str) or not story_id:
            raise DiscussionQueueError("discussion history requires a Story id")
        question_ids = entry["questionIds"]
        if (not isinstance(question_ids, list)
                or not all(isinstance(value, str) and value for value in question_ids)
                or len(set(question_ids)) != len(question_ids)):
            raise DiscussionQueueError("discussion history requires unique question ids")
        normalized_history.append({
            **entry,
            "queuedAt": _now(entry["queuedAt"]),
            "questionIds": list(question_ids),
        })
    if revision == 0 and history:
        raise DiscussionQueueError("revision-zero discussion queue cannot have history")
    if revision and (not history or history[-1]["revision"] != revision):
        raise DiscussionQueueError("discussion queue history must end at current revision")
    return {**data, "queues": normalized, "history": normalized_history}


def read_discussion_queue(cfg, root: Path, graph: Graph | None = None, *, strict=True):
    try:
        path = _queue_path(cfg, root)
        if not path.exists():
            return empty_queue(), []
        if not path.is_file() or path.is_symlink():
            raise DiscussionQueueError("discussion queue must be a regular file")
        return _validate(json.loads(path.read_text(encoding="utf-8")), graph), []
    except (OSError, UnicodeError, json.JSONDecodeError, DiscussionQueueError) as exc:
        error = exc if isinstance(exc, DiscussionQueueError) else DiscussionQueueError(str(exc))
        if strict:
            raise error
        return None, [f"discussion queue ignored: {error}"]


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def discussion_queue_snapshot(cfg, root: Path, graph: Graph | None = None) -> dict | None:
    """Capture both queue content and the meaningful missing-file state."""
    path = _queue_path(cfg, root)
    if not path.exists():
        return None
    queue, _ = read_discussion_queue(cfg, root, graph)
    return queue


def restore_discussion_queue(cfg, root: Path, snapshot: dict | None) -> None:
    path = _queue_path(cfg, root)
    if snapshot is None:
        if path.exists():
            if not path.is_file() or path.is_symlink():
                raise DiscussionQueueError(
                    "discussion queue rollback target must be a regular file"
                )
            path.unlink()
        return
    _write(path, _validate(snapshot))


def enqueue_discussion(
    cfg,
    root: Path,
    graph: Graph,
    *,
    provider: str,
    story_id: str,
    questions: object,
    expected_revision: int,
    now: str | None = None,
) -> tuple[dict, bool]:
    current, _ = read_discussion_queue(cfg, root, graph)
    if expected_revision != current["revision"]:
        raise DiscussionQueueConflict(
            f"stale discussion queue revision {expected_revision}; current is {current['revision']}"
        )
    if provider not in PROVIDERS:
        raise DiscussionQueueError(f"unsupported discussion provider {provider!r}")
    if story_id not in graph.item_map():
        raise DiscussionQueueError(f"unknown discussion Story {story_id}")
    if not isinstance(questions, list):
        raise DiscussionQueueError("discussion queue questions must be an array")
    received = {}
    for entry in questions:
        if not isinstance(entry, dict) or set(entry) != {"id", "fingerprint"}:
            raise DiscussionQueueError("discussion questions require id and fingerprint")
        question_id, fingerprint = entry["id"], entry["fingerprint"]
        if not isinstance(question_id, str) or not isinstance(fingerprint, str):
            raise DiscussionQueueError("discussion question id and fingerprint must be text")
        if question_id in received:
            raise DiscussionQueueError(f"duplicate discussion question {question_id}")
        received[question_id] = fingerprint
    live = {
        question.id: owner_question_fingerprint(question)
        for question in graph.owner_questions
        if question.story_id == story_id
    }
    if received != live:
        raise DiscussionQueueConflict(
            "open questions changed while this Story was being queued; reload and try again"
        )
    queues = {
        lane: [value for value in current["queues"][lane] if value != story_id]
        for lane in PROVIDERS
    }
    queues[provider].insert(0, story_id)
    if queues == current["queues"]:
        return current, False
    revision = current["revision"] + 1
    timestamp = _now(now)
    history = [*current["history"], {
        "revision": revision,
        "queuedAt": timestamp,
        "provider": provider,
        "storyId": story_id,
        "questionIds": sorted(live),
    }][-MAX_HISTORY:]
    updated = {
        "schema": SCHEMA,
        "revision": revision,
        "updatedAt": timestamp,
        "queues": queues,
        "history": history,
    }
    updated = _validate(updated, graph)
    _write(_queue_path(cfg, root), updated)
    return updated, True
