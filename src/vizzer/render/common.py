"""Shared deterministic helpers for rendered views."""
from __future__ import annotations

from ..config import Config
from ..model import Item


def emoji(cfg: Config, status: str) -> str:
    return cfg.status_meta(status)["emoji"]


def status_cell(cfg: Config, status: str) -> str:
    return f"{emoji(cfg, status)} {status}"


def _id_tail(item_id: str) -> str:
    return item_id.split(":", 1)[-1].split("/")[-1]


def item_link(item: Item) -> str:
    tail = _id_tail(item.id)
    path = item.source.get("path")
    return f"[{tail}](../../{path})" if path else tail


def bar(done: int, total: int, width: int = 12) -> str:
    if width <= 0:
        return ""
    filled = 0 if total <= 0 else round(width * max(0, min(done, total)) / total)
    return "█" * filled + "░" * (width - filled)


def topo(items: list[Item], all_deps: dict[str, list[str]]) -> list[Item]:
    """Return a deterministic dependency-first order, tolerating cycles."""
    by_id = {item.id: item for item in items}
    remaining = {
        item_id: {dep for dep in all_deps.get(item_id, []) if dep in by_id}
        for item_id in by_id
    }
    ordered: list[Item] = []

    while remaining:
        wave = sorted(item_id for item_id, deps in remaining.items() if not deps)
        if not wave:
            ordered.extend(by_id[item_id] for item_id in sorted(remaining))
            break
        ordered.extend(by_id[item_id] for item_id in wave)
        for item_id in wave:
            remaining.pop(item_id)
        completed = set(wave)
        for deps in remaining.values():
            deps.difference_update(completed)

    return ordered
