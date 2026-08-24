"""Versioned workstream intent and leased local agent sessions.

The definitions file is suitable for version control.  The runtime file is
machine-local by default and changes on heartbeats.  Both use revision compare-
and-swap plus atomic replacement; callers must additionally hold Vizzer's
cross-process mutation guard around read/modify/write transactions.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

from .model import Graph


SCHEMA = 1
MAX_WORKSTREAMS = 100
MAX_DISCUSSIONS = 1000
MAX_HISTORY = 100
WORKSTREAM_STATUSES = {"planned", "active", "review", "integrating", "blocked", "done"}
SESSION_STATES = {"active", "paused", "stopped"}
SESSION_ROLES = {"lead", "reviewer", "observer"}
DISCUSSION_KINDS = {"question", "proposal", "response", "decision", "escalation"}
DISCUSSION_SCOPES = {"implementation", "product", "scope", "contract"}
_ID = re.compile(r"^[a-z][a-z0-9_-]*$")


class WorkstreamError(ValueError):
    pass


class WorkstreamConflict(WorkstreamError):
    pass


def _now(value: str | None = None) -> tuple[str, datetime]:
    raw = value or datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise WorkstreamError("timestamp must be offset-aware ISO-8601") from None
    if parsed.tzinfo is None:
        raise WorkstreamError("timestamp must be offset-aware ISO-8601")
    parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return parsed.isoformat().replace("+00:00", "Z"), parsed


def _configured_path(cfg, root: Path, field: str) -> Path:
    raw = cfg.get(f"workstreams.{field}")
    if not isinstance(raw, str) or not raw.strip():
        raise WorkstreamError(f"workstreams.{field} must be a non-empty string")
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise WorkstreamError(f"workstreams.{field} must stay inside the project")
    project = root.resolve()
    lexical = project / relative
    try:
        parent = lexical.parent.resolve()
        parent.relative_to(project)
    except (OSError, ValueError):
        raise WorkstreamError(f"workstreams.{field} must stay inside the project") from None
    if lexical.is_symlink():
        raise WorkstreamError(f"workstreams.{field} must not be a symlink")
    return parent / lexical.name


def _atomic_write(path: Path, data: dict) -> None:
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


def empty_workstreams() -> dict:
    return {
        "schema": SCHEMA, "revision": 0, "updatedAt": None,
        "actor": "", "rationale": "", "state": {
            "workstreams": [], "discussions": [],
        }, "history": [],
    }


def empty_runtime() -> dict:
    return {"schema": SCHEMA, "revision": 0, "sessions": []}


def _text(value, subject: str, *, optional: bool = False) -> str:
    if optional and value is None:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise WorkstreamError(f"{subject} must be non-empty text")
    return value.strip()


def _path(value, subject: str) -> str:
    text = _text(value, subject)
    relative = PurePosixPath(text)
    if relative.is_absolute() or ".." in relative.parts:
        raise WorkstreamError(f"{subject} path must stay inside the project")
    return relative.as_posix().rstrip("/")


def _id(value, subject: str) -> str:
    text = _text(value, subject)
    if not _ID.fullmatch(text):
        raise WorkstreamError(f"{subject} must use lowercase letters, numbers, _ or -")
    return text


def _ids(value, subject: str, known: set[str] | None = None) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(entry, str) and entry for entry in value):
        raise WorkstreamError(f"{subject} must be an array of non-empty ids")
    if len(set(value)) != len(value):
        raise WorkstreamError(f"{subject} contains duplicates")
    if known is not None:
        unknown = sorted(set(value) - known)
        if unknown:
            raise WorkstreamError(f"{subject} references unknown id {unknown[0]}")
    return list(value)


def _validate_state(value: object, graph: Graph) -> dict:
    if not isinstance(value, dict) or set(value) != {"workstreams", "discussions"}:
        raise WorkstreamError("workstream state needs workstreams and discussions arrays")
    raw_streams = value["workstreams"]
    if not isinstance(raw_streams, list) or len(raw_streams) > MAX_WORKSTREAMS:
        raise WorkstreamError(f"workstreams must be an array of at most {MAX_WORKSTREAMS}")
    item_ids = set(graph.item_map())
    streams = []
    stream_ids: set[str] = set()
    required = {
        "id", "title", "objective", "status", "lead", "reviewer", "storyIds",
        "dependsOn", "allowedPaths", "sharedPaths", "checkpoint", "completed", "total",
    }
    for index, raw in enumerate(raw_streams, 1):
        if not isinstance(raw, dict) or set(raw) != required:
            raise WorkstreamError(f"workstream #{index} has unknown or missing fields")
        stream_id = _id(raw["id"], f"workstream #{index} id")
        if stream_id in stream_ids:
            raise WorkstreamError(f"duplicate workstream id {stream_id}")
        stream_ids.add(stream_id)
        status = raw["status"]
        if status not in WORKSTREAM_STATUSES:
            raise WorkstreamError(f"workstream {stream_id} has unsupported status {status!r}")
        completed, total = raw["completed"], raw["total"]
        if (isinstance(completed, bool) or not isinstance(completed, int)
                or isinstance(total, bool) or not isinstance(total, int)
                or completed < 0 or total < 0 or completed > total):
            raise WorkstreamError(f"workstream {stream_id} requires 0 <= completed <= total")
        allowed = raw["allowedPaths"]
        shared = raw["sharedPaths"]
        if not isinstance(allowed, list) or not isinstance(shared, list):
            raise WorkstreamError(f"workstream {stream_id} paths must be arrays")
        normalized = {
            "id": stream_id,
            "title": _text(raw["title"], f"workstream {stream_id} title"),
            "objective": _text(raw["objective"], f"workstream {stream_id} objective"),
            "status": status,
            "lead": _text(raw["lead"], f"workstream {stream_id} lead"),
            "reviewer": _text(raw["reviewer"], f"workstream {stream_id} reviewer"),
            "storyIds": _ids(raw["storyIds"], f"workstream {stream_id} storyIds", item_ids),
            "dependsOn": _ids(raw["dependsOn"], f"workstream {stream_id} dependsOn"),
            "allowedPaths": [_path(entry, f"workstream {stream_id} allowed") for entry in allowed],
            "sharedPaths": [_path(entry, f"workstream {stream_id} shared") for entry in shared],
            "checkpoint": _text(raw["checkpoint"], f"workstream {stream_id} checkpoint"),
            "completed": completed, "total": total,
        }
        if len(set(normalized["allowedPaths"])) != len(normalized["allowedPaths"]):
            raise WorkstreamError(f"workstream {stream_id} allowedPaths contains duplicates")
        if len(set(normalized["sharedPaths"])) != len(normalized["sharedPaths"]):
            raise WorkstreamError(f"workstream {stream_id} sharedPaths contains duplicates")
        streams.append(normalized)
    for stream in streams:
        unknown = sorted(set(stream["dependsOn"]) - stream_ids)
        if unknown:
            raise WorkstreamError(
                f"workstream {stream['id']} dependsOn references unknown id {unknown[0]}"
            )
    parents = {stream["id"]: stream["dependsOn"] for stream in streams}
    visiting: set[str] = set()
    complete: set[str] = set()
    def visit(stream_id: str) -> None:
        if stream_id in complete:
            return
        if stream_id in visiting:
            raise WorkstreamError("workstream dependency cycle detected")
        visiting.add(stream_id)
        for dependency in parents[stream_id]:
            visit(dependency)
        visiting.remove(stream_id)
        complete.add(stream_id)
    for stream_id in sorted(stream_ids):
        visit(stream_id)

    raw_discussions = value["discussions"]
    if not isinstance(raw_discussions, list) or len(raw_discussions) > MAX_DISCUSSIONS:
        raise WorkstreamError(f"discussions must be an array of at most {MAX_DISCUSSIONS}")
    discussions = []
    discussion_ids: set[str] = set()
    question_ids = {question.id for question in graph.owner_questions}
    for index, raw in enumerate(raw_discussions, 1):
        if not isinstance(raw, dict):
            raise WorkstreamError(f"discussion #{index} must be an object")
        allowed = {
            "id", "workstreamId", "author", "kind", "scope", "body", "createdAt",
            "replyTo", "ownerQuestionId",
        }
        if set(raw) != allowed:
            raise WorkstreamError(f"discussion #{index} has unknown or missing fields")
        discussion_id = _id(raw["id"], f"discussion #{index} id")
        if discussion_id in discussion_ids:
            raise WorkstreamError(f"duplicate discussion id {discussion_id}")
        discussion_ids.add(discussion_id)
        workstream_id = raw["workstreamId"]
        if workstream_id not in stream_ids:
            raise WorkstreamError(f"discussion {discussion_id} has unknown workstream")
        kind, scope = raw["kind"], raw["scope"]
        if kind not in DISCUSSION_KINDS or scope not in DISCUSSION_SCOPES:
            raise WorkstreamError(f"discussion {discussion_id} has unsupported kind or scope")
        if kind == "decision" and scope != "implementation":
            raise WorkstreamError(
                "peer decisions outside reversible implementation scope must escalate to the owner"
            )
        owner_question = raw["ownerQuestionId"]
        if kind == "escalation":
            if owner_question not in question_ids:
                raise WorkstreamError(
                    f"discussion {discussion_id} escalation must name an open owner question"
                )
        elif owner_question is not None:
            raise WorkstreamError(
                f"discussion {discussion_id} ownerQuestionId is only valid for escalation"
            )
        reply_to = raw["replyTo"]
        if reply_to is not None and reply_to not in discussion_ids:
            raise WorkstreamError(f"discussion {discussion_id} replyTo must name an earlier entry")
        created_at, _ = _now(raw["createdAt"])
        discussions.append({
            "id": discussion_id, "workstreamId": workstream_id,
            "author": _text(raw["author"], f"discussion {discussion_id} author"),
            "kind": kind, "scope": scope,
            "body": _text(raw["body"], f"discussion {discussion_id} body"),
            "createdAt": created_at, "replyTo": reply_to,
            "ownerQuestionId": owner_question,
        })
    return {"workstreams": streams, "discussions": discussions}


def _validate_overlay(value: object, graph: Graph) -> dict:
    expected = {"schema", "revision", "updatedAt", "actor", "rationale", "state", "history"}
    if not isinstance(value, dict) or set(value) != expected or value.get("schema") != SCHEMA:
        raise WorkstreamError("workstreams file must be a schema-1 JSON object")
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise WorkstreamError("workstream revision must be a non-negative integer")
    state = _validate_state(value.get("state"), graph)
    history = value.get("history", [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise WorkstreamError(f"workstream history must have at most {MAX_HISTORY} entries")
    previous = 0
    for index, entry in enumerate(history, 1):
        required = {"revision", "updatedAt", "actor", "rationale", "state"}
        if not isinstance(entry, dict) or set(entry) != required:
            raise WorkstreamError(f"workstream history entry #{index} is malformed")
        entry_revision = entry["revision"]
        if (isinstance(entry_revision, bool) or not isinstance(entry_revision, int)
                or entry_revision <= previous or entry_revision > revision):
            raise WorkstreamError("workstream history revisions must increase")
        previous = entry_revision
        _now(entry["updatedAt"])
        _text(entry["actor"], f"workstream history entry #{index} actor")
        _text(entry["rationale"], f"workstream history entry #{index} rationale")
        _validate_state(entry["state"], graph)
    if revision == 0:
        if history or value["updatedAt"] is not None:
            raise WorkstreamError("revision-zero workstreams cannot have history")
    elif not history or history[-1]["revision"] != revision:
        raise WorkstreamError("workstream history must end at the current revision")
    return {**value, "state": state, "history": history}


def read_workstreams(cfg, root: Path, graph: Graph, *, strict: bool = True):
    try:
        path = _configured_path(cfg, root, "definitions_path")
        if not path.exists():
            return empty_workstreams(), []
        if not path.is_file() or path.is_symlink():
            raise WorkstreamError("workstreams file must be a regular file")
        return _validate_overlay(json.loads(path.read_text(encoding="utf-8")), graph), []
    except (OSError, UnicodeError, json.JSONDecodeError, WorkstreamError) as exc:
        error = exc if isinstance(exc, WorkstreamError) else WorkstreamError(str(exc))
        if strict:
            raise error
        return None, [f"workstreams ignored: {error}"]


def apply_workstreams(cfg, root: Path, graph: Graph, state: dict, *,
                      expected_revision: int, actor: str, rationale: str,
                      now: str | None = None) -> dict:
    current, _ = read_workstreams(cfg, root, graph)
    if expected_revision != current["revision"]:
        raise WorkstreamConflict(
            f"stale workstream revision {expected_revision}; current is {current['revision']}"
        )
    normalized = _validate_state(state, graph)
    timestamp, _ = _now(now)
    revision = current["revision"] + 1
    actor = _text(actor, "workstream actor")
    rationale = _text(rationale, "workstream rationale")
    history = list(current.get("history", []))
    history.append({
        "revision": revision, "updatedAt": timestamp, "actor": actor,
        "rationale": rationale, "state": normalized,
    })
    updated = {
        "schema": SCHEMA, "revision": revision, "updatedAt": timestamp,
        "actor": actor, "rationale": rationale, "state": normalized,
        "history": history[-MAX_HISTORY:],
    }
    _atomic_write(_configured_path(cfg, root, "definitions_path"), updated)
    return updated


def restore_workstreams(cfg, root: Path, graph: Graph, overlay: dict) -> None:
    """Restore a validated snapshot after a derived refresh failure."""
    _atomic_write(
        _configured_path(cfg, root, "definitions_path"),
        _validate_overlay(overlay, graph),
    )


def append_discussion(cfg, root: Path, graph: Graph, *, expected_revision: int,
                      workstream_id: str, discussion_id: str, author: str,
                      kind: str, scope: str, body: str, reply_to: str | None = None,
                      owner_question_id: str | None = None,
                      now: str | None = None) -> dict:
    current, _ = read_workstreams(cfg, root, graph)
    if current["revision"] != expected_revision:
        raise WorkstreamConflict(
            f"stale workstream revision {expected_revision}; current is {current['revision']}"
        )
    timestamp, _ = _now(now)
    state = copy.deepcopy(current["state"])
    state["discussions"].append({
        "id": discussion_id, "workstreamId": workstream_id, "author": author,
        "kind": kind, "scope": scope, "body": body, "createdAt": timestamp,
        "replyTo": reply_to, "ownerQuestionId": owner_question_id,
    })
    return apply_workstreams(
        cfg, root, graph, state, expected_revision=expected_revision,
        actor=author, rationale=f"{kind} discussion {discussion_id}", now=timestamp,
    )


def _validate_runtime(value: object, stream_ids: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != {"schema", "revision", "sessions"} \
            or value.get("schema") != SCHEMA:
        raise WorkstreamError("session runtime must be a schema-1 JSON object")
    revision = value["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise WorkstreamError("session revision must be a non-negative integer")
    if not isinstance(value["sessions"], list) or len(value["sessions"]) > 500:
        raise WorkstreamError("sessions must be an array of at most 500 records")
    sessions, seen = [], set()
    required = {
        "id", "actor", "model", "role", "workstreamId", "state", "branch",
        "worktree", "startedAt", "heartbeatAt", "leaseExpiresAt", "stoppedAt",
    }
    for index, raw in enumerate(value["sessions"], 1):
        if not isinstance(raw, dict) or set(raw) != required:
            raise WorkstreamError(f"session #{index} has unknown or missing fields")
        session_id = _id(raw["id"], f"session #{index} id")
        if session_id in seen:
            raise WorkstreamError(f"duplicate session id {session_id}")
        seen.add(session_id)
        if raw["workstreamId"] not in stream_ids:
            raise WorkstreamError(f"session {session_id} names unknown workstream")
        if raw["state"] not in SESSION_STATES or raw["role"] not in SESSION_ROLES:
            raise WorkstreamError(f"session {session_id} has unsupported state or role")
        started_at, _ = _now(raw["startedAt"])
        heartbeat_at, heartbeat = _now(raw["heartbeatAt"])
        lease_at, lease = _now(raw["leaseExpiresAt"])
        if raw["state"] != "stopped" and lease <= heartbeat:
            raise WorkstreamError(f"session {session_id} lease must follow its heartbeat")
        stopped = raw["stoppedAt"]
        if raw["state"] == "stopped":
            stopped, _ = _now(stopped)
        elif stopped is not None:
            raise WorkstreamError(f"session {session_id} stoppedAt requires stopped state")
        sessions.append({
            "id": session_id,
            "actor": _text(raw["actor"], f"session {session_id} actor"),
            "model": _text(raw["model"], f"session {session_id} model"),
            "role": raw["role"], "workstreamId": raw["workstreamId"],
            "state": raw["state"],
            "branch": _text(raw["branch"], f"session {session_id} branch"),
            "worktree": _text(raw["worktree"], f"session {session_id} worktree"),
            "startedAt": started_at, "heartbeatAt": heartbeat_at,
            "leaseExpiresAt": lease_at, "stoppedAt": stopped,
        })
    return {"schema": SCHEMA, "revision": revision, "sessions": sessions}


def read_runtime(cfg, root: Path, graph: Graph, *, strict: bool = True):
    try:
        overlay, _ = read_workstreams(cfg, root, graph)
        stream_ids = {stream["id"] for stream in overlay["state"]["workstreams"]}
        path = _configured_path(cfg, root, "runtime_path")
        if not path.exists():
            return empty_runtime(), []
        if not path.is_file() or path.is_symlink():
            raise WorkstreamError("session runtime must be a regular file")
        return _validate_runtime(json.loads(path.read_text(encoding="utf-8")), stream_ids), []
    except (OSError, UnicodeError, json.JSONDecodeError, WorkstreamError) as exc:
        error = exc if isinstance(exc, WorkstreamError) else WorkstreamError(str(exc))
        if strict:
            raise error
        return None, [f"session runtime ignored: {error}"]


def restore_runtime(cfg, root: Path, graph: Graph, runtime: dict) -> None:
    overlay, _ = read_workstreams(cfg, root, graph)
    stream_ids = {stream["id"] for stream in overlay["state"]["workstreams"]}
    _atomic_write(
        _configured_path(cfg, root, "runtime_path"),
        _validate_runtime(runtime, stream_ids),
    )


def _lease(cfg, now: datetime, minutes: int | None = None) -> str:
    duration = minutes if minutes is not None else cfg.get("workstreams.lease_minutes", 30)
    if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
        raise WorkstreamError("session lease minutes must be positive")
    return (now + timedelta(minutes=duration)).isoformat().replace("+00:00", "Z")


def start_session(cfg, root: Path, graph: Graph, *, session_id: str, actor: str,
                  model: str, role: str, workstream_id: str, branch: str,
                  worktree: str, expected_revision: int, now: str | None = None,
                  lease_minutes: int | None = None) -> dict:
    runtime, _ = read_runtime(cfg, root, graph)
    if runtime["revision"] != expected_revision:
        raise WorkstreamConflict(
            f"stale session revision {expected_revision}; current is {runtime['revision']}"
        )
    if any(session["id"] == session_id for session in runtime["sessions"]):
        raise WorkstreamConflict(f"session {session_id} already exists")
    overlay, _ = read_workstreams(cfg, root, graph)
    if workstream_id not in {stream["id"] for stream in overlay["state"]["workstreams"]}:
        raise WorkstreamError(f"unknown workstream {workstream_id}")
    timestamp, parsed = _now(now)
    session = {
        "id": session_id, "actor": actor, "model": model, "role": role,
        "workstreamId": workstream_id, "state": "active", "branch": branch,
        "worktree": worktree, "startedAt": timestamp, "heartbeatAt": timestamp,
        "leaseExpiresAt": _lease(cfg, parsed, lease_minutes), "stoppedAt": None,
    }
    updated = _validate_runtime({
        "schema": SCHEMA, "revision": runtime["revision"] + 1,
        "sessions": [*runtime["sessions"], session],
    }, {stream["id"] for stream in overlay["state"]["workstreams"]})
    _atomic_write(_configured_path(cfg, root, "runtime_path"), updated)
    return updated


def heartbeat_session(cfg, root: Path, graph: Graph, *, session_id: str, expected_revision: int,
                      now: str | None = None, lease_minutes: int | None = None) -> dict:
    # A graph is not needed to validate existing runtime ids; the caller already
    # loaded authority under the mutation lock. Read the raw file and preserve shape.
    path = _configured_path(cfg, root, "runtime_path")
    if not path.is_file():
        raise WorkstreamError("session runtime does not exist")
    overlay, _ = read_workstreams(cfg, root, graph)
    stream_ids = {stream["id"] for stream in overlay["state"]["workstreams"]}
    raw = _validate_runtime(json.loads(path.read_text(encoding="utf-8")), stream_ids)
    if raw["revision"] != expected_revision:
        raise WorkstreamConflict(
            f"stale session revision {expected_revision}; current is {raw['revision']}"
        )
    timestamp, parsed = _now(now)
    found = False
    sessions = copy.deepcopy(raw.get("sessions", []))
    for session in sessions:
        if session.get("id") != session_id:
            continue
        if session.get("state") == "stopped":
            raise WorkstreamConflict(f"session {session_id} is stopped")
        session["heartbeatAt"] = timestamp
        session["leaseExpiresAt"] = _lease(cfg, parsed, lease_minutes)
        session["state"] = "active"
        found = True
    if not found:
        raise WorkstreamError(f"unknown session {session_id}")
    updated = _validate_runtime(
        {"schema": SCHEMA, "revision": expected_revision + 1, "sessions": sessions},
        stream_ids,
    )
    _atomic_write(path, updated)
    return updated


def stop_session(cfg, root: Path, graph: Graph, *, session_id: str, expected_revision: int,
                 now: str | None = None) -> dict:
    path = _configured_path(cfg, root, "runtime_path")
    if not path.is_file():
        raise WorkstreamError("session runtime does not exist")
    overlay, _ = read_workstreams(cfg, root, graph)
    stream_ids = {stream["id"] for stream in overlay["state"]["workstreams"]}
    raw = _validate_runtime(json.loads(path.read_text(encoding="utf-8")), stream_ids)
    if raw["revision"] != expected_revision:
        raise WorkstreamConflict(
            f"stale session revision {expected_revision}; current is {raw['revision']}"
        )
    timestamp, _ = _now(now)
    found = False
    sessions = copy.deepcopy(raw.get("sessions", []))
    for session in sessions:
        if session.get("id") == session_id:
            session["state"] = "stopped"
            session["stoppedAt"] = timestamp
            session["heartbeatAt"] = timestamp
            found = True
    if not found:
        raise WorkstreamError(f"unknown session {session_id}")
    updated = _validate_runtime(
        {"schema": SCHEMA, "revision": expected_revision + 1, "sessions": sessions},
        stream_ids,
    )
    _atomic_write(path, updated)
    return updated


def _overlap(first: str, second: str) -> bool:
    a, b = PurePosixPath(first), PurePosixPath(second)
    return a == b or a in b.parents or b in a.parents


def _collisions(streams: list[dict], sessions: list[dict]) -> list[dict]:
    active_ids = {session["workstreamId"] for session in sessions if session["fresh"]}
    active = [stream for stream in streams if stream["id"] in active_ids]
    collisions = []
    for stream_id in sorted(active_ids):
        leads = sorted(
            session["id"] for session in sessions
            if session["fresh"] and session["workstreamId"] == stream_id
            and session["role"] == "lead"
        )
        if len(leads) > 1:
            collisions.append({
                "kind": "session-role", "workstreams": [stream_id],
                "values": leads,
            })
    for index, first in enumerate(active):
        for second in active[index + 1:]:
            story_ids = sorted(set(first["storyIds"]) & set(second["storyIds"]))
            if story_ids:
                collisions.append({
                    "kind": "story", "workstreams": [first["id"], second["id"]],
                    "values": story_ids,
                })
            shared = sorted({
                left for left in first["sharedPaths"]
                for right in second["sharedPaths"] if _overlap(left, right)
            })
            if shared:
                collisions.append({
                    "kind": "shared-path", "workstreams": [first["id"], second["id"]],
                    "values": shared,
                })
            exclusive = sorted({
                left for left in first["allowedPaths"]
                for right in second["allowedPaths"] if _overlap(left, right)
            })
            if exclusive:
                collisions.append({
                    "kind": "path", "workstreams": [first["id"], second["id"]],
                    "values": exclusive,
                })
    return collisions


def load_workstream_overlay(
    graph: Graph,
    cfg,
    root: Path,
    *,
    now: str | None = None,
    include_runtime: bool = False,
) -> list[str]:
    """Attach durable intent and opt into machine-local sessions only for live APIs."""
    if not cfg.get("workstreams.enabled", False):
        graph.workstreams = {}
        return []
    overlay, warnings = read_workstreams(cfg, root, graph, strict=False)
    if overlay is None:
        graph.workstreams = {}
        return warnings
    runtime = empty_runtime()
    if include_runtime:
        runtime, runtime_warnings = read_runtime(cfg, root, graph, strict=False)
        warnings.extend(runtime_warnings)
        if runtime is None:
            runtime = empty_runtime()
    _, parsed = _now(now)
    sessions = []
    for session in runtime["sessions"]:
        fresh = (
            session["state"] == "active"
            and datetime.fromisoformat(session["leaseExpiresAt"].replace("Z", "+00:00")) > parsed
        )
        # Runtime may carry an absolute worktree location for local tooling.
        # Generated/checked-in graph artifacts expose only its final label.
        sessions.append({
            **session,
            "worktree": Path(session["worktree"]).name,
            "fresh": fresh,
        })
    streams = overlay["state"]["workstreams"]
    # codex-sequence-2026-08-10: checked-in graphs must not change merely
    # because refresh ran a few seconds later.  Lease freshness can change at
    # its actual boundary; the observation label comes only from persisted
    # definition/session events.
    persisted_times = [overlay.get("updatedAt")]
    if include_runtime:
        persisted_times.extend(session.get("heartbeatAt") for session in runtime["sessions"])
        persisted_times.extend(session.get("stoppedAt") for session in runtime["sessions"])
    as_of = max((value for value in persisted_times if value), default=None)
    graph.workstreams = {
        "schema": SCHEMA, "revision": overlay["revision"],
        "runtimeIncluded": include_runtime,
        "runtimeRevision": runtime["revision"] if include_runtime else None,
        "asOf": as_of,
        "definitionsPath": cfg.get("workstreams.definitions_path"),
        "workstreams": streams,
        "discussions": overlay["state"]["discussions"],
        "sessions": sessions,
        "collisions": _collisions(streams, sessions),
    }
    return warnings
