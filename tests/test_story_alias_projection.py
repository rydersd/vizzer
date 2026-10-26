import copy
import json
import re

from vizzer.config import Config, DEFAULTS
from vizzer.activity import load_active_work
from vizzer.model import (
    Graph, Item, OwnerQuestion, OwnerQuestionOption, OwnerQuestionRecommendation,
    owner_question_fingerprint,
)
from vizzer.render import render_all
from vizzer.story_aliases import load_story_aliases
from vizzer.workstreams import (
    apply_workstreams, restore_workstreams, snapshot_workstreams_source,
)


def _config(tmp_path):
    data = copy.deepcopy(DEFAULTS)
    data["workstreams"] = {
        "enabled": True,
        "definitions_path": "vizzer/workstreams.json",
        "runtime_path": ".vizzer/runtime/sessions.json",
        "lease_minutes": 30,
    }
    data["render"]["story_aliases"] = "vizzer/story-id-crosswalk.json"
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer/story-id-crosswalk.json").write_text(json.dumps({
        "schema": 1, "aliases": {"story:retired": "story:current"},
    }))
    return Config(data=data)


def _state(story_id):
    return {
        "workstreams": [{
            "id": "paint", "title": "Paint", "objective": "Implement paint",
            "status": "active", "lead": "Agent", "reviewer": "Reviewer",
            "storyIds": [story_id], "dependsOn": [], "allowedPaths": ["src/"],
            "sharedPaths": [], "checkpoint": "Run checks", "completed": 0, "total": 1,
        }],
        "discussions": [],
    }


def test_workstream_apply_resolves_validated_story_alias(tmp_path):
    cfg = _config(tmp_path)
    graph = Graph(items=[Item(id="story:current", title="Current")])

    result = apply_workstreams(
        cfg, tmp_path, graph, _state("story:retired"), expected_revision=0,
        actor="Owner", rationale="Start the current story",
    )

    assert result["state"]["workstreams"][0]["storyIds"] == ["story:current"]


def test_workstream_edit_preserves_retired_ids_in_authored_history(tmp_path):
    cfg = _config(tmp_path)
    graph = Graph(items=[Item(id="story:current", title="Current")])
    first = apply_workstreams(
        cfg, tmp_path, graph, _state("story:current"), expected_revision=0,
        actor="Owner", rationale="Initial workstream",
    )
    path = tmp_path / "vizzer/workstreams.json"
    payload = json.loads(path.read_text())
    payload["history"][0]["state"]["workstreams"][0]["storyIds"] = ["story:retired"]
    path.write_text(json.dumps(payload))
    preserved = copy.deepcopy(payload["history"])

    apply_workstreams(
        cfg, tmp_path, graph, _state("story:current"), expected_revision=first["revision"],
        actor="Owner", rationale="Continue current work",
    )

    written = json.loads(path.read_text())
    assert written["history"][:-1] == preserved


def test_workstream_rollback_restores_authored_history_ids_exactly(tmp_path):
    cfg = _config(tmp_path)
    graph = Graph(items=[Item(id="story:current", title="Current")])
    first = apply_workstreams(
        cfg, tmp_path, graph, _state("story:current"), expected_revision=0,
        actor="Owner", rationale="Initial workstream",
    )
    path = tmp_path / "vizzer/workstreams.json"
    payload = json.loads(path.read_text())
    payload["history"][0]["state"]["workstreams"][0]["storyIds"] = ["story:retired"]
    path.write_text(json.dumps(payload))
    snapshot = snapshot_workstreams_source(cfg, tmp_path, graph)
    apply_workstreams(
        cfg, tmp_path, graph, _state("story:current"), expected_revision=first["revision"],
        actor="Owner", rationale="Temporary edit",
    )

    restore_workstreams(cfg, tmp_path, graph, snapshot)

    assert json.loads(path.read_text()) == snapshot


def _question(question_id, story_id):
    return OwnerQuestion(
        id=question_id, story_id=story_id, owner="Owner", prompt="Which behavior?",
        options=[OwnerQuestionOption(id="a", label="A", tradeoff="A tradeoff"),
                 OwnerQuestionOption(id="b", label="B", tradeoff="B tradeoff")],
        recommendation=OwnerQuestionRecommendation(option_id="a", rationale="Evidence"),
        falsifier="A counterexample", evidence=["stories/current.md"],
    )


def test_active_and_historical_alias_questions_keep_source_identity_in_projection(tmp_path):
    cfg = _config(tmp_path)
    alias_file = json.loads((tmp_path / "vizzer/story-id-crosswalk.json").read_text())
    alias_file["historical_question_ids"] = ["question:retired"]
    alias_file["historical_questions"] = [{
        "id": "question:retired", "story_id": "story:retired",
        "canonical_target": "story:current", "status": "historical",
        "source_reason": "Replaced by the current decision record.",
    }]
    (tmp_path / "vizzer/story-id-crosswalk.json").write_text(json.dumps(alias_file))
    graph = Graph(items=[Item(id="story:current", title="Current")], owner_questions=[
        _question("question:active", "story:retired"),
        _question("question:retired", "story:retired"),
    ])
    rendered = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]
    match = re.search(r"const DATA=(.*?);\s*\n", rendered, re.DOTALL)
    assert match
    data = json.loads(match.group(1))

    active = data["questions"]
    assert [(entry["id"], entry["storyId"], entry["n"]) for entry in active] == [
        ("question:active", "story:retired", 0),
    ]
    historical, = data["historicalQuestions"]
    assert historical["id"] == "question:retired"
    assert historical["storyId"] == "story:retired"
    assert historical["canonicalTarget"] == "story:current"
    assert historical["fingerprint"] == owner_question_fingerprint(graph.owner_questions[1])


def test_mismatched_historical_disposition_does_not_hide_current_question(tmp_path):
    cfg = _config(tmp_path)
    payload = json.loads((tmp_path / "vizzer/story-id-crosswalk.json").read_text())
    payload["historical_question_ids"] = ["question:retired"]
    payload["historical_questions"] = [{
        "id": "question:retired", "story_id": "story:retired",
        "canonical_target": "story:current", "status": "historical",
        "source_reason": "Wrong source story for this fixture.",
    }]
    (tmp_path / "vizzer/story-id-crosswalk.json").write_text(json.dumps(payload))
    graph = Graph(items=[Item(id="story:current", title="Current")], owner_questions=[
        _question("question:retired", "story:current"),
    ])

    rendered = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]
    data = json.loads(re.search(r"const DATA=(.*?);\s*\n", rendered, re.DOTALL).group(1))

    assert [entry["id"] for entry in data["questions"]] == ["question:retired"]
    assert data["historicalQuestions"] == []


def test_story_alias_validator_rejects_cycles_unknown_targets_and_shadowing(tmp_path):
    cfg = _config(tmp_path)
    path = tmp_path / "vizzer/story-id-crosswalk.json"
    path.write_text(json.dumps({"schema": 1, "aliases": {
        "story:current": "story:retired", "story:cycle-a": "story:cycle-b",
        "story:cycle-b": "story:cycle-a", "story:unknown": "story:missing",
    }}))

    aliases, _, _, warnings = load_story_aliases(
        tmp_path, cfg, {"story:current"},
    )

    assert aliases == {}
    assert any("shadows" in warning for warning in warnings)
    assert any("cycle" in warning for warning in warnings)
    assert any("unknown" in warning for warning in warnings)


def test_activity_resolves_alias_and_drops_unhashable_story_id(tmp_path):
    cfg = _config(tmp_path)
    data = copy.deepcopy(cfg.data)
    data["activity"]["path"] = "vizzer/activity.json"
    cfg = Config(data=data)
    (tmp_path / "vizzer/activity.json").write_text(json.dumps({
        "schema": 1,
        "work": [{
            "storyId": "story:retired", "agent": "Agent", "task": "Migrate",
            "state": "active", "updatedAt": "2026-10-26T12:00:00Z",
            "checkpoints": {"completed": 1, "total": 2},
        }, {
            "storyId": ["story:current"], "agent": "Bad", "task": "Malformed",
            "state": "active", "updatedAt": "2026-10-26T12:00:00Z",
            "checkpoints": {"completed": 0, "total": 0},
        }],
    }))
    graph = Graph(items=[Item(id="story:current", title="Current")])

    warnings = load_active_work(graph, cfg, tmp_path)

    assert [work.story_id for work in graph.active_work] == ["story:current"]
    assert any("storyId" in warning and "dropped" in warning for warning in warnings)
