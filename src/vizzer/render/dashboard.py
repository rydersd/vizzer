"""Action-oriented dashboard renderer."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..model import Graph, Group, Item
from .common import bar, item_link, source_link_prefix, status_cell, topo


_NOT_STARTED = {"idea", "backlog", "specced", "ready", "parked", "unknown"}
_READY = _NOT_STARTED - {"parked"}


def _planned(item: Item) -> bool:
    return not item.id.startswith(("phase:", "todo:"))


def _item_line(item: Item, cfg: Config, prefix: str) -> str:
    return (
        f"- {status_cell(cfg, item.status)} {item_link(item, prefix)} — "
        f"{item.one_liner or item.title}"
    )


def _belongs_to(item: Item, top_id: str, groups: dict[str, Group]) -> bool:
    group_id = item.group
    seen: set[str] = set()
    while group_id and group_id not in seen:
        if group_id == top_id:
            return True
        seen.add(group_id)
        group = groups.get(group_id)
        group_id = group.parent if group else None
    return False


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    prefix = source_link_prefix(cfg, root)
    done_statuses = cfg.done_statuses()
    known_statuses = {status["name"] for status in cfg.vocab["statuses"]}
    planned = [item for item in graph.items if _planned(item)]
    item_map = graph.item_map()
    all_deps = {item.id: item.deps for item in graph.items}

    # Custom lifecycle states belong in [[status]] so they are classifiable here.
    in_progress = sorted(
        (item for item in planned
         if item.status in known_statuses
         and item.status not in done_statuses
         and item.status not in _NOT_STARTED),
        key=lambda item: item.id,
    )

    release_order = list(cfg.get("render.releases", []))
    active_release = next(
        (release for release in release_order
         if any(item.release == release and item.status not in done_statuses
                for item in planned)),
        None,
    )
    gates = cfg.gates()
    ready = []
    if active_release is not None:
        ready = [
            item for item in planned
            if item.release == active_release
            and item.status in _READY
            and item.id not in gates
            and all(item_map.get(dep) is None or item_map[dep].status in done_statuses
                    for dep in item.deps)
        ]
        ready = topo(ready, all_deps)

    gated = sorted(
        (item for item in planned
         if item.id in gates and item.status not in done_statuses),
        key=lambda item: item.id,
    )

    lines = ["# Dashboard — what to work on", "", "## In progress", ""]
    lines.extend(_item_line(item, cfg, prefix) for item in in_progress)
    lines.extend(["", "## Ready queue", ""])
    lines.extend(_item_line(item, cfg, prefix) for item in ready)
    lines.extend(["", "## Blocked on decisions", ""])
    lines.extend(
        f"- {item_link(item, prefix)} — {gates[item.id]}" for item in gated
    )
    lines.extend(["", "## Progress", ""])

    for release in release_order:
        release_items = [item for item in planned if item.release == release]
        done = sum(item.status in done_statuses for item in release_items)
        lines.append(f"{release} {bar(done, len(release_items))} {done}/{len(release_items)}")

    groups = {group.id: group for group in graph.groups}
    top_groups = sorted(
        (group for group in graph.groups if group.parent is None),
        key=lambda group: group.id,
    )
    if release_order and top_groups:
        lines.append("")
    for group in top_groups:
        group_items = [item for item in planned if _belongs_to(item, group.id, groups)]
        done = sum(item.status in done_statuses for item in group_items)
        lines.append(f"{group.title} {bar(done, len(group_items))} {done}/{len(group_items)}")

    lines.append("")
    return {"dashboard.md": "\n".join(lines)}
