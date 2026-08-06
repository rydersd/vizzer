"""Continuity-ledger summary table renderer."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..model import Graph, Item
from .common import bar


NOT_STARTED = {"idea", "backlog", "specced", "ready", "parked", "unknown"}


def _escape(value: object) -> str:
    return str(value).replace("|", "\\|")


def _active_phase(children: list[Item], cfg: Config) -> str:
    done = cfg.done_statuses()
    for item in children:
        if item.status not in done and item.status not in NOT_STARTED:
            return item.title
    return "—"


def _last_modified(children: list[Item]) -> str:
    modified = [item.activity.get("modified") for item in children
                if item.activity.get("modified")]
    return max(modified)[:10] if modified else "—"


def _is_stale(children: list[Item], newest: int, staleness_days: int) -> bool:
    if not children or newest <= 0:
        return False
    cutoff = newest - staleness_days * 24 * 60 * 60
    return all((item.activity.get("last_touched", 0) or 0) < cutoff
               for item in children)


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    del root
    lines = [
        "# Ledger table",
        "",
        "| Ledger | Goal | Phase | Progress | Open Qs | Last touched | Stale |",
        "|---|---|---|---|---:|---|---|",
    ]
    ledgers = sorted(
        (group for group in graph.groups if group.kind == "ledger"),
        key=lambda group: group.id,
    )
    if not ledgers:
        lines.extend(["", "_No continuity ledgers found._", ""])
        return {"ledger-table.md": "\n".join(lines)}

    newest = max(
        (item.activity.get("last_touched", 0) or 0 for item in graph.items),
        default=0,
    )
    staleness_days = cfg.get("reconcile.staleness_days", 14)
    done = cfg.done_statuses()
    for ledger in ledgers:
        children = sorted(
            (item for item in graph.items if item.group == ledger.id),
            key=lambda item: item.id,
        )
        completed = sum(item.status in done for item in children)
        progress = f"{bar(completed, len(children))} {completed}/{len(children)}"
        stale = "⚠️" if _is_stale(children, newest, staleness_days) else ""
        lines.append(
            f"| {_escape(ledger.title)} | {_escape(ledger.meta.get('goal', ''))} "
            f"| {_escape(_active_phase(children, cfg))} | {progress} "
            f"| {ledger.meta.get('open_questions', 0)} | {_last_modified(children)} "
            f"| {stale} |"
        )
    lines.append("")
    return {"ledger-table.md": "\n".join(lines)}
