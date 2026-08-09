"""Interactive 3D constellation: inject graph data into the self-contained template."""
from __future__ import annotations

import html
import json
import re
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote

from ..config import Config
from ..model import Graph
from .common import priority_items, source_link_prefix

TEMPLATE_NAME = "constellation_template.html"


def _template_text() -> str:
    """Read the template through the resources API so it works inside a zipapp too."""
    return (files(__package__) / TEMPLATE_NAME).read_text(encoding="utf-8")

# story complexity → node radius weight, from the item's appetite field
APPETITE_W = {"small": 1.0, "medium": 1.9, "large": 2.9}
DEFAULT_W = 1.4


def _int(value) -> int:
    """Best-effort integer for a value that reached us from a hand-editable file."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _progress(value: object) -> dict:
    """Constrain hand-edited graph progress to the renderer's tiny data contract."""
    if not isinstance(value, dict):
        return {}
    events = []
    for event in value.get("events", []):
        if not isinstance(event, dict):
            continue
        if all(isinstance(event.get(field), str) for field in ("at", "kind", "source", "detail")):
            events.append({"at": event["at"], "kind": event["kind"],
                           "source": event["source"], "detail": event["detail"]})
    result = {"events": events[-3:]}
    hot_window = value.get("hotWindowDays")
    if (isinstance(hot_window, (int, float)) and not isinstance(hot_window, bool)
            and hot_window > 0):
        result["hotWindowDays"] = min(float(hot_window), 36500)
    stall = value.get("stall")
    if (isinstance(stall, dict) and isinstance(stall.get("since"), str)
            and isinstance(stall.get("source"), str)):
        after_days = stall.get("afterDays")
        max_days = stall.get("maxDays")
        if (isinstance(after_days, (int, float)) and not isinstance(after_days, bool)
                and after_days >= 0
                and isinstance(max_days, (int, float)) and not isinstance(max_days, bool)
                and max_days > 0):
            result["stall"] = {
                "since": stall["since"],
                "source": stall["source"],
                "afterDays": min(float(after_days), 36500),
                "maxDays": min(float(max_days), 36500),
            }
    return result


def _top_group(graph: Graph, group_id: str | None) -> tuple[str, str]:
    """(top-level group id tail, immediate group title) for a node."""
    by_id = {g.id: g for g in graph.groups}
    imm = by_id.get(group_id or "")
    cur = imm
    while cur is not None and cur.parent is not None:
        cur = by_id.get(cur.parent)
    top_tail = cur.id.split(":", 1)[1] if cur else ""
    return top_tail, (imm.title if imm else "")


def _group_search_text(graph: Graph, group_id: str | None) -> str:
    """Return every authored id/title in an item's group ancestry."""
    by_id = {group.id: group for group in graph.groups}
    terms = []
    seen: set[str] = set()
    current = group_id
    while current and current not in seen:
        seen.add(current)
        group = by_id.get(current)
        terms.append(current)
        if group is None:
            break
        terms.append(group.title)
        current = group.parent
    return " ".join(terms)


def _visual_group(cfg: Config, status: str) -> str:
    """Map configured lifecycle roles onto the constellation's visual grammar."""
    role = cfg.status_role(status)
    if role == "done":
        return "shipped"
    if role == "active":
        return "active"
    if role == "regression":
        return "buggap"
    if role == "hold":
        return "parked"
    if role == "ready":
        if status == "ready":
            return "ready"
        if status == "specced":
            return "specced"
        return "faint"
    return "specced"


def _source_href(root: Path, cfg: Config, source_path: object) -> str:
    """Return a portable path-escaped link only for sources inside the repo."""
    if not isinstance(source_path, str) or not source_path:
        return ""
    repo = root.resolve()
    source = (repo / source_path).resolve()
    try:
        source.relative_to(repo)
    except ValueError:
        return ""
    relative = source.relative_to(repo).as_posix()
    return quote(source_link_prefix(cfg, root) + relative, safe="/")


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    # Manual highlights remain supported; deterministic recommendations augment
    # them when the priority engine is enabled.
    recommended = set(cfg.get("render.recommended", []))
    recommended.update(item.id for item in priority_items(graph))
    nodes, idx = [], {}
    items = sorted(graph.items, key=lambda i: i.id)
    for it in items:
        if it.id in idx:
            continue
        idx[it.id] = len(nodes)
        cap_tail, epic_title = _top_group(graph, it.group)
        w = APPETITE_W.get(it.appetite or "", DEFAULT_W)
        node = {
            "id": it.id,
            "s": it.id.split(":", 1)[1].split("/")[-1],
            "t": it.title[:80],
            "st": it.status,
            # codex-sequence-2026-08-08: one lifecycle role map across views.
            "g": _visual_group(cfg, it.status),
            "c": cap_tail,
            "e": epic_title[:40],
            "r": it.release or "",
            "p": it.source.get("path", ""),
            # codex-sequence-2026-08-08: visible canonical on-drive story link.
            "h": _source_href(root, cfg, it.source.get("path")),
            "w": round(0.72 + 0.36 * w, 2),
            # Activity comes from a checked-in file a human may have edited, and these
            # values are interpolated into the page — coerce to ints, never pass through.
            "ac": _int(it.activity.get("commits")),
            "am": _int(it.activity.get("mentions")),
            "ts": _int(it.activity.get("last_touched")),
            # codex-sequence-2026-08-08: one portable, renderer-owned search
            # index covers authored item text and the full group ancestry. Live
            # activity is appended below after its graph records are resolved.
            "q": " ".join(str(value) for value in (
                it.title,
                it.id,
                it.one_liner or "",
                it.status,
                it.release or "",
                _group_search_text(graph, it.group),
                it.source.get("path", ""),
            ) if value),
        }
        progress = _progress(it.progress)
        if progress:
            node["pg"] = progress
            node["q"] += " " + " ".join(
                event["detail"] + " " + event["source"]
                for event in progress.get("events", [])
            )
        if it.id in recommended:
            node["rec"] = 1
        if it.priority:
            node["pr"] = it.priority.get("rank")
            node["ps"] = it.priority.get("score")
            node["pw"] = it.priority.get("rationale", "")
            node["pu"] = it.priority.get("components", {}).get(
                "target_dependents", 0
            )
        nodes.append(node)

    # codex-sequence-2026-08-08: Foundation groups are explicit non-work nodes.  They deliberately have
    # no status, activity, hard edges, or priority; their only purpose is to
    # make the DAG's declared structural-root relationships inspectable.
    foundations = sorted(
        (group for group in graph.groups if group.kind == "foundation"),
        key=lambda group: group.id,
    )
    for group in foundations:
        idx[group.id] = len(nodes)
        nodes.append({
            "s": group.id.split(":", 1)[1],
            "t": group.title[:80],
            "st": "foundation",
            "g": "foundation",
            "c": "foundations",
            "e": "Structural root",
            "r": "",
            "p": "",
            "w": 1.35,
            "ac": 0,
            "am": 0,
            "ts": 0,
            "foundation": 1,
            "q": f"{group.id} {group.title} foundation Structural root",
        })

    edges = []
    for it in items:
        j = idx[it.id]
        for dep in it.deps:
            i = idx.get(dep)
            if i is not None:
                edges.append([i, j])

    # codex-sequence-2026-08-08: typed lineage is visible but deliberately not
    # included in DATA.edges, which remains the hard-prerequisite readiness graph.
    relations = []
    for it in items:
        source = idx[it.id]
        for relation in it.relations:
            target = idx.get(relation.target)
            if target is not None:
                relations.append([source, target, relation.kind])

    # codex-sequence-2026-08-08: activity stays a switchable overlay. Explicit
    # relatedStoryIds create work-link pulses; ordinary graph edges only receive
    # one/both-active emphasis and never claim that the relation itself is edited.
    work = []
    work_links = []
    for entry in sorted(
        graph.active_work,
        key=lambda value: (value.story_id, value.agent, value.task),
    ):
        node_index = idx.get(entry.story_id)
        if node_index is None:
            continue
        work_index = len(work)
        work.append({
            "n": node_index,
            "agent": entry.agent,
            "task": entry.task,
            "state": entry.state,
            "done": entry.completed,
            "total": entry.total,
            "updatedAt": entry.updated_at,
            "staleAt": entry.stale_at,
            "checkpoint": entry.checkpoint or "",
        })
        nodes[node_index].setdefault("aw", []).append(work_index)
        # codex-sequence-2026-08-08: activity is searchable without becoming
        # lifecycle or priority truth. Keep every human-facing text field.
        nodes[node_index]["q"] += " " + " ".join(filter(None, (
            entry.agent,
            entry.task,
            entry.state,
            entry.checkpoint or "",
            entry.updated_at,
            entry.stale_at,
        )))
        for related_id in entry.related_story_ids:
            related_index = idx.get(related_id)
            if related_index is not None:
                work_links.append([work_index, related_index])

    caps: dict[str, dict] = {}
    done = cfg.done_statuses()
    for it in items:
        cap_tail, _ = _top_group(graph, it.group)
        caps.setdefault(cap_tail, {"total": 0, "shipped": 0})
        caps[cap_tail]["total"] += 1
        if it.status in done:
            caps[cap_tail]["shipped"] += 1
    # codex-sequence-2026-08-08: foundation nodes are Structure-lens relation
    # targets, not deliverable capabilities with a fake 0/N progress bar.

    planning = dict(graph.priority.get("planning", {}))
    planning["baseTargets"] = graph.priority.get("base_targets", [])
    planning["effectiveTargets"] = graph.priority.get("effective_targets", [])
    data = {
        "nodes": nodes,
        "edges": edges,
        "relations": relations,
        "work": work,
        "workLinks": work_links,
        # Accepted owner planning course is inspectable in static mode. Writes
        # remain available only through the guarded loopback service.
        "planning": planning,
        "caps": caps,
        # deterministic "now": the newest activity in the graph, never wall clock
        "now": max((n["ts"] for n in nodes), default=0),
    }
    # codex-sequence-2026-08-08: Default output is portable and root-free.
    # The documented Obsidian integration remains an explicit local-vault opt-in.
    if cfg.get("render.obsidian_links", False):
        data["root"] = str(root)
    repo_url = cfg.get("render.repo_url", "")
    if repo_url:
        data["repo"] = repo_url

    title = cfg.get("render.title", "") or f"{cfg.get('project.name', 'project')} — constellation"
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    payload = (
        payload.replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    # Substitute in ONE pass. Replacing sequentially lets the first substitution's
    # output be re-scanned by the second: a title containing the literal "__DATA__"
    # smuggled the whole JSON payload into the HTML body, outside the script element,
    # where node titles are not HTML-escaped.
    substitutions = {"__TITLE__": html.escape(title, quote=True), "__DATA__": payload}
    rendered = re.sub(
        "|".join(re.escape(token) for token in substitutions),
        lambda match: substitutions[match.group(0)],
        _template_text(),
    )
    return {"constellation.html": rendered}
