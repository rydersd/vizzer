import json
from datetime import datetime, timezone

from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import (
    ActiveWork, Graph, Group, Item, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation,
)
from vizzer.question_aging import question_ages
from vizzer.render import agent_ops, analytics, awaiting_owner, lanes


def _cfg(**values):
    return Config(data=deep_merge(
        deep_merge(DEFAULTS, {"perspectives": {"enabled": True}}), values,
    ))


def _question():
    return OwnerQuestion(
        id="question:route", story_id="story:a", owner="Owner",
        prompt="Which route?",
        options=[
            OwnerQuestionOption("one", "One", "Lower coupling."),
            OwnerQuestionOption("two", "Two", "Faster delivery."),
        ],
        recommendation=OwnerQuestionRecommendation("one", "One authority."),
        falsifier="The route cannot meet the contract.",
        evidence=["spec/a.md"],
    )


def test_analytics_uses_configured_status_roles_and_persisted_time(tmp_path):
    story = tmp_path / "spec/a.md"
    story.parent.mkdir()
    story.write_text("# A\n\n> Status: working\n", encoding="utf-8")
    graph = Graph(
        groups=[Group(id="capability:alpha", kind="capability", title="Alpha")],
        items=[Item(
            id="story:a", title="A", status="working", group="capability:alpha",
            source={"path": "spec/a.md"}, role="delivery",
        )],
        active_work=[ActiveWork(
            story_id="story:a", agent="Agent", task="Build", state="active",
            completed=0, total=1, updated_at="2026-08-01T00:00:00Z",
            stale_at="2026-08-01T01:00:00Z",
        )],
    )
    cfg = _cfg(
        status=[
            {"name": "queued", "role": "ready", "done": False},
            {"name": "working", "role": "active", "done": False},
            {"name": "finished", "role": "done", "done": True},
        ],
        reconcile={"staleness_days": 0},
    )

    output = analytics.render(graph, cfg, tmp_path)

    assert "`working`" in output["risk-heat.md"]
    assert "| Alpha | 1 | 0/1" in output["capability-rollup.md"]
    assert "| Ready | Active | Regression |" in output["capability-rollup.md"]


def test_question_age_prefers_explicit_raised_at_and_keeps_unknown_unknown(tmp_path):
    feed = tmp_path / "records/activity.json"
    feed.parent.mkdir()
    feed.write_text(json.dumps({
        "schema": 1,
        "questions": [{"id": "question:route", "raisedAt": "2026-08-01T00:00:00Z"}],
    }), encoding="utf-8")
    graph = Graph(owner_questions=[_question()])
    cfg = _cfg(activity={"path": "records/activity.json"}, questions={
        "age_budget_hours": 24,
    })

    [age] = question_ages(
        graph, cfg, tmp_path, datetime(2026, 8, 3, tzinfo=timezone.utc)
    )

    assert age.source == "raisedAt" and age.age_hours == 48 and age.over_budget


def test_awaiting_owner_and_lanes_use_configured_paths_only(tmp_path):
    story = tmp_path / "records/a.md"
    story.parent.mkdir()
    story.write_text(
        "# A\n\nAMENDMENT PROPOSED — pending owner ruling\n", encoding="utf-8"
    )
    register = tmp_path / "ops/register.md"
    register.parent.mkdir()
    register.write_text(
        "## Active\n\n`agent/alpha`: active since 2026-08-01\n", encoding="utf-8"
    )
    graph = Graph(
        items=[Item(id="story:a", title="A", source={"path": "records/a.md"})],
        owner_questions=[_question()],
    )
    cfg = _cfg(
        activity={"path": "records/activity.json"},
        perspectives={"register_path": "ops/register.md"},
    )

    owner_view = awaiting_owner.render(graph, cfg, tmp_path)["awaiting-owner.md"]
    lane_view = lanes.render(graph, cfg, tmp_path)["lanes.md"]

    assert "AMENDMENT PROPOSED" in owner_view
    assert "ops/register.md" in lane_view and "agent/alpha" in lane_view
    assert "wiki/dev" not in lane_view


def test_agent_ops_is_optional_and_uses_configured_ledger_and_story_glob(tmp_path):
    ledger = tmp_path / "ops/lanes.jsonl"
    ledger.parent.mkdir()
    ledger.write_text(json.dumps({
        "lane": "alpha", "model": "model-x", "effort": "high", "est": "T-shirt",
        "dispatched": "2026-08-01T00:00:00Z", "terminal": "2026-08-01T01:00:00Z",
        "outcome": "merged", "tokens": 1200, "continuations": 0,
        "wander": [], "idleEvents": [], "evidence": [],
    }) + "\n", encoding="utf-8")
    story = tmp_path / "spec/stories/a.md"
    story.parent.mkdir(parents=True)
    story.write_text(
        "# A\n\n> Burn: est T-shirt · actual 1h 00m · lane alpha\n",
        encoding="utf-8",
    )
    cfg = _cfg(
        agent_ops={"enabled": True, "ledger_path": "ops/lanes.jsonl"},
        sources={"spec_tree": {"glob": "spec/stories/*.md"}},
    )

    output = agent_ops.render(Graph(), cfg, tmp_path)

    assert set(output) == {"agent-ops.md", "agent-ops.html"}
    assert "model-x" in output["agent-ops.md"]
    assert "T-shirt" in output["agent-ops.md"]
