"""Action-oriented dashboard renderer."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..model import Graph, Group, Item
from .common import bar, item_link, priority_items, source_link_prefix, status_cell, topo


def _planned(item: Item) -> bool:
    return not item.id.startswith(("phase:", "todo:"))


def _item_line(item: Item, cfg: Config, prefix: str) -> str:
    # codex-sequence-2026-08-08: source prose may carry Markdown hard-break
    # whitespace; generated dashboards must still pass repository diff hygiene.
    summary = (item.one_liner or item.title).strip()
    return (
        f"- {status_cell(cfg, item.status)} {item_link(item, prefix)} — "
        f"{summary}"
    )


def _priority_line(item: Item, cfg: Config, prefix: str) -> str:
    priority = item.priority
    rank = priority.get("rank", "?")
    score = priority.get("score", "?")
    return (
        f"{rank}. {status_cell(cfg, item.status)} {item_link(item, prefix)} "
        f"— score {score}: {priority.get('rationale', '')}"
    )


def _agent_work_line(work, item: Item, prefix: str) -> str:
    """Render exact checkpoint evidence; zero-total work never becomes fake 0%."""
    progress = (
        f"{work.completed}/{work.total} checkpoints"
        if work.total
        else "0/0 checkpoints (not estimated)"
    )
    checkpoint = f" · now: {work.checkpoint}" if work.checkpoint else ""
    return (
        f"- **{work.state}** {item_link(item, prefix)} — {work.agent}: "
        f"{work.task} · {progress}{checkpoint} · updated `{work.updated_at}`; "
        f"stale after `{work.stale_at}`"
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
    planned = [item for item in graph.items if _planned(item)]
    item_map = graph.item_map()
    all_deps = {item.id: item.deps for item in graph.items}

    # codex-sequence-2026-08-08: custom lifecycle roles prevent regression work
    # from impersonating active implementation simply because it is unfinished.
    in_progress = sorted(
        (item for item in planned
         if cfg.status_role(item.status) == "active"),
        key=lambda item: item.id,
    )
    regression = sorted(
        (item for item in planned if cfg.status_role(item.status) == "regression"),
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
            and cfg.status_role(item.status) == "ready"
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

    lines = ["# Dashboard — what to work on", ""]

    # codex-sequence-2026-08-08: project uptake follows persisted, explainable
    # target leverage rather than activity/popularity.
    recommended = priority_items(graph)
    if recommended:
        target_tier = graph.priority.get("target_tier", "configured targets")
        lines.extend([
            "## Recommended uptake",
            "",
            f"Target scope: `{target_tier}`. Scores use hard-dependency target "
            "reach, critical depth, lifecycle bias, and appetite cost.",
            "",
            *(_priority_line(item, cfg, prefix) for item in recommended),
            "",
        ])

    # codex-sequence-2026-08-08: agent activity is a lens, not lifecycle state.
    # Expiry is printed explicitly because Markdown cannot age itself in place.
    if graph.active_work:
        lines.extend([
            "## Agent work",
            "",
            "Live-work overlay. Progress is checkpoint evidence, not a guessed percent; "
            "entries stop pulsing in the constellation at their `stale after` time.",
            "",
            *(
                _agent_work_line(work, item_map[work.story_id], prefix)
                for work in graph.active_work
                if work.story_id in item_map
            ),
            "",
        ])

    active_milestone = next((
        milestone for milestone in graph.milestones
        if any(
            item_map.get(item_id) is not None
            and item_map[item_id].status not in done_statuses
            for phase in milestone.phases
            for item_id in phase.items
        )
    ), None)
    if active_milestone is not None:
        milestone_ids = [
            item_id
            for phase in active_milestone.phases
            for item_id in phase.items
            if item_id in item_map
        ]
        done_count = sum(
            item_map[item_id].status in done_statuses for item_id in milestone_ids
        )
        next_item = next((
            item_map[item_id]
            for item_id in milestone_ids
            if item_map[item_id].status not in done_statuses
            and item_id not in gates
            and all(
                item_map.get(dep) is None or item_map[dep].status in done_statuses
                for dep in item_map[item_id].deps
            )
        ), None)
        lines.extend([
            f"## Milestone: {active_milestone.title}",
            "",
            active_milestone.goal,
            "",
            f"Progress {bar(done_count, len(milestone_ids))} "
            f"{done_count}/{len(milestone_ids)}"
            + (f" · Next → {item_link(next_item, prefix)}" if next_item else ""),
            "",
        ])
        for phase in active_milestone.phases:
            phase_items = [item_map[item_id] for item_id in phase.items if item_id in item_map]
            phase_done = sum(item.status in done_statuses for item in phase_items)
            lines.extend([
                f"**{phase.name}** ({phase_done}/{len(phase_items)})",
                *(_item_line(item, cfg, prefix) for item in phase_items),
                "",
            ])

    lines.extend(["## In progress", ""])
    lines.extend(_item_line(item, cfg, prefix) for item in in_progress)
    if regression:
        lines.extend(["", "## Regression queue", ""])
        lines.extend(_item_line(item, cfg, prefix) for item in regression)
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
        # codex-sequence-2026-08-08: relation-only synthetic groups (for example
        # foundation roots) are structure, not zero-item delivery capabilities.
        if not group_items:
            continue
        done = sum(item.status in done_statuses for item in group_items)
        lines.append(f"{group.title} {bar(done, len(group_items))} {done}/{len(group_items)}")

    lines.append("")
    return {"dashboard.md": "\n".join(lines)}
