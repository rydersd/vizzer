"""Action-oriented dashboard renderer."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..decision_journal import (
    decision_application_is_recorded, decision_is_journaled,
)
from ..model import Graph, Group, Item
from .common import bar, item_link, priority_items, source_link_prefix, status_cell, topo


def _assessment_text(value: object, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())[:limit].replace("`", "'")
    for marker in ("\\", "*", "_", "[", "]", "<", ">"):
        text = text.replace(marker, "\\" + marker)
    return text


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


def _assessment_line(item: Item, assessment: dict, cfg: Config, prefix: str) -> str:
    if not isinstance(assessment, dict):
        assessment = {}
    size = assessment.get("size", {})
    impact = assessment.get("impact", {})
    parallel = assessment.get("parallelism", {})
    size = size if isinstance(size, dict) else {}
    impact = impact if isinstance(impact, dict) else {}
    parallel = parallel if isinstance(parallel, dict) else {}
    plausible = size.get("plausible_range", {})
    plausible = plausible if isinstance(plausible, dict) else {}
    band = size.get("assessed_band")
    band = band if band in {"XS", "S", "M", "L", "XL"} else "unassessed"
    uncertainty = size.get("uncertainty")
    uncertainty = uncertainty if uncertainty in {"U0", "U1", "U2", "U3"} else "U3"
    provenance = size.get("provenance")
    provenance = provenance if provenance in {
        "observed", "authored", "inferred", "unknown",
    } else "unknown"
    range_min = plausible.get("min")
    range_max = plausible.get("max")
    range_min = range_min if range_min in {"XS", "S", "M", "L", "XL"} else "?"
    range_max = range_max if range_max in {"XS", "S", "M", "L", "XL"} else "?"
    range_text = f"{range_min}–{range_max}"
    raw = size.get("raw_authored_appetite")
    raw = _assessment_text(raw, 120) or "—"
    target_reach = impact.get("structural_target_reach")
    immediate = impact.get("immediate_unlock")
    target_reach = target_reach if isinstance(target_reach, int) \
        and not isinstance(target_reach, bool) and target_reach >= 0 else 0
    immediate = immediate if isinstance(immediate, int) \
        and not isinstance(immediate, bool) and immediate >= 0 else 0
    parallel_class = parallel.get("classification")
    parallel_class = parallel_class if parallel_class in {
        "candidate", "serial", "unknown",
    } else "unknown"
    return (
        f"- {status_cell(cfg, item.status)} {item_link(item, prefix)} — "
        f"**{band} · {uncertainty} · {provenance}** "
        f"(raw `{raw}`; plausible {range_text}) · "
        f"{target_reach} target(s), {immediate} immediate unlock(s) · "
        f"parallel: {parallel_class}"
    )


def _occupied_assessment_line(
    item: Item, assessment: dict, work_entries: list, cfg: Config, prefix: str,
) -> str:
    base = _assessment_line(item, assessment, cfg, prefix)
    ownership = "; ".join(
        f"{work.agent}: {work.state} — {work.task}" for work in work_entries
    )
    return f"{base} · current work: {ownership}"


def _defect_line(item: Item, cfg: Config, prefix: str) -> str:
    defect = item.priority["defect"]
    components = defect["components"]
    lineage = (
        "linked contract"
        if defect["lineage"] == "bug-against"
        else "story-only estimate; missing `Bug against`"
    )
    return (
        f"{defect['rank']}. {status_cell(cfg, item.status)} "
        f"{item_link(item, prefix)} — "
        f"{components['target_impact']} V1 target(s), "
        f"{components['incomplete_dependents']} incomplete downstream, "
        f"{components['total_dependents']} total downstream · {lineage}"
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


def _owner_question_line(question, item: Item, prefix: str) -> str:
    options = "; ".join(
        f"{option.label}: {option.tradeoff}" for option in question.options
    )
    recommended = next(
        option.label for option in question.options
        if option.id == question.recommendation.option_id
    )
    return (
        f"- **question** {item_link(item, prefix)} — {question.owner}: "
        f"{question.prompt} · options: {options} · recommended: {recommended} — "
        f"{question.recommendation.rationale} · falsifier: {question.falsifier}"
    )


def _owner_decision_line(
    decision, item: Item, prefix: str, graph: Graph, root: Path,
) -> str:
    question = decision.question
    if decision.kind == "option":
        chosen = next(
            option.label for option in question.options
            if option.id == decision.option_id
        )
        answer = f"selected **{chosen}** (`{decision.option_id}`)"
    else:
        answer = f"answered: {decision.text}"
    if not decision_is_journaled(graph, root, decision):
        journal = "**STORY JOURNAL MISSING**"
    elif decision_application_is_recorded(graph, root, decision):
        journal = "story evolution recorded; normative application applied"
    else:
        journal = "story evolution recorded; normative application pending"
    deviation = (
        "recommendation accepted"
        if decision.kind == "option"
        and decision.option_id == question.recommendation.option_id
        else "owner answer deviates from the recorded recommendation"
    )
    return (
        f"- **accepted · {journal}** {item_link(item, prefix)} — "
        f"{question.prompt} · "
        f"{answer} · by {decision.answered_by} at `{decision.answered_at}` "
        f"(revision {decision.revision}) · {deviation}"
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
    regression = [
        item for item in planned if cfg.status_role(item.status) == "regression"
    ]
    bug_gaps = [item for item in regression if item.status == "bug-gap"]
    scored_bug_gaps = sorted(
        (item for item in bug_gaps
         if item.priority.get("defect", {}).get("rank") is not None),
        key=lambda item: (item.priority["defect"]["rank"], item.id),
    )
    v1_impact_bug_gaps = [
        item for item in scored_bug_gaps
        if item.priority["defect"]["components"]["target_impact"] > 0
    ]
    known_graph_bug_gaps = [
        item for item in scored_bug_gaps
        if item.priority["defect"]["components"]["target_impact"] == 0
    ]
    unscored_bug_gaps = sorted(
        (item for item in bug_gaps if "defect" not in item.priority),
        key=lambda item: item.id,
    )
    integration_regressions = sorted(
        (item for item in regression if item.status != "bug-gap"),
        key=lambda item: (
            item.priority.get("rank") is None,
            item.priority.get("rank") if item.priority.get("rank") is not None else 10 ** 9,
            item.id,
        ),
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

    assessment_items = graph.assessment.get("items", {})
    portfolio = graph.assessment.get("portfolio", {})
    if graph.assessment and isinstance(assessment_items, dict) \
            and isinstance(portfolio, dict):
        lines.extend([
            "## Provisional assessed portfolio",
            "",
            "Deterministic, model-neutral guidance. Delivery size, structural "
            "impact, uncertainty, and parallel safety remain separate claims; "
            "there is no universal AI speed multiplier or magic combined score.",
            "",
        ])
        for key, title in (
            ("small", "High structural-leverage small candidates"),
            ("anchors", "Provisional strategic anchors"),
            ("defects", "Defect burn-down"),
            ("questions", "Decision/research lanes"),
        ):
            item_ids = portfolio.get(key, [])
            if not isinstance(item_ids, list) or not item_ids:
                continue
            item_ids = [item_id for item_id in item_ids if isinstance(item_id, str)]
            lines.extend([
                f"### {title}",
                "",
                *(
                    _assessment_line(item_map[item_id], assessment_items[item_id], cfg, prefix)
                    for item_id in item_ids
                    if item_id in item_map and item_id in assessment_items
                ),
                "",
            ])
        occupied_ids = portfolio.get("occupied", [])
        work_by_story = {}
        for work in graph.active_work:
            work_by_story.setdefault(work.story_id, []).append(work)
        if isinstance(occupied_ids, list) and occupied_ids:
            lines.extend([
                "### Freshly owned work",
                "",
                "Visible for coordination, excluded from new-dispatch lanes.",
                "",
                *(
                    _occupied_assessment_line(
                        item_map[item_id], assessment_items[item_id],
                        work_by_story.get(item_id, []), cfg, prefix,
                    )
                    for item_id in occupied_ids
                    if item_id in item_map and item_id in assessment_items
                ),
                "",
            ])
        blocked_ids = portfolio.get("blocked", [])
        if isinstance(blocked_ids, list) and blocked_ids:
            lines.extend([
                "### Unresolved stale blockers",
                "",
                "Ownership has expired, but the recorded blocker has not been "
                "resolved. These remain outside delivery lanes until a newer "
                "record or owner decision clears them.",
                "",
                *(
                    _occupied_assessment_line(
                        item_map[item_id], assessment_items[item_id],
                        work_by_story.get(item_id, []), cfg, prefix,
                    )
                    for item_id in blocked_ids
                    if item_id in item_map and item_id in assessment_items
                ),
                "",
            ])
        stale_work_ids = portfolio.get("stale_work", [])
        if isinstance(stale_work_ids, list) and stale_work_ids:
            lines.extend([
                f"{len(stale_work_ids)} stale active/blocked/paused work record(s) "
                "remain as context but do not reserve a dispatch lane.",
                "",
            ])
        warnings = portfolio.get("warnings", [])
        if isinstance(warnings, list) and warnings:
            lines.extend([
                "### Assessment cautions",
                "",
                *(f"- {_assessment_text(warning)}"
                  for warning in warnings if isinstance(warning, str)),
                "",
            ])
        unknown_ids = portfolio.get("unknown_size", [])
        if isinstance(unknown_ids, list) and unknown_ids:
            lines.extend([
                f"{len(unknown_ids)} otherwise eligible item(s) remain unsized; "
                "they are excluded from small/anchor lanes rather than silently "
                "receiving a default.",
                "",
            ])

    if graph.owner_questions:
        lines.extend([
            "## Open owner questions",
            "",
            "Explicit researched decisions only; operational blockers do not receive "
            "a question badge.",
            "",
            *(
                _owner_question_line(question, item_map[question.story_id], prefix)
                for question in graph.owner_questions
                if question.story_id in item_map
            ),
            "",
        ])

    if graph.owner_decisions:
        lines.extend([
            "## Accepted owner decisions",
            "",
            "Model-neutral repo authority. These are accepted answers, not still-open "
            "questions or operational blockers.",
            "",
            *(
                _owner_decision_line(
                    decision, item_map[decision.question.story_id], prefix,
                    graph, root,
                )
                for decision in graph.owner_decisions
                if decision.question.story_id in item_map
            ),
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
        if v1_impact_bug_gaps:
            lines.extend([
                "### V1-impact bug gaps",
                "",
                "Sorted by known hard-dependency blast radius, not guessed severity.",
                "",
            ])
            lines.extend(_defect_line(item, cfg, prefix) for item in v1_impact_bug_gaps)
            lines.append("")
        if known_graph_bug_gaps:
            lines.extend([
                "### Remaining bug gaps by known graph reach",
                "",
                "No current V1 target is downstream. Ranking still uses known dependency "
                "fan-out; story-only estimates explicitly flag missing defect lineage.",
                "",
            ])
            lines.extend(_defect_line(item, cfg, prefix) for item in known_graph_bug_gaps)
            lines.append("")
        if unscored_bug_gaps:
            lines.extend([
                "### Unscored bug gaps",
                "",
                "Priority metadata is missing; run `vizzer refresh` before relying on this view.",
                "",
            ])
            lines.extend(_item_line(item, cfg, prefix) for item in unscored_bug_gaps)
            lines.append("")
        if integration_regressions:
            lines.extend(["### In-flight integration", ""])
            lines.extend(
                _priority_line(item, cfg, prefix)
                if item.priority.get("rank") is not None
                else _item_line(item, cfg, prefix)
                for item in integration_regressions
            )
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
