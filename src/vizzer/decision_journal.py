"""Append accepted owner decisions to their source stories as evolution events.

The answer ledger is the immutable decision receipt.  A story is the evolving
task record humans and agents actually read, so an accepted answer is also
journaled there immediately.  Journaling is append-only and deliberately does
not rewrite normative clauses: a later implementation pass records how the
decision changed scope, acceptance, dependencies, or code.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

from .model import Graph, OwnerDecision


class DecisionJournalError(ValueError):
    """A decision cannot be safely journaled into its source story."""


def decision_marker(decision: OwnerDecision) -> str:
    """Stable marker for one exact answer revision and question fingerprint."""
    return (
        f"<!-- vizzer:evolution-answer:{decision.fingerprint}:"
        f"r{decision.revision}:begin -->"
    )


def _end_marker(decision: OwnerDecision) -> str:
    return (
        f"<!-- vizzer:evolution-answer:{decision.fingerprint}:"
        f"r{decision.revision}:end -->"
    )


def decision_application_marker(
    decision: OwnerDecision, *, end: bool = False,
) -> str:
    """Stable boundary for the follow-through that applies an accepted answer."""
    boundary = "end" if end else "begin"
    return (
        f"<!-- vizzer:evolution-application:{decision.fingerprint}:"
        f"r{decision.revision}:{boundary} -->"
    )


def _story_path(graph: Graph, root: Path, decision: OwnerDecision) -> Path:
    item = graph.item_map().get(decision.question.story_id)
    if item is None:
        raise DecisionJournalError(
            f"decision {decision.question.id} references an unknown story"
        )
    raw = item.source.get("path")
    if not isinstance(raw, str) or not raw:
        raise DecisionJournalError(
            f"story {item.id} has no writable source path"
        )
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise DecisionJournalError(
            f"story {item.id} source path must stay inside the project"
        )
    project_root = root.resolve()
    lexical = project_root / relative
    if lexical.is_symlink():
        raise DecisionJournalError(
            f"story {item.id} source must be a regular file, not a symlink"
        )
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(project_root)
    except (OSError, ValueError):
        raise DecisionJournalError(
            f"story {item.id} source is missing or outside the project"
        ) from None
    if not resolved.is_file() or resolved.suffix.lower() != ".md":
        raise DecisionJournalError(
            f"story {item.id} source must be an existing Markdown file"
        )
    return resolved


def _selected_answer(decision: OwnerDecision) -> tuple[str, str]:
    question = decision.question
    if decision.kind == "freeform":
        return "Owner-authored alternative", decision.text or ""
    option = next(
        (value for value in question.options if value.id == decision.option_id),
        None,
    )
    if option is None:  # Model validation should make this unreachable.
        raise DecisionJournalError(
            f"decision {question.id} selects an unknown option"
        )
    return f"{option.label} (`{option.id}`)", option.tradeoff


def _recommendation_deviation(decision: OwnerDecision) -> str:
    recommendation = decision.question.recommendation.option_id
    if decision.kind == "freeform":
        return (
            "Owner supplied a direction outside the authored option set; the "
            f"recorded recommendation was `{recommendation}`."
        )
    if decision.option_id == recommendation:
        return "None at decision capture; owner accepted the recorded recommendation."
    return (
        f"Owner selected `{decision.option_id}` instead of the recorded "
        f"recommendation `{recommendation}`."
    )


def render_evolution_event(decision: OwnerDecision) -> str:
    """Human- and LLM-readable append-only story event."""
    question = decision.question
    selected, selected_detail = _selected_answer(decision)
    options = "\n".join(
        f"- **{option.label}** (`{option.id}`) — {option.tradeoff}"
        for option in question.options
    )
    evidence = "\n".join(f"- `{value}`" for value in question.evidence)
    return "\n".join([
        decision_marker(decision),
        f"## Evolution event — owner decision {decision.answered_at[:10]}",
        "",
        f"- **Question ID:** `{question.id}`",
        f"- **Answer ledger revision:** `{decision.revision}`",
        f"- **Question fingerprint:** `{decision.fingerprint}`",
        f"- **Accepted by:** {decision.answered_by} at `{decision.answered_at}`",
        "- **Application state:** accepted; normative story/test integration pending",
        "",
        "### Question",
        "",
        question.prompt,
        "",
        "### Options considered",
        "",
        options,
        "",
        "### Recommendation at decision time",
        "",
        f"**{question.recommendation.option_id}** — "
        f"{question.recommendation.rationale}",
        "",
        "### Owner answer",
        "",
        f"**{selected}** — {selected_detail}",
        "",
        "### Deviation from recommendation",
        "",
        _recommendation_deviation(decision),
        "",
        "### Falsifier retained for later review",
        "",
        question.falsifier,
        "",
        "### Evidence available when asked",
        "",
        evidence or "- None recorded.",
        "",
        "This event records why the task evolved. It does not silently rewrite "
        "earlier requirements; the implementation pass must append how scope, "
        "acceptance, dependencies, or follow-up stories changed.",
        _end_marker(decision),
    ])


def render_application_event(
    decision: OwnerDecision,
    *,
    applied_at: str,
    summary: str,
    evidence: list[str],
) -> str:
    """Render the explicit follow-through without rewriting the accepted receipt."""
    summary = summary.strip()
    if not summary or len(summary) > 4000:
        raise DecisionJournalError(
            "decision application summary must contain 1..4000 characters"
        )
    if len(evidence) > 32 or any(
        not isinstance(value, str) or not value.strip()
        or len(value) > 1000 or "\n" in value or "\r" in value
        for value in evidence
    ):
        raise DecisionJournalError(
            "decision application evidence must contain at most 32 bounded lines"
        )
    evidence_lines = [f"- `{value.strip()}`" for value in evidence]
    return "\n".join([
        decision_application_marker(decision),
        f"## Decision application — {decision.question.id}",
        "",
        f"- **Applied at:** `{applied_at}`",
        f"- **Answer ledger revision:** `{decision.revision}`",
        f"- **Question fingerprint:** `{decision.fingerprint}`",
        "- **Application state:** applied to the evolving story/acceptance record",
        "",
        "### Applied outcome",
        "",
        summary,
        "",
        "### Application evidence",
        "",
        *(evidence_lines or ["- None recorded."]),
        "",
        "This event records follow-through on the accepted answer. Delivery and "
        "lifecycle still require their own named acceptance evidence.",
        decision_application_marker(decision, end=True),
    ])


def decision_is_journaled(
    graph: Graph, root: Path, decision: OwnerDecision,
) -> bool:
    try:
        path = _story_path(graph, root, decision)
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, DecisionJournalError):
        return False
    return decision_marker(decision) in text and _end_marker(decision) in text


def decision_application_is_recorded(
    graph: Graph, root: Path, decision: OwnerDecision,
) -> bool:
    try:
        path = _story_path(graph, root, decision)
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, DecisionJournalError):
        return False
    return (
        decision_application_marker(decision) in text
        and decision_application_marker(decision, end=True) in text
    )


def story_snapshots(
    graph: Graph, root: Path, decisions: list[OwnerDecision],
) -> dict[Path, bytes]:
    snapshots = {}
    for decision in decisions:
        path = _story_path(graph, root, decision)
        if path not in snapshots:
            snapshots[path] = path.read_bytes()
    return snapshots


def _atomic_write(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def restore_story_snapshots(snapshots: dict[Path, bytes]) -> None:
    for path, data in snapshots.items():
        _atomic_write(path, data)


def append_evolution_events(
    graph: Graph, root: Path, decisions: list[OwnerDecision],
) -> list[Path]:
    """Append missing events transactionally and return changed story paths."""
    snapshots = story_snapshots(graph, root, decisions)
    additions: dict[Path, list[str]] = {}
    for decision in decisions:
        path = _story_path(graph, root, decision)
        text = snapshots[path].decode("utf-8")
        marker = decision_marker(decision)
        if marker in text or any(marker in value for value in additions.get(path, [])):
            continue
        additions.setdefault(path, []).append(render_evolution_event(decision))

    changed = []
    try:
        for path, events in additions.items():
            original = snapshots[path].decode("utf-8")
            body = original.rstrip("\n") + "\n\n" + "\n\n".join(events) + "\n"
            _atomic_write(path, body.encode("utf-8"))
            changed.append(path)
    except BaseException:
        restore_story_snapshots({path: snapshots[path] for path in changed})
        raise
    return changed


def append_application_event(
    graph: Graph,
    root: Path,
    decision: OwnerDecision,
    *,
    applied_at: str,
    summary: str,
    evidence: list[str],
) -> list[Path]:
    """Append one exact application event atomically and idempotently."""
    path = _story_path(graph, root, decision)
    original = path.read_bytes()
    text = original.decode("utf-8")
    begin = decision_application_marker(decision)
    end = decision_application_marker(decision, end=True)
    if begin in text and end in text:
        return []
    if begin in text or end in text:
        raise DecisionJournalError(
            f"decision {decision.question.id} has an incomplete application event"
        )
    event = render_application_event(
        decision, applied_at=applied_at, summary=summary, evidence=evidence,
    )
    body = text.rstrip("\n") + "\n\n" + event + "\n"
    _atomic_write(path, body.encode("utf-8"))
    return [path]
