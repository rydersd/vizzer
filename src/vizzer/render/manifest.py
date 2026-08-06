"""Deterministic JSON manifest of source-backed graph items."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import Config
from ..model import Graph, SCHEMA


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    del cfg, root
    items = sorted(
        (item for item in graph.items if item.source.get("path")),
        key=lambda item: (item.source["path"], item.id),
    )
    docs = [
        {
            "path": item.source["path"],
            "kind": item.id.split(":", 1)[0],
            "id": item.id,
            "title": item.title,
            "status": item.status,
            "group": item.group,
            "synopsis": item.one_liner,
            "created": item.activity.get("created"),
            "modified": item.activity.get("modified"),
        }
        for item in items
    ]
    manifest = {
        "generated_by": "vizzer",
        "schema": SCHEMA,
        "doc_count": len(docs),
        "docs": docs,
    }
    return {
        "manifest.json": json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    }
