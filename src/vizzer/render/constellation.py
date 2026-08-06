"""Interactive 3D constellation: inject graph data into the self-contained template."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import Config
from ..model import Graph

TEMPLATE = Path(__file__).parent / "constellation_template.html"

# story complexity → node radius weight, from the item's appetite field
APPETITE_W = {"small": 1.0, "medium": 1.9, "large": 2.9}
DEFAULT_W = 1.4


def _top_group(graph: Graph, group_id: str | None) -> tuple[str, str]:
    """(top-level group id tail, immediate group title) for a node."""
    by_id = {g.id: g for g in graph.groups}
    imm = by_id.get(group_id or "")
    cur = imm
    while cur is not None and cur.parent is not None:
        cur = by_id.get(cur.parent)
    top_tail = cur.id.split(":", 1)[1] if cur else ""
    return top_tail, (imm.title if imm else "")


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    recommended = set(cfg.get("render.recommended", []))
    nodes, idx = [], {}
    items = sorted(graph.items, key=lambda i: i.id)
    for it in items:
        if it.id in idx:
            continue
        idx[it.id] = len(nodes)
        cap_tail, epic_title = _top_group(graph, it.group)
        w = APPETITE_W.get(it.appetite or "", DEFAULT_W)
        node = {
            "s": it.id.split(":", 1)[1].split("/")[-1],
            "t": it.title[:80],
            "st": it.status,
            "c": cap_tail,
            "e": epic_title[:40],
            "r": it.release or "",
            "p": it.source.get("path", ""),
            "w": round(0.72 + 0.36 * w, 2),
            "ac": it.activity.get("commits", 0),
            "am": it.activity.get("mentions", 0),
            "ts": it.activity.get("last_touched", 0),
        }
        if it.id in recommended:
            node["rec"] = 1
        nodes.append(node)

    edges = []
    for it in items:
        j = idx[it.id]
        for dep in it.deps:
            i = idx.get(dep)
            if i is not None:
                edges.append([i, j])

    caps: dict[str, dict] = {}
    done = cfg.done_statuses()
    for it in items:
        cap_tail, _ = _top_group(graph, it.group)
        caps.setdefault(cap_tail, {"total": 0, "shipped": 0})
        caps[cap_tail]["total"] += 1
        if it.status in done:
            caps[cap_tail]["shipped"] += 1

    data = {
        "nodes": nodes,
        "edges": edges,
        "caps": caps,
        # deterministic "now": the newest activity in the graph, never wall clock
        "now": max((n["ts"] for n in nodes), default=0),
    }
    if cfg.get("render.obsidian_links", False):
        data["root"] = str(root)
    repo_url = cfg.get("render.repo_url", "")
    if repo_url:
        data["repo"] = repo_url

    title = cfg.get("render.title", "") or f"{cfg.get('project.name', 'project')} — constellation"
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", title)
    html = html.replace("__DATA__", json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    return {"constellation.html": html}
