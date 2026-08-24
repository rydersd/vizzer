"""Deterministic risk, capability, and decision-aging perspectives."""
from __future__ import annotations

import re
from pathlib import Path

from ..config import Config
from ..model import Graph
from ..question_aging import question_ages
from .common import item_link, source_link_prefix
from .perspective_common import (
    age_days, age_text, capability_for, explicit_receipt_paths, git_metadata,
    parse_time, safe_source_text, snapshot_time,
)


UNCONFIRMED = re.compile(r"\bunconfirmed\b", re.IGNORECASE)


def _latest_work_time(graph: Graph, item) -> object:
    candidates = [
        parse_time(work.updated_at) for work in graph.active_work
        if work.story_id == item.id
    ]
    candidates.extend(
        parse_time(event.get("at")) for event in item.progress.get("events", [])
        if isinstance(event, dict)
    )
    return max((value for value in candidates if value), default=None)


def _risk_view(graph: Graph, cfg: Config, root: Path) -> str:
    anchor = snapshot_time(graph)
    threshold = int(cfg.get("reconcile.staleness_days", 14))
    prefix = source_link_prefix(cfg, root)
    metadata = git_metadata(str(root.resolve()))
    stale_work, stale_receipts, unverifiable, unconfirmed = [], [], [], []
    for item in graph.items:
        source_path = item.source.get("path")
        text = safe_source_text(root, source_path)
        if cfg.status_role(item.status) == "active":
            latest = _latest_work_time(graph, item)
            lower_bound = False
            if latest is None:
                latest = metadata.modified(source_path) if source_path else None
                lower_bound = True
            days = age_days(latest, anchor)
            if days is not None and days >= threshold:
                stale_work.append((days, item, latest, lower_bound))
        story_epoch = metadata.last_touched(source_path) if source_path else 0
        for receipt in explicit_receipt_paths(text):
            receipt_epoch = metadata.last_touched(receipt)
            if not receipt_epoch:
                unverifiable.append((item, receipt))
            elif story_epoch and receipt_epoch < story_epoch:
                stale_receipts.append((story_epoch - receipt_epoch, item, receipt))
        if UNCONFIRMED.search(text):
            modified = metadata.modified(source_path) if source_path else None
            unconfirmed.append((age_days(modified, anchor), item, modified))
    stale_work.sort(key=lambda value: (-value[0], value[1].id))
    stale_receipts.sort(key=lambda value: (-value[0], value[1].id, value[2]))
    unverifiable.sort(key=lambda value: (value[0].id, value[1]))
    unconfirmed.sort(key=lambda value: (
        value[0] is None, -(value[0] or 0), value[1].id,
    ))
    lines = [
        "# Risk and staleness heat", "",
        "Read-only. Ages use the newest persisted evidence, never refresh time. ",
        f"Snapshot: `{anchor.isoformat().replace('+00:00', 'Z')}`.", "",
        f"## Active lifecycle without evidence for {threshold}+ days", "",
    ]
    lines.extend(
        f"- **{age_text(latest, anchor, lower_bound=lower)}** · "
        f"{item_link(item, prefix)} · `{item.status}`"
        for _days, item, latest, lower in stale_work
    )
    if not stale_work:
        lines.append("_None._")
    lines.extend(["", "## Stale tracked receipts", ""])
    lines.extend(
        f"- **{max(1, delta // 86_400)}d behind source** · "
        f"{item_link(item, prefix)} · `{receipt}`"
        for delta, item, receipt in stale_receipts
    )
    if not stale_receipts:
        lines.append("_None reproducibly stale in tracked Git history._")
    lines.extend(["", "### Receipt references not reproducible from Git", ""])
    lines.extend(
        f"- {item_link(item, prefix)} · `{receipt}`"
        for item, receipt in unverifiable
    )
    if not unverifiable:
        lines.append("_None._")
    lines.extend(["", "## Aging UNCONFIRMED claims", ""])
    lines.extend(
        f"- **{age_text(modified, anchor, lower_bound=True)}** · "
        f"{item_link(item, prefix)}"
        for _days, item, modified in unconfirmed
    )
    if not unconfirmed:
        lines.append("_None._")
    lines.append("")
    return "\n".join(lines)


def _capability_view(graph: Graph, cfg: Config, root: Path) -> str:
    anchor = snapshot_time(graph)
    window = int(cfg.get("progress.hot_window_days", 7))
    groups = {group.id: group for group in graph.groups}
    done = cfg.done_statuses()
    buckets = {}
    for item in graph.items:
        if item.role == "delivery":
            buckets.setdefault(capability_for(item, groups), []).append(item)
    lines = [
        "# Capability rollup", "",
        "Read-only. Lifecycle buckets come from configured status roles; momentum "
        f"is recorded done transitions in the {window}-day evidence window.", "",
        "| Capability | Total | Done | Ready | Active | Regression | Momentum |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for capability_id, items in sorted(buckets.items()):
        total = len(items)
        counts = {
            role: sum(cfg.status_role(item.status) == role for item in items)
            for role in ("ready", "active", "regression")
        }
        completed = sum(item.status in done for item in items)
        momentum = 0
        for item in items:
            for event in item.progress.get("events", []):
                if not isinstance(event, dict) or event.get("kind") != "lifecycle":
                    continue
                target = event.get("detail", "").rsplit("→", 1)[-1].strip()
                days = age_days(parse_time(event.get("at")), anchor)
                if target in done and days is not None and days <= window:
                    momentum += 1
        group = groups.get(capability_id)
        title = group.title if group else "Unassigned"
        pct = lambda value: f"{value}/{total} ({value / total:.0%})"
        lines.append(
            f"| {title} | {total} | {pct(completed)} | {pct(counts['ready'])} | "
            f"{pct(counts['active'])} | {pct(counts['regression'])} | +{momentum} |"
        )
    lines.append("")
    return "\n".join(lines)


def _decision_view(graph: Graph, cfg: Config, root: Path) -> str:
    anchor = snapshot_time(graph)
    prefix = source_link_prefix(cfg, root)
    items = graph.item_map()
    budget = int(cfg.get("questions.age_budget_hours", 72))
    ages = question_ages(graph, cfg, root, anchor)
    lines = [
        "# Decision aging", "",
        "Read-only. Ages use explicit `raisedAt`, then Git introduction history; "
        "unknown stays unknown.", "",
        "| Age | Question | Story | Recommendation |", "|---:|---|---|---|",
    ]
    for entry in ages:
        question = entry.question
        item = items.get(question.story_id)
        story = item_link(item, prefix) if item else f"`{question.story_id}`"
        age = (
            "unknown" if entry.age_hours is None
            else f"**{entry.age_hours // 24}d ⏰ OVER {budget}h**"
            if entry.over_budget else f"{entry.age_hours // 24}d"
        )
        prompt = question.prompt.replace("|", "\\|")
        rationale = question.recommendation.rationale.replace("|", "\\|")
        lines.append(
            f"| {age} | `{question.id}` — {prompt} | "
            f"{story} | `{question.recommendation.option_id}` — "
            f"{rationale} |"
        )
    if not ages:
        lines.append("| — | No open owner questions | — | — |")
    lines.append("")
    return "\n".join(lines)


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    if not cfg.get("perspectives.enabled", False):
        return {}
    return {
        "risk-heat.md": _risk_view(graph, cfg, root),
        "capability-rollup.md": _capability_view(graph, cfg, root),
        "decision-aging.md": _decision_view(graph, cfg, root),
    }
