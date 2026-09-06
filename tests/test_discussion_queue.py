import hashlib
import json

import pytest

from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.discussion_queue import (
    MAX_HISTORY, DiscussionQueueConflict, DiscussionQueueError, enqueue_discussion,
    discussion_queue_snapshot, read_discussion_queue, restore_discussion_queue,
)
from vizzer.model import (
    Graph, Item, OwnerQuestion, OwnerQuestionOption, OwnerQuestionRecommendation,
    owner_question_fingerprint,
)
from vizzer.render import render_all


def _question(story_id="story:a"):
    return OwnerQuestion(
        id="question:route", story_id=story_id, owner="Ryder",
        prompt="Which route should own this behavior?",
        options=[
            OwnerQuestionOption(id="a", label="Route A", tradeoff="Small change"),
            OwnerQuestionOption(id="b", label="Route B", tradeoff="Broad change"),
        ],
        recommendation=OwnerQuestionRecommendation(option_id="a", rationale="Narrower"),
        falsifier="Route A cannot represent the state", evidence=["spec/a.md"],
    )


def _graph(with_question=True):
    question = _question()
    return Graph(
        items=[
            Item(id="story:a", title="Story A", status="specced",
                 source={"adapter": "spec_tree", "path": "spec/a.md"}),
            Item(id="story:b", title="Story B", status="specced",
                 source={"adapter": "spec_tree", "path": "spec/b.md"}),
        ],
        owner_questions=[question] if with_question else [],
    )


def _cfg():
    return Config(data=deep_merge(DEFAULTS, {
        "discussions": {"queue_path": "vizzer/discussion-queue.json"},
    }))


def test_provider_queue_is_audited_top_first_and_moves_between_lanes(tmp_path):
    graph, cfg = _graph(), _cfg()
    question = graph.owner_questions[0]
    refs = [{"id": question.id, "fingerprint": owner_question_fingerprint(question)}]

    first, changed = enqueue_discussion(
        cfg, tmp_path, graph, provider="codex", story_id="story:a",
        questions=refs, expected_revision=0, now="2026-08-11T20:00:00Z",
    )
    assert changed is True
    assert first["queues"] == {"codex": ["story:a"], "claude": []}
    assert first["history"][0]["questionIds"] == ["question:route"]

    second, changed = enqueue_discussion(
        cfg, tmp_path, graph, provider="claude", story_id="story:a",
        questions=refs, expected_revision=1, now="2026-08-11T20:01:00Z",
    )
    assert changed is True
    assert second["queues"] == {"codex": [], "claude": ["story:a"]}
    assert [entry["provider"] for entry in second["history"]] == ["codex", "claude"]

    same, changed = enqueue_discussion(
        cfg, tmp_path, graph, provider="claude", story_id="story:a",
        questions=refs, expected_revision=2,
    )
    assert changed is False and same["revision"] == 2
    with pytest.raises(DiscussionQueueConflict, match="current is 2"):
        enqueue_discussion(
            cfg, tmp_path, graph, provider="codex", story_id="story:a",
            questions=refs, expected_revision=1,
        )


def test_general_story_discussion_allows_no_questions_but_rejects_stale_question_set(tmp_path):
    cfg = _cfg()
    general = _graph(with_question=False)
    queue, changed = enqueue_discussion(
        cfg, tmp_path, general, provider="codex", story_id="story:b",
        questions=[], expected_revision=0,
    )
    assert changed and queue["queues"]["codex"] == ["story:b"]

    graph = _graph()
    with pytest.raises(DiscussionQueueConflict, match="open questions changed"):
        enqueue_discussion(
            cfg, tmp_path, graph, provider="claude", story_id="story:a",
            questions=[], expected_revision=1,
        )
    with pytest.raises(DiscussionQueueError, match="unsupported discussion provider"):
        enqueue_discussion(
            cfg, tmp_path, graph, provider="gemini", story_id="story:a",
            questions=[{"id": "question:route", "fingerprint": "wrong"}],
            expected_revision=1,
        )


def test_queue_snapshot_restores_missing_and_existing_states(tmp_path):
    graph, cfg = _graph(with_question=False), _cfg()
    assert discussion_queue_snapshot(cfg, tmp_path, graph) is None
    first, _ = enqueue_discussion(
        cfg, tmp_path, graph, provider="codex", story_id="story:a",
        questions=[], expected_revision=0, now="2026-08-11T20:00:00Z",
    )
    queue_path = tmp_path / "vizzer/discussion-queue.json"
    restore_discussion_queue(cfg, tmp_path, None)
    assert not queue_path.exists()

    enqueue_discussion(
        cfg, tmp_path, graph, provider="codex", story_id="story:a",
        questions=[], expected_revision=0, now="2026-08-11T20:00:00Z",
    )
    snapshot = discussion_queue_snapshot(cfg, tmp_path, graph)
    original = queue_path.read_bytes()
    enqueue_discussion(
        cfg, tmp_path, graph, provider="claude", story_id="story:a",
        questions=[], expected_revision=first["revision"],
        now="2026-08-11T20:01:00Z",
    )
    restore_discussion_queue(cfg, tmp_path, snapshot)
    assert queue_path.read_bytes() == original


def test_discussion_markdown_is_llm_readable_and_never_claims_answer_authority(tmp_path):
    graph, cfg = _graph(), _cfg()
    question = graph.owner_questions[0]
    enqueue_discussion(
        cfg, tmp_path, graph, provider="codex", story_id="story:a",
        questions=[{"id": question.id, "fingerprint": owner_question_fingerprint(question)}],
        expected_revision=0, now="2026-08-11T20:00:00Z",
    )
    rendered = render_all(graph, cfg, tmp_path, only={"discussion_queue"})
    text = rendered["discussion-queue.md"]
    assert "Read your provider lane top-first at session start" in text
    assert "Queued does not mean discussed, answered, or applied" in text
    assert "## Codex" in text and "## Claude" in text
    assert "[a](../../spec/a.md)" in text
    assert question.id in text and question.prompt in text

    persisted, warnings = read_discussion_queue(cfg, tmp_path, graph)
    assert warnings == [] and persisted["revision"] == 1
    assert json.loads((tmp_path / "vizzer/discussion-queue.json").read_text()) == persisted


def test_schema_one_queue_loads_as_schema_two_without_losing_history(tmp_path):
    graph, cfg = _graph(with_question=False), _cfg()
    path = tmp_path / "vizzer/discussion-queue.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema": 1, "revision": 1, "updatedAt": "2026-08-11T20:00:00Z",
        "queues": {"codex": ["story:a"], "claude": []},
        "history": [{
            "revision": 1, "provider": "codex", "storyId": "story:a",
            "questionIds": [], "queuedAt": "2026-08-11T20:00:00Z",
        }],
    }))
    queue, warnings = read_discussion_queue(cfg, tmp_path, graph)
    assert warnings == []
    assert queue["schema"] == 2 and queue["requests"] == []
    assert queue["history"][0]["storyId"] == "story:a"


def test_test_design_request_moves_append_only_between_providers(tmp_path):
    graph, cfg = _graph(with_question=False), _cfg()
    request = {"kind": "test-design", "prompt": "One bounded test with one goal."}
    queue, _ = enqueue_discussion(cfg, tmp_path, graph, provider="codex",
                                  story_id="story:a", questions=[], request=request,
                                  expected_revision=0, now="2026-09-05T12:00:00Z")
    queue, _ = enqueue_discussion(cfg, tmp_path, graph, provider="claude",
                                  story_id="story:a", questions=[], request=request,
                                  expected_revision=queue["revision"], now="2026-09-05T12:01:00Z")
    queue, _ = enqueue_discussion(cfg, tmp_path, graph, provider="codex",
                                  story_id="story:a", questions=[], request=request,
                                  expected_revision=queue["revision"], now="2026-09-05T12:02:00Z")
    assert [entry["state"] for entry in queue["requests"]] == ["superseded", "superseded", "queued"]
    assert len({entry["id"] for entry in queue["requests"]}) == 3
    loaded, warnings = read_discussion_queue(cfg, tmp_path, graph)
    assert warnings == [] and loaded == queue


def test_request_retention_never_evicts_unrelated_live_dispatch(tmp_path):
    graph, cfg = _graph(with_question=False), _cfg()
    queue, _ = enqueue_discussion(cfg, tmp_path, graph, provider="codex",
                                  story_id="story:a", questions=[],
                                  request={"kind": "test-design", "prompt": "Keep this live."},
                                  expected_revision=0, now="2026-09-05T12:00:00Z")
    provider = "codex"
    for index in range(MAX_HISTORY + 1):
        provider = "claude" if provider == "codex" else "codex"
        queue, _ = enqueue_discussion(cfg, tmp_path, graph, provider=provider,
                                      story_id="story:b", questions=[],
                                      request={"kind": "test-design", "prompt": "Move this."},
                                      expected_revision=queue["revision"],
                                      now=f"2026-09-06T12:{index // 60 % 60:02d}:{index % 60:02d}Z")
    assert len(queue["requests"]) == MAX_HISTORY
    assert len([entry for entry in queue["requests"] if entry["storyId"] == "story:a"
                and entry["state"] == "queued"]) == 1
    loaded, warnings = read_discussion_queue(cfg, tmp_path, graph)
    assert warnings == [] and loaded == queue
