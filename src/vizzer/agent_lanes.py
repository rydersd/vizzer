"""Validation for an optional append-only agent-operations JSONL ledger."""
from __future__ import annotations

import json
from pathlib import Path


LANE_OUTCOMES = {
    "merged", "pr-open", "blocked-spec", "blocked-env", "superseded",
    "killed", "rework", "wandered",
}
SAMPLE_STATES = {"working", "quiet", "error-loop", "dead"}


class AgentLaneError(ValueError):
    pass


def _need(record: dict, name: str, kind: str, line: int):
    if name not in record:
        raise AgentLaneError(
            f"agent operations ledger line {line} ({kind}) is missing {name}"
        )
    return record[name]


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_lane(record: dict, line: int) -> None:
    for name in (
        "lane", "model", "effort", "est", "dispatched", "tokens",
        "continuations", "wander", "idleEvents", "evidence",
    ):
        _need(record, name, "lane", line)
    if not isinstance(record["lane"], str) or not record["lane"].strip():
        raise AgentLaneError(f"agent operations ledger line {line} has invalid lane")
    if not all(isinstance(record[name], str) for name in ("model", "effort", "est")):
        raise AgentLaneError(f"agent operations ledger line {line} has invalid model metadata")
    if not isinstance(record.get("stories", []), list):
        raise AgentLaneError(f"agent operations ledger line {line} has invalid items")
    if record.get("outcome") is not None and record["outcome"] not in LANE_OUTCOMES:
        raise AgentLaneError(f"agent operations ledger line {line} has invalid outcome")
    if not _number(record["tokens"]) or record["tokens"] < 0:
        raise AgentLaneError(f"agent operations ledger line {line} has invalid tokens")
    if not isinstance(record["continuations"], int) or record["continuations"] < 0:
        raise AgentLaneError(f"agent operations ledger line {line} has invalid continuations")
    if not all(isinstance(record[name], list) for name in ("wander", "idleEvents", "evidence")):
        raise AgentLaneError(f"agent operations ledger line {line} has invalid event lists")


def _validate_sample(record: dict, line: int) -> None:
    for name in ("lane", "at", "state", "logAgeSeconds", "pid", "errorSignature"):
        _need(record, name, "sample", line)
    if not isinstance(record["lane"], str) or not record["lane"].strip():
        raise AgentLaneError(f"agent operations sample line {line} has invalid lane")
    if record["state"] not in SAMPLE_STATES:
        raise AgentLaneError(f"agent operations sample line {line} has invalid state")
    if not _number(record["logAgeSeconds"]) or record["logAgeSeconds"] < 0:
        raise AgentLaneError(f"agent operations sample line {line} has invalid log age")
    if record["pid"] is not None and (
        not isinstance(record["pid"], int) or record["pid"] <= 0
    ):
        raise AgentLaneError(f"agent operations sample line {line} has invalid pid")
    if record["errorSignature"] is not None and not isinstance(
        record["errorSignature"], str
    ):
        raise AgentLaneError(f"agent operations sample line {line} has invalid error")


def read_ledger(root: Path, relpath: str, *, strict: bool = True) -> list[dict]:
    path = root / relpath
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise AgentLaneError(f"could not read agent operations ledger: {exc}") from exc
    records = []
    for number, raw in enumerate(lines, 1):
        if not raw.strip():
            if strict:
                raise AgentLaneError(f"agent operations ledger line {number} is blank")
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentLaneError(
                f"agent operations ledger line {number} is malformed JSON: {exc.msg}"
            ) from exc
        if not isinstance(record, dict):
            raise AgentLaneError(f"agent operations ledger line {number} is not an object")
        kind = record.get("kind", "lane")
        if kind == "lane":
            _validate_lane(record, number)
        elif kind == "sample":
            _validate_sample(record, number)
        else:
            raise AgentLaneError(
                f"agent operations ledger line {number} has unknown kind {kind!r}"
            )
        records.append(record)
    return records
