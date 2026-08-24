"""Optional offline renderer for the normalized developer-object graph."""
from __future__ import annotations

import html
import json
from importlib.resources import files
from pathlib import Path

from ..config import Config
from ..developer_graph import from_work_graph
from ..developer_query import DeveloperGraphIndex
from ..model import Graph
from ..story_sidebar import object_detail_provider


ASSET_DIR = "developer_flow_assets"


def _asset(name: str) -> str:
    return (files(__package__) / ASSET_DIR / name).read_text(encoding="utf-8")


def _json_for_script(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    """Return nothing when disabled without touching optional asset resources."""
    if not bool(cfg.get("developer_flow.enabled", False)):
        return {}
    full_data = from_work_graph(
        graph, cfg, detail_provider=object_detail_provider(root)
    )
    restart_stable_origin = bool(cfg.get("server.port", 0))
    cap = full_data["limits"]["materializationCap"]
    if len(full_data["objects"]) > cap:
        initial = DeveloperGraphIndex(full_data).query({
            "schema": 1,
            "scope": {"kind": "overview"},
            "page": {"limit": cap},
        })
        data = {
            **full_data,
            "objects": initial["objects"],
            "relations": initial["relations"],
            "groups": initial["groups"],
            "summaries": initial["summaries"],
            "page": initial["page"],
            "queryScope": initial["scope"],
            "delivery": {
                "mode": "served",
                "endpoint": "/api/developer-flow",
                "snapshot": initial["snapshot"],
                "restartStableOrigin": restart_stable_origin,
            },
        }
    else:
        data = {
            **full_data,
            "summaries": [],
            "delivery": {
                "mode": "embedded",
                "restartStableOrigin": restart_stable_origin,
            },
        }
    shell = _asset("shell.html")
    page = (
        shell.replace("__TITLE__", html.escape(str(data["title"])))
        .replace("__DATA__", _json_for_script(data))
        .replace("__APP_CSS__", _asset("app.css"))
        .replace("__APP_JS__", _asset("app.js"))
    )
    unresolved = [
        token for token in ("__TITLE__", "__DATA__", "__APP_CSS__", "__APP_JS__")
        if token in page
    ]
    if unresolved:
        raise RuntimeError(f"developer flow shell has unresolved slots: {unresolved}")
    return {"developer-flow.html": page}
