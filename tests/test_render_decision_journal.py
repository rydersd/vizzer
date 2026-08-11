from vizzer.config import Config, DEFAULTS
from vizzer.decision_journal import append_application_event, append_evolution_events
from vizzer.model import (
    Graph, Item, OwnerDecision, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation, owner_question_fingerprint,
)
from vizzer.render import render_all


def _question(question_id="question:route"):
    return OwnerQuestion(
        id=question_id,
        story_id="story:a",
        owner="Ryder",
        prompt="Which route wins?",
        options=[
            OwnerQuestionOption("shared", "Shared", "Portable."),
            OwnerQuestionOption("native", "Native", "Coupled."),
        ],
        recommendation=OwnerQuestionRecommendation("shared", "One truth path."),
        falsifier="A required surface cannot consume it.",
        evidence=["spec/a.md"],
    )


def _graph(tmp_path):
    story = tmp_path / "spec/a.md"
    story.parent.mkdir(parents=True)
    story.write_text("# A\n", encoding="utf-8")
    question = _question()
    decision = OwnerDecision(
        question=question,
        fingerprint=owner_question_fingerprint(question),
        revision=1,
        answered_at="2026-08-10T18:30:00Z",
        answered_by="owner",
        kind="option",
        option_id="native",
    )
    graph = Graph(
        items=[Item(id="story:a", title="A", source={"path": "spec/a.md"})],
        owner_questions=[_question("question:open")],
        owner_decisions=[decision],
    )
    return graph, decision


def test_decision_journal_is_complete_and_marks_missing_story_event(tmp_path):
    graph, _decision = _graph(tmp_path)
    output = render_all(
        graph, Config(data=DEFAULTS), tmp_path, only={"decision_journal"}
    )["decision-journal.md"]

    assert "# Owner decision journal" in output
    assert "question:route" in output and "question:open" in output
    assert "Native (`native`)" in output
    assert "One truth path." in output
    assert "Owner answer differs" in output
    assert "MISSING FROM SOURCE STORY" in output
    assert "Normative application:** pending" in output


def test_decision_journal_marks_answer_recorded_after_append(tmp_path):
    graph, decision = _graph(tmp_path)
    append_evolution_events(graph, tmp_path, [decision])

    output = render_all(
        graph, Config(data=DEFAULTS), tmp_path, only={"decision_journal"}
    )["decision-journal.md"]
    assert "Evolution journal:** recorded in source story" in output
    assert "Normative application:** pending" in output
    assert "MISSING FROM SOURCE STORY" not in output


def test_decision_journal_marks_normative_follow_through_applied(tmp_path):
    graph, decision = _graph(tmp_path)
    append_evolution_events(graph, tmp_path, [decision])
    append_application_event(
        graph,
        tmp_path,
        decision,
        applied_at="2026-08-10T19:00:00Z",
        summary="Updated the shared route and its named acceptance.",
        evidence=["src/shared.py", "tests/test_shared.py"],
    )

    output = render_all(
        graph, Config(data=DEFAULTS), tmp_path, only={"decision_journal"}
    )["decision-journal.md"]
    assert "Normative application:** applied — follow-through recorded" in output
    assert "Normative application:** pending" not in output
