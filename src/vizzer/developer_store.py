"""Atomic SQLite query store for large served Developer Flow graphs.

The store is a disposable projection of the normalized graph. It never becomes
source authority: metadata binds it to the exact canonical graph bytes and
renderer identity, and serving falls back to the validated in-memory index when
the cache is absent or stale.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import process_render_id
from .config import Config
from .developer_graph import stream_work_graph_index
from .developer_query import (
    BOUNDARY_OBJECT_BUDGET,
    MAX_BOUNDARY_OBJECTS,
    MAX_LIMIT,
    MAX_RESPONSE_BYTES,
    PRIMARY_OBJECT_BUDGET,
    RELATION_BUDGET,
    DeveloperQueryError,
    developer_graph_fingerprint_stream,
    materialize_developer_object,
    normalize_developer_query,
)
from .model import Graph
from .object_detail import validate_object_detail
from .story_sidebar import object_detail_providers


STORE_SCHEMA = 1
STORE_RELPATH = Path(".vizzer/cache/developer-flow-v1.sqlite3")
GRAPH_RELPATH = Path("vizzer/vizzer-graph.json")
_SQL_CHUNK = 400


class DeveloperStoreError(RuntimeError):
    """Raised when a persisted developer-query store is unsafe or malformed."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _decode(value: str | bytes) -> dict[str, Any]:
    try:
        raw = zlib.decompress(value).decode("utf-8") if isinstance(value, bytes) else value
        decoded = json.loads(raw)
    except (UnicodeError, ValueError, zlib.error) as exc:
        raise DeveloperStoreError("developer store record is malformed") from exc
    if not isinstance(decoded, dict):
        raise DeveloperStoreError("developer store record must be a JSON object")
    return decoded


def _decode_object(value: str | bytes, expected_id: str | None = None) -> dict[str, Any]:
    """Revalidate a stored public object before returning it to a client."""
    record = _decode(value)
    required = {
        "id", "kind", "title", "summary", "status", "statusRole",
        "groupId", "provenance", "details", "detail",
    }
    if not required.issubset(record):
        raise DeveloperStoreError("developer store object is incomplete")
    if expected_id is not None and record["id"] != expected_id:
        raise DeveloperStoreError("developer store object id does not match its row")
    if (
        not all(isinstance(record[name], str) for name in (
            "id", "kind", "title", "summary", "status", "statusRole",
        ))
        or record["statusRole"] not in {"blocked", "active", "ready", "shipped"}
        or not isinstance(record["provenance"], dict)
        or not isinstance(record["details"], dict)
    ):
        raise DeveloperStoreError("developer store object fields are malformed")
    source = {
        key: entry for key, entry in record.items()
        if key not in {"detail", "details"}
    }
    active_work = record["details"].get("activeWork")
    if active_work is not None:
        source["details"] = {"activeWork": active_work}
    try:
        materialized = materialize_developer_object(source, record["detail"])
    except DeveloperQueryError as exc:
        raise DeveloperStoreError(
            "developer store object detail is malformed"
        ) from exc
    if materialized != record:
        raise DeveloperStoreError("developer store object is not canonically materialized")
    return materialized


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def graph_source_fingerprint(graph: Graph) -> str:
    """Bind a cache build to the canonical normalized-graph artifact."""
    return _sha256_bytes(graph.dumps().encode("utf-8"))


def _config_fingerprint(cfg: Config) -> str:
    return _sha256_bytes(_canonical(cfg.data))


def _file_fingerprint(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def developer_store_path(root: Path) -> Path:
    """Resolve the fixed local cache path without permitting project escape."""
    project_root = root.resolve()
    candidate = (project_root / STORE_RELPATH).resolve()
    if not candidate.is_relative_to(project_root):
        raise DeveloperStoreError("developer store path escapes the project")
    return candidate


def needs_developer_store(graph: Graph, cfg: Config) -> bool:
    cap = cfg.get("developer_flow.materialization_cap", 1_200)
    if isinstance(cap, bool) or not isinstance(cap, int):
        cap = 1_200
    return bool(cfg.get("developer_flow.enabled", False)) and len(graph.items) > cap


def _boundary_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "kind": record["kind"],
        "title": record["title"],
        "summary": "",
        "status": record["status"],
        "statusRole": record["statusRole"],
        "groupId": record.get("groupId"),
        "provenance": record["provenance"],
        "boundaryOnly": True,
    }


def prepare_developer_store(
    graph: Graph,
    cfg: Config,
    root: Path,
) -> Path | None:
    """Build and atomically replace the large-graph store, if one is needed."""
    if not needs_developer_store(graph, cfg):
        return None
    path = developer_store_path(root)
    cache_dir = path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)
    if not cache_dir.resolve().is_relative_to(root.resolve()):
        raise DeveloperStoreError("developer store directory escapes the project")

    detail_provider, detail_identity_provider = object_detail_providers(root)
    graph_fingerprint = graph_source_fingerprint(graph)
    renderer = process_render_id()
    if renderer is None:
        raise DeveloperStoreError(
            "developer store needs an available renderer identity"
        )
    config_fingerprint = _config_fingerprint(cfg)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".developer-flow-", suffix=".sqlite3", dir=str(cache_dir),
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    spool_descriptor, spool_name = tempfile.mkstemp(
        prefix=".developer-flow-objects-", suffix=".jsonl", dir=str(cache_dir),
    )
    os.close(spool_descriptor)
    object_spool = Path(spool_name)
    try:
        connection = sqlite3.connect(str(temporary))
        try:
            connection.executescript("""
                PRAGMA journal_mode=OFF;
                PRAGMA synchronous=OFF;
                PRAGMA temp_store=MEMORY;
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                ) WITHOUT ROWID;
                CREATE TABLE groups (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    data TEXT NOT NULL
                ) WITHOUT ROWID;
                CREATE TABLE objects (
                    id TEXT PRIMARY KEY,
                    group_id TEXT,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    status_role TEXT NOT NULL,
                    search_text TEXT NOT NULL,
                    encoded_bytes INTEGER NOT NULL,
                    data BLOB NOT NULL,
                    boundary_data BLOB NOT NULL
                ) WITHOUT ROWID;
                CREATE TABLE relations (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    data TEXT NOT NULL
                ) WITHOUT ROWID;
                CREATE TABLE group_rollups (
                    group_id TEXT PRIMARY KEY,
                    object_count INTEGER NOT NULL,
                    blocked INTEGER NOT NULL,
                    active INTEGER NOT NULL,
                    ready INTEGER NOT NULL,
                    shipped INTEGER NOT NULL
                ) WITHOUT ROWID;
            """)
            direct_rollups: dict[str, Counter] = defaultdict(Counter)
            with object_spool.open("w+b") as spool:
                def visit_object(item: Any, source: dict[str, Any]) -> None:
                    record = materialize_developer_object(
                        source, detail_provider(item)
                    )
                    encoded = _canonical(record)
                    search_text = " ".join(str(record.get(name, "")) for name in (
                        "id", "kind", "title", "summary", "status",
                    )).casefold()
                    connection.execute(
                        """INSERT INTO objects(
                               id, group_id, kind, status, status_role, search_text,
                               encoded_bytes, data, boundary_data
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            record["id"], record.get("groupId"), record["kind"],
                            record["status"], record["statusRole"], search_text,
                            len(encoded), zlib.compress(encoded),
                            zlib.compress(_canonical(_boundary_record(record))),
                        ),
                    )
                    group_id = source.get("groupId")
                    if group_id is not None:
                        direct_rollups[group_id][source["statusRole"]] += 1
                    spool.write(_canonical(source))
                    spool.write(b"\n")

                envelope, relations = stream_work_graph_index(
                    graph,
                    cfg,
                    detail_identity_provider=detail_identity_provider,
                    object_visitor=visit_object,
                )
                groups = envelope.pop("groups")
                connection.executemany(
                    "INSERT INTO groups(id, parent_id, data) VALUES (?, ?, ?)",
                    (
                        (group["id"], group.get("parentId"),
                         _canonical(group).decode("utf-8"))
                        for group in groups
                    ),
                )

                def object_values():
                    spool.flush()
                    spool.seek(0)
                    for line in spool:
                        yield line.rstrip(b"\n")

                def relation_values():
                    for relation in relations:
                        connection.execute(
                            """INSERT INTO relations(id, source, target, kind, data)
                               VALUES (?, ?, ?, ?, ?)""",
                            (
                                relation["id"], relation["source"], relation["target"],
                                relation["kind"],
                                _canonical(relation).decode("utf-8"),
                            ),
                        )
                        yield relation

                snapshot = developer_graph_fingerprint_stream(
                    envelope,
                    {
                        "groups": groups,
                        "objects": object_values(),
                        "relations": relation_values(),
                    },
                )
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                (
                    ("schema", str(STORE_SCHEMA)),
                    ("sourceGraphSha256", graph_fingerprint),
                    ("projectionConfigSha256", config_fingerprint),
                    ("renderId", renderer),
                    ("snapshot", snapshot),
                    ("header", _canonical(envelope).decode("utf-8")),
                ),
            )
            parents = {
                group["id"]: group.get("parentId")
                for group in groups
            }
            rollups = {
                group_id: Counter(direct_rollups[group_id]) for group_id in parents
            }
            depths: dict[str, int] = {}

            def depth(group_id: str) -> int:
                trail: list[str] = []
                visiting: set[str] = set()
                current: str | None = group_id
                while current is not None and current not in depths:
                    if current in visiting:
                        raise DeveloperStoreError(
                            f"developer store group cycle at: {current}"
                        )
                    trail.append(current)
                    visiting.add(current)
                    current = parents.get(current)
                value = depths.get(current, -1) + 1
                for entry in reversed(trail):
                    depths[entry] = value
                    value += 1
                return depths[group_id]

            for group_id in parents:
                depth(group_id)
            for group_id in sorted(parents, key=lambda value: depths[value], reverse=True):
                parent_id = parents[group_id]
                if parent_id in rollups:
                    rollups[parent_id].update(rollups[group_id])
            connection.executemany(
                """INSERT INTO group_rollups(
                       group_id, object_count, blocked, active, ready, shipped
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    (
                        group_id,
                        sum(composition.values()),
                        composition["blocked"],
                        composition["active"],
                        composition["ready"],
                        composition["shipped"],
                    )
                    for group_id, composition in rollups.items()
                ),
            )
            connection.executescript("""
                CREATE INDEX objects_group_id ON objects(group_id, id);
                CREATE INDEX objects_kind ON objects(kind, id);
                CREATE INDEX objects_status ON objects(status, id);
                CREATE INDEX relations_source ON relations(source, kind, id);
                CREATE INDEX relations_target ON relations(target, kind, id);
                CREATE INDEX groups_parent_id ON groups(parent_id, id);
                PRAGMA user_version=1;
            """)
            connection.commit()
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if result != ("ok",):
                raise DeveloperStoreError("developer store integrity check failed")
        finally:
            connection.close()
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(cache_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    finally:
        try:
            object_spool.unlink()
        except OSError:
            pass
    return path


class StoredDeveloperGraphIndex:
    """Bounded Developer Flow queries over one immutable read-only SQLite file."""

    is_persisted = True

    def __init__(self, path: Path, connection: sqlite3.Connection, metadata: dict[str, str]):
        self.path = path
        self._connection = connection
        self._lock = threading.Lock()
        self.fingerprint = metadata["snapshot"]
        self.header = _decode(metadata["header"])

    @classmethod
    def open_current(
        cls, root: Path, cfg: Config,
    ) -> "StoredDeveloperGraphIndex | None":
        """Open only a store matching the current graph artifact and renderer."""
        try:
            path = developer_store_path(root)
        except DeveloperStoreError:
            return None
        graph_fingerprint = _file_fingerprint(root.resolve() / GRAPH_RELPATH)
        if graph_fingerprint is None or not path.is_file():
            return None
        renderer = process_render_id()
        if renderer is None:
            return None
        try:
            uri = f"{path.as_uri()}?mode=ro&immutable=1"
            connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
            connection.execute("PRAGMA query_only=ON")
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            required = {
                "schema", "sourceGraphSha256", "projectionConfigSha256",
                "renderId", "snapshot", "header",
            }
            if (
                set(metadata) != required
                or metadata["schema"] != str(STORE_SCHEMA)
                or metadata["sourceGraphSha256"] != graph_fingerprint
                or metadata["projectionConfigSha256"] != _config_fingerprint(cfg)
                or metadata["renderId"] != renderer
                or len(metadata["snapshot"]) != 64
                or any(character not in "0123456789abcdef"
                       for character in metadata["snapshot"])
            ):
                connection.close()
                return None
            header = _decode(metadata["header"])
            if header.get("schema") != 1:
                connection.close()
                return None
            return cls(path, connection, metadata)
        except (
            OSError, sqlite3.Error, ValueError, json.JSONDecodeError,
            DeveloperStoreError,
        ):
            try:
                connection.close()
            except (NameError, sqlite3.Error):
                pass
            return None

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _filter_sql(filters: dict[str, Any], alias: str = "o") -> tuple[str, list[Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        for field, name in (("kind", "kinds"), ("status", "statuses")):
            values = filters[name]
            if values:
                clauses.append(
                    f"{alias}.{field} IN ({','.join('?' for _ in values)})"
                )
                parameters.extend(values)
        if filters["query"]:
            clauses.append(f"instr({alias}.search_text, ?) > 0")
            parameters.append(filters["query"])
        return (" AND ".join(clauses) or "1"), parameters

    @staticmethod
    def _relation_sql(kinds: list[str], alias: str = "r") -> tuple[str, list[str]]:
        if not kinds:
            return "1", []
        return f"{alias}.kind IN ({','.join('?' for _ in kinds)})", list(kinds)

    def _cursor(self, request_identity: str, offset: int) -> str:
        return f"v1.{self.fingerprint[:20]}.{request_identity[:20]}.{offset}"

    def _offset(self, cursor: str | None, request_identity: str) -> int:
        if cursor is None:
            return 0
        parts = cursor.split(".")
        if (
            len(parts) != 4 or parts[0] != "v1"
            or parts[1] != self.fingerprint[:20]
            or parts[2] != request_identity[:20]
        ):
            raise DeveloperQueryError(
                "developer query cursor is stale or belongs to another query"
            )
        try:
            offset = int(parts[3])
        except ValueError:
            raise DeveloperQueryError(
                "developer query cursor offset is malformed"
            ) from None
        if offset < 0:
            raise DeveloperQueryError("developer query cursor offset is malformed")
        return offset

    @staticmethod
    def _bounded_records(
        values: list[dict[str, Any]], maximum: int, byte_budget: int,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        used = 0
        for value in values:
            size = len(_canonical(value))
            if result and (len(result) >= maximum or used + size > byte_budget):
                break
            if not result and size > byte_budget:
                raise DeveloperQueryError(
                    "one developer record exceeds its response budget"
                )
            result.append(value)
            used += size
        return result

    @staticmethod
    def _object_page(
        rows: list[sqlite3.Row], *, prefix: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        selected = list(prefix or [])
        used = sum(len(_canonical(record)) for record in selected)
        consumed = 0
        for row in rows:
            size = int(row["encoded_bytes"])
            if consumed and used + size > PRIMARY_OBJECT_BUDGET:
                break
            if not consumed and used + size > PRIMARY_OBJECT_BUDGET:
                raise DeveloperQueryError(
                    "one developer object exceeds the query response budget"
                )
            selected.append(_decode_object(row["data"], row["id"]))
            used += size
            consumed += 1
        return selected, consumed

    @staticmethod
    def _chunks(values: list[str]) -> list[list[str]]:
        return [values[index:index + _SQL_CHUNK]
                for index in range(0, len(values), _SQL_CHUNK)]

    def _descendants(self, connection: sqlite3.Connection, group_id: str) -> set[str]:
        rows = connection.execute("""
            WITH RECURSIVE descendants(id) AS (
                SELECT ?
                UNION ALL
                SELECT g.id FROM groups g JOIN descendants d ON g.parent_id=d.id
            )
            SELECT id FROM descendants
        """, (group_id,))
        return {row[0] for row in rows}

    def _summaries(
        self,
        connection: sqlite3.Connection,
        parent_id: str | None,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not any(filters[name] for name in ("query", "kinds", "statuses")):
            if parent_id is None:
                where = "g.parent_id IS NULL"
                parameters: list[Any] = []
            else:
                where = "g.parent_id=?"
                parameters = [parent_id]
            rows = connection.execute(f"""
                SELECT g.id, r.object_count, r.blocked, r.active, r.ready, r.shipped
                FROM groups g JOIN group_rollups r ON r.group_id=g.id
                WHERE {where} AND r.object_count > 0
                ORDER BY g.id
            """, parameters)
            return [
                {
                    "groupId": row[0],
                    "objectCount": row[1],
                    "statusComposition": {
                        "blocked": row[2], "active": row[3],
                        "ready": row[4], "shipped": row[5],
                    },
                }
                for row in rows
            ]
        filter_sql, parameters = self._filter_sql(filters)
        if parent_id is None:
            anchor = "SELECT id, id FROM groups WHERE parent_id IS NULL"
            anchor_parameters: list[Any] = []
        else:
            anchor = "SELECT id, id FROM groups WHERE parent_id = ?"
            anchor_parameters = [parent_id]
        rows = connection.execute(f"""
            WITH RECURSIVE roots(group_id, root_id) AS (
                {anchor}
                UNION ALL
                SELECT g.id, roots.root_id
                FROM groups g JOIN roots ON g.parent_id=roots.group_id
            )
            SELECT roots.root_id, COUNT(o.id),
                   SUM(CASE WHEN o.status_role='blocked' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN o.status_role='active' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN o.status_role='ready' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN o.status_role='shipped' THEN 1 ELSE 0 END)
            FROM roots JOIN objects o ON o.group_id=roots.group_id
            WHERE {filter_sql}
            GROUP BY roots.root_id
            ORDER BY roots.root_id
        """, [*anchor_parameters, *parameters])
        return [
            {
                "groupId": row[0],
                "objectCount": row[1],
                "statusComposition": {
                    "blocked": row[2] or 0,
                    "active": row[3] or 0,
                    "ready": row[4] or 0,
                    "shipped": row[5] or 0,
                },
            }
            for row in rows
        ]

    def _groups(
        self, connection: sqlite3.Connection, group_ids: set[str],
    ) -> list[dict[str, Any]]:
        pending = list(group_ids)
        while pending:
            chunk = pending[:_SQL_CHUNK]
            del pending[:_SQL_CHUNK]
            placeholders = ",".join("?" for _ in chunk)
            for group_id, parent_id in connection.execute(
                f"SELECT id, parent_id FROM groups WHERE id IN ({placeholders})", chunk
            ):
                if parent_id and parent_id not in group_ids:
                    group_ids.add(parent_id)
                    pending.append(parent_id)
        result: list[dict[str, Any]] = []
        for chunk in self._chunks(sorted(group_ids)):
            placeholders = ",".join("?" for _ in chunk)
            for expected_id, data in connection.execute(
                    f"SELECT id, data FROM groups WHERE id IN ({placeholders}) ORDER BY id",
                    chunk,
                ):
                group = _decode(data)
                if group.get("id") != expected_id:
                    raise DeveloperStoreError(
                        "developer store group id does not match its row"
                    )
                try:
                    validate_object_detail(group.get("detail"))
                except ValueError as exc:
                    raise DeveloperStoreError(
                        "developer store group detail is malformed"
                    ) from exc
                if group["detail"]["id"] != expected_id:
                    raise DeveloperStoreError(
                        "developer store group detail id does not match"
                    )
                result.append(group)
        return sorted(result, key=lambda value: value["id"])

    def _incident_relations(
        self,
        connection: sqlite3.Connection,
        object_ids: list[str],
        relation_kinds: list[str],
    ) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        kind_sql, kind_parameters = self._relation_sql(relation_kinds)
        for chunk in self._chunks(object_ids):
            placeholders = ",".join("?" for _ in chunk)
            rows = connection.execute(f"""
                SELECT r.id, r.source, r.target, r.kind, r.data FROM relations r
                WHERE (r.source IN ({placeholders}) OR r.target IN ({placeholders}))
                  AND {kind_sql}
                ORDER BY r.id
            """, [*chunk, *chunk, *kind_parameters])
            for row in rows:
                relation = _decode(row[4])
                if [relation.get(name) for name in ("id", "source", "target", "kind")] != [
                    row[0], row[1], row[2], row[3],
                ]:
                    raise DeveloperStoreError(
                        "developer store relation identity does not match its row"
                    )
                if (
                    relation.get("direction") not in {"directed", "undirected"}
                    or not isinstance(relation.get("confidence"), str)
                    or not isinstance(relation.get("provenance"), dict)
                ):
                    raise DeveloperStoreError(
                        "developer store relation fields are malformed"
                    )
                found[relation["id"]] = relation
        return [found[key] for key in sorted(found)]

    def _boundary_records(
        self, connection: sqlite3.Connection, object_ids: list[str],
    ) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        for chunk in self._chunks(object_ids):
            placeholders = ",".join("?" for _ in chunk)
            for object_id, object_data, boundary_data in connection.execute(
                f"""SELECT id, data, boundary_data FROM objects
                    WHERE id IN ({placeholders})""",
                chunk,
            ):
                source = _decode_object(object_data, object_id)
                record = _decode(boundary_data)
                if record != _boundary_record(source):
                    raise DeveloperStoreError(
                        "developer store boundary object does not match its row"
                    )
                records[object_id] = record
        return [records[object_id] for object_id in sorted(records)]

    def query(self, request: object) -> dict[str, Any]:
        """Return the same bounded contract as the in-memory query oracle."""
        scope, filters, limit, cursor = normalize_developer_query(request)
        kind, identity = scope["kind"], scope.get("id")
        request_key = hashlib.sha256(_canonical({
            "scope": scope, "filters": filters, "limit": limit,
        })).hexdigest()
        offset = self._offset(cursor, request_key)

        with self._lock:
            connection = self._connection
            connection.row_factory = sqlite3.Row
            if kind == "group":
                exists = connection.execute(
                    "SELECT 1 FROM groups WHERE id=?", (identity,)
                ).fetchone()
                if exists is None:
                    raise DeveloperQueryError(f"unknown developer group: {identity}")
            if kind == "object":
                exists = connection.execute(
                    "SELECT 1 FROM objects WHERE id=?", (identity,)
                ).fetchone()
                if exists is None:
                    raise DeveloperQueryError(f"unknown developer object: {identity}")
                if limit < 2:
                    raise DeveloperQueryError(
                        "developer object queries need a limit of at least 2"
                    )

            if kind == "overview":
                summary_candidates = self._summaries(connection, None, filters)
                matched_count = len(summary_candidates)
                summaries = summary_candidates[offset:offset + limit]
                primary: list[dict[str, Any]] = []
                boundary: list[dict[str, Any]] = []
                relevant_relations: list[dict[str, Any]] = []
                group_ids = {entry["groupId"] for entry in summaries}
                boundary_matched = relation_matched = 0
                primary_consumed = 0
                summary_matched = matched_count
            elif kind == "group":
                descendants = self._descendants(connection, identity)
                filter_sql, filter_parameters = self._filter_sql(filters)
                candidate_cte = """
                    WITH RECURSIVE descendants(id) AS (
                        SELECT ?
                        UNION ALL
                        SELECT g.id
                        FROM groups g JOIN descendants d ON g.parent_id=d.id
                    )
                """
                matched_count = connection.execute(f"""
                    {candidate_cte}
                    SELECT COUNT(*) FROM objects o JOIN descendants d ON o.group_id=d.id
                    WHERE {filter_sql}
                """, [identity, *filter_parameters]).fetchone()[0]
                rows = list(connection.execute(f"""
                    {candidate_cte}
                    SELECT o.id, o.data, o.encoded_bytes
                    FROM objects o JOIN descendants d ON o.group_id=d.id
                    WHERE {filter_sql}
                    ORDER BY o.id LIMIT ? OFFSET ?
                """, [identity, *filter_parameters, limit, offset]))
                primary, primary_consumed = self._object_page(rows)
                page_ids = [record["id"] for record in primary]
                page_set = set(page_ids)
                summaries = self._summaries(connection, identity, filters)
                summary_matched = len(summaries)
                summaries = summaries[:min(limit, 500)]
                group_ids = {identity, *(row[0] for row in connection.execute(
                    "SELECT id FROM groups WHERE parent_id=? ORDER BY id", (identity,)
                ))}
                group_ids.update(record.get("groupId") for record in primary)
                group_ids.discard(None)

                incident = self._incident_relations(
                    connection, page_ids, filters["relationKinds"]
                )
                internal = [
                    relation for relation in incident
                    if relation["source"] in page_set and relation["target"] in page_set
                ]
                outside_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for relation in incident:
                    source_inside = relation["source"] in page_set
                    target_inside = relation["target"] in page_set
                    if source_inside == target_inside:
                        continue
                    outside = relation["target"] if source_inside else relation["source"]
                    outside_candidates[outside].append(relation)
                outside_group: dict[str, str | None] = {}
                for chunk in self._chunks(sorted(outside_candidates)):
                    marks = ",".join("?" for _ in chunk)
                    outside_group.update(connection.execute(
                        f"SELECT id, group_id FROM objects WHERE id IN ({marks})", chunk
                    ))
                boundary_candidates = {
                    object_id: values for object_id, values in outside_candidates.items()
                    if outside_group.get(object_id) not in descendants
                }
                boundary_values = self._bounded_records(
                    self._boundary_records(connection, sorted(boundary_candidates)),
                    MAX_BOUNDARY_OBJECTS,
                    BOUNDARY_OBJECT_BUDGET,
                )
                boundary_ids = [record["id"] for record in boundary_values]
                boundary_set = set(boundary_ids)
                boundary = boundary_values
                boundary_matched = len(boundary_candidates)
                boundary_relations = [
                    relation
                    for object_id in boundary_ids
                    for relation in boundary_candidates[object_id]
                    if (
                        relation["source"] in page_set
                        and relation["target"] in boundary_set
                    ) or (
                        relation["target"] in page_set
                        and relation["source"] in boundary_set
                    )
                ]
                all_relation_candidates = {
                    relation["id"]: relation
                    for relation in [
                        *internal,
                        *(entry for values in boundary_candidates.values() for entry in values),
                    ]
                }
                relation_candidates = sorted(
                    {relation["id"]: relation
                     for relation in [*internal, *boundary_relations]}.values(),
                    key=lambda value: value["id"],
                )
                relation_matched = len(all_relation_candidates)
                relevant_relations = self._bounded_records(
                    relation_candidates, MAX_LIMIT, RELATION_BUDGET,
                )
            else:
                filter_sql, filter_parameters = self._filter_sql(filters)
                relation_sql, relation_parameters = self._relation_sql(
                    filters["relationKinds"]
                )
                neighbor_expression = (
                    "CASE WHEN r.source=? THEN r.target ELSE r.source END"
                )
                base_parameters = [identity, identity, identity,
                                   *relation_parameters, *filter_parameters]
                base_sql = f"""
                    FROM relations r
                    JOIN objects o ON o.id={neighbor_expression}
                    WHERE (r.source=? OR r.target=?) AND {relation_sql} AND {filter_sql}
                """
                neighbor_count = connection.execute(
                    f"SELECT COUNT(DISTINCT o.id) {base_sql}", base_parameters
                ).fetchone()[0]
                neighbor_rows = list(connection.execute(f"""
                    SELECT DISTINCT o.id, o.data, o.encoded_bytes {base_sql}
                    ORDER BY o.id LIMIT ? OFFSET ?
                """, [*base_parameters, limit - 1, offset]))
                focus_row = connection.execute(
                    "SELECT data, encoded_bytes FROM objects WHERE id=?", (identity,)
                ).fetchone()
                assert focus_row is not None
                focus = _decode_object(focus_row["data"], identity)
                primary, neighbor_consumed = self._object_page(
                    neighbor_rows, prefix=[focus]
                )
                primary_consumed = neighbor_consumed
                matched_count = 1 + neighbor_count
                page_ids = [record["id"] for record in primary]
                page_set = set(page_ids)
                relevant_relations = [
                    relation for relation in self._incident_relations(
                        connection, [identity], filters["relationKinds"]
                    )
                    if relation["source"] in page_set and relation["target"] in page_set
                ]
                relation_matched = len(relevant_relations)
                relevant_relations = self._bounded_records(
                    relevant_relations, MAX_LIMIT, RELATION_BUDGET,
                )
                summaries = []
                summary_matched = 0
                group_ids = {record.get("groupId") for record in primary}
                group_ids.discard(None)
                boundary = []
                boundary_matched = 0

            groups = self._groups(connection, group_ids)

        if kind == "overview":
            next_offset = offset + len(summaries)
            has_more = next_offset < matched_count
        elif kind == "object":
            next_offset = offset + primary_consumed
            has_more = next_offset < matched_count - 1
        else:
            next_offset = offset + primary_consumed
            has_more = next_offset < matched_count
        response = {
            "schema": 1,
            "snapshot": self.fingerprint,
            "scope": scope,
            "objects": [*primary, *boundary],
            "relations": relevant_relations,
            "groups": groups,
            "summaries": summaries,
            "page": {
                "matched": matched_count,
                "returned": len(primary) + len(boundary),
                "primaryReturned": len(primary),
                "boundaryMatched": boundary_matched,
                "boundaryReturned": len(boundary),
                "boundaryOmitted": boundary_matched - len(boundary),
                "relationMatched": relation_matched,
                "relationReturned": len(relevant_relations),
                "relationOmitted": relation_matched - len(relevant_relations),
                "nextCursor": (
                    self._cursor(request_key, next_offset) if has_more else None
                ),
                "summaryMatched": summary_matched,
                "summaryReturned": len(summaries),
                "encodedBytes": 0,
                "maxEncodedBytes": MAX_RESPONSE_BYTES,
            },
        }
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
            raise DeveloperQueryError(
                "developer query byte accounting did not converge"
            )
        return response


def ensure_developer_store(graph: Graph, cfg: Config, root: Path) -> Path | None:
    """Reuse the exact current store or build it before a large served session."""
    if not needs_developer_store(graph, cfg):
        return None
    existing = StoredDeveloperGraphIndex.open_current(root, cfg)
    if existing is not None:
        path = existing.path
        existing.close()
        return path
    return prepare_developer_store(graph, cfg, root)
