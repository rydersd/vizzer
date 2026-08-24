"""Read-only rollup of records that genuinely await owner attention."""
from __future__ import annotations

import re
from pathlib import Path

from ..config import Config
from ..decision_journal import decision_application_is_recorded
from ..discussion_queue import PROVIDERS, read_discussion_queue
from ..model import Graph
from .common import item_link, source_link_prefix
from .perspective_common import (
    age_text, git_introduced, git_metadata, safe_source_text, snapshot_time,
)


AMENDMENT_MARKER = re.compile(
    r"(?:AMENDMENT\s+PROPOSED.{0,80}(?:NOT\s+YET\s+RULED|pending)|"
    r"amendment\s+proposal\s+pending\s+owner|PENDING\s+OWNER\s+RATIFICATION|"
    r"pending\s+owner\s+ruling|awaiting\s+owner\s+ruling)",
    re.IGNORECASE,
)


def _clean(value: object, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit].replace("|", "\\|")


def _recommendation(question) -> str:
    return (
        f"`{question.recommendation.option_id}` — "
        f"{_clean(question.recommendation.rationale)}"
    )


def _amendments(graph: Graph, root: Path) -> list[tuple]:
    metadata = git_metadata(str(root.resolve()))
    questions = {question.story_id: question for question in graph.owner_questions}
    applied = {
        decision.question.story_id for decision in graph.owner_decisions
        if decision_application_is_recorded(graph, root, decision)
    }
    rows = []
    for item in graph.items:
        if item.id in applied:
            continue
        path = item.source.get("path")
        match = AMENDMENT_MARKER.search(safe_source_text(root, path))
        if match:
            rows.append((metadata.modified(path), item, _clean(match.group(0)), questions.get(item.id)))
    return sorted(rows, key=lambda row: (row[0] is None, row[0] or "", row[1].id))


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    if not cfg.get("perspectives.enabled", False):
        return {}
    anchor = snapshot_time(graph)
    prefix = source_link_prefix(cfg, root)
    item_map = graph.item_map()
    activity_path = str(cfg.get("activity.path", ""))
    queue_path = str(cfg.get("discussions.queue_path", ""))
    lines = [
        "# Awaiting owner", "",
        "Read-only. This view joins explicit open questions, narrowly marked "
        "pending amendments, queued discussions, and accepted decisions lacking "
        "an application event.", "",
        "## Explicit questions", "",
        "| Age | Question / item | Recommendation |", "|---:|---|---|",
    ]
    questions = [
        (git_introduced(str(root.resolve()), activity_path, question.id), question)
        for question in graph.owner_questions
    ]
    for introduced, question in sorted(
        questions, key=lambda row: (row[0] is None, row[0] or "", row[1].id)
    ):
        item = item_map.get(question.story_id)
        target = item_link(item, prefix) if item else f"`{question.story_id}`"
        lines.append(
            f"| {age_text(introduced, anchor)} | `{question.id}` · {target} — "
            f"{_clean(question.prompt)} | {_recommendation(question)} |"
        )
    if not questions:
        lines.append("| — | No explicit open questions | — |")

    lines.extend([
        "", "## Pending amendments", "",
        "| Age | Item | Marker | Recommendation |", "|---:|---|---|---|",
    ])
    amendments = _amendments(graph, root)
    for modified, item, marker, question in amendments:
        lines.append(
            f"| {age_text(modified, anchor, lower_bound=True)} | "
            f"{item_link(item, prefix)} | {marker} | "
            f"{_recommendation(question) if question else '—'} |"
        )
    if not amendments:
        lines.append("| — | No unresolved amendment markers | — | — |")

    queue, warnings = read_discussion_queue(cfg, root, graph, strict=False)
    lines.extend([
        "", "## Discussion queue", "",
        "| Provider | Item | Recommendation |", "|---|---|---|",
    ])
    queued = []
    if queue:
        by_story = {question.story_id: question for question in graph.owner_questions}
        for provider in PROVIDERS:
            for story_id in queue.get("queues", {}).get(provider, []):
                queued.append((provider, story_id, by_story.get(story_id)))
    for provider, story_id, question in queued:
        item = item_map.get(story_id)
        target = item_link(item, prefix) if item else f"`{story_id}`"
        lines.append(
            f"| {provider.title()} | {target} | "
            f"{_recommendation(question) if question else '—'} |"
        )
    if not queued:
        note = _clean("; ".join(warnings)) if warnings else f"No items queued in `{queue_path}`"
        lines.append(f"| — | {note} | — |")

    lines.extend([
        "", "## Accepted decisions awaiting application", "",
        "| Age | Decision / item | Accepted answer |", "|---:|---|---|",
    ])
    pending = [
        decision for decision in graph.owner_decisions
        if not decision_application_is_recorded(graph, root, decision)
    ]
    for decision in sorted(pending, key=lambda value: (value.answered_at, value.question.id)):
        question = decision.question
        item = item_map.get(question.story_id)
        target = item_link(item, prefix) if item else f"`{question.story_id}`"
        answer = decision.option_id if decision.kind == "option" else decision.text
        lines.append(
            f"| {age_text(decision.answered_at, anchor)} | `{question.id}` · "
            f"{target} | `{_clean(answer)}` |"
        )
    if not pending:
        lines.append("| — | No accepted decisions await application | — |")
    lines.append("")
    return {"awaiting-owner.md": "\n".join(lines)}
