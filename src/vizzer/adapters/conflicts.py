"""Optional adapter for decisions between incompatible work objects."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..model import Group, Item
from . import ScanResult


GROUP_ID = "conflicts:decisions"
_STATES = {"open", "decided", "applied"}
_PRIORITIES = {"p0", "p1", "p2"}
_ID_RE = re.compile(r"^conflict:[a-z0-9]+(?:-[a-z0-9]+)*$")


class _DuplicateJSONKey(ValueError):
    pass


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(key)
        result[key] = value
    return result


def _status(cfg, state: str) -> str:
    role = {"open": "ready", "decided": "active", "applied": "done"}[state]
    return cfg.status_for_role(role)


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def scan(cfg, root: Path) -> ScanResult:
    """Scan a conflict ledger without making its project vocabulary universal."""
    root = Path(root)
    relpath = cfg.get("sources.conflicts.path", "")
    warnings: list[str] = []
    if not isinstance(relpath, str) or not relpath.strip():
        return ScanResult(warnings=warnings)
    path = root / relpath
    if not path.is_file():
        return ScanResult(warnings=warnings)
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs
        )
    except _DuplicateJSONKey as exc:
        return ScanResult(warnings=[f"{relpath}: duplicate JSON key {str(exc)!r}"])
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return ScanResult(warnings=[f"{relpath}: unreadable ({exc})"])
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        return ScanResult(warnings=[f"{relpath}: expected a schema-1 object"])
    records = payload.get("conflicts")
    if not isinstance(records, list):
        return ScanResult(warnings=[f"{relpath}: expected a conflicts array"])

    items: list[Item] = []
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        label = f"{relpath}: conflict #{index}"
        if not isinstance(record, dict):
            warnings.append(f"{label} is not an object")
            continue
        conflict_id = record.get("id")
        if not isinstance(conflict_id, str) or not _ID_RE.fullmatch(conflict_id):
            warnings.append(f"{label} needs an id like conflict:<kebab-slug>")
            continue
        if conflict_id in seen:
            warnings.append(f"{relpath}: duplicate conflict id {conflict_id}")
            continue
        seen.add(conflict_id)
        state = record.get("status")
        if state not in _STATES:
            warnings.append(f"{conflict_id}: status must be one of {sorted(_STATES)}")
            continue
        priority = record.get("priority")
        if priority not in _PRIORITIES:
            warnings.append(
                f"{conflict_id}: priority must be one of {sorted(_PRIORITIES)}"
            )
            continue
        objects = record.get("objects")
        if not isinstance(objects, list) or len(objects) < 2 or not all(
            isinstance(value, dict)
            and all(_nonempty(value.get(field)) for field in ("kind", "ref", "claim"))
            for value in objects
        ):
            warnings.append(
                f"{conflict_id}: a conflict needs at least two objects with kind, ref, and claim"
            )
            continue
        options = record.get("options")
        if state == "open" and (
            not isinstance(options, list) or len(options) not in (2, 3)
        ):
            warnings.append(f"{conflict_id}: an open conflict needs 2 or 3 options")
            continue
        if state in {"decided", "applied"} and not isinstance(
            record.get("decision"), dict
        ):
            warnings.append(f"{conflict_id}: {state} requires a recorded decision")
            continue
        title = record.get("title")
        collision = record.get("collision")
        if not _nonempty(title) or not _nonempty(collision):
            warnings.append(f"{conflict_id}: title and collision must be non-empty")
            continue
        kind = record.get("type")
        tags = [priority]
        if _nonempty(kind):
            tags.insert(0, kind.strip())
        items.append(Item(
            id=conflict_id,
            title=title.strip(),
            one_liner=collision.strip()[:280],
            status=_status(cfg, state),
            group=GROUP_ID,
            role="decision",
            tags=tags,
            facets={
                "source-area": ["conflicts"],
                "conflict-state": [state],
                "conflict-type": [kind.strip() if _nonempty(kind) else "unclassified"],
                "priority": [priority],
            },
            flags=["conflict"],
            source={"adapter": "conflicts", "path": relpath},
        ))

    groups = [Group(id=GROUP_ID, kind="folder", title="Conflict decisions")]
    return ScanResult(groups=groups if items else [], items=items, warnings=warnings)
