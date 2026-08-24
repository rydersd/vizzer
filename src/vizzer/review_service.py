"""Project-scoped storage and presentation for agent-to-owner reviews.

The contract module validates one plan and one append-only run ledger.  This
module supplies the project boundary: opt-in configuration, bounded plan
discovery, one ledger per plan, owner-only served writes, and opaque evidence
URLs that never accept a caller-provided path.
"""
from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import Config
from .review_adapters import load_adapter_registry, validate_plan_adapters
from .review_contract import (
    ReviewContractError,
    append_run,
    empty_run_ledger,
    parse_plan,
    plan_fingerprint,
    validate_run_ledger,
    read_evidence_file,
    verify_evidence_file,
    verify_plan_sources,
)


_MAX_PLANS = 250
_MAX_PLAN_BYTES = 1024 * 1024
_PLAN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_MAX_STATE_EVIDENCE_FILES = 256
_MAX_STATE_EVIDENCE_BYTES = 128 * 1024 * 1024
_MAX_STATE_LEDGER_BYTES = 128 * 1024 * 1024
_MAX_STATE_ROWS = 2_000


class ReviewServiceError(ReviewContractError):
    """Raised when configured review storage violates its project boundary."""


@dataclass(frozen=True)
class ReviewPaths:
    plans: Path
    runs: Path
    evidence: Path
    evidence_relative: PurePosixPath


def _configured_directory(cfg: Config, root: Path, field: str) -> Path:
    value = cfg.get(f"reviews.{field}")
    if not isinstance(value, str) or not value.strip():
        raise ReviewServiceError(f"reviews.{field} must be a non-empty string")
    relative = Path(value)
    if relative == Path(".") or relative.is_absolute() or ".." in relative.parts:
        raise ReviewServiceError(f"reviews.{field} must stay inside the project")
    project_root = root.resolve()
    cursor = project_root
    for part in relative.parts:
        cursor = cursor / part
        try:
            if stat.S_ISLNK(cursor.lstat().st_mode):
                raise ReviewServiceError(
                    f"reviews.{field} may not traverse a symlink"
                )
        except FileNotFoundError:
            break
    candidate = project_root / relative
    try:
        candidate.resolve().relative_to(project_root)
    except (OSError, ValueError) as exc:
        raise ReviewServiceError(f"reviews.{field} resolves outside the project") from exc
    return candidate


def review_paths(cfg: Config, root: Path) -> ReviewPaths:
    """Resolve all review storage roots without creating them."""
    plans = _configured_directory(cfg, root, "plans_dir")
    runs = _configured_directory(cfg, root, "runs_dir")
    evidence = _configured_directory(cfg, root, "evidence_dir")
    evidence_relative = PurePosixPath(evidence.relative_to(root.resolve()).as_posix())
    return ReviewPaths(plans, runs, evidence, evidence_relative)


def _regular_json(path: Path, subject: str, maximum: int) -> dict:
    """Read a bounded, non-symlinked regular JSON file."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReviewServiceError(f"cannot open {subject}: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ReviewServiceError(f"{subject} must be a regular file")
        if metadata.st_size <= 0 or metadata.st_size > maximum:
            raise ReviewServiceError(f"{subject} must contain 1 to {maximum} bytes")
        payload = b""
        while len(payload) <= maximum:
            block = os.read(descriptor, min(65_536, maximum + 1 - len(payload)))
            if not block:
                break
            payload += block
    finally:
        os.close(descriptor)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewServiceError(f"{subject} is malformed JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ReviewServiceError(f"{subject} must contain a JSON object")
    return value


def _load_ledger(path: Path, plan: dict) -> dict:
    if not path.exists():
        return empty_run_ledger()
    return validate_run_ledger(
        _regular_json(path, f"review ledger {path.name}", 32 * 1024 * 1024),
        plan=plan,
    )


def _plan_candidates(paths: ReviewPaths) -> list[Path]:
    if not paths.plans.exists():
        return []
    if paths.plans.is_symlink() or not paths.plans.is_dir():
        raise ReviewServiceError("reviews.plans_dir must be a non-symlinked directory")
    candidates = sorted(paths.plans.glob("*.json"), key=lambda path: path.name)
    if len(candidates) > _MAX_PLANS:
        raise ReviewServiceError(f"reviews.plans_dir exceeds {_MAX_PLANS} plans")
    return candidates


def _load_plan_file(path: Path, registry: dict | None, root: Path) -> dict:
    raw = _regular_json(path, f"review plan {path.name}", _MAX_PLAN_BYTES)
    plan = verify_plan_sources(root, parse_plan(raw, f"review plan {path.name}"))
    if path.stem != plan["id"]:
        raise ReviewServiceError(
            f"review plan filename {path.name!r} must match id {plan['id']!r}"
        )
    validate_plan_adapters(plan, registry)
    return plan


def load_review_plans(cfg: Config, root: Path) -> list[dict]:
    """Load every configured plan deterministically and verify its source bytes."""
    if not cfg.get("reviews.enabled", False):
        raise ReviewServiceError("reviews are disabled")
    paths = review_paths(cfg, root)
    candidates = _plan_candidates(paths)
    plans: list[dict] = []
    adapter_registry = load_adapter_registry(cfg, root)
    for path in candidates:
        plans.append(_load_plan_file(path, adapter_registry, root))
    return plans


def load_review_plan(cfg: Config, root: Path, plan_id: str) -> dict:
    """Load one filename-addressed plan without coupling to sibling validity."""
    if not cfg.get("reviews.enabled", False):
        raise ReviewServiceError("reviews are disabled")
    if not isinstance(plan_id, str) or not _PLAN_ID_RE.fullmatch(plan_id):
        raise ReviewServiceError("review plan id must be a safe lowercase id")
    paths = review_paths(cfg, root)
    _plan_candidates(paths)  # Validate the directory and global count first.
    path = paths.plans / f"{plan_id}.json"
    if not path.exists():
        raise ReviewServiceError(f"unknown review plan {plan_id!r}")
    return _load_plan_file(path, load_adapter_registry(cfg, root), root)


def _ledger_path(paths: ReviewPaths, plan: dict) -> Path:
    """Address one immutable plan-fingerprint acceptance epoch."""
    return paths.runs / plan["id"] / f"{plan_fingerprint(plan)}.json"


def _latest_by_actor(events: list[dict], row_id: str) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for event in events:
        if event["rowId"] == row_id:
            latest[event["actor"]["kind"]] = event
    return latest


def _event_to_api(plan_id: str, event: dict, requirement_kinds: dict[str, str],
                  root: Path, paths: ReviewPaths, verification_budget: dict) -> dict:
    result = {key: event[key] for key in (
        "revision", "eventId", "recordedAt", "actor", "rowId",
        "stepResults", "verdict",
    )}
    if "basedOnAgentEventId" in event:
        result["basedOnAgentEventId"] = event["basedOnAgentEventId"]
    if "note" in event:
        result["note"] = event["note"]
    projected_evidence = []
    for evidence in event["evidence"]:
        requirement_id = evidence["requirementId"]
        projected = {
            "requirementId": requirement_id,
            "kind": requirement_kinds[requirement_id],
            "caption": evidence.get("caption", ""),
            "mediaType": evidence.get("mediaType", "application/octet-stream"),
            "width": evidence.get("width"),
            "height": evidence.get("height"),
        }
        if "capture" in evidence:
            projected["capture"] = evidence["capture"]
        evidence_parts = PurePosixPath(evidence["path"]).parts
        prefix = paths.evidence_relative.parts
        budget_available = (
            verification_budget["files"] < _MAX_STATE_EVIDENCE_FILES
            and verification_budget["bytes"] + evidence["bytes"]
            <= _MAX_STATE_EVIDENCE_BYTES
        )
        url = "/api/reviews/evidence/" + "/".join((
            plan_id, event["eventId"], requirement_id,
        ))
        if not budget_available:
            projected.update({
                "available": None,
                "availabilityNote": "Evidence availability will be checked when opened.",
                "url": url,
            })
            projected_evidence.append(projected)
            continue
        verification_budget["files"] += 1
        verification_budget["bytes"] += evidence["bytes"]
        try:
            if evidence_parts[:len(prefix)] != prefix:
                raise ReviewServiceError("evidence is outside reviews.evidence_dir")
            verify_evidence_file(
                root, evidence, kind=requirement_kinds[requirement_id]
            )
        except (ReviewContractError, OSError):
            projected.update({
                "available": False,
                "error": "Evidence is unavailable or changed.",
            })
        else:
            projected.update({
                "available": True,
                "url": url,
            })
        projected_evidence.append(projected)
    result["evidence"] = projected_evidence
    return result


def review_state(cfg: Config, root: Path) -> dict:
    """Return the bounded owner-facing projection of current review authority."""
    paths = review_paths(cfg, root)
    if not cfg.get("reviews.enabled", False):
        raise ReviewServiceError("reviews are disabled")
    registry = load_adapter_registry(cfg, root)
    projected = []
    warnings = []
    verification_budget = {"files": 0, "bytes": 0}
    ledger_bytes = 0
    projected_rows = 0
    for path in _plan_candidates(paths):
        try:
            plan = _load_plan_file(path, registry, root)
            if projected_rows + len(plan["rows"]) > _MAX_STATE_ROWS:
                raise ReviewServiceError(
                    f"served review state exceeds {_MAX_STATE_ROWS} rows"
                )
            ledger_path = _ledger_path(paths, plan)
            try:
                ledger_size = ledger_path.stat().st_size if ledger_path.exists() else 0
            except OSError as exc:
                raise ReviewServiceError(
                    f"cannot inspect review ledger for {plan['id']!r}"
                ) from exc
            if ledger_bytes + ledger_size > _MAX_STATE_LEDGER_BYTES:
                raise ReviewServiceError(
                    "served review state exceeds its aggregate ledger budget"
                )
            ledger = _load_ledger(ledger_path, plan)
        except ReviewContractError as exc:
            warnings.append({"file": path.name, "error": str(exc)})
            continue
        ledger_bytes += ledger_size
        projected_rows += len(plan["rows"])
        rows = []
        for row in plan["rows"]:
            requirements = {
                item["id"]: item["kind"] for item in row["evidenceRequirements"]
            }
            latest = _latest_by_actor(ledger["events"], row["id"])
            rows.append({
                **row,
                "latest": {
                    kind: _event_to_api(
                        plan["id"], event, requirements, root, paths,
                        verification_budget,
                    )
                    for kind, event in latest.items()
                },
                "runCount": sum(
                    event["rowId"] == row["id"] for event in ledger["events"]
                ),
            })
        projected.append({
            "schema": 1,
            "id": plan["id"],
            "title": plan["title"],
            "description": plan.get("description", ""),
            "fingerprint": plan_fingerprint(plan),
            "revision": ledger["revision"],
            "rows": rows,
        })
    return {"schema": 1, "warnings": warnings, "plans": projected}


def append_review_event(cfg: Config, root: Path, plan_id: str, event: dict,
                        *, expected_revision: int, allow_owner: bool) -> dict:
    """Append one agent or owner event to the selected plan's own ledger."""
    plan = load_review_plan(cfg, root, plan_id)
    if not isinstance(event, dict) or event.get("planId") != plan_id:
        raise ReviewServiceError("review event planId must match the selected plan")
    paths = review_paths(cfg, root)
    evidence_prefix = paths.evidence_relative.parts
    for item in event.get("evidence", []):
        if not isinstance(item, dict):
            continue
        try:
            parts = PurePosixPath(str(item.get("path", ""))).parts
        except (TypeError, ValueError):
            parts = ()
        if parts[:len(evidence_prefix)] != evidence_prefix:
            raise ReviewServiceError(
                "review evidence must live under reviews.evidence_dir"
            )
    return append_run(
        _ledger_path(paths, plan), plan, event,
        project_root=root, expected_revision=expected_revision,
        allow_owner=allow_owner,
    )


def resolve_evidence(cfg: Config, root: Path, plan_id: str, event_id: str,
                     requirement_id: str) -> tuple[bytes, str]:
    """Resolve current evidence using only validated plan/event/requirement IDs."""
    plan = load_review_plan(cfg, root, plan_id)
    paths = review_paths(cfg, root)
    ledger = _load_ledger(_ledger_path(paths, plan), plan)
    event = next((item for item in ledger["events"] if item["eventId"] == event_id), None)
    if event is None:
        raise ReviewServiceError("unknown review run")
    row = next(item for item in plan["rows"] if item["id"] == event["rowId"])
    kinds = {item["id"]: item["kind"] for item in row["evidenceRequirements"]}
    matches = [item for item in event["evidence"]
               if item["requirementId"] == requirement_id]
    if len(matches) != 1 or requirement_id not in kinds:
        raise ReviewServiceError("unknown or ambiguous review evidence")
    evidence_parts = PurePosixPath(matches[0]["path"]).parts
    prefix = paths.evidence_relative.parts
    if evidence_parts[:len(prefix)] != prefix:
        raise ReviewServiceError("review evidence is outside reviews.evidence_dir")
    verified, payload = read_evidence_file(
        root, matches[0], kind=kinds[requirement_id]
    )
    return payload, verified.get("mediaType", "application/octet-stream")
