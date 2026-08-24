"""Durable, bounded saved Developer Flow views and canvas annotations."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
import re
import stat
import tempfile
import threading
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


SCHEMA = 1
MAX_VIEWS = 100
MAX_ANNOTATIONS = 200
MAX_STROKE_POINTS = 4_096
MAX_TOTAL_POINTS = 20_000
MAX_STORE_BYTES = 4 * 1024 * 1024
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_SCOPES = {"overview", "all", "group", "object"}
_DIRECTIONS = {"RIGHT", "DOWN"}
_COLORS = {"blue", "yellow", "pink", "green", "white"}
_PROCESS_LOCK = threading.RLock()


class DeveloperViewError(ValueError):
    """Raised when a saved view or its persistence boundary is invalid."""


def _exact(value: object, subject: str, required: set[str],
           optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        raise DeveloperViewError(f"{subject} must be an object")
    optional = optional or set()
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing or unknown:
        field = (missing or unknown)[0]
        raise DeveloperViewError(f"{subject} has an unknown or missing field: {field}")
    return value


def _text(value: object, subject: str, maximum: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        qualifier = "bounded string" if empty else "non-empty bounded string"
        raise DeveloperViewError(f"{subject} must be a {qualifier}")
    return value if empty else value.strip()


def _id(value: object, subject: str) -> str:
    result = _text(value, subject, 80)
    if not _ID_RE.fullmatch(result):
        raise DeveloperViewError(f"{subject} must be a safe lowercase id")
    return result


def _coordinate(value: object, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DeveloperViewError(f"{subject} must be a finite coordinate")
    result = float(value)
    if not math.isfinite(result) or abs(result) > 10_000_000:
        raise DeveloperViewError(f"{subject} must be a finite coordinate")
    return result


def _view_state(value: object) -> dict[str, Any]:
    view = _exact(value, "saved view state", {
        "schema", "scope", "id", "direction", "selectedId", "filters",
    })
    if view["schema"] != 1 or view["scope"] not in _SCOPES \
            or view["direction"] not in _DIRECTIONS:
        raise DeveloperViewError("saved view state has an unsupported schema or mode")
    identity = _text(view["id"], "saved view scope id", 500, empty=True)
    if view["scope"] in {"group", "object"} and not identity:
        raise DeveloperViewError("saved group/object view needs an id")
    if view["scope"] in {"overview", "all"} and identity:
        raise DeveloperViewError("saved overview/all view cannot have an id")
    filters = _exact(view["filters"], "saved view filters", {
        "query", "kind", "status", "group", "relationKinds",
    })
    relations = filters["relationKinds"]
    if (not isinstance(relations, list) or len(relations) > 16
            or not all(isinstance(item, str) and 0 < len(item) <= 120 for item in relations)
            or len(set(relations)) != len(relations)):
        raise DeveloperViewError("saved view relation filters must be unique bounded strings")
    return {
        "schema": 1, "scope": view["scope"], "id": identity,
        "direction": view["direction"],
        "selectedId": _text(view["selectedId"], "saved selected id", 500, empty=True),
        "filters": {
            "query": _text(filters["query"], "saved query", 500, empty=True),
            "kind": _text(filters["kind"], "saved kind", 120, empty=True),
            "status": _text(filters["status"], "saved status", 120, empty=True),
            "group": _text(filters["group"], "saved group", 500, empty=True),
            "relationKinds": list(relations),
        },
    }


def _annotation(value: object, index: int) -> tuple[dict[str, Any], int]:
    subject = f"saved view annotation #{index}"
    annotation = _exact(value, subject, {"id", "kind", "color"}, {
        "x", "y", "text", "objectId", "points", "width",
    })
    base = {
        "id": _id(annotation["id"], f"{subject} id"),
        "kind": annotation["kind"],
        "color": annotation["color"],
    }
    if base["color"] not in _COLORS:
        raise DeveloperViewError(f"{subject} color is unsupported")
    if base["kind"] == "note":
        required = {"x", "y", "text"}
        if not required <= set(annotation) or set(annotation) & {"points", "width"}:
            raise DeveloperViewError(f"{subject} note fields are malformed")
        result = {
            **base,
            "x": _coordinate(annotation["x"], f"{subject} x"),
            "y": _coordinate(annotation["y"], f"{subject} y"),
            "text": _text(annotation["text"], f"{subject} text", 2_000),
        }
        if "objectId" in annotation:
            result["objectId"] = _text(
                annotation["objectId"], f"{subject} objectId", 500
            )
        return result, 0
    if base["kind"] == "stroke":
        if set(annotation) & {"x", "y", "text", "objectId"} \
                or "points" not in annotation or "width" not in annotation:
            raise DeveloperViewError(f"{subject} stroke fields are malformed")
        points = annotation["points"]
        if not isinstance(points, list) or not 2 <= len(points) <= MAX_STROKE_POINTS:
            raise DeveloperViewError(
                f"{subject} needs 2 through {MAX_STROKE_POINTS} points"
            )
        normalized = []
        for point_index, point in enumerate(points, 1):
            if not isinstance(point, list) or len(point) != 2:
                raise DeveloperViewError(f"{subject} point #{point_index} is malformed")
            normalized.append([
                _coordinate(point[0], f"{subject} point #{point_index} x"),
                _coordinate(point[1], f"{subject} point #{point_index} y"),
            ])
        width = annotation["width"]
        if (isinstance(width, bool) or not isinstance(width, (int, float))
                or not math.isfinite(float(width)) or not 1 <= float(width) <= 16):
            raise DeveloperViewError(f"{subject} width must be 1 through 16")
        return {**base, "points": normalized, "width": float(width)}, len(normalized)
    raise DeveloperViewError(f"{subject} kind is unsupported")


def parse_view_document(value: object, *, stored: bool = False) -> dict[str, Any]:
    optional = {"annotationsVisible"}
    if stored:
        optional.add("updatedAt")
    document = _exact(value, "saved view", {
        "schema", "id", "name", "view", "notes", "annotations",
    }, optional)
    if document["schema"] != SCHEMA:
        raise DeveloperViewError("saved view schema must be 1")
    annotations = document["annotations"]
    if not isinstance(annotations, list) or len(annotations) > MAX_ANNOTATIONS:
        raise DeveloperViewError(
            f"saved view annotations must contain at most {MAX_ANNOTATIONS} entries"
        )
    normalized, total_points, identities = [], 0, set()
    for index, raw in enumerate(annotations, 1):
        item, points = _annotation(raw, index)
        if item["id"] in identities:
            raise DeveloperViewError("saved view annotation ids must be unique")
        identities.add(item["id"])
        total_points += points
        normalized.append(item)
    if total_points > MAX_TOTAL_POINTS:
        raise DeveloperViewError(
            f"saved view strokes exceed {MAX_TOTAL_POINTS} total points"
        )
    result = {
        "schema": SCHEMA,
        "id": _id(document["id"], "saved view id"),
        "name": _text(document["name"], "saved view name", 80),
        "view": _view_state(document["view"]),
        "notes": _text(document["notes"], "saved view notes", 20_000, empty=True),
        "annotations": normalized,
        "annotationsVisible": document.get("annotationsVisible", True),
    }
    if not isinstance(result["annotationsVisible"], bool):
        raise DeveloperViewError("saved view annotationsVisible must be boolean")
    if stored:
        result["updatedAt"] = _text(
            document.get("updatedAt"), "saved view updatedAt", 80
        )
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_STORE_BYTES:
        raise DeveloperViewError("one saved view exceeds the store byte budget")
    return result


def empty_view_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "revision": 0, "views": []}


def validate_view_store(value: object) -> dict[str, Any]:
    store = _exact(value, "saved view store", {"schema", "revision", "views"})
    if store["schema"] != SCHEMA:
        raise DeveloperViewError("saved view store schema must be 1")
    revision = store["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise DeveloperViewError("saved view store revision must be non-negative")
    views = store["views"]
    if not isinstance(views, list) or len(views) > MAX_VIEWS:
        raise DeveloperViewError(f"saved view store may contain at most {MAX_VIEWS} views")
    normalized = [parse_view_document(view, stored=True) for view in views]
    identities = [view["id"] for view in normalized]
    if len(set(identities)) != len(identities):
        raise DeveloperViewError("saved view ids must be unique")
    return {"schema": SCHEMA, "revision": revision, "views": normalized}


def view_store_path(cfg, root: Path) -> Path:
    raw = cfg.get("developer_flow.views_path", "vizzer/developer-views.json")
    if not isinstance(raw, str) or not raw or "\\" in raw or "\0" in raw:
        raise DeveloperViewError("developer_flow.views_path must be project-relative")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise DeveloperViewError("developer_flow.views_path must stay inside the project")
    project = root.resolve()
    cursor = project
    for part in relative.parts:
        cursor /= part
        try:
            if stat.S_ISLNK(cursor.lstat().st_mode):
                raise DeveloperViewError("developer_flow.views_path may not traverse a symlink")
        except FileNotFoundError:
            break
    candidate = project / relative
    try:
        candidate.parent.resolve().relative_to(project)
    except ValueError as exc:
        raise DeveloperViewError("developer_flow.views_path escapes the project") from exc
    return candidate


@contextmanager
def _store_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(f".{path.name}.lock")
    with _PROCESS_LOCK:
        descriptor = os.open(
            lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        try:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def load_view_store(cfg, root: Path) -> dict[str, Any]:
    path = view_store_path(cfg, root)
    if not path.exists():
        return empty_view_store()
    try:
        if path.is_symlink() or path.stat().st_size > MAX_STORE_BYTES:
            raise DeveloperViewError("saved view store is unsafe or exceeds its byte budget")
        return validate_view_store(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeveloperViewError(f"cannot read saved view store: {exc}") from exc


def _atomic_store(path: Path, store: dict[str, Any]) -> None:
    payload = (json.dumps(store, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_STORE_BYTES:
        raise DeveloperViewError("saved view store exceeds its byte budget")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def upsert_view(cfg, root: Path, document: object, *, expected_revision: int,
                now: str | None = None) -> dict[str, Any]:
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) \
            or expected_revision < 0:
        raise DeveloperViewError("expectedRevision must be non-negative")
    parsed = parse_view_document(document)
    path = view_store_path(cfg, root)
    with _store_lock(path):
        current = load_view_store(cfg, root)
        if current["revision"] != expected_revision:
            raise DeveloperViewError(
                f"expectedRevision {expected_revision} is stale; current revision is "
                f"{current['revision']}"
            )
        timestamp = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        stored = parse_view_document({**parsed, "updatedAt": timestamp}, stored=True)
        existing = next((i for i, view in enumerate(current["views"])
                         if view["id"] == stored["id"]), None)
        views = list(current["views"])
        if existing is None:
            if len(views) >= MAX_VIEWS:
                raise DeveloperViewError(f"saved view store may contain at most {MAX_VIEWS} views")
            views.insert(0, stored)
        else:
            views.pop(existing)
            views.insert(0, stored)
        updated = {"schema": SCHEMA, "revision": expected_revision + 1, "views": views}
        _atomic_store(path, updated)
        return updated


def delete_view(cfg, root: Path, view_id: str, *, expected_revision: int) -> dict[str, Any]:
    identity = _id(view_id, "saved view id")
    path = view_store_path(cfg, root)
    with _store_lock(path):
        current = load_view_store(cfg, root)
        if current["revision"] != expected_revision:
            raise DeveloperViewError(
                f"expectedRevision {expected_revision} is stale; current revision is "
                f"{current['revision']}"
            )
        views = [view for view in current["views"] if view["id"] != identity]
        if len(views) == len(current["views"]):
            raise DeveloperViewError(f"unknown saved view {identity!r}")
        updated = {"schema": SCHEMA, "revision": expected_revision + 1, "views": views}
        _atomic_store(path, updated)
        return updated
