"""Bounded query contract for large developer-object graphs.

The standalone renderer is useful for ordinary projects, but a DOM cap is not a
transport strategy.  This module supplies the server-side projection boundary:
clients request an overview, one group, or one object's functional neighborhood
and receive a deterministic, paged slice of the portable developer graph.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter, OrderedDict, defaultdict
from collections.abc import Callable
from typing import Any

from .developer_graph import validate_developer_graph, validate_developer_graph_index
from .object_detail import validate_object_detail


QUERY_SCHEMA = 1
RESPONSE_SCHEMA = 1
DEFAULT_LIMIT = 500
MAX_LIMIT = 5_000
MAX_QUERY_TEXT = 500
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PRIMARY_OBJECT_BUDGET = 2 * 1024 * 1024
BOUNDARY_OBJECT_BUDGET = 512 * 1024
RELATION_BUDGET = 1024 * 1024
MAX_BOUNDARY_OBJECTS = 250
DETAIL_CACHE_LIMIT = MAX_LIMIT
DETAIL_CACHE_BYTES = 8 * 1024 * 1024


class DeveloperQueryError(ValueError):
    """Raised when a developer-view query is malformed or stale."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def developer_graph_fingerprint_stream(
    scalars: dict[str, Any],
    lists: dict[str, Any],
) -> str:
    """Hash a graph from scalar values plus repeatable or streaming list values."""
    digest = hashlib.sha256()
    digest.update(b"{")
    for key_index, key in enumerate(sorted({*scalars, *lists})):
        if key_index:
            digest.update(b",")
        digest.update(_canonical(key))
        digest.update(b":")
        if key in lists:
            digest.update(b"[")
            for item_index, item in enumerate(lists[key]):
                if item_index:
                    digest.update(b",")
                digest.update(item if isinstance(item, bytes) else _canonical(item))
            digest.update(b"]")
        else:
            digest.update(_canonical(scalars[key]))
    digest.update(b"}")
    return digest.hexdigest()


def developer_graph_fingerprint(value: object) -> str:
    """Return the cursor snapshot identity for a developer-graph projection."""
    if not isinstance(value, dict):
        return hashlib.sha256(_canonical(value)).hexdigest()
    return developer_graph_fingerprint_stream(
        {key: entry for key, entry in value.items() if not isinstance(entry, list)},
        {key: entry for key, entry in value.items() if isinstance(entry, list)},
    )


def materialize_developer_object(
    source: dict[str, Any], detail: dict[str, Any],
) -> dict[str, Any]:
    """Combine one compact card record with its validated shared dossier."""
    try:
        validate_object_detail(detail)
    except ValueError as exc:
        raise DeveloperQueryError(
            f"invalid developer object detail: {source.get('id', '')}"
        ) from exc
    object_id = source.get("id")
    if detail["id"] != object_id:
        raise DeveloperQueryError(
            f"developer object detail id does not match: {object_id}"
        )
    core = detail["core"]
    details = {
        "role": core["role"],
        "release": core["release"],
        "appetite": core["appetite"],
        "sourceLocator": detail["provenance"]["locator"],
        "tags": list(core["tags"]),
        "flags": list(core["flags"]),
        "facets": dict(core["facets"]),
    }
    active_work = source.get("details", {}).get("activeWork")
    if active_work is not None:
        details["activeWork"] = active_work
    return {**source, "details": details, "detail": detail}


def normalize_developer_query(
    request: object,
) -> tuple[dict, dict, int, str | None]:
    """Validate and normalize the shared in-memory/persisted query contract."""
    if not isinstance(request, dict) or request.get("schema") != QUERY_SCHEMA:
        raise DeveloperQueryError("developer query schema must be 1")
    if set(request) - {"schema", "scope", "filters", "page"}:
        raise DeveloperQueryError("developer query has unknown fields")
    scope = request.get("scope")
    if not isinstance(scope, dict) or set(scope) - {"kind", "id"}:
        raise DeveloperQueryError("developer query scope is malformed")
    kind = scope.get("kind")
    if kind not in {"overview", "group", "object"}:
        raise DeveloperQueryError("developer query scope kind is invalid")
    identity = scope.get("id")
    if kind == "overview":
        if identity is not None:
            raise DeveloperQueryError("overview scope cannot have an id")
    elif not isinstance(identity, str) or not identity or len(identity) > 500:
        raise DeveloperQueryError(f"developer query {kind} scope needs a bounded id")

    filters = request.get("filters", {})
    if not isinstance(filters, dict) or set(filters) - {
        "query", "kinds", "statuses", "relationKinds",
    }:
        raise DeveloperQueryError("developer query filters are malformed")
    query = filters.get("query", "")
    if not isinstance(query, str) or len(query) > MAX_QUERY_TEXT:
        raise DeveloperQueryError("developer query text must be a bounded string")
    normalized_filters = {"query": query.strip().casefold()}
    for name in ("kinds", "statuses", "relationKinds"):
        values = filters.get(name, [])
        if (not isinstance(values, list) or len(values) > 64
                or not all(isinstance(value, str) and 0 < len(value) <= 120
                           for value in values)):
            raise DeveloperQueryError(f"developer query {name} must be bounded strings")
        normalized_filters[name] = sorted(set(values))

    page = request.get("page", {})
    if not isinstance(page, dict) or set(page) - {"limit", "cursor"}:
        raise DeveloperQueryError("developer query page is malformed")
    limit = page.get("limit", DEFAULT_LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise DeveloperQueryError(f"developer query limit must be 1 through {MAX_LIMIT}")
    cursor = page.get("cursor")
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 180):
        raise DeveloperQueryError("developer query cursor is malformed")
    return scope, normalized_filters, limit, cursor


class DeveloperGraphIndex:
    """Immutable in-memory index over one validated developer-graph snapshot."""

    def __init__(
        self,
        graph: dict[str, Any],
        *,
        assume_validated: bool = False,
        detail_provider: Callable[[str], dict[str, Any]] | None = None,
    ):
        # Public/adaptor input remains fail-closed.  The normalized work-graph
        # adapter validates immediately before returning, so its two internal
        # consumers can avoid a second O(objects + relations) validation pass.
        if not assume_validated:
            if detail_provider is None:
                validate_developer_graph(graph)
            else:
                validate_developer_graph_index(graph)
        self.graph = graph
        self._detail_provider = detail_provider
        self._detail_cache: OrderedDict[
            str, tuple[dict[str, Any], int]
        ] = OrderedDict()
        self._detail_cache_bytes = 0
        self._detail_lock = threading.Lock()
        self.objects = {entry["id"]: entry for entry in graph["objects"]}
        self.groups = {entry["id"]: entry for entry in graph["groups"]}
        self.relations = list(graph["relations"])
        self.children: dict[str | None, list[str]] = defaultdict(list)
        for group in graph["groups"]:
            self.children[group.get("parentId")].append(group["id"])
        for values in self.children.values():
            values.sort()
        self.group_objects: dict[str | None, list[str]] = defaultdict(list)
        for entry in graph["objects"]:
            self.group_objects[entry.get("groupId")].append(entry["id"])
        for values in self.group_objects.values():
            values.sort()
        self.incident: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for relation in self.relations:
            self.incident[relation["source"]].append(relation)
            if relation["target"] != relation["source"]:
                self.incident[relation["target"]].append(relation)
        for values in self.incident.values():
            values.sort(key=lambda entry: entry["id"])
        # Stable ids do not imply stable content. Status, title, provenance,
        # grouping, relationships, or the compact graph's detailSnapshot must
        # invalidate old cursors even though lazy dossiers are not retained.
        self.fingerprint = developer_graph_fingerprint(graph)

    def _object_record(self, object_id: str) -> dict[str, Any]:
        """Hydrate one complete public object while bounding retained detail."""
        source = self.objects[object_id]
        if "detail" in source:
            return source
        if self._detail_provider is None:
            raise DeveloperQueryError(
                f"developer object detail is unavailable: {object_id}"
            )
        with self._detail_lock:
            cached = self._detail_cache.get(object_id)
            if cached is not None:
                self._detail_cache.move_to_end(object_id)
                return cached[0]
            record = materialize_developer_object(
                source, self._detail_provider(object_id)
            )
            encoded_size = len(_canonical(record))
            self._detail_cache[object_id] = (record, encoded_size)
            self._detail_cache_bytes += encoded_size
            while (len(self._detail_cache) > DETAIL_CACHE_LIMIT
                   or self._detail_cache_bytes > DETAIL_CACHE_BYTES):
                _evicted_id, (_evicted, evicted_size) = self._detail_cache.popitem(
                    last=False
                )
                self._detail_cache_bytes -= evicted_size
            return record

    def _descendant_groups(self, root: str) -> set[str]:
        found, pending = set(), [root]
        while pending:
            current = pending.pop()
            if current in found:
                continue
            found.add(current)
            pending.extend(reversed(self.children.get(current, [])))
        return found

    @staticmethod
    def _request(request: object) -> tuple[dict, dict, int, str | None]:
        return normalize_developer_query(request)

    @staticmethod
    def _matches(entry: dict[str, Any], filters: dict[str, Any]) -> bool:
        if filters["kinds"] and entry["kind"] not in filters["kinds"]:
            return False
        if filters["statuses"] and entry["status"] not in filters["statuses"]:
            return False
        query = filters["query"]
        if query:
            haystack = " ".join(str(entry.get(name, "")) for name in (
                "id", "kind", "title", "summary", "status",
            )).casefold()
            if query not in haystack:
                return False
        return True

    def _cursor(self, request_identity: str, offset: int) -> str:
        return f"v1.{self.fingerprint[:20]}.{request_identity[:20]}.{offset}"

    def _offset(self, cursor: str | None, request_identity: str) -> int:
        if cursor is None:
            return 0
        parts = cursor.split(".")
        if (len(parts) != 4 or parts[0] != "v1"
                or parts[1] != self.fingerprint[:20]
                or parts[2] != request_identity[:20]):
            raise DeveloperQueryError("developer query cursor is stale or belongs to another query")
        try:
            offset = int(parts[3])
        except ValueError:
            raise DeveloperQueryError("developer query cursor offset is malformed") from None
        if offset < 0:
            raise DeveloperQueryError("developer query cursor offset is malformed")
        return offset

    def _group_summary(self, group_id: str, matching: set[str]) -> dict[str, Any]:
        descendant_groups = self._descendant_groups(group_id)
        object_ids = sorted(
            object_id
            for nested in descendant_groups
            for object_id in self.group_objects.get(nested, [])
            if object_id in matching
        )
        composition = Counter(self.objects[object_id]["statusRole"] for object_id in object_ids)
        return {
            "groupId": group_id,
            "objectCount": len(object_ids),
            "statusComposition": {
                name: composition.get(name, 0)
                for name in ("blocked", "active", "ready", "shipped")
            },
        }

    def _object_page(
        self,
        candidates: list[str],
        offset: int,
        limit: int,
        *,
        prefix: list[str] | None = None,
    ) -> tuple[list[str], int]:
        """Bound a page by records and encoded bytes, never merely by count."""
        selected = list(prefix or [])
        used = sum(len(_canonical(self._object_record(object_id))) for object_id in selected)
        consumed = 0
        for object_id in candidates[offset:offset + max(0, limit - len(selected))]:
            size = len(_canonical(self._object_record(object_id)))
            if consumed and used + size > PRIMARY_OBJECT_BUDGET:
                break
            if not consumed and used + size > PRIMARY_OBJECT_BUDGET:
                raise DeveloperQueryError(
                    "one developer object exceeds the query response budget"
                )
            selected.append(object_id)
            used += size
            consumed += 1
        return selected, consumed

    @staticmethod
    def _bounded_records(
        values: list[dict[str, Any]], maximum: int, byte_budget: int,
    ) -> list[dict[str, Any]]:
        result, used = [], 0
        for value in values:
            size = len(_canonical(value))
            if result and (len(result) >= maximum or used + size > byte_budget):
                break
            if not result and size > byte_budget:
                raise DeveloperQueryError("one developer record exceeds its response budget")
            result.append(value)
            used += size
        return result

    def _boundary_object(self, object_id: str) -> dict[str, Any]:
        """Return the bounded identity rendered as an outside dependency card."""
        source = self.objects[object_id]
        return {
            "id": source["id"],
            "kind": source["kind"],
            "title": source["title"],
            "summary": "",
            "status": source["status"],
            "statusRole": source["statusRole"],
            "groupId": source.get("groupId"),
            "provenance": source["provenance"],
            "boundaryOnly": True,
        }

    def query(self, request: object) -> dict[str, Any]:
        """Return a bounded deterministic slice for one semantic zoom level."""
        scope, filters, limit, cursor = self._request(request)
        kind, identity = scope["kind"], scope.get("id")
        if kind == "group" and identity not in self.groups:
            raise DeveloperQueryError(f"unknown developer group: {identity}")
        if kind == "object" and identity not in self.objects:
            raise DeveloperQueryError(f"unknown developer object: {identity}")
        if kind == "object" and limit < 2:
            raise DeveloperQueryError("developer object queries need a limit of at least 2")

        relation_kinds = set(filters["relationKinds"])
        matching = {
            object_id for object_id, entry in self.objects.items()
            if self._matches(entry, filters)
        }
        request_key = hashlib.sha256(_canonical({
            "scope": scope, "filters": filters, "limit": limit,
        })).hexdigest()
        offset = self._offset(cursor, request_key)

        if kind == "overview":
            summary_candidates = [
                self._group_summary(group_id, matching)
                for group_id in self.children.get(None, [])
            ]
            summary_candidates = [
                entry for entry in summary_candidates if entry["objectCount"]
            ]
            summaries = summary_candidates[offset:offset + limit]
            page_ids: list[str] = []
            group_ids = {entry["groupId"] for entry in summaries}
            matched_count = len(summary_candidates)
            relevant_relations: list[dict[str, Any]] = []
            boundary_ids: list[str] = []
            boundary_matched = 0
            relation_matched = 0
        elif kind == "group":
            descendants = self._descendant_groups(identity)
            candidates = sorted(
                object_id for group_id in descendants
                for object_id in self.group_objects.get(group_id, [])
                if object_id in matching
            )
            page_ids, primary_consumed = self._object_page(
                candidates, offset, limit
            )
            matched_count = len(candidates)
            summaries = [
                self._group_summary(group_id, matching)
                for group_id in self.children.get(identity, [])
            ]
            summaries = [entry for entry in summaries if entry["objectCount"]]
            summary_matched = len(summaries)
            summaries = summaries[:min(limit, 500)]
            group_ids = {identity, *self.children.get(identity, [])}
            group_ids.update(
                self.objects[object_id].get("groupId") for object_id in page_ids
            )
            page_set = set(page_ids)
            internal_relations = [
                relation for relation in self.relations
                if relation["source"] in page_set and relation["target"] in page_set
                and (not relation_kinds or relation["kind"] in relation_kinds)
            ]
            scoped_ids = {
                object_id for group_id in descendants
                for object_id in self.group_objects.get(group_id, [])
            }
            boundary_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for relation in self.relations:
                if relation_kinds and relation["kind"] not in relation_kinds:
                    continue
                source_inside = relation["source"] in page_set
                target_inside = relation["target"] in page_set
                if source_inside == target_inside:
                    continue
                outside = relation["target"] if source_inside else relation["source"]
                if outside in scoped_ids:
                    continue
                boundary_candidates[outside].append(relation)
            boundary_values = self._bounded_records(
                [self._boundary_object(object_id)
                 for object_id in sorted(boundary_candidates)],
                MAX_BOUNDARY_OBJECTS,
                BOUNDARY_OBJECT_BUDGET,
            )
            boundary_ids = [entry["id"] for entry in boundary_values]
            boundary_matched = len(boundary_candidates)
            boundary_set = set(boundary_ids)
            boundary_relations = [
                relation for object_id in boundary_ids
                for relation in boundary_candidates[object_id]
                if ((relation["source"] in page_set and relation["target"] in boundary_set)
                    or (relation["target"] in page_set and relation["source"] in boundary_set))
            ]
            all_relation_candidates = {
                entry["id"]: entry
                for entry in [
                    *internal_relations,
                    *(relation for values in boundary_candidates.values()
                      for relation in values),
                ]
            }
            relation_candidates = sorted(
                {entry["id"]: entry
                 for entry in [*internal_relations, *boundary_relations]}.values(),
                key=lambda entry: entry["id"],
            )
            relation_matched = len(all_relation_candidates)
            relevant_relations = self._bounded_records(
                relation_candidates,
                MAX_LIMIT,
                RELATION_BUDGET,
            )
        else:
            incident = [
                relation for relation in self.incident.get(identity, [])
                if not relation_kinds or relation["kind"] in relation_kinds
            ]
            neighbor_ids = sorted({
                relation["target"] if relation["source"] == identity else relation["source"]
                for relation in incident
                if (relation["target"] if relation["source"] == identity
                    else relation["source"]) in matching
            })
            page_ids, neighbor_consumed = self._object_page(
                neighbor_ids, offset, limit, prefix=[identity]
            )
            page_neighbors = page_ids[1:]
            matched_count = 1 + len(neighbor_ids)
            page_set = set(page_ids)
            relevant_relations = [
                relation for relation in incident
                if relation["source"] in page_set and relation["target"] in page_set
            ]
            relation_matched = len(relevant_relations)
            relevant_relations = self._bounded_records(
                relevant_relations, MAX_LIMIT, RELATION_BUDGET,
            )
            group_ids = {
                self.objects[object_id].get("groupId") for object_id in page_ids
            }
            summaries = []
            boundary_ids = []
            boundary_matched = 0

        group_ids.discard(None)
        # Include the short ancestry chain required to render nested frames.
        pending = list(group_ids)
        while pending:
            current = pending.pop()
            parent = self.groups[current].get("parentId") if current in self.groups else None
            if parent and parent not in group_ids:
                group_ids.add(parent)
                pending.append(parent)

        if kind == "overview":
            next_offset = offset + len(summaries)
            has_more = next_offset < matched_count
        elif kind == "object":
            next_offset = offset + len(page_neighbors)
            has_more = next_offset < len(neighbor_ids)
        else:
            next_offset = offset + primary_consumed
            has_more = next_offset < matched_count
        next_cursor = (
            self._cursor(request_key, next_offset)
            if has_more else None
        )
        response = {
            "schema": RESPONSE_SCHEMA,
            "snapshot": self.fingerprint,
            "scope": scope,
            "objects": [self._object_record(object_id) for object_id in page_ids] + [
                self._boundary_object(object_id) for object_id in boundary_ids
            ],
            "relations": relevant_relations,
            "groups": [self.groups[group_id] for group_id in sorted(group_ids)],
            "summaries": summaries,
            "page": {
                "matched": matched_count,
                "returned": len(page_ids) + len(boundary_ids),
                "primaryReturned": len(page_ids),
                "boundaryMatched": boundary_matched,
                "boundaryReturned": len(boundary_ids),
                "boundaryOmitted": boundary_matched - len(boundary_ids),
                "relationMatched": relation_matched,
                "relationReturned": len(relevant_relations),
                "relationOmitted": relation_matched - len(relevant_relations),
                "nextCursor": next_cursor,
                "summaryMatched": (
                    matched_count if kind == "overview"
                    else summary_matched if kind == "group" else 0
                ),
                "summaryReturned": len(summaries),
            },
        }
        response["page"].update({
            "encodedBytes": 0,
            "maxEncodedBytes": MAX_RESPONSE_BYTES,
        })
        # Include this metadata in its own byte count; decimal width converges
        # after at most a few iterations.
        for _ in range(4):
            encoded_size = len(_canonical(response))
            if response["page"]["encodedBytes"] == encoded_size:
                break
            response["page"]["encodedBytes"] = encoded_size
        encoded_size = len(_canonical(response))
        if encoded_size > MAX_RESPONSE_BYTES:
            raise DeveloperQueryError(
                "developer query response exceeds the byte budget; narrow the scope"
            )
        if response["page"]["encodedBytes"] != encoded_size:
            raise DeveloperQueryError("developer query byte accounting did not converge")
        return response
