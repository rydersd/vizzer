import json

# codex-sequence-2026-08-08: active-work instrumentation negative controls.

from vizzer.activity import (
    answered_blocker_records, load_active_work, load_grandfathered_blockers,
    unresolved_blocker_records,
)
from vizzer.adapters import ScanResult
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import (
    ActiveWork, Graph, Item, OwnerDecision, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation, owner_question_fingerprint,
)
from vizzer.reconcile import build_graph


def _cfg(path="vizzer/active-work.json", stale=30):
    return Config(data=deep_merge(DEFAULTS, {"activity": {
        "path": path,
        "stale_after_minutes": stale,
    }}))


def _graph():
    return Graph(items=[
        Item(id="story:a", title="A"),
        Item(id="story:b", title="B"),
    ])


def _write(tmp_path, work):
    feed = tmp_path / "vizzer" / "active-work.json"
    feed.parent.mkdir()
    feed.write_text(json.dumps({"schema": 1, "work": work}), encoding="utf-8")


def _write_feed(tmp_path, work, questions):
    feed = tmp_path / "vizzer" / "active-work.json"
    feed.parent.mkdir()
    feed.write_text(json.dumps({
        "schema": 1, "work": work, "questions": questions,
    }), encoding="utf-8")


def _question(**overrides):
    value = {
        "id": "question:hit-priority",
        "storyId": "story:a",
        "owner": "Ryder",
        "prompt": "Which target wins?",
        "options": [
            {"id": "nearest", "label": "Nearest", "tradeoff": "Predictable geometry."},
            {"id": "close", "label": "Close target", "tradeoff": "Faster closing."},
        ],
        "recommendation": {
            "optionId": "nearest", "rationale": "It preserves hit-test truth.",
        },
        "falsifier": "User testing shows nearest makes closing unreliable.",
        "evidence": ["wiki/product-spec/story.md:42"],
    }
    value.update(overrides)
    return value


def _owner_question(story_id="story:a"):
    return OwnerQuestion(
        id="question:route", story_id=story_id, owner="Owner",
        prompt="Which route?",
        options=[
            OwnerQuestionOption("one", "One", "Lower coupling."),
            OwnerQuestionOption("two", "Two", "Faster delivery."),
        ],
        recommendation=OwnerQuestionRecommendation("one", "Keeps one authority."),
        falsifier="The shared path cannot meet the contract.",
        evidence=["spec/story.md:12"],
    )


def _decision(story_id="story:a"):
    question = _owner_question(story_id)
    return OwnerDecision(
        question=question,
        fingerprint=owner_question_fingerprint(question),
        revision=1,
        answered_at="2026-08-08T17:05:00Z",
        answered_by="owner",
        kind="option",
        option_id="one",
    )


def test_activity_feed_keeps_valid_records_and_drops_unknown_links(tmp_path):
    """codex-sequence-2026-08-08: bad telemetry must fail visibly, not lie."""
    _write(tmp_path, [
        {
            "storyId": "story:a", "agent": "Galileo", "task": "Wire tokens",
            "state": "active", "checkpoints": {"completed": 2, "total": 4},
            "checkpoint": "renderer tests", "updatedAt": "2026-08-08T10:00:00-07:00",
            "relatedStoryIds": ["story:b", "story:missing", "story:a"],
        },
        {
            "storyId": "story:missing", "agent": "Ghost", "task": "Invent progress",
            "state": "active", "checkpoints": {"completed": 1, "total": 1},
            "updatedAt": "2026-08-08T17:00:00Z",
        },
    ])
    graph = _graph()

    warnings = load_active_work(graph, _cfg(), tmp_path)

    assert len(graph.active_work) == 1
    work = graph.active_work[0]
    assert (work.completed, work.total, work.checkpoint) == (2, 4, "renderer tests")
    assert work.updated_at == "2026-08-08T17:00:00Z"
    assert work.stale_at == "2026-08-08T17:30:00Z"
    assert work.related_story_ids == ["story:b"]
    assert any("unknown item story:missing" in warning for warning in warnings)
    assert any("cannot link story:a to itself" in warning for warning in warnings)


def test_activity_feed_preserves_start_and_explicit_blocker_links(tmp_path):
    _write(tmp_path, [{
        "storyId": "story:a", "agent": "Agent", "task": "Await prerequisite",
        "state": "blocked", "checkpoints": {"completed": 1, "total": 2},
        "startedAt": "2026-08-08T09:00:00-07:00",
        "updatedAt": "2026-08-08T17:00:00Z",
        "blockedBy": ["story:b", "story:missing", "story:a", "story:b"],
    }])
    graph = _graph()

    warnings = load_active_work(graph, _cfg(), tmp_path)

    assert graph.active_work[0].started_at == "2026-08-08T16:00:00Z"
    assert graph.active_work[0].blocked_by == ["story:b"]
    assert any("blockedBy references unknown item story:missing" in value for value in warnings)
    assert any("cannot block story:a on itself" in value for value in warnings)


def test_activity_feed_rejects_start_after_update(tmp_path):
    _write(tmp_path, [{
        "storyId": "story:a", "agent": "Agent", "task": "Time travel",
        "state": "active", "checkpoints": {"completed": 0, "total": 1},
        "startedAt": "2026-08-08T18:00:00Z",
        "updatedAt": "2026-08-08T17:00:00Z",
    }])
    graph = _graph()

    warnings = load_active_work(graph, _cfg(), tmp_path)

    assert graph.active_work == []
    assert any("startedAt must be <= updatedAt" in value for value in warnings)


def test_blocker_gate_requires_a_live_question_or_unfinished_dependency(tmp_path):
    graph = _graph()
    graph.items[1].status = "ready"
    _write(tmp_path, [{
        "storyId": "story:a", "agent": "Agent", "task": "Blocked",
        "state": "blocked", "checkpoints": {"completed": 0, "total": 1},
        "updatedAt": "2026-08-08T17:00:00Z",
    }])
    load_active_work(graph, _cfg(), tmp_path)

    violation = unresolved_blocker_records(graph, done_statuses={"done"})[0]
    assert violation.reasons == ("unlinked",)
    assert "add an owner question" in violation.remedy

    graph.active_work[0].blocked_by = ["story:b"]
    assert unresolved_blocker_records(graph, done_statuses={"done"}) == []
    graph.items[1].status = "done"
    assert unresolved_blocker_records(graph, done_statuses={"done"})[0].reasons == (
        "unlinked",
    )


def test_blocker_gate_detects_expired_and_uncheckable_leases():
    graph = _graph()
    graph.active_work = [ActiveWork(
        story_id="story:a", agent="Agent", task="Await owner", state="blocked",
        completed=0, total=1, updated_at="2026-08-08T17:00:00Z",
        stale_at="2026-08-08T17:30:00Z",
    )]
    graph.owner_questions = [_owner_question()]

    assert unresolved_blocker_records(graph, done_statuses={"done"})[0].reasons == (
        "unknown-lease",
    )
    graph.activity = {"as_of": "2026-08-08T18:00:00Z"}
    assert unresolved_blocker_records(graph, done_statuses={"done"})[0].reasons == (
        "expired-lease",
    )


def test_answered_owner_decision_requires_blocked_record_to_advance():
    graph = _graph()
    graph.active_work = [ActiveWork(
        story_id="story:a", agent="Agent", task="Await owner", state="blocked",
        completed=0, total=1, updated_at="2026-08-08T17:00:00Z",
        stale_at="2026-08-08T17:30:00Z",
    )]
    graph.owner_decisions = [_decision()]

    records = answered_blocker_records(graph)
    assert records[0][0].story_id == "story:a"
    assert records[0][1][0].question.id == "question:route"

    graph.owner_questions = [_owner_question()]
    assert answered_blocker_records(graph) == []


def test_grandfathered_blocker_is_pinned_to_exact_record_revision(tmp_path):
    path = tmp_path / "vizzer/blocked-gate-grandfathered.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "schema": 1,
        "records": [{
            "storyId": "story:a", "agent": "Agent", "task": "Legacy block",
            "updatedAt": "2026-08-08T17:00:00Z",
        }],
    }), encoding="utf-8")

    keys, warnings = load_grandfathered_blockers(tmp_path)

    assert warnings == []
    assert ("story:a", "Agent", "Legacy block", "2026-08-08T17:00:00Z") in keys
    assert ("story:a", "Agent", "Legacy block", "2026-08-08T17:01:00Z") not in keys


def test_activity_feed_loads_explicit_questions_independently_of_work_state(tmp_path):
    _write_feed(tmp_path, [{
        "storyId": "story:a", "agent": "Galileo", "task": "Keep working",
        "state": "active", "checkpoints": {"completed": 1, "total": 3},
        "updatedAt": "2026-08-08T17:00:00Z",
    }], [_question()])
    graph = _graph()

    assert load_active_work(graph, _cfg(), tmp_path) == []
    assert len(graph.owner_questions) == 1
    question = graph.owner_questions[0]
    assert question.story_id == "story:a"
    assert [option.id for option in question.options] == ["nearest", "close"]
    assert question.recommendation.option_id == "nearest"
    assert graph.active_work[0].state == "active"


def test_bad_questions_drop_independently_without_erasing_work_or_valid_questions(tmp_path):
    bad_unknown = _question(id="question:unknown", storyId="story:missing")
    bad_options = _question(id="question:one-option", options=[
        {"id": "only", "label": "Only", "tradeoff": "No real choice."},
    ])
    duplicate = _question()
    _write_feed(tmp_path, [{
        "storyId": "story:b", "agent": "Planck", "task": "Blocked on evidence",
        "state": "blocked", "checkpoints": {"completed": 0, "total": 1},
        "updatedAt": "2026-08-08T17:00:00Z",
    }], [_question(), bad_unknown, bad_options, duplicate])
    graph = _graph()

    warnings = load_active_work(graph, _cfg(), tmp_path)

    assert len(graph.active_work) == 1
    assert [question.id for question in graph.owner_questions] == ["question:hit-priority"]
    assert any("unknown item story:missing" in warning for warning in warnings)
    assert any("requires 2 or 3 options" in warning for warning in warnings)
    assert any("duplicates question:hit-priority" in warning for warning in warnings)


def test_owner_question_validation_rejects_unresearched_or_ambiguous_packets(tmp_path):
    duplicate_options = [
        {"id": "same", "label": "First", "tradeoff": "One route."},
        {"id": "same", "label": "Second", "tradeoff": "Another route."},
    ]
    four_options = [
        {"id": str(index), "label": f"Option {index}", "tradeoff": "Too many."}
        for index in range(4)
    ]
    cases = [
        _question(owner=""),
        _question(falsifier=""),
        _question(evidence=[]),
        _question(options=duplicate_options),
        _question(options=four_options),
        _question(recommendation={
            "optionId": "missing", "rationale": "Names no real option.",
        }),
    ]

    for index, question in enumerate(cases):
        case_root = tmp_path / str(index)
        case_root.mkdir()
        _write_feed(case_root, [], [question])
        graph = _graph()

        warnings = load_active_work(graph, _cfg(), case_root)

        assert graph.owner_questions == []
        assert len(warnings) == 1
        assert "question dropped" in warnings[0]


def test_zero_checkpoint_work_is_exactly_represented(tmp_path):
    _write(tmp_path, [{
        "storyId": "story:a", "agent": "Planck", "task": "Investigate",
        "state": "paused", "checkpoints": {"completed": 0, "total": 0},
        "updatedAt": "2026-08-08T17:00:00Z",
    }])
    graph = _graph()

    assert load_active_work(graph, _cfg(), tmp_path) == []
    assert (graph.active_work[0].completed, graph.active_work[0].total) == (0, 0)


def test_malformed_progress_and_timestamp_are_dropped_independently(tmp_path):
    _write(tmp_path, [
        {
            "storyId": "story:a", "agent": "A", "task": "Bad count",
            "state": "active", "checkpoints": {"completed": 3, "total": 2},
            "updatedAt": "2026-08-08T17:00:00Z",
        },
        {
            "storyId": "story:b", "agent": "B", "task": "Bad time",
            "state": "active", "checkpoints": {"completed": 0, "total": 2},
            "updatedAt": "yesterday-ish",
        },
    ])
    graph = _graph()

    warnings = load_active_work(graph, _cfg(), tmp_path)

    assert graph.active_work == []
    assert any("0 <= completed <= total" in warning for warning in warnings)
    assert any("offset-aware ISO" in warning for warning in warnings)


def test_activity_feed_rejects_duplicate_json_keys_instead_of_using_last_value(tmp_path):
    feed = tmp_path / "vizzer" / "active-work.json"
    feed.parent.mkdir()
    feed.write_text("""{
      "schema": 1,
      "work": [{
        "storyId": "story:a",
        "agent": "Galileo",
        "task": "Do not let source order choose status",
        "state": "active",
        "checkpoints": {"completed": 1, "total": 2},
        "checkpoint": "new truth",
        "checkpoint": "stale truth",
        "updatedAt": "2026-08-08T17:00:00Z"
      }]
    }""", encoding="utf-8")
    graph = _graph()

    warnings = load_active_work(graph, _cfg(), tmp_path)

    assert graph.active_work == []
    assert warnings == [
        "activity feed vizzer/active-work.json contains duplicate JSON key "
        "'checkpoint' (feed ignored)"
    ]


def test_activity_feed_cannot_escape_project_root(tmp_path):
    graph = _graph()
    warnings = load_active_work(graph, _cfg("../outside.json"), tmp_path)
    assert graph.active_work == []
    assert warnings == ["activity feed ../outside.json escapes the project root (ignored)"]


def test_reconcile_applies_activity_as_overlay_without_changing_story_truth(tmp_path):
    _write(tmp_path, [{
        "storyId": "story:a", "agent": "Galileo", "task": "Overlay",
        "state": "active", "checkpoints": {"completed": 1, "total": 2},
        "updatedAt": "2026-08-08T17:00:00Z",
    }])
    source = Item(id="story:a", title="A", status="specced", deps=[])

    graph = build_graph(
        _cfg(), tmp_path,
        [("spec_tree", ScanResult(items=[source]))],
    )

    assert len(graph.active_work) == 1
    assert graph.item_map()["story:a"].status == "specced"
    assert graph.item_map()["story:a"].deps == []
    assert graph.priority == {}
