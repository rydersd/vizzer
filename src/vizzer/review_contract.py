"""Project-agnostic contracts for repeatable agent-to-owner reviews.

Review plans are authored source. Runs are append-only observations.  Keeping
those records separate prevents an agent's green run from becoming an owner's
approval, and prevents a later owner verdict from erasing machine evidence.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
import os
import re
import stat
import tempfile
import threading
from datetime import datetime
from pathlib import Path, PurePosixPath

from .images import image_dimensions, image_media_type
from .story_sidebar import canonical_story_sections

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


class ReviewContractError(ValueError):
    """Raised when a review plan, run, or ledger violates the contract."""


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STEP_MODES = {"manual", "browser", "local-app", "http", "command"}
_EVIDENCE_KINDS = {"screenshot", "log", "report", "file"}
_OUTCOMES = {"pass", "fail", "blocked", "skipped"}
_VERDICTS = _OUTCOMES
_MAX_LEDGER_EVENTS = 20_000
_MAX_LEDGER_BYTES = 32 * 1024 * 1024
_MAX_SOURCE_BYTES = 4 * 1024 * 1024
_MAX_IMAGE_PIXELS = 32 * 1024 * 1024
_PROCESS_RUN_LOCK = threading.RLock()


@contextmanager
def _run_ledger_lock(path: Path):
    """Hold a crash-safe ledger lock; the marker itself is not lock authority."""
    lock = path.with_name(f".{path.name}.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with _PROCESS_RUN_LOCK:
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(lock, flags, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _object(value: object, subject: str) -> dict:
    if not isinstance(value, dict):
        raise ReviewContractError(f"{subject} must be an object")
    return value


def _exact_fields(value: dict, subject: str, required: set[str],
                  optional: set[str] | None = None) -> None:
    optional = optional or set()
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        raise ReviewContractError(f"{subject} is missing {', '.join(missing)}")
    if unknown:
        raise ReviewContractError(f"{subject} has unknown fields: {', '.join(unknown)}")


def _text(value: object, subject: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewContractError(f"{subject} must be a non-empty string")
    if len(value) > maximum:
        raise ReviewContractError(f"{subject} exceeds {maximum} characters")
    return value.strip()


def _id(value: object, subject: str) -> str:
    result = _text(value, subject, 80)
    if not _ID_RE.fullmatch(result):
        raise ReviewContractError(f"{subject} must be a safe lowercase id")
    return result


def _relative_path(value: object, subject: str) -> str:
    result = _text(value, subject, 500)
    if "\\" in result or "\0" in result:
        raise ReviewContractError(f"{subject} must use a safe POSIX project-relative path")
    path = PurePosixPath(result)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ReviewContractError(f"{subject} must stay inside the project")
    return path.as_posix()


@contextmanager
def _contained_descriptor(root: Path, relative: str, subject: str):
    """Open a project-relative file without following a swapped path component."""
    project_root = root.resolve()
    parts = PurePosixPath(relative).parts
    if not parts:
        raise ReviewContractError(f"{subject} must name a file")
    # Preserve a useful diagnostic for already-present symlinks. The actual
    # authority remains the descriptor walk below, so a post-check swap still
    # cannot redirect the open.
    diagnostic_cursor = project_root
    for part in parts:
        diagnostic_cursor = diagnostic_cursor / part
        try:
            if stat.S_ISLNK(diagnostic_cursor.lstat().st_mode):
                raise ReviewContractError(f"{subject} may not traverse a symlink")
        except FileNotFoundError:
            break
    supports_openat = os.open in getattr(os, "supports_dir_fd", set())
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    if supports_openat and directory_flag and nofollow_flag:
        opened: list[int] = []
        try:
            current = os.open(project_root, os.O_RDONLY | directory_flag)
            opened.append(current)
            for part in parts[:-1]:
                current = os.open(
                    part,
                    os.O_RDONLY | directory_flag | nofollow_flag,
                    dir_fd=current,
                )
                opened.append(current)
            descriptor = os.open(
                parts[-1], os.O_RDONLY | nofollow_flag, dir_fd=current
            )
            opened.append(descriptor)
            yield descriptor
        except OSError as exc:
            raise ReviewContractError(f"cannot open {subject}: {exc}") from exc
        finally:
            for descriptor in reversed(opened):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        return

    # Fallback for platforms without openat/O_NOFOLLOW. It retains containment
    # checks, but POSIX platforms use the race-safe descriptor walk above.
    candidate = project_root / PurePosixPath(relative)
    cursor = project_root
    for part in parts:
        cursor = cursor / part
        try:
            if stat.S_ISLNK(cursor.lstat().st_mode):
                raise ReviewContractError(f"{subject} may not traverse a symlink")
        except FileNotFoundError as exc:
            raise ReviewContractError(f"{subject} does not exist: {relative}") from exc
    try:
        candidate.resolve().relative_to(project_root)
    except ValueError as exc:
        raise ReviewContractError(f"{subject} resolves outside the project") from exc
    try:
        descriptor = os.open(candidate, os.O_RDONLY | nofollow_flag)
    except OSError as exc:
        raise ReviewContractError(f"cannot open {subject}: {exc}") from exc
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _sha256(value: object, subject: str) -> str:
    result = _text(value, subject, 64)
    if not _SHA256_RE.fullmatch(result):
        raise ReviewContractError(f"{subject} must be a lowercase SHA-256 digest")
    return result


def _json_value(value: object, subject: str, *, maximum_bytes: int = 16_384) -> object:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ReviewContractError(f"{subject} must be JSON data") from exc
    if len(encoded.encode("utf-8")) > maximum_bytes:
        raise ReviewContractError(f"{subject} exceeds {maximum_bytes} encoded bytes")
    return copy.deepcopy(value)


def _source(value: object, subject: str) -> dict:
    source = _object(value, subject)
    _exact_fields(source, subject, {"itemId", "path", "fingerprint"}, {"adapter"})
    result = {
        "itemId": _text(source["itemId"], f"{subject} itemId", 200),
        "path": _relative_path(source["path"], f"{subject} path"),
        "fingerprint": _sha256(source["fingerprint"], f"{subject} fingerprint"),
    }
    if "adapter" in source:
        result["adapter"] = _id(source["adapter"], f"{subject} adapter")
    return result


def _step(value: object, subject: str) -> dict:
    step = _object(value, subject)
    _exact_fields(
        step, subject, {"id", "instruction", "expected", "mode"},
        {"adapter", "operation", "inputs"},
    )
    mode = _text(step["mode"], f"{subject} mode", 40)
    if mode not in _STEP_MODES:
        raise ReviewContractError(f"{subject} mode must be one of {sorted(_STEP_MODES)}")
    has_adapter_fields = any(field in step for field in ("adapter", "operation", "inputs"))
    if has_adapter_fields and not all(field in step for field in ("adapter", "operation")):
        raise ReviewContractError(
            f"{subject} adapter and operation must be declared together"
        )
    result = {
        "id": _id(step["id"], f"{subject} id"),
        "instruction": _text(step["instruction"], f"{subject} instruction", 2000),
        "expected": _text(step["expected"], f"{subject} expected", 2000),
        "mode": mode,
    }
    if has_adapter_fields:
        result["adapter"] = _id(step["adapter"], f"{subject} adapter")
        result["operation"] = _id(step["operation"], f"{subject} operation")
        result["inputs"] = _json_value(step.get("inputs", {}), f"{subject} inputs")
    return result


def _evidence_requirement(value: object, subject: str,
                          step_ids: set[str]) -> dict:
    requirement = _object(value, subject)
    _exact_fields(
        requirement, subject, {"id", "kind", "afterStepIds", "required"},
        {"description"},
    )
    kind = _text(requirement["kind"], f"{subject} kind", 40)
    if kind not in _EVIDENCE_KINDS:
        raise ReviewContractError(
            f"{subject} kind must be one of {sorted(_EVIDENCE_KINDS)}"
        )
    after = requirement["afterStepIds"]
    if not isinstance(after, list) or not after:
        raise ReviewContractError(f"{subject} afterStepIds must be a non-empty array")
    normalized_after = [_id(value, f"{subject} afterStepIds entry") for value in after]
    if len(set(normalized_after)) != len(normalized_after):
        raise ReviewContractError(f"{subject} afterStepIds contains duplicates")
    unknown = sorted(set(normalized_after) - step_ids)
    if unknown:
        raise ReviewContractError(
            f"{subject} references unknown steps: {', '.join(unknown)}"
        )
    if not isinstance(requirement["required"], bool):
        raise ReviewContractError(f"{subject} required must be true or false")
    result = {
        "id": _id(requirement["id"], f"{subject} id"),
        "kind": kind,
        "afterStepIds": normalized_after,
        "required": requirement["required"],
    }
    if "description" in requirement:
        result["description"] = _text(
            requirement["description"], f"{subject} description", 1000
        )
    return result


def _row(value: object, subject: str) -> dict:
    row = _object(value, subject)
    _exact_fields(
        row, subject,
        {"id", "title", "source", "definitionOfDone", "steps", "evidenceRequirements"},
        {"setup", "description"},
    )
    dod = row["definitionOfDone"]
    if not isinstance(dod, list) or not 1 <= len(dod) <= 48:
        raise ReviewContractError(f"{subject} definitionOfDone must contain 1 to 48 entries")
    normalized_dod = [
        _text(entry, f"{subject} definitionOfDone entry", 2000) for entry in dod
    ]
    steps = row["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 24:
        raise ReviewContractError(f"{subject} steps must contain 1 to 24 entries")
    normalized_steps = [_step(step, f"{subject} step #{index}")
                        for index, step in enumerate(steps, 1)]
    step_ids = [step["id"] for step in normalized_steps]
    if len(set(step_ids)) != len(step_ids):
        raise ReviewContractError(f"{subject} has duplicate step ids")
    requirements = row["evidenceRequirements"]
    if not isinstance(requirements, list) or len(requirements) > 24:
        raise ReviewContractError(f"{subject} evidenceRequirements must contain at most 24 entries")
    normalized_requirements = [
        _evidence_requirement(requirement, f"{subject} evidence requirement #{index}",
                              set(step_ids))
        for index, requirement in enumerate(requirements, 1)
    ]
    requirement_ids = [requirement["id"] for requirement in normalized_requirements]
    if len(set(requirement_ids)) != len(requirement_ids):
        raise ReviewContractError(f"{subject} has duplicate evidence requirement ids")
    visual = any(step["mode"] in {"browser", "local-app"} for step in normalized_steps)
    if visual and not any(
        requirement["kind"] == "screenshot" and requirement["required"]
        for requirement in normalized_requirements
    ):
        raise ReviewContractError(
            f"{subject} has visual steps but no required screenshot evidence"
        )
    result = {
        "id": _id(row["id"], f"{subject} id"),
        "title": _text(row["title"], f"{subject} title", 200),
        "source": _source(row["source"], f"{subject} source"),
        "definitionOfDone": normalized_dod,
        "steps": normalized_steps,
        "evidenceRequirements": normalized_requirements,
    }
    for field in ("setup", "description"):
        if field in row:
            result[field] = _text(row[field], f"{subject} {field}", 2000)
    return result


def parse_plan(value: object, subject: str = "review plan") -> dict:
    """Validate and normalize one authored review plan."""
    plan = _object(value, subject)
    _exact_fields(plan, subject, {"schema", "id", "title", "rows"}, {"description"})
    if plan["schema"] != 1:
        raise ReviewContractError(f"{subject} schema must be 1")
    rows = plan["rows"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ReviewContractError(f"{subject} rows must contain 1 to 100 entries")
    normalized_rows = [_row(row, f"{subject} row #{index}")
                       for index, row in enumerate(rows, 1)]
    row_ids = [row["id"] for row in normalized_rows]
    if len(set(row_ids)) != len(row_ids):
        raise ReviewContractError(f"{subject} has duplicate row ids")
    result = {
        "schema": 1,
        "id": _id(plan["id"], f"{subject} id"),
        "title": _text(plan["title"], f"{subject} title", 200),
        "rows": normalized_rows,
    }
    if "description" in plan:
        result["description"] = _text(plan["description"], f"{subject} description", 2000)
    return result


def plan_fingerprint(plan: dict) -> str:
    """Fingerprint the normalized plan so stale clients cannot certify revisions."""
    normalized = parse_plan(plan)
    payload = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_plan_sources(root: Path, plan: dict) -> dict:
    """Verify every row still cites the exact non-symlinked source bytes."""
    normalized = parse_plan(plan)
    project_root = root.resolve()
    for row in normalized["rows"]:
        source = row["source"]
        relative = PurePosixPath(source["path"])
        with _contained_descriptor(
            project_root, relative.as_posix(),
            f"review source {source['path']}",
        ) as descriptor:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ReviewContractError("review source must be a regular file")
            if metadata.st_size <= 0 or metadata.st_size > _MAX_SOURCE_BYTES:
                raise ReviewContractError(
                    f"review source must contain 1 to {_MAX_SOURCE_BYTES} bytes"
                )
            digest = hashlib.sha256()
            source_bytes = bytearray()
            while len(source_bytes) <= _MAX_SOURCE_BYTES:
                block = os.read(
                    descriptor,
                    min(65_536, _MAX_SOURCE_BYTES + 1 - len(source_bytes)),
                )
                if not block:
                    break
                digest.update(block)
                source_bytes.extend(block)
        if not source_bytes or len(source_bytes) > _MAX_SOURCE_BYTES:
            raise ReviewContractError("review source exceeded its read budget")
        if digest.hexdigest() != source["fingerprint"]:
            raise ReviewContractError(
                f"review source changed after the plan was derived: {source['path']}"
            )
        try:
            source_text = bytes(source_bytes).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReviewContractError(
                f"review source is not UTF-8 text: {source['path']}"
            ) from exc
        authoritative_text = source_text
        if relative.suffix.lower() == ".md":
            authoritative_text = canonical_story_sections(source_text).get(
                "definitionOfDone", ""
            )
            if not authoritative_text:
                raise ReviewContractError(
                    f"review source has no authored Definition of Done section: "
                    f"{source['path']}"
                )
        for criterion in row["definitionOfDone"]:
            if criterion not in authoritative_text:
                raise ReviewContractError(
                    f"Definition of Done is not verbatim in the authored contract section "
                    f"of {source['path']}: {criterion}"
                )
    return normalized


def empty_run_ledger() -> dict:
    return {"schema": 1, "revision": 0, "events": []}


def _timestamp(value: object, subject: str) -> str:
    result = _text(value, subject, 40)
    if not result.endswith("Z"):
        raise ReviewContractError(f"{subject} must be an ISO-8601 UTC timestamp")
    try:
        datetime.fromisoformat(result[:-1] + "+00:00")
    except ValueError as exc:
        raise ReviewContractError(f"{subject} must be an ISO-8601 UTC timestamp") from exc
    return result


def _find_row(plan: dict, row_id: str) -> dict:
    for row in plan["rows"]:
        if row["id"] == row_id:
            return row
    raise ReviewContractError(f"review run references unknown row {row_id!r}")


def _evidence(value: object, subject: str, requirement_ids: set[str]) -> dict:
    evidence = _object(value, subject)
    _exact_fields(
        evidence, subject,
        {"requirementId", "path", "sha256", "bytes"},
        {"mediaType", "width", "height", "caption", "capture"},
    )
    requirement_id = _id(evidence["requirementId"], f"{subject} requirementId")
    if requirement_id not in requirement_ids:
        raise ReviewContractError(
            f"{subject} references unknown evidence requirement {requirement_id!r}"
        )
    byte_count = evidence["bytes"]
    if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count <= 0:
        raise ReviewContractError(f"{subject} bytes must be a positive integer")
    result = {
        "requirementId": requirement_id,
        "path": _relative_path(evidence["path"], f"{subject} path"),
        "sha256": _sha256(evidence["sha256"], f"{subject} sha256"),
        "bytes": byte_count,
    }
    if "mediaType" in evidence:
        result["mediaType"] = _text(evidence["mediaType"], f"{subject} mediaType", 100)
    for dimension in ("width", "height"):
        if dimension in evidence:
            number = evidence[dimension]
            if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
                raise ReviewContractError(f"{subject} {dimension} must be a positive integer")
            result[dimension] = number
    if ("width" in result) != ("height" in result):
        raise ReviewContractError(f"{subject} width and height must be declared together")
    if "caption" in evidence:
        result["caption"] = _text(evidence["caption"], f"{subject} caption", 500)
    if "capture" in evidence:
        capture = _object(evidence["capture"], f"{subject} capture")
        _exact_fields(
            capture, f"{subject} capture",
            {"adapter", "observedAt", "redaction"},
        )
        redaction = _text(
            capture["redaction"], f"{subject} capture redaction", 40,
        )
        if redaction not in {"not-needed", "reviewed"}:
            raise ReviewContractError(
                f"{subject} capture redaction must be not-needed or reviewed"
            )
        result["capture"] = {
            "adapter": _text(capture["adapter"], f"{subject} capture adapter", 120),
            "observedAt": _timestamp(
                capture["observedAt"], f"{subject} capture observedAt",
            ),
            "redaction": redaction,
        }
    return result


def parse_run_event(value: object, plan: dict, *, allow_owner: bool = False) -> dict:
    """Validate a complete independent agent or owner execution event."""
    normalized_plan = parse_plan(plan)
    event = _object(value, "review run")
    _exact_fields(
        event, "review run",
        {"eventId", "recordedAt", "actor", "planId", "rowId", "planFingerprint",
         "stepResults", "evidence", "verdict"},
        {"note", "basedOnAgentEventId"},
    )
    if event["planId"] != normalized_plan["id"]:
        raise ReviewContractError("review run planId does not match the plan")
    fingerprint = plan_fingerprint(normalized_plan)
    if event["planFingerprint"] != fingerprint:
        raise ReviewContractError("review run planFingerprint is stale")
    row_id = _id(event["rowId"], "review run rowId")
    row = _find_row(normalized_plan, row_id)
    actor = _object(event["actor"], "review run actor")
    _exact_fields(actor, "review run actor", {"kind", "id"})
    actor_kind = _text(actor["kind"], "review run actor kind", 20)
    if actor_kind not in {"agent", "owner"}:
        raise ReviewContractError("review run actor kind must be agent or owner")
    if actor_kind == "owner" and not allow_owner:
        raise ReviewContractError("owner runs may be recorded only by an owner-facing surface")
    if actor_kind == "owner":
        based_on_agent = _id(
            event.get("basedOnAgentEventId"),
            "review run basedOnAgentEventId",
        )
    else:
        if "basedOnAgentEventId" in event:
            raise ReviewContractError(
                "agent runs may not declare basedOnAgentEventId"
            )
        based_on_agent = None
    results = event["stepResults"]
    if not isinstance(results, list):
        raise ReviewContractError("review run stepResults must be an array")
    expected_step_ids = [step["id"] for step in row["steps"]]
    normalized_results = []
    for index, raw in enumerate(results, 1):
        result = _object(raw, f"review run step result #{index}")
        _exact_fields(result, f"review run step result #{index}",
                      {"stepId", "outcome"}, {"observation"})
        step_id = _id(result["stepId"], f"review run step result #{index} stepId")
        outcome = _text(result["outcome"], f"review run step result #{index} outcome", 20)
        if outcome not in _OUTCOMES:
            raise ReviewContractError(f"review run step outcome must be one of {sorted(_OUTCOMES)}")
        normalized = {"stepId": step_id, "outcome": outcome}
        if "observation" in result:
            normalized["observation"] = _text(
                result["observation"], f"review run step result #{index} observation", 2000
            )
        normalized_results.append(normalized)
    result_ids = [result["stepId"] for result in normalized_results]
    if result_ids != expected_step_ids:
        raise ReviewContractError(
            "review run stepResults must cover every step once, in authored order"
        )
    requirements = {requirement["id"]: requirement
                    for requirement in row["evidenceRequirements"]}
    raw_evidence = event["evidence"]
    if not isinstance(raw_evidence, list) or len(raw_evidence) > 48:
        raise ReviewContractError("review run evidence must contain at most 48 entries")
    normalized_evidence = [
        _evidence(item, f"review run evidence #{index}", set(requirements))
        for index, item in enumerate(raw_evidence, 1)
    ]
    evidence_ids = [item["requirementId"] for item in normalized_evidence]
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ReviewContractError(
            "review run evidence may satisfy each requirement at most once"
        )
    verdict = _text(event["verdict"], "review run verdict", 20)
    if verdict not in _VERDICTS:
        raise ReviewContractError(f"review run verdict must be one of {sorted(_VERDICTS)}")
    if verdict == "pass" and any(result["outcome"] != "pass" for result in normalized_results):
        raise ReviewContractError("a passing review run requires every step to pass")
    if verdict != "pass" and not any(
        result["outcome"] == verdict for result in normalized_results
    ):
        raise ReviewContractError(
            f"a {verdict} review run requires at least one {verdict} step"
        )
    if actor_kind == "agent" and verdict == "pass":
        supplied = {item["requirementId"] for item in normalized_evidence}
        missing = sorted(
            requirement_id for requirement_id, requirement in requirements.items()
            if requirement["required"] and requirement_id not in supplied
        )
        if missing:
            raise ReviewContractError(
                f"passing agent run is missing required evidence: {', '.join(missing)}"
            )
    normalized_event = {
        "eventId": _id(event["eventId"], "review run eventId"),
        "recordedAt": _timestamp(event["recordedAt"], "review run recordedAt"),
        "actor": {"kind": actor_kind, "id": _text(actor["id"], "review run actor id", 120)},
        "planId": normalized_plan["id"],
        "rowId": row_id,
        "planFingerprint": fingerprint,
        "stepResults": normalized_results,
        "evidence": normalized_evidence,
        "verdict": verdict,
    }
    if based_on_agent is not None:
        normalized_event["basedOnAgentEventId"] = based_on_agent
    if "note" in event:
        normalized_event["note"] = _text(event["note"], "review run note", 2000)
    return normalized_event


def _verify_owner_lineage(event: dict, prior_events: list[dict]) -> None:
    """Bind an owner verdict to the latest preceding agent run for its row."""
    if event["actor"]["kind"] != "owner":
        return
    latest_agent = next((
        prior for prior in reversed(prior_events)
        if prior["rowId"] == event["rowId"]
        and prior["actor"]["kind"] == "agent"
    ), None)
    if latest_agent is None:
        raise ReviewContractError(
            "owner validation requires a preceding agent run for the same row"
        )
    if event["basedOnAgentEventId"] != latest_agent["eventId"]:
        raise ReviewContractError(
            "owner validation must cite the latest agent run for the same row"
        )


def validate_run_ledger(value: object, plan: dict | None = None) -> dict:
    ledger = _object(value, "review run ledger")
    _exact_fields(ledger, "review run ledger", {"schema", "revision", "events"})
    if ledger["schema"] != 1:
        raise ReviewContractError("review run ledger schema must be 1")
    revision = ledger["revision"]
    events = ledger["events"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ReviewContractError("review run ledger revision must be non-negative")
    if not isinstance(events, list) or len(events) != revision:
        raise ReviewContractError("review run ledger revision must equal its event count")
    if len(events) > _MAX_LEDGER_EVENTS:
        raise ReviewContractError(
            f"review run ledger exceeds {_MAX_LEDGER_EVENTS} events"
        )
    normalized_events = []
    seen_ids = set()
    for expected_revision, raw in enumerate(events, 1):
        event = _object(raw, f"review run ledger event #{expected_revision}")
        if event.get("revision") != expected_revision:
            raise ReviewContractError("review run ledger revisions must be contiguous")
        if plan is not None:
            event_without_revision = dict(event)
            event_without_revision.pop("revision", None)
            normalized_event = parse_run_event(
                event_without_revision, plan, allow_owner=True
            )
            event = dict(normalized_event, revision=expected_revision)
            _verify_owner_lineage(event, normalized_events)
        event_id = _id(event.get("eventId"), "review run ledger eventId")
        if event_id in seen_ids:
            raise ReviewContractError("review run ledger event ids must be unique")
        seen_ids.add(event_id)
        normalized_events.append(copy.deepcopy(event))
    return {"schema": 1, "revision": revision, "events": normalized_events}


def read_evidence_file(root: Path, evidence: dict, *, kind: str,
                       maximum_bytes: int = 4 * 1024 * 1024) -> tuple[dict, bytes]:
    """Verify one evidence reference against contained, non-symlinked bytes.

    The caller supplies the requirement kind from the normalized plan.  Paths
    are opened only after every existing component is checked for symlinks;
    the final file is also opened with ``O_NOFOLLOW`` where the platform offers
    it.  This keeps a repo-relative path from becoming an escape hatch.
    """
    if kind not in _EVIDENCE_KINDS:
        raise ReviewContractError(f"unknown evidence kind {kind!r}")
    if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int) \
            or maximum_bytes <= 0:
        raise ReviewContractError("maximum evidence bytes must be positive")
    relative = _relative_path(evidence.get("path"), "evidence path")
    with _contained_descriptor(root, relative, f"evidence file {relative}") as descriptor:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ReviewContractError("evidence must be a regular file")
        if metadata.st_size <= 0 or metadata.st_size > maximum_bytes:
            raise ReviewContractError(
                f"evidence must contain 1 to {maximum_bytes} bytes"
            )
        payload = b""
        while len(payload) <= maximum_bytes:
            block = os.read(descriptor, min(65_536, maximum_bytes + 1 - len(payload)))
            if not block:
                break
            payload += block
    digest = hashlib.sha256(payload).hexdigest()
    if evidence.get("bytes") != len(payload) or evidence.get("sha256") != digest:
        raise ReviewContractError("evidence bytes do not match their recorded size and SHA-256")
    verified = dict(evidence)
    if kind == "screenshot":
        media_type = image_media_type(payload)
        dimensions = image_dimensions(payload)
        if media_type is None or dimensions is None:
            raise ReviewContractError("screenshot evidence is not a valid PNG, JPEG, or WebP")
        if evidence.get("mediaType") not in {None, media_type}:
            raise ReviewContractError("screenshot mediaType does not match its bytes")
        if (evidence.get("width"), evidence.get("height")) not in {
            (None, None), dimensions
        }:
            raise ReviewContractError("screenshot dimensions do not match its bytes")
        if dimensions[0] * dimensions[1] > _MAX_IMAGE_PIXELS:
            raise ReviewContractError(
                f"screenshot exceeds the {_MAX_IMAGE_PIXELS}-pixel decode budget"
            )
        verified.update({"mediaType": media_type, "width": dimensions[0],
                         "height": dimensions[1]})
    return verified, payload


def verify_evidence_file(root: Path, evidence: dict, *, kind: str,
                         maximum_bytes: int = 4 * 1024 * 1024) -> dict:
    """Verify one evidence reference and discard the already-verified bytes."""
    verified, _ = read_evidence_file(
        root, evidence, kind=kind, maximum_bytes=maximum_bytes
    )
    return verified


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def append_run(path: Path, plan: dict, event: dict, *, project_root: Path,
               expected_revision: int, allow_owner: bool = False) -> dict:
    """CAS-append one run event with an exclusive mutation lock."""
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) \
            or expected_revision < 0:
        raise ReviewContractError("expectedRevision must be a non-negative integer")
    normalized_plan = verify_plan_sources(project_root, plan)
    normalized_event = parse_run_event(
        event, normalized_plan, allow_owner=allow_owner
    )
    row = _find_row(normalized_plan, normalized_event["rowId"])
    requirement_kinds = {
        requirement["id"]: requirement["kind"]
        for requirement in row["evidenceRequirements"]
    }
    for evidence in normalized_event["evidence"]:
        if requirement_kinds[evidence["requirementId"]] != "screenshot":
            continue
        if "capture" not in evidence or "caption" not in evidence:
            raise ReviewContractError(
                "new screenshot evidence requires a semantic caption and capture "
                "attestation (adapter, observedAt, redaction)"
            )
    normalized_event["evidence"] = [
        verify_evidence_file(
            project_root, evidence,
            kind=requirement_kinds[evidence["requirementId"]],
        )
        for evidence in normalized_event["evidence"]
    ]
    with _run_ledger_lock(path):
        if path.exists():
            try:
                if path.stat().st_size > _MAX_LEDGER_BYTES:
                    raise ReviewContractError(
                        f"review run ledger exceeds {_MAX_LEDGER_BYTES} bytes"
                    )
                current = validate_run_ledger(
                    json.loads(path.read_text(encoding="utf-8")), plan=normalized_plan
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise ReviewContractError(f"cannot read review run ledger: {exc}") from exc
        else:
            current = empty_run_ledger()
        if current["revision"] != expected_revision:
            raise ReviewContractError(
                f"expectedRevision {expected_revision} is stale; current revision is "
                f"{current['revision']}"
            )
        if any(item["eventId"] == normalized_event["eventId"] for item in current["events"]):
            raise ReviewContractError("review run eventId already exists")
        _verify_owner_lineage(normalized_event, current["events"])
        revision = current["revision"] + 1
        appended = dict(normalized_event, revision=revision)
        updated = {"schema": 1, "revision": revision,
                   "events": [*current["events"], appended]}
        encoded_size = len(json.dumps(updated, ensure_ascii=False).encode("utf-8"))
        if encoded_size > _MAX_LEDGER_BYTES:
            raise ReviewContractError(
                f"review run ledger would exceed {_MAX_LEDGER_BYTES} bytes"
            )
        _atomic_json(path, updated)
        return updated
