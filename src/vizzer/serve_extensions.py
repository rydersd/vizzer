"""Optional loopback HTTP extensions.

The static server owns transport policy. Feature modules own their routes and
domain mutations through this deliberately small context, avoiding another
feature-specific ladder in ``cli.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import threading
from typing import Callable, ContextManager
from urllib.parse import SplitResult, parse_qs, unquote

from . import __version__, process_render_id
from .config import Config
from .developer_graph import DeveloperGraphError, index_from_work_graph
from .developer_query import DeveloperGraphIndex, DeveloperQueryError
from .developer_store import DeveloperStoreError, StoredDeveloperGraphIndex
from .developer_views import (
    DeveloperViewError, delete_view, load_view_store, upsert_view,
)
from .model import Graph
from .review_contract import ReviewContractError
from .review_service import (
    ReviewServiceError, append_review_event, resolve_evidence, review_state,
)
from .story_sidebar import object_detail_providers


@dataclass(frozen=True)
class ServeRequestContext:
    root: Path
    cfg: Config
    graph: Graph
    csrf_token: str
    current_engine: Callable[[], bool]
    same_origin: Callable[[], bool]
    read_json: Callable[..., dict]
    mutation_guard: Callable[[], ContextManager]
    send_json: Callable[[int, dict], None]
    send_bytes: Callable[[int, bytes, str], None]


class ReviewHttpExtension:
    """Serve review authority, owner events, and opaque evidence references."""

    def get(self, ctx: ServeRequestContext, parsed: SplitResult) -> bool:
        if parsed.path == "/api/reviews" and not parsed.query:
            if not ctx.current_engine():
                return True
            if not ctx.cfg.get("reviews.enabled", False):
                ctx.send_json(404, {"error": "reviews are disabled"})
                return True
            try:
                state = review_state(ctx.cfg, ctx.root)
            except ReviewContractError as exc:
                ctx.send_json(500, {"error": str(exc)})
                return True
            ctx.send_json(200, {
                "engineVersion": __version__,
                "renderId": process_render_id(),
                "csrfToken": ctx.csrf_token,
                **state,
            })
            return True
        prefix = "/api/reviews/evidence/"
        if not parsed.path.startswith(prefix) or parsed.query:
            return False
        if not ctx.current_engine():
            return True
        encoded = parsed.path[len(prefix):].split("/")
        if len(encoded) != 3 or not all(encoded):
            ctx.send_json(404, {"error": "not found"})
            return True
        try:
            payload, media_type = resolve_evidence(
                ctx.cfg, ctx.root, *(unquote(value) for value in encoded)
            )
        except ReviewContractError as exc:
            ctx.send_json(404, {"error": str(exc)})
        except OSError as exc:
            ctx.send_json(500, {"error": f"could not read evidence: {exc}"})
        else:
            ctx.send_bytes(200, payload, media_type)
        return True

    def post(self, ctx: ServeRequestContext, parsed: SplitResult) -> bool:
        if parsed.path != "/api/reviews/runs" or parsed.query:
            return False
        if not ctx.current_engine():
            return True
        if not ctx.same_origin():
            ctx.send_json(403, {"error": "same-origin CSRF check failed"})
            return True
        if not ctx.cfg.get("reviews.enabled", False):
            ctx.send_json(404, {"error": "reviews are disabled"})
            return True
        try:
            body = ctx.read_json("review run")
            required = {"expectedRevision", "event"}
            missing = sorted(required - set(body))
            unknown = sorted(set(body) - required)
            if missing or unknown:
                field = (missing or unknown)[0]
                raise ReviewServiceError(
                    f"review run request has unknown or missing field: {field}"
                )
            event = body["event"]
            if (not isinstance(event, dict)
                    or not isinstance(event.get("actor"), dict)
                    or event["actor"].get("kind") != "owner"):
                raise ReviewServiceError(
                    "served review runs must be independent owner runs"
                )
            plan_id = event.get("planId")
            if not isinstance(plan_id, str):
                raise ReviewServiceError("review event planId must be a string")
            with ctx.mutation_guard():
                ledger = append_review_event(
                    ctx.cfg, ctx.root, plan_id, event,
                    expected_revision=body["expectedRevision"],
                    allow_owner=True,
                )
            ctx.send_json(200, {
                "revision": ledger["revision"],
                "event": ledger["events"][-1],
                "reloadRequired": False,
            })
        except (ReviewContractError, ValueError) as exc:
            status = 409 if "stale; current revision" in str(exc) else 400
            ctx.send_json(status, {"error": str(exc)})
        except (OSError, UnicodeError) as exc:
            ctx.send_json(500, {"error": f"could not persist review run: {exc}"})
        return True


class DeveloperFlowHttpExtension:
    """Serve bounded semantic slices instead of one enterprise-sized HTML blob."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: tuple[str, int] | None = None
        self._index: DeveloperGraphIndex | StoredDeveloperGraphIndex | None = None

    def _graph_index(
        self, ctx: ServeRequestContext,
    ) -> DeveloperGraphIndex | StoredDeveloperGraphIndex:
        key = (ctx.root.resolve().as_posix(), id(ctx.graph))
        with self._lock:
            if self._key != key or self._index is None:
                previous = self._index
                persisted = StoredDeveloperGraphIndex.open_current(ctx.root, ctx.cfg)
                if persisted is not None:
                    self._index = persisted
                else:
                    detail_provider, detail_identity_provider = object_detail_providers(
                        ctx.root
                    )
                    projected, indexed_detail_provider = index_from_work_graph(
                        ctx.graph,
                        ctx.cfg,
                        detail_provider=detail_provider,
                        detail_identity_provider=detail_identity_provider,
                    )
                    self._index = DeveloperGraphIndex(
                        projected,
                        assume_validated=True,
                        detail_provider=indexed_detail_provider,
                    )
                if previous is not None and hasattr(previous, "close"):
                    previous.close()
                self._key = key
            return self._index

    @staticmethod
    def _one(values: dict[str, list[str]], name: str, default: str = "") -> str:
        entries = values.get(name, [])
        if len(entries) > 1:
            raise DeveloperQueryError(f"developer query {name} may appear only once")
        return entries[0] if entries else default

    def get(self, ctx: ServeRequestContext, parsed: SplitResult) -> bool:
        if parsed.path == "/api/developer-flow/views" and not parsed.query:
            if not ctx.current_engine():
                return True
            if not ctx.cfg.get("developer_flow.enabled", False):
                ctx.send_json(404, {"error": "developer flow is disabled"})
                return True
            try:
                store = load_view_store(ctx.cfg, ctx.root)
            except DeveloperViewError as exc:
                ctx.send_json(500, {"error": str(exc)})
            else:
                ctx.send_json(200, {**store, "csrfToken": ctx.csrf_token})
            return True
        if parsed.path != "/api/developer-flow":
            return False
        if not ctx.current_engine():
            return True
        if not ctx.cfg.get("developer_flow.enabled", False):
            ctx.send_json(404, {"error": "developer flow is disabled"})
            return True
        try:
            values = parse_qs(
                parsed.query, keep_blank_values=True, strict_parsing=True,
                max_num_fields=24,
            )
            allowed = {"scope", "id", "q", "kind", "status", "relation", "limit", "cursor"}
            unknown = sorted(set(values) - allowed)
            if unknown:
                raise DeveloperQueryError(
                    f"developer query has unknown parameter: {unknown[0]}"
                )
            scope_kind = self._one(values, "scope", "overview")
            scope: dict[str, str] = {"kind": scope_kind}
            identity = self._one(values, "id")
            if identity:
                scope["id"] = identity
            filters = {
                "query": self._one(values, "q"),
                "kinds": values.get("kind", []),
                "statuses": values.get("status", []),
                "relationKinds": values.get("relation", []),
            }
            page: dict[str, object] = {}
            limit = self._one(values, "limit")
            if limit:
                try:
                    page["limit"] = int(limit)
                except ValueError:
                    raise DeveloperQueryError(
                        "developer query limit must be an integer"
                    ) from None
            cursor = self._one(values, "cursor")
            if cursor:
                page["cursor"] = cursor
            response = self._graph_index(ctx).query({
                "schema": 1, "scope": scope, "filters": filters, "page": page,
            })
        except (DeveloperGraphError, DeveloperQueryError, ValueError) as exc:
            ctx.send_json(400, {"error": str(exc)})
        except (OSError, UnicodeError, sqlite3.Error, DeveloperStoreError) as exc:
            ctx.send_json(500, {"error": f"could not build developer view: {exc}"})
        else:
            ctx.send_json(200, response)
        return True

    def post(self, ctx: ServeRequestContext, parsed: SplitResult) -> bool:
        if parsed.path == "/api/developer-flow/views" and not parsed.query:
            if not ctx.current_engine():
                return True
            if not ctx.same_origin():
                ctx.send_json(403, {"error": "same-origin CSRF check failed"})
                return True
            if not ctx.cfg.get("developer_flow.enabled", False):
                ctx.send_json(404, {"error": "developer flow is disabled"})
                return True
            try:
                body = ctx.read_json("saved view", 4 * 1024 * 1024)
                action = body.get("action")
                expected = body.get("expectedRevision")
                if action == "upsert" and set(body) == {
                    "action", "expectedRevision", "view",
                }:
                    with ctx.mutation_guard():
                        store = upsert_view(
                            ctx.cfg, ctx.root, body["view"],
                            expected_revision=expected,
                        )
                elif action == "delete" and set(body) == {
                    "action", "expectedRevision", "id",
                }:
                    with ctx.mutation_guard():
                        store = delete_view(
                            ctx.cfg, ctx.root, body["id"],
                            expected_revision=expected,
                        )
                else:
                    raise DeveloperViewError("saved view request is malformed")
            except DeveloperViewError as exc:
                status = 409 if "is stale; current revision" in str(exc) else 400
                ctx.send_json(status, {"error": str(exc)})
            except (OSError, UnicodeError) as exc:
                ctx.send_json(500, {"error": f"could not persist saved view: {exc}"})
            else:
                ctx.send_json(200, store)
            return True
        if parsed.path != "/api/developer-flow":
            return False
        ctx.send_json(405, {"error": "GET required"})
        return True


SERVE_EXTENSIONS = (DeveloperFlowHttpExtension(), ReviewHttpExtension())
