import json
import re

from vizzer.config import Config, DEFAULTS
from vizzer.model import (
    Graph,
    Item,
    OwnerDecision,
    OwnerQuestion,
    OwnerQuestionOption,
    OwnerQuestionRecommendation,
    owner_question_fingerprint,
)
from vizzer.render import render_all


def _question(question_id: str, story_id: str, prompt: str) -> OwnerQuestion:
    return OwnerQuestion(
        id=question_id,
        story_id=story_id,
        owner="Ryder",
        prompt=prompt,
        options=[
            OwnerQuestionOption("shared", "Shared", "One authority."),
            OwnerQuestionOption("local", "Local", "Smaller patch."),
        ],
        recommendation=OwnerQuestionRecommendation("shared", "Avoid drift."),
        falsifier="The concept remains permanently single-use.",
        evidence=["wiki/story.md:12"],
    )


def _data(html: str) -> dict:
    match = re.search(r"const DATA=(\{.*?\});\n", html, re.S)
    assert match is not None
    return json.loads(match.group(1))


def test_constellation_serializes_open_questions_and_accepted_decisions_separately(
    tmp_path,
):
    open_question = _question(
        "question:open-route", "story:a", "Which route remains open?",
    )
    answered_question = _question(
        "question:accepted-route", "story:b", "Which route was accepted?",
    )
    fingerprint = owner_question_fingerprint(answered_question)
    graph = Graph(
        vocab=Config(data=DEFAULTS).vocab,
        items=[
            Item(id="story:a", title="A", status="specced"),
            Item(id="story:b", title="B", status="building"),
        ],
        owner_questions=[open_question],
        owner_decisions=[OwnerDecision(
            question=answered_question,
            fingerprint=fingerprint,
            revision=4,
            answered_at="2026-08-10T18:30:00Z",
            answered_by="Ryder",
            kind="freeform",
            option_id=None,
            text="Use a shared adapter, but keep its policy injectable.",
        )],
    )

    html = render_all(
        graph, Config(data=DEFAULTS), tmp_path, only={"constellation"},
    )["constellation.html"]
    data = _data(html)

    assert [question["id"] for question in data["questions"]] == [
        "question:open-route",
    ]
    assert data["questions"][0]["storyId"] == "story:a"
    assert data["questions"][0]["fingerprint"] == owner_question_fingerprint(
        open_question,
    )
    assert data["nodes"][0]["oq"] == [0]
    assert "od" not in data["nodes"][0]

    assert [decision["id"] for decision in data["decisions"]] == [
        "question:accepted-route",
    ]
    decision = data["decisions"][0]
    assert decision["storyId"] == "story:b"
    assert decision["prompt"] == "Which route was accepted?"
    assert [option["id"] for option in decision["options"]] == ["shared", "local"]
    assert decision["fingerprint"] == fingerprint
    assert decision["revision"] == 4
    assert decision["answeredAt"] == "2026-08-10T18:30:00Z"
    assert decision["answeredBy"] == "Ryder"
    assert decision["kind"] == "freeform"
    assert decision["optionId"] is None
    assert decision["text"] == "Use a shared adapter, but keep its policy injectable."
    assert data["nodes"][1]["od"] == [0]
    assert "oq" not in data["nodes"][1]
    assert "policy injectable" in data["nodes"][1]["q"]
