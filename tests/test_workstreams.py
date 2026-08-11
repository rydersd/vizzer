import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from vizzer.config import Config, DEFAULTS
from vizzer.cli import main
from vizzer.model import Graph, Item, OwnerQuestion, OwnerQuestionOption, OwnerQuestionRecommendation
from vizzer.workstreams import (
    WorkstreamConflict, WorkstreamError, append_discussion, apply_workstreams,
    empty_runtime, empty_workstreams, heartbeat_session, load_workstream_overlay,
    read_runtime, read_workstreams, start_session, stop_session,
)


def _cfg(tmp_path):
    data = json.loads(json.dumps(DEFAULTS))
    data["workstreams"] = {
        "enabled": True,
        "definitions_path": "vizzer/workstreams.json",
        "runtime_path": ".vizzer/runtime/sessions.json",
        "lease_minutes": 30,
    }
    return Config(data=data)


def _graph():
    return Graph(items=[
        Item(id="story:a", title="A"),
        Item(id="story:b", title="B", deps=["story:a"]),
        Item(id="story:c", title="C"),
    ], owner_questions=[OwnerQuestion(
        id="question:policy", story_id="story:b", owner="Ryder",
        prompt="Which policy?",
        options=[OwnerQuestionOption(id="one", label="One", tradeoff="A"),
                 OwnerQuestionOption(id="two", label="Two", tradeoff="B")],
        recommendation=OwnerQuestionRecommendation(option_id="one", rationale="Evidence"),
        falsifier="A counterexample", evidence=["spec.md"],
    )])


def _state():
    return {
        "workstreams": [{
            "id": "tokens", "title": "Token system", "objective": "Finish token stories",
            "status": "active", "lead": "Claude", "reviewer": "Codex",
            "storyIds": ["story:a"], "dependsOn": [],
            "allowedPaths": ["core/tokens", "tests/tokens"],
            "sharedPaths": ["vizzer/active-work.json"],
            "checkpoint": "Resolver tests", "completed": 1, "total": 3,
        }, {
            "id": "canvas", "title": "Canvas", "objective": "Ship canvas route",
            "status": "active", "lead": "Codex", "reviewer": "Claude",
            "storyIds": ["story:b"], "dependsOn": ["tokens"],
            "allowedPaths": ["render/canvas"], "sharedPaths": ["vizzer/active-work.json"],
            "checkpoint": "Integration", "completed": 0, "total": 2,
        }],
        "discussions": [],
    }


def test_versioned_workstreams_and_leased_sessions_load_into_graph(tmp_path):
    cfg, graph = _cfg(tmp_path), _graph()
    applied = apply_workstreams(
        cfg, tmp_path, graph, _state(), expected_revision=0,
        actor="Ryder", rationale="Split token and canvas work",
    )
    assert applied["revision"] == 1
    runtime = start_session(
        cfg, tmp_path, graph, session_id="claude-1", actor="Claude",
        model="Opus", role="lead", workstream_id="tokens", branch="claude/tokens",
        worktree="/repo/.worktrees/tokens", expected_revision=0,
        now="2026-08-10T20:00:00Z",
    )
    runtime = start_session(
        cfg, tmp_path, graph, session_id="codex-1", actor="Codex",
        model="Spark", role="lead", workstream_id="canvas", branch="codex/canvas",
        worktree="/repo/.worktrees/canvas", expected_revision=runtime["revision"],
        now="2026-08-10T20:01:00Z",
    )

    warnings = load_workstream_overlay(
        graph, cfg, tmp_path, now="2026-08-10T20:02:00Z",
    )

    assert warnings == []
    assert graph.workstreams["revision"] == 1
    assert len(graph.workstreams["sessions"]) == 2
    assert graph.workstreams["sessions"][0]["fresh"] is True
    assert any(collision["kind"] == "shared-path" for collision in graph.workstreams["collisions"])


def test_stale_definition_and_session_revisions_fail_closed(tmp_path):
    cfg, graph = _cfg(tmp_path), _graph()
    apply_workstreams(cfg, tmp_path, graph, _state(), expected_revision=0,
                      actor="Ryder", rationale="Initial split")
    with pytest.raises(WorkstreamConflict, match="stale workstream revision"):
        apply_workstreams(cfg, tmp_path, graph, _state(), expected_revision=0,
                          actor="Claude", rationale="Lost race")

    start_session(cfg, tmp_path, graph, session_id="one", actor="Claude", model="Opus",
                  role="lead", workstream_id="tokens", branch="claude/tokens",
                  worktree="/repo/tokens", expected_revision=0,
                  now="2026-08-10T20:00:00Z")
    with pytest.raises(WorkstreamConflict, match="stale session revision"):
        start_session(cfg, tmp_path, graph, session_id="two", actor="Codex", model="Spark",
                      role="lead", workstream_id="canvas", branch="codex/canvas",
                      worktree="/repo/canvas", expected_revision=0,
                      now="2026-08-10T20:00:01Z")


def test_expired_session_remains_auditable_but_is_not_fresh_or_colliding(tmp_path):
    cfg, graph = _cfg(tmp_path), _graph()
    apply_workstreams(cfg, tmp_path, graph, _state(), expected_revision=0,
                      actor="Ryder", rationale="Initial split")
    start_session(cfg, tmp_path, graph, session_id="old", actor="Claude", model="Opus",
                  role="lead", workstream_id="tokens", branch="claude/tokens",
                  worktree="/repo/tokens", expected_revision=0,
                  now="2026-08-10T18:00:00Z")

    load_workstream_overlay(graph, cfg, tmp_path, now="2026-08-10T20:00:00Z")

    assert graph.workstreams["sessions"][0]["fresh"] is False
    assert graph.workstreams["collisions"] == []


def test_peer_decision_is_limited_to_reversible_implementation_scope(tmp_path):
    cfg, graph = _cfg(tmp_path), _graph()
    apply_workstreams(cfg, tmp_path, graph, _state(), expected_revision=0,
                      actor="Ryder", rationale="Initial split")
    with pytest.raises(WorkstreamError, match="must escalate"):
        append_discussion(
            cfg, tmp_path, graph, expected_revision=1, workstream_id="tokens",
            discussion_id="policy-decision", author="Claude", kind="decision",
            scope="product", body="Claude and Codex agree, so ship it.",
        )

    updated = append_discussion(
        cfg, tmp_path, graph, expected_revision=1, workstream_id="tokens",
        discussion_id="policy-escalation", author="Claude", kind="escalation",
        scope="product", body="We disagree on product policy; Ryder must choose.",
        owner_question_id="question:policy",
    )
    assert updated["state"]["discussions"][0]["ownerQuestionId"] == "question:policy"


def test_session_heartbeat_and_stop_preserve_audit_record(tmp_path):
    cfg, graph = _cfg(tmp_path), _graph()
    apply_workstreams(cfg, tmp_path, graph, _state(), expected_revision=0,
                      actor="Ryder", rationale="Initial split")
    runtime = start_session(cfg, tmp_path, graph, session_id="codex", actor="Codex",
                            model="Spark", role="lead", workstream_id="canvas",
                            branch="codex/canvas", worktree="/repo/canvas",
                            expected_revision=0, now="2026-08-10T20:00:00Z")
    runtime = heartbeat_session(cfg, tmp_path, graph, session_id="codex",
                                expected_revision=runtime["revision"],
                                now="2026-08-10T20:10:00Z")
    runtime = stop_session(cfg, tmp_path, graph, session_id="codex",
                           expected_revision=runtime["revision"],
                           now="2026-08-10T20:11:00Z")
    assert runtime["sessions"][0]["state"] == "stopped"
    assert runtime["sessions"][0]["stoppedAt"] == "2026-08-10T20:11:00Z"


def test_workstream_validation_rejects_path_escape_and_dependency_cycles(tmp_path):
    cfg, graph = _cfg(tmp_path), _graph()
    state = _state()
    state["workstreams"][0]["allowedPaths"] = ["../other-repo"]
    with pytest.raises(WorkstreamError, match="path must stay inside"):
        apply_workstreams(cfg, tmp_path, graph, state, expected_revision=0,
                          actor="Ryder", rationale="Bad paths")

    state = _state()
    state["workstreams"][0]["dependsOn"] = ["canvas"]
    with pytest.raises(WorkstreamError, match="dependency cycle"):
        apply_workstreams(cfg, tmp_path, graph, state, expected_revision=0,
                          actor="Ryder", rationale="Bad cycle")


def test_cli_applies_workstream_and_registers_model_neutral_session(
    tmp_path, make_repo, capsys,
):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(config.read_text() + """
[workstreams]
enabled = true
definitions_path = "vizzer/workstreams.json"
runtime_path = ".vizzer/runtime/sessions.json"
lease_minutes = 30
""")
    request = repo / "workstreams-request.json"
    request.write_text(json.dumps({"workstreams": [{
        "id": "canvas", "title": "Canvas", "objective": "Ship canvas",
        "status": "active", "lead": "Claude", "reviewer": "Codex",
        "storyIds": ["story:canvas-core"], "dependsOn": [],
        "allowedPaths": ["src/canvas"], "sharedPaths": ["vizzer/active-work.json"],
        "checkpoint": "Acceptance", "completed": 1, "total": 2,
    }], "discussions": []}))

    assert main([
        "workstreams", "apply", "--root", str(repo), "--file", str(request),
        "--expected-revision", "0", "--actor", "Ryder",
        "--rationale", "Split the canvas lane",
    ]) == 0
    assert main([
        "sessions", "start", "--root", str(repo), "--id", "claude-canvas",
        "--actor", "Claude", "--model", "Opus", "--role", "lead",
        "--workstream", "canvas", "--branch", "claude/canvas",
        "--worktree", "/tmp/canvas", "--expected-revision", "0",
    ]) == 0
    assert main(["sessions", "show", "--root", str(repo)]) == 0
    output = capsys.readouterr().out
    assert '"actor": "Claude"' in output
    assert '"model": "Opus"' in output
    assert json.loads((repo / "vizzer/workstreams.json").read_text())["revision"] == 1
    assert json.loads((repo / ".vizzer/runtime/sessions.json").read_text())["revision"] == 1


def test_concurrent_cli_apply_has_one_winner_and_one_stale_loser(tmp_path, make_repo):
    """The repo lock + CAS must reject a real simultaneous revision-zero race."""
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(config.read_text() + """
[workstreams]
enabled = true
definitions_path = "vizzer/workstreams.json"
runtime_path = ".vizzer/runtime/sessions.json"
lease_minutes = 30
""")
    request = repo / "race-request.json"
    request.write_text(json.dumps({"workstreams": [{
        "id": "canvas", "title": "Canvas", "objective": "Ship canvas",
        "status": "active", "lead": "Claude", "reviewer": "Codex",
        "storyIds": ["story:canvas-core"], "dependsOn": [],
        "allowedPaths": ["src/canvas"], "sharedPaths": [],
        "checkpoint": "Acceptance", "completed": 1, "total": 2,
    }], "discussions": []}))
    command = [
        "workstreams", "apply", "--root", str(repo), "--file", str(request),
        "--expected-revision", "0", "--actor", "Ryder",
        "--rationale", "Resolve one concurrent writer",
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(lambda _: main(command), range(2)))

    assert results == [0, 3]
    assert json.loads((repo / "vizzer/workstreams.json").read_text())["revision"] == 1
