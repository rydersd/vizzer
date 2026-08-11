"""LLM-readable export of open questions and accepted owner decisions."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..decision_journal import (
    decision_application_is_recorded, decision_is_journaled,
)
from ..model import Graph
from .common import item_link, source_link_prefix


def _question_block(question, item, prefix: str) -> list[str]:
    options = [
        f"- **{option.label}** (`{option.id}`) — {option.tradeoff}"
        for option in question.options
    ]
    return [
        f"### {question.id}",
        "",
        f"- **Story:** {item_link(item, prefix)} (`{question.story_id}`)",
        f"- **Owner:** {question.owner}",
        f"- **State:** open — answer required",
        "",
        question.prompt,
        "",
        "Options:",
        "",
        *options,
        "",
        f"**Recommendation:** `{question.recommendation.option_id}` — "
        f"{question.recommendation.rationale}",
        "",
        f"**Falsifier:** {question.falsifier}",
        "",
        "Evidence:",
        "",
        *(f"- `{value}`" for value in question.evidence),
        "",
    ]


def _decision_block(decision, item, prefix: str, graph: Graph, root: Path) -> list[str]:
    question = decision.question
    selected = decision.text
    selected_label = "Owner-authored alternative"
    if decision.kind == "option":
        option = next(value for value in question.options
                      if value.id == decision.option_id)
        selected = option.tradeoff
        selected_label = f"{option.label} (`{option.id}`)"
    recommendation_accepted = (
        decision.kind == "option"
        and decision.option_id == question.recommendation.option_id
    )
    deviation = (
        "None; owner accepted the recorded recommendation."
        if recommendation_accepted
        else "Owner answer differs from the recorded recommendation; retain both."
    )
    journal = (
        "recorded in source story"
        if decision_is_journaled(graph, root, decision)
        else "MISSING FROM SOURCE STORY"
    )
    application = (
        "applied — follow-through recorded in source story"
        if decision_application_is_recorded(graph, root, decision)
        else "pending until the story records the resulting "
             "scope/acceptance/dependency changes"
    )
    return [
        f"### {question.id}",
        "",
        f"- **Story:** {item_link(item, prefix)} (`{question.story_id}`)",
        f"- **Answer revision:** `{decision.revision}`",
        f"- **Fingerprint:** `{decision.fingerprint}`",
        f"- **Accepted:** {decision.answered_by} at `{decision.answered_at}`",
        f"- **Evolution journal:** {journal}",
        f"- **Normative application:** {application}",
        "",
        f"**Question:** {question.prompt}",
        "",
        f"**Owner answer:** {selected_label} — {selected}",
        "",
        f"**Recommendation at decision time:** "
        f"`{question.recommendation.option_id}` — "
        f"{question.recommendation.rationale}",
        "",
        f"**Deviation:** {deviation}",
        "",
        f"**Falsifier retained:** {question.falsifier}",
        "",
    ]


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    prefix = source_link_prefix(cfg, root)
    items = graph.item_map()
    lines = [
        "# Owner decision journal",
        "",
        "Generated, LLM-readable index. The answer ledger and source stories are "
        "authoritative; do not edit this export.",
        "",
        "Accepted answers are appended to their stories as evolution events. "
        "That preserves the question, alternatives, recommendation, owner choice, "
        "deviation, falsifier, and evidence. It does not pretend the normative "
        "acceptance clauses were already updated.",
        "",
        "## Accepted decisions",
        "",
    ]
    if graph.owner_decisions:
        for decision in sorted(
            graph.owner_decisions,
            key=lambda value: (value.answered_at, value.revision, value.question.id),
            reverse=True,
        ):
            item = items.get(decision.question.story_id)
            if item is not None:
                lines.extend(_decision_block(decision, item, prefix, graph, root))
    else:
        lines.extend(["No accepted owner decisions.", ""])

    lines.extend(["## Open questions", ""])
    if graph.owner_questions:
        for question in sorted(graph.owner_questions, key=lambda value: value.id):
            item = items.get(question.story_id)
            if item is not None:
                lines.extend(_question_block(question, item, prefix))
    else:
        lines.extend(["No open owner questions.", ""])
    return {"decision-journal.md": "\n".join(lines).rstrip() + "\n"}
