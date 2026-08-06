"""Behavior-oriented feature index renderer."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..model import Graph, Group, Item
from .common import item_link, status_cell


def _escape(value: str) -> str:
    return value.replace("|", "\\|")


def _table(items: list[Item], cfg: Config) -> list[str]:
    lines = ["| Behavior | Status | Rel | Item |", "|---|---|---|---|"]
    for item in sorted(items, key=lambda candidate: candidate.id):
        behavior = _escape(item.one_liner or item.title)
        lines.append(
            f"| {behavior} | {status_cell(cfg, item.status)} "
            f"| {item.release or '—'} | {item_link(item)} |"
        )
    return lines


def _first_child(
    group_id: str | None,
    top_id: str,
    groups: dict[str, Group],
) -> str | None:
    current = groups.get(group_id or "")
    child_id = None
    seen: set[str] = set()
    while current is not None and current.id not in seen:
        if current.id == top_id:
            return child_id
        seen.add(current.id)
        child_id = current.id
        current = groups.get(current.parent or "")
    return None


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    del root
    lines = ["# Feature Index", "", f"{len(graph.groups)} groups · {len(graph.items)} items", ""]
    groups = {group.id: group for group in graph.groups}
    tops = sorted(
        (group for group in graph.groups
         if group.parent is None and group.kind not in {"ledger", "folder"}),
        key=lambda group: group.id,
    )

    for top in tops:
        lines.extend([f"## {top.title}", ""])
        direct = [item for item in graph.items if item.group == top.id]
        if direct:
            lines.extend(["### (root)", "", *_table(direct, cfg), ""])

        children = sorted(
            (group for group in graph.groups
             if group.parent == top.id and group.kind not in {"ledger", "folder"}),
            key=lambda group: group.id,
        )
        for child in children:
            child_items = [
                item for item in graph.items
                if _first_child(item.group, top.id, groups) == child.id
            ]
            lines.extend([f"### {child.title}", "", *_table(child_items, cfg), ""])

    return {"feature-index.md": "\n".join(lines)}
