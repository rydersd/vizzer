import json

import pytest

from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import (
    Graph, Item, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation, owner_question_fingerprint,
)
from vizzer.question_answers import (
    QuestionAnswerConflict, QuestionAnswerError, append_answer, append_answers,
    read_answers, reconcile_answers,
)


def _cfg(path="vizzer/question-answers.json"):
    return Config(data=deep_merge(DEFAULTS, {"questions": {"answers_path": path}}))


def _question(prompt="Which route wins?", question_id="question:route"):
    return OwnerQuestion(
        id=question_id,
        story_id="story:a",
        owner="Ryder",
        prompt=prompt,
        options=[
            OwnerQuestionOption("shared", "Shared", "One portable contract."),
            OwnerQuestionOption("native", "Native", "Deeper vendor coupling."),
        ],
        recommendation=OwnerQuestionRecommendation(
            "shared", "It keeps the protocol model-neutral."
        ),
        falsifier="A required provider cannot express the shared contract.",
        evidence=["docs/architecture.md:12"],
    )


def _graph(question=None):
    questions = [] if question is None else [question]
    return Graph(items=[Item(id="story:a", title="A")], owner_questions=questions)


def test_answer_ledger_snapshots_question_and_reconciles_decision(tmp_path):
    question = _question()
    graph = _graph(question)

    ledger, decision = append_answer(
        graph, _cfg(), tmp_path, question.id,
        expected_revision=0,
        expected_fingerprint=owner_question_fingerprint(question),
        kind="option", option_id="shared",
    )

    assert ledger["revision"] == 1
    event = ledger["answers"][0]
    assert event["question"]["prompt"] == question.prompt
    assert event["question"]["options"][0]["id"] == "shared"
    assert event["fingerprint"] == owner_question_fingerprint(question)
    assert decision.question == question
    assert decision.option_id == "shared"

    rebuilt = _graph(_question())
    assert reconcile_answers(rebuilt, _cfg(), tmp_path) == [
        "accepted decision question:route revision 1 is not journaled in its "
        "source story"
    ]
    assert rebuilt.owner_questions == []
    assert len(rebuilt.owner_decisions) == 1
    assert rebuilt.owner_decisions[0].question.prompt == question.prompt
    assert rebuilt.owner_decisions[0].revision == 1

    # The derived graph round trip preserves decisions independently of opens.
    round_tripped = Graph.from_dict(json.loads(rebuilt.dumps()))
    assert round_tripped.owner_questions == []
    assert round_tripped.owner_decisions == rebuilt.owner_decisions


def test_batch_answers_are_one_validated_atomic_ledger_write(tmp_path):
    first = _question(question_id="question:first")
    second = _question(question_id="question:second")
    graph = Graph(
        items=[Item(id="story:a", title="A")],
        owner_questions=[first, second],
    )
    payload = [
        {"questionId": first.id,
         "expectedFingerprint": owner_question_fingerprint(first),
         "kind": "option", "optionId": "shared", "text": None},
        {"questionId": second.id,
         "expectedFingerprint": owner_question_fingerprint(second),
         "kind": "freeform", "optionId": None, "text": "Use the adapter."},
    ]

    ledger, decisions = append_answers(
        graph, _cfg(), tmp_path, payload, expected_revision=0,
    )

    assert ledger["revision"] == 2
    assert [entry["revision"] for entry in ledger["answers"]] == [1, 2]
    assert [decision.question.id for decision in decisions] == [
        first.id, second.id,
    ]

    invalid_root = tmp_path / "invalid"
    invalid = [*payload]
    invalid[1] = {**invalid[1], "kind": "option", "optionId": "invented",
                  "text": None}
    with pytest.raises(QuestionAnswerError, match="current option"):
        append_answers(
            graph, _cfg(), invalid_root, invalid, expected_revision=0,
        )
    assert not (invalid_root / "vizzer/question-answers.json").exists()


def test_changed_question_fingerprint_reopens_without_erasing_history(tmp_path):
    original = _question()
    append_answer(
        _graph(original), _cfg(), tmp_path, original.id,
        expected_revision=0,
        expected_fingerprint=owner_question_fingerprint(original),
        kind="freeform", text="Use an adapter boundary.",
    )
    revised = _question(prompt="Which adapter boundary wins?")
    rebuilt = _graph(revised)

    assert reconcile_answers(rebuilt, _cfg(), tmp_path) == []
    assert rebuilt.owner_questions == [revised]
    assert rebuilt.owner_decisions == []
    ledger, _ = read_answers(_cfg(), tmp_path)
    assert ledger["revision"] == 1
    assert ledger["answers"][0]["question"]["prompt"] == original.prompt


def test_revision_and_fingerprint_compare_and_swap_prevent_stale_answers(tmp_path):
    first = _question(question_id="question:first")
    append_answer(
        _graph(first), _cfg(), tmp_path, first.id,
        expected_revision=0,
        expected_fingerprint=owner_question_fingerprint(first),
        kind="option", option_id="shared",
    )
    second = _question(question_id="question:second")

    with pytest.raises(QuestionAnswerConflict, match="stale question answer revision"):
        append_answer(
            _graph(second), _cfg(), tmp_path, second.id,
            expected_revision=0,
            expected_fingerprint=owner_question_fingerprint(second),
            kind="option", option_id="shared",
        )

    with pytest.raises(QuestionAnswerConflict, match="stale question fingerprint"):
        append_answer(
            _graph(second), _cfg(), tmp_path, second.id,
            expected_revision=1,
            expected_fingerprint="0" * 64,
            kind="option", option_id="shared",
        )

    ledger, _ = read_answers(_cfg(), tmp_path)
    assert ledger["revision"] == 1
    assert len(ledger["answers"]) == 1


def test_answer_validation_and_malformed_ledger_fail_open(tmp_path):
    question = _question()
    with pytest.raises(QuestionAnswerError, match="current option"):
        append_answer(
            _graph(question), _cfg(), tmp_path, question.id,
            expected_revision=0,
            expected_fingerprint=owner_question_fingerprint(question),
            kind="option", option_id="invented",
        )
    with pytest.raises(QuestionAnswerError, match="1..2000"):
        append_answer(
            _graph(question), _cfg(), tmp_path, question.id,
            expected_revision=0,
            expected_fingerprint=owner_question_fingerprint(question),
            kind="freeform", text="   ",
        )

    path = tmp_path / "vizzer/question-answers.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text('{"schema":1,"revision":4,"answers":[]}', encoding="utf-8")
    graph = _graph(question)
    warnings = reconcile_answers(graph, _cfg(), tmp_path)
    assert graph.owner_questions == [question]
    assert graph.owner_decisions == []
    assert len(warnings) == 1
    assert "question answers ignored" in warnings[0]


def test_answers_path_cannot_escape_project_or_follow_leaf_symlink(tmp_path):
    with pytest.raises(QuestionAnswerError, match="inside the project"):
        read_answers(_cfg("../answers.json"), tmp_path)

    outside = tmp_path / "outside.json"
    outside.write_text("do not overwrite", encoding="utf-8")
    ledger = tmp_path / "vizzer/question-answers.json"
    ledger.parent.mkdir()
    ledger.symlink_to(outside)
    with pytest.raises(QuestionAnswerError, match="not a symlink"):
        read_answers(_cfg(), tmp_path)
    assert outside.read_text(encoding="utf-8") == "do not overwrite"
