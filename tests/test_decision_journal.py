from pathlib import Path

import pytest

import vizzer.decision_journal as journal
from vizzer.decision_journal import (
    DecisionJournalError, append_application_event, append_evolution_events,
    decision_application_is_recorded, decision_application_marker,
    decision_is_journaled, decision_marker, render_application_event,
    render_evolution_event, restore_story_snapshots, story_snapshots,
)
from vizzer.model import (
    Graph, Item, OwnerDecision, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation, owner_question_fingerprint,
)


def _decision(*, option_id="shared", revision=1):
    question = OwnerQuestion(
        id="question:render-authority",
        story_id="story:canvas-core",
        owner="Ryder",
        prompt="Which rendering authority wins?",
        options=[
            OwnerQuestionOption("shared", "Shared evaluator", "One truth path."),
            OwnerQuestionOption("native", "Native path", "Deeper coupling."),
        ],
        recommendation=OwnerQuestionRecommendation(
            "shared", "It keeps every surface coherent."
        ),
        falsifier="A required surface cannot consume the shared result.",
        evidence=["spec/canvas-core.md", "src/render.py:12"],
    )
    return OwnerDecision(
        question=question,
        fingerprint=owner_question_fingerprint(question),
        revision=revision,
        answered_at="2026-08-10T18:30:00Z",
        answered_by="owner",
        kind="option",
        option_id=option_id,
    )


def _repo(tmp_path):
    story = tmp_path / "spec/canvas-core.md"
    story.parent.mkdir(parents=True)
    story.write_text("# Canvas core\n\nOriginal contract.\n", encoding="utf-8")
    graph = Graph(items=[Item(
        id="story:canvas-core", title="Canvas core",
        source={"adapter": "spec_tree", "path": "spec/canvas-core.md"},
    )])
    return graph, story


def test_evolution_event_preserves_question_options_rationale_and_falsifier():
    event = render_evolution_event(_decision(option_id="native"))

    assert "question:render-authority" in event
    assert "Which rendering authority wins?" in event
    assert "Shared evaluator" in event and "Native path" in event
    assert "It keeps every surface coherent." in event
    assert "selected `native` instead of" in event
    assert "A required surface cannot consume" in event
    assert "normative story/test integration pending" in event
    assert "src/render.py:12" in event


def test_append_evolution_event_touches_story_once_and_is_idempotent(tmp_path):
    graph, story = _repo(tmp_path)
    decision = _decision()
    original = story.read_bytes()

    assert append_evolution_events(graph, tmp_path, [decision]) == [story.resolve()]
    changed = story.read_text(encoding="utf-8")
    assert changed.startswith(original.decode("utf-8").rstrip("\n"))
    assert changed.count(decision_marker(decision)) == 1
    assert decision_is_journaled(graph, tmp_path, decision)

    assert append_evolution_events(graph, tmp_path, [decision]) == []
    assert story.read_text(encoding="utf-8") == changed


def test_application_event_is_explicit_idempotent_and_separate_from_acceptance(tmp_path):
    graph, story = _repo(tmp_path)
    decision = _decision()
    append_evolution_events(graph, tmp_path, [decision])

    assert not decision_application_is_recorded(graph, tmp_path, decision)
    assert append_application_event(
        graph,
        tmp_path,
        decision,
        applied_at="2026-08-10T19:00:00Z",
        summary="Routed export through the shared evaluator and strengthened acceptance.",
        evidence=["src/export.py", "tests/test_export.py"],
    ) == [story.resolve()]
    text = story.read_text(encoding="utf-8")
    assert decision_application_marker(decision) in text
    assert decision_application_marker(decision, end=True) in text
    assert "Routed export through the shared evaluator" in text
    assert "tests/test_export.py" in text
    assert decision_application_is_recorded(graph, tmp_path, decision)

    assert append_application_event(
        graph,
        tmp_path,
        decision,
        applied_at="2026-08-10T19:01:00Z",
        summary="This later duplicate must not replace the original.",
        evidence=[],
    ) == []
    assert story.read_text(encoding="utf-8") == text


def test_application_event_rejects_empty_summary_and_malformed_evidence():
    decision = _decision()
    with pytest.raises(DecisionJournalError, match="summary"):
        render_application_event(
            decision, applied_at="2026-08-10T19:00:00Z", summary=" ", evidence=[]
        )
    with pytest.raises(DecisionJournalError, match="evidence"):
        render_application_event(
            decision,
            applied_at="2026-08-10T19:00:00Z",
            summary="Applied.",
            evidence=["first\nsecond"],
        )


def test_batch_groups_multiple_answers_for_one_story(tmp_path):
    graph, story = _repo(tmp_path)
    first = _decision(revision=1)
    second = _decision(revision=2)
    second.question.id = "question:preview-authority"
    second.fingerprint = owner_question_fingerprint(second.question)

    assert append_evolution_events(graph, tmp_path, [first, second]) == [story.resolve()]
    text = story.read_text(encoding="utf-8")
    assert text.count("## Evolution event — owner decision") == 2
    assert "question:render-authority" in text
    assert "question:preview-authority" in text


def test_freeform_answer_records_explicit_recommendation_deviation():
    decision = _decision()
    decision.kind = "freeform"
    decision.option_id = None
    decision.text = "Use a versioned adapter and revisit after dogfood."

    event = render_evolution_event(decision)
    assert "Owner-authored alternative" in event
    assert decision.text in event
    assert "outside the authored option set" in event


def test_journal_rejects_missing_escape_and_symlink_sources(tmp_path):
    decision = _decision()
    for path in ("missing.md", "../outside.md"):
        graph = Graph(items=[Item(
            id="story:canvas-core", title="Canvas core",
            source={"path": path},
        )])
        with pytest.raises(DecisionJournalError):
            append_evolution_events(graph, tmp_path, [decision])

    outside = tmp_path / "real.md"
    outside.write_text("# Real\n", encoding="utf-8")
    link = tmp_path / "story.md"
    link.symlink_to(outside)
    graph = Graph(items=[Item(
        id="story:canvas-core", title="Canvas core",
        source={"path": "story.md"},
    )])
    with pytest.raises(DecisionJournalError, match="symlink"):
        append_evolution_events(graph, tmp_path, [decision])


def test_multi_story_write_failure_restores_every_story(tmp_path, monkeypatch):
    graph, first_story = _repo(tmp_path)
    second_story = tmp_path / "spec/other.md"
    second_story.write_text("# Other\n", encoding="utf-8")
    graph.items.append(Item(
        id="story:other", title="Other",
        source={"path": "spec/other.md"},
    ))
    first = _decision()
    second = _decision(revision=2)
    second.question.id = "question:other"
    second.question.story_id = "story:other"
    second.fingerprint = owner_question_fingerprint(second.question)
    before = story_snapshots(graph, tmp_path, [first, second])
    real_write = journal._atomic_write
    calls = 0

    def fail_second(path: Path, data: bytes):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        real_write(path, data)

    monkeypatch.setattr(journal, "_atomic_write", fail_second)
    with pytest.raises(OSError, match="disk full"):
        append_evolution_events(graph, tmp_path, [first, second])
    monkeypatch.setattr(journal, "_atomic_write", real_write)

    restore_story_snapshots(before)
    assert first_story.read_bytes() == before[first_story.resolve()]
    assert second_story.read_bytes() == before[second_story.resolve()]
