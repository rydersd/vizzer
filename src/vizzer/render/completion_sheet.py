"""Completion and post-ship health renderer."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..config import Config
from ..model import Graph, Group, Item
from .common import item_link


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
    del root
    vocab = graph.vocab.get("statuses", cfg.vocab["statuses"])
    status_names = [status.get("name", "unknown") for status in vocab]
    known_statuses = set(status_names)
    counts = Counter(item.status for item in graph.items)
    other_statuses = sorted(status for status in counts if status not in known_statuses)

    lines = [
        "# Completion sheet",
        "",
        "## Overall",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    lines.extend(f"| {status} | {counts[status]} |" for status in status_names)
    lines.extend(f"| {status.upper()} | {counts[status]} |" for status in other_statuses)
    lines.extend([f"| Total | {len(graph.items)} |", "", "## Post-ship health", "",
                  "| Measure | Value |", "|---|---:|"])

    verified = counts["verified"]
    shipped = sum(counts[status] for status in cfg.done_statuses())
    verified_rate = 100.0 * verified / shipped if shipped else 0.0
    debt = sum("debt" in item.flags for item in graph.items)
    lines.extend([
        f"| Verified | {verified} |",
        f"| Shipped incl. verified | {shipped} |",
        f"| Verified-rate | {verified_rate:.1f}% |",
        f"| Debt (flagged items) | {debt} |",
        "",
        "## By group",
        "",
    ])

    group_columns = [*status_names, "other", "debt", "total"]
    lines.append("| Group | " + " | ".join(group_columns) + " |")
    lines.append("|---|" + "|".join("---:" for _ in group_columns) + "|")
    groups = {group.id: group for group in graph.groups}
    top_groups = sorted(
        (group for group in graph.groups if group.parent is None),
        key=lambda group: group.id,
    )
    for group in top_groups:
        items = [item for item in graph.items if _belongs_to(item, group.id, groups)]
        group_counts = Counter(item.status for item in items)
        values = [group_counts[status] for status in status_names]
        values.extend([
            sum(group_counts[status] for status in group_counts if status not in known_statuses),
            sum("debt" in item.flags for item in items),
            len(items),
        ])
        lines.append(f"| {group.title} | " + " | ".join(str(value) for value in values) + " |")

    lines.extend([
        "",
        "## Full list",
        "",
        "| Group | Item | Status | Release | Wave | Debt |",
        "|---|---|---|---|---|---|",
    ])
    group_titles = {group.id: group.title for group in graph.groups}
    for item in sorted(graph.items, key=lambda candidate: (candidate.group or "", candidate.id)):
        group = group_titles.get(item.group or "", "—")
        debt_cell = "yes" if "debt" in item.flags else ""
        lines.append(
            f"| {group} | {item_link(item)} | {item.status} | {item.release or '—'} "
            f"| {item.wave or '—'} | {debt_cell} |"
        )

    lines.append("")
    return {"completion-sheet.md": "\n".join(lines)}
