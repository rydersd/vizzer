"""Portable developer-object graph and normalized work-graph adapter."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .config import Config
from .model import Graph, Item
from .object_detail import SCHEMA as DETAIL_SCHEMA, object_detail_for, validate_object_detail


SCHEMA = 1
MAX_OBJECTS = 100_000
MAX_RELATIONS = 400_000
MAX_GROUPS = 20_000
MAX_TEXT = 4_000
MAX_DETAIL_BYTES = 64 * 1024
DetailProvider = Callable[[Item], dict[str, Any]]


class DeveloperGraphError(ValueError):
    """Raised when a developer graph violates the portable renderer contract."""


def _text(value: object, *, limit: int = MAX_TEXT) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _kind(item_id: str) -> str:
    prefix, separator, _ = item_id.partition(":")
    return prefix if separator and prefix else "object"


def _provenance(source: str, *, locator: str = "") -> dict[str, str]:
    result = {"kind": "observed", "source": source}
    if locator:
        result["locator"] = locator
    return result


def _group_detail(group: object, parent_id: str | None) -> dict[str, Any]:
    """Give selectable groups the same renderer-neutral dossier floor as objects."""
    group_id = _text(getattr(group, "id", ""), limit=500)
    title = _text(getattr(group, "title", ""), limit=500) or group_id
    kind = _text(getattr(group, "kind", ""), limit=120) or "group"
    detail = {
        "schema": DETAIL_SCHEMA,
        "id": group_id,
        "title": title,
        "summary": f"Authored {kind} grouping.",
        "status": "group",
        "sections": {},
        "core": {
            "role": kind,
            "release": "",
            "appetite": "",
            "tags": [],
            "flags": [],
            "facets": {},
        },
        "relationships": {
            "dependsOn": [],
            "typed": ([{"kind": "contained-by", "target": parent_id}]
                      if parent_id else []),
        },
        "provenance": {"adapter": "work-graph-group", "locator": ""},
    }
    validate_object_detail(detail)
    return detail


def _status_role(cfg: Config, item: Item, failure_state: str = "") -> str:
    if failure_state in {"blocked", "error", "failed"}:
        return "blocked"
    role = cfg.status_role(item.status)
    return {"done": "shipped", "active": "active"}.get(role, "ready")


def from_work_graph(
    graph: Graph,
    cfg: Config,
    *,
    detail_provider: DetailProvider | None = None,
) -> dict[str, Any]:
    """Project the normalized work graph without recognizing project paths.

    Source-code, runtime, SaaS, database, and work adapters can emit this same
    contract.  Rich detail is injected through ``detail_provider`` so this
    adapter never parses a repository-specific source format.
    """
    provide_detail = detail_provider or object_detail_for
    groups = []
    group_ids = {group.id for group in graph.groups}
    for group in sorted(graph.groups, key=lambda entry: entry.id):
        parent_id = group.parent if group.parent in group_ids else None
        detail = _group_detail(group, parent_id)
        groups.append({
            "id": group.id,
            "title": _text(group.title, limit=500) or group.id,
            "kind": _text(group.kind, limit=120) or "group",
            "parentId": parent_id,
            "entityType": "group",
            "summary": detail["summary"],
            "grouping": "authored",
            "provenance": _provenance("work-graph-group"),
            "details": {"grouping": "authored", "parentId": parent_id or ""},
            "detail": detail,
        })

    latest_work = {}
    for work in graph.active_work:
        current = latest_work.get(work.story_id)
        if current is None or work.updated_at > current.updated_at:
            latest_work[work.story_id] = work

    objects = []
    for item in sorted(graph.items, key=lambda entry: entry.id):
        locator = _text(item.source.get("path"), limit=1_000)
        work = latest_work.get(item.id)
        failure_state = work.state if work is not None else ""
        details = {
            "role": _text(item.role, limit=120),
            "release": _text(item.release, limit=120),
            "appetite": _text(item.appetite, limit=120),
            "sourceLocator": locator,
            "tags": [_text(tag, limit=500) for tag in item.tags[:64]],
            "flags": [_text(flag, limit=500) for flag in item.flags[:64]],
            "facets": {
                _text(name, limit=120): [_text(entry, limit=500) for entry in values[:64]]
                for name, values in list(item.facets.items())[:64]
            },
        }
        if work is not None:
            details["activeWork"] = {
                "actor": _text(work.agent, limit=160),
                "task": _text(work.task, limit=500),
                "state": _text(work.state, limit=120),
                "checkpoint": _text(work.checkpoint, limit=1_000),
                "startedAt": _text(work.started_at, limit=80),
                "updatedAt": _text(work.updated_at, limit=80),
                "blockedBy": [_text(value, limit=500) for value in work.blocked_by[:64]],
            }
        detail = provide_detail(item)
        validate_object_detail(detail)
        value = {
            "id": item.id,
            "kind": _kind(item.id),
            "title": _text(item.title, limit=500) or item.id,
            "summary": _text(item.one_liner, limit=4_000),
            "status": _text(item.status, limit=120) or "unknown",
            "statusRole": _status_role(cfg, item, failure_state),
            "groupId": item.group if item.group in group_ids else None,
            "provenance": _provenance(
                _text(item.source.get("adapter"), limit=120) or "work-graph",
                locator=locator,
            ),
            "details": details,
            "detail": detail,
        }
        if failure_state in {"blocked", "error", "failed"}:
            value["failure"] = {
                "message": _text(work.checkpoint, limit=1_000)
                or f"Agent work is {failure_state}",
                "source": _text(work.agent, limit=160) or "activity",
                "at": _text(work.updated_at, limit=80),
                "provenance": _provenance("active-work"),
            }
        objects.append(value)

    object_ids = {entry["id"] for entry in objects}
    relations = []
    seen = set()
    for item in sorted(graph.items, key=lambda entry: entry.id):
        for dependency in sorted(set(item.deps)):
            if dependency not in object_ids:
                continue
            identity = f"dependency:{item.id}->{dependency}"
            if identity in seen:
                continue
            seen.add(identity)
            relations.append({
                "id": identity,
                "source": item.id,
                "target": dependency,
                "kind": "depends-on",
                "direction": "directed",
                "confidence": "observed",
                "provenance": _provenance("work-graph-dependency"),
            })
        for index, relation in enumerate(item.relations):
            if relation.target not in object_ids:
                continue
            identity = f"relation:{item.id}:{relation.kind}:{relation.target}:{index}"
            relations.append({
                "id": identity,
                "source": item.id,
                "target": relation.target,
                "kind": relation.kind,
                "direction": "directed",
                "confidence": "observed",
                "provenance": _provenance("work-graph-relation"),
            })

    cap = cfg.get("developer_flow.materialization_cap", 1_200)
    if isinstance(cap, bool) or not isinstance(cap, int):
        cap = 1_200
    result = {
        "schema": SCHEMA,
        "title": _text(cfg.get("render.title", ""), limit=500)
        or _text(cfg.get("project.name", "project"), limit=500),
        "objects": objects,
        "relations": relations,
        "groups": groups,
        "vocab": {
            "objectKinds": {
                kind: {"label": kind.replace("-", " ")}
                for kind in sorted({_kind(item.id) for item in graph.items})
            },
            "statuses": sorted({item.status for item in graph.items}),
            "relationKinds": {
                kind: {
                    "label": kind.replace("-", " "),
                    "role": "dependency" if kind == "depends-on" else "relation",
                }
                for kind in sorted({"depends-on", *(
                    relation.kind for item in graph.items for relation in item.relations
                )})
            },
        },
        "limits": {
            "sourceObjectCount": len(objects),
            "sourceRelationCount": len(relations),
            "sourceGroupCount": len(groups),
            "materializationCap": max(100, min(cap, 5_000)),
            "boundaryMaterializationCap": 250,
        },
        "provenance": _provenance("normalized-work-graph"),
    }
    validate_developer_graph(result)
    return result


def _bounded_text(value: object, subject: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise DeveloperGraphError(f"{subject} must be a non-empty bounded string")
    return value


def _validate_provenance(value: object, subject: str) -> None:
    if not isinstance(value, dict):
        raise DeveloperGraphError(f"{subject} provenance must be an object")
    if set(value) - {"kind", "source", "locator"}:
        raise DeveloperGraphError(f"{subject} provenance has unknown fields")
    _bounded_text(value.get("kind"), f"{subject} provenance kind", 120)
    _bounded_text(value.get("source"), f"{subject} provenance source", 120)
    if "locator" in value:
        _bounded_text(value["locator"], f"{subject} provenance locator", 1_000)


def validate_developer_graph(value: object) -> None:
    """Fail closed on identity, hierarchy, endpoints, provenance, and bounds."""
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise DeveloperGraphError("developer graph schema must be 1")
    objects = value.get("objects")
    relations = value.get("relations")
    groups = value.get("groups")
    if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
        raise DeveloperGraphError("developer graph objects must be a bounded list")
    if not isinstance(relations, list) or len(relations) > MAX_RELATIONS:
        raise DeveloperGraphError("developer graph relations must be a bounded list")
    if not isinstance(groups, list) or len(groups) > MAX_GROUPS:
        raise DeveloperGraphError("developer graph groups must be a bounded list")
    _bounded_text(value.get("title"), "developer graph title", 500)
    _validate_provenance(value.get("provenance"), "developer graph")

    def identities(entries: list, subject: str) -> set[str]:
        found = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise DeveloperGraphError(f"developer graph {subject} must be objects")
            identity = entry.get("id")
            _bounded_text(identity, f"developer graph {subject} id", 500)
            if identity in found:
                raise DeveloperGraphError(f"duplicate developer graph id: {identity}")
            found.add(identity)
        return found

    object_ids = identities(objects, "objects")
    group_ids = identities(groups, "groups")
    relation_ids = identities(relations, "relations")
    collisions = (object_ids & group_ids) | (object_ids & relation_ids) | (group_ids & relation_ids)
    if collisions:
        raise DeveloperGraphError(
            f"developer graph ids share a renderer namespace: {sorted(collisions)[0]}"
        )

    parent_by_group = {}
    for group in groups:
        _bounded_text(group.get("title"), "developer graph group title", 500)
        _bounded_text(group.get("kind"), "developer graph group kind", 120)
        if group.get("grouping") not in {"authored", "derived", "inferred"}:
            raise DeveloperGraphError("developer graph group needs a grouping authority")
        _validate_provenance(group.get("provenance"), "developer graph group")
        if "entityType" in group and group["entityType"] != "group":
            raise DeveloperGraphError("developer graph group entityType must be group")
        if "summary" in group and (not isinstance(group["summary"], str)
                                   or len(group["summary"]) > MAX_TEXT):
            raise DeveloperGraphError("developer graph group summary must be bounded text")
        if "detail" in group:
            try:
                validate_object_detail(group["detail"])
            except ValueError as exc:
                raise DeveloperGraphError(
                    f"invalid developer graph group detail: {group['id']}"
                ) from exc
        if "details" in group:
            try:
                encoded_group_details = json.dumps(
                    group["details"], ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise DeveloperGraphError(
                    "developer graph group details must be JSON data"
                ) from exc
            if len(encoded_group_details) > MAX_DETAIL_BYTES:
                raise DeveloperGraphError(
                    "developer graph group details exceed the byte limit"
                )
        parent = group.get("parentId")
        if parent is not None and parent not in group_ids:
            raise DeveloperGraphError(f"unknown developer graph parent group: {parent}")
        parent_by_group[group["id"]] = parent
    for group_id in group_ids:
        seen = set()
        current = group_id
        while current is not None:
            if current in seen:
                raise DeveloperGraphError(f"developer graph group cycle at: {current}")
            seen.add(current)
            current = parent_by_group.get(current)

    for obj in objects:
        for field, maximum in (("kind", 120), ("title", 500), ("status", 120),
                               ("statusRole", 40)):
            _bounded_text(obj.get(field), f"developer graph object {field}", maximum)
        if obj["statusRole"] not in {"blocked", "active", "ready", "shipped"}:
            raise DeveloperGraphError("developer graph object statusRole is unknown")
        if not isinstance(obj.get("summary"), str) or len(obj["summary"]) > MAX_TEXT:
            raise DeveloperGraphError("developer graph object summary must be bounded text")
        group_id = obj.get("groupId")
        if group_id is not None and group_id not in group_ids:
            raise DeveloperGraphError(f"unknown developer graph object group: {group_id}")
        _validate_provenance(obj.get("provenance"), "developer graph object")
        try:
            validate_object_detail(obj.get("detail"))
        except ValueError as exc:
            raise DeveloperGraphError(f"invalid developer graph object detail: {obj['id']}") from exc
        failure = obj.get("failure")
        if failure is not None:
            if not isinstance(failure, dict):
                raise DeveloperGraphError("developer graph failure must be an object")
            for field, maximum in (("message", 1_000), ("source", 160), ("at", 80)):
                _bounded_text(failure.get(field), f"developer graph failure {field}", maximum)
            _validate_provenance(failure.get("provenance"), "developer graph failure")
        try:
            encoded_details = json.dumps(obj.get("details"), ensure_ascii=False,
                                         sort_keys=True, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise DeveloperGraphError("developer graph object details must be JSON data") from exc
        if len(encoded_details) > MAX_DETAIL_BYTES:
            raise DeveloperGraphError("developer graph object details exceed the byte limit")

    for relation in relations:
        if relation.get("source") not in object_ids or relation.get("target") not in object_ids:
            raise DeveloperGraphError(
                f"developer graph relation has a dangling endpoint: {relation['id']}"
            )
        _bounded_text(relation.get("kind"), "developer graph relation kind", 120)
        if relation.get("direction") not in {"directed", "undirected"}:
            raise DeveloperGraphError("developer graph relation direction is unknown")
        if relation.get("confidence") not in {"observed", "authored", "inferred"}:
            raise DeveloperGraphError("developer graph relation confidence is unknown")
        _validate_provenance(relation.get("provenance"), "developer graph relation")

    limits = value.get("limits")
    if not isinstance(limits, dict):
        raise DeveloperGraphError("developer graph limits must be an object")
    expected = {
        "sourceObjectCount": len(objects),
        "sourceRelationCount": len(relations),
        "sourceGroupCount": len(groups),
    }
    for field, count in expected.items():
        if limits.get(field) != count:
            raise DeveloperGraphError(f"developer graph {field} does not match its payload")
    cap = limits.get("materializationCap")
    if isinstance(cap, bool) or not isinstance(cap, int) or not 100 <= cap <= 5_000:
        raise DeveloperGraphError("developer graph materializationCap must be 100 through 5000")
    boundary_cap = limits.get("boundaryMaterializationCap", 250)
    if (isinstance(boundary_cap, bool) or not isinstance(boundary_cap, int)
            or not 1 <= boundary_cap <= 1_000):
        raise DeveloperGraphError(
            "developer graph boundaryMaterializationCap must be 1 through 1000"
        )
