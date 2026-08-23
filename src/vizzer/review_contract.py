"""Project-agnostic contracts for repeatable agent-to-owner reviews.

Review plans are authored source. Runs are append-only observations.  Keeping
those records separate prevents an agent's green run from becoming an owner's
approval, and prevents a later owner verdict from erasing machine evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from .images import image_dimensions, image_media_type


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
_MAX_IMAGE_PIXELS = 32 * 1024 * 1024


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
        candidate = project_root / relative
        cursor = project_root
        for part in relative.parts:
            cursor = cursor / part
            try:
                if stat.S_ISLNK(cursor.lstat().st_mode):
                    raise ReviewContractError(
                        f"review source may not traverse a symlink: {source['path']}"
                    )
            except FileNotFoundError as exc:
                raise ReviewContractError(
                    f"review source does not exist: {source['path']}"
                ) from exc
        try:
            candidate.resolve().relative_to(project_root)
        except ValueError as exc:
            raise ReviewContractError("review source resolves outside the project") from exc
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(candidate, flags)
        except OSError as exc:
            raise ReviewContractError(
                f"cannot open review source {source['path']}: {exc}"
            ) from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ReviewContractError("review source must be a regular file")
            digest = hashlib.sha256()
            source_bytes = bytearray()
            while True:
                block = os.read(descriptor, 65_536)
                if not block:
                    break
                digest.update(block)
                source_bytes.extend(block)
        finally:
            os.close(descriptor)
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
        for criterion in row["definitionOfDone"]:
            if criterion not in source_text:
                raise ReviewContractError(
                    f"Definition of Done is not verbatim in {source['path']}: {criterion}"
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
        {"mediaType", "width", "height", "caption"},
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
    return result


def parse_run_event(value: object, plan: dict, *, allow_owner: bool = False) -> dict:
    """Validate a complete independent agent or owner execution event."""
    normalized_plan = parse_plan(plan)
    event = _object(value, "review run")
    _exact_fields(
        event, "review run",
        {"eventId", "recordedAt", "actor", "planId", "rowId", "planFingerprint",
         "stepResults", "evidence", "verdict"},
        {"note"},
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
    verdict = _text(event["verdict"], "review run verdict", 20)
    if verdict not in _VERDICTS:
        raise ReviewContractError(f"review run verdict must be one of {sorted(_VERDICTS)}")
    if verdict == "pass" and any(result["outcome"] != "pass" for result in normalized_results):
        raise ReviewContractError("a passing review run requires every step to pass")
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
    if "note" in event:
        normalized_event["note"] = _text(event["note"], "review run note", 2000)
    return normalized_event


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
        event_id = _id(event.get("eventId"), "review run ledger eventId")
        if event_id in seen_ids:
            raise ReviewContractError("review run ledger event ids must be unique")
        seen_ids.add(event_id)
        normalized_events.append(copy.deepcopy(event))
    return {"schema": 1, "revision": revision, "events": normalized_events}


def verify_evidence_file(root: Path, evidence: dict, *, kind: str,
                         maximum_bytes: int = 4 * 1024 * 1024) -> dict:
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
    project_root = root.resolve()
    relative = _relative_path(evidence.get("path"), "evidence path")
    candidate = project_root / PurePosixPath(relative)
    cursor = project_root
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        try:
            if stat.S_ISLNK(cursor.lstat().st_mode):
                raise ReviewContractError("evidence path may not traverse a symlink")
        except FileNotFoundError as exc:
            raise ReviewContractError(f"evidence file does not exist: {relative}") from exc
    try:
        candidate.resolve().relative_to(project_root)
    except ValueError as exc:
        raise ReviewContractError("evidence path resolves outside the project") from exc
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise ReviewContractError(f"cannot open evidence file {relative}: {exc}") from exc
    try:
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
    finally:
        os.close(descriptor)
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
    normalized_event["evidence"] = [
        verify_evidence_file(
            project_root, evidence,
            kind=requirement_kinds[evidence["requirementId"]],
        )
        for evidence in normalized_event["evidence"]
    ]
    lock = path.with_name(f".{path.name}.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ReviewContractError("review run ledger is being updated") from exc
    os.close(lock_fd)
    try:
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
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
