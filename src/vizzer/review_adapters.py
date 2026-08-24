"""Trusted declarations for symbolic review adapter operations.

Plans may request an operation, but they never define how it executes. This
registry lets a project declare which host adapter owns the request and which
JSON input names are valid without embedding commands, credentials, or URLs in
Vizzer's executable core.
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from .config import Config
from .review_contract import ReviewContractError


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_INPUT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
_MODES = {"browser", "local-app", "http", "command", "manual"}
_MAX_REGISTRY_BYTES = 512 * 1024


class ReviewAdapterError(ReviewContractError):
    pass


def _fields(value: dict, subject: str, required: set[str], optional: set[str] = set()):
    missing, unknown = sorted(required - set(value)), sorted(set(value) - required - optional)
    if missing or unknown:
        field = (missing or unknown)[0]
        raise ReviewAdapterError(f"{subject} has unknown or missing field: {field}")


def _id(value: object, subject: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ReviewAdapterError(f"{subject} must be a safe lowercase id")
    return value


def _names(value: object, subject: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and _ID_RE.fullmatch(item) for item in value
    ):
        raise ReviewAdapterError(f"{subject} must contain safe lowercase names")
    if len(set(value)) != len(value):
        raise ReviewAdapterError(f"{subject} contains duplicates")
    return list(value)


def _input_names(value: object, subject: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and _INPUT_RE.fullmatch(item) for item in value
    ):
        raise ReviewAdapterError(f"{subject} must contain safe JSON field names")
    if len(set(value)) != len(value):
        raise ReviewAdapterError(f"{subject} contains duplicates")
    return list(value)


def parse_adapter_registry(value: object) -> dict:
    if not isinstance(value, dict):
        raise ReviewAdapterError("review adapter registry must be an object")
    _fields(value, "review adapter registry", {"schema", "adapters"})
    if value["schema"] != 1 or not isinstance(value["adapters"], list):
        raise ReviewAdapterError("review adapter registry schema must be 1 with adapters")
    adapters, seen = [], set()
    for number, raw in enumerate(value["adapters"], 1):
        subject = f"review adapter #{number}"
        if not isinstance(raw, dict):
            raise ReviewAdapterError(f"{subject} must be an object")
        _fields(raw, subject, {"id", "modes", "operations"}, {"description"})
        adapter_id = _id(raw["id"], f"{subject} id")
        if adapter_id in seen:
            raise ReviewAdapterError(f"duplicate review adapter {adapter_id!r}")
        seen.add(adapter_id)
        modes = _names(raw["modes"], f"{subject} modes")
        if not modes or any(mode not in _MODES for mode in modes):
            raise ReviewAdapterError(f"{subject} has an unsupported mode")
        if not isinstance(raw["operations"], list) or not raw["operations"]:
            raise ReviewAdapterError(f"{subject} operations must be a non-empty array")
        operations, operation_ids = [], set()
        for operation_number, operation in enumerate(raw["operations"], 1):
            op_subject = f"{subject} operation #{operation_number}"
            if not isinstance(operation, dict):
                raise ReviewAdapterError(f"{op_subject} must be an object")
            _fields(operation, op_subject, {"id", "requiredInputs"}, {"optionalInputs"})
            operation_id = _id(operation["id"], f"{op_subject} id")
            if operation_id in operation_ids:
                raise ReviewAdapterError(f"{subject} has duplicate operation ids")
            operation_ids.add(operation_id)
            required = _input_names(
                operation["requiredInputs"], f"{op_subject} requiredInputs"
            )
            optional = _input_names(
                operation.get("optionalInputs", []), f"{op_subject} optionalInputs"
            )
            if set(required) & set(optional):
                raise ReviewAdapterError(f"{op_subject} repeats required and optional inputs")
            operations.append({"id": operation_id, "requiredInputs": required,
                               "optionalInputs": optional})
        adapters.append({"id": adapter_id, "modes": modes, "operations": operations})
    return {"schema": 1, "adapters": adapters}


def load_adapter_registry(cfg: Config, root: Path) -> dict | None:
    value = cfg.get("reviews.adapters_path", "")
    if not value:
        return None
    project_root = root.resolve()
    relative = Path(value)
    cursor = project_root
    for part in relative.parts:
        cursor = cursor / part
        try:
            if stat.S_ISLNK(cursor.lstat().st_mode):
                raise ReviewAdapterError(
                    "reviews.adapters_path may not traverse a symlink"
                )
        except FileNotFoundError:
            break
    candidate = project_root / relative
    try:
        candidate.resolve().relative_to(project_root)
    except (OSError, ValueError) as exc:
        raise ReviewAdapterError("reviews.adapters_path resolves outside the project") from exc
    if not candidate.exists():
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(candidate, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= _MAX_REGISTRY_BYTES:
            raise ReviewAdapterError("review adapter registry must be a bounded regular file")
        payload = b""
        while len(payload) <= _MAX_REGISTRY_BYTES:
            block = os.read(
                descriptor, min(65_536, _MAX_REGISTRY_BYTES + 1 - len(payload))
            )
            if not block:
                break
            payload += block
    finally:
        os.close(descriptor)
    try:
        return parse_adapter_registry(json.loads(payload.decode("utf-8")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewAdapterError(f"review adapter registry is malformed JSON: {exc}") from exc


def validate_plan_adapters(plan: dict, registry: dict | None) -> dict:
    requested = [step for row in plan["rows"] for step in row["steps"] if "adapter" in step]
    if not requested:
        return plan
    if registry is None:
        raise ReviewAdapterError(
            "review plan requests adapter operations but reviews.adapters_path is unavailable"
        )
    adapters = {adapter["id"]: adapter for adapter in registry["adapters"]}
    for step in requested:
        adapter = adapters.get(step["adapter"])
        if adapter is None:
            raise ReviewAdapterError(f"review step requests unknown adapter {step['adapter']!r}")
        if step["mode"] not in adapter["modes"]:
            raise ReviewAdapterError(
                f"review adapter {step['adapter']!r} does not support mode {step['mode']!r}"
            )
        operation = next(
            (item for item in adapter["operations"] if item["id"] == step["operation"]), None
        )
        if operation is None:
            raise ReviewAdapterError(
                f"review step requests unknown operation {step['operation']!r}"
            )
        inputs = step.get("inputs", {})
        if not isinstance(inputs, dict):
            raise ReviewAdapterError("review adapter inputs must be an object")
        required, allowed = set(operation["requiredInputs"]), set(operation["optionalInputs"])
        missing, unknown = sorted(required - set(inputs)), sorted(set(inputs) - required - allowed)
        if missing or unknown:
            field = (missing or unknown)[0]
            raise ReviewAdapterError(
                f"review operation inputs have unknown or missing field: {field}"
            )
    return plan
