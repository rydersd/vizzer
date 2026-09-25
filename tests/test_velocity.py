"""Portable contracts for evidence-backed delivery velocity."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import shutil
import subprocess

import pytest

from vizzer import velocity
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import (
    Graph, Item, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation,
)
from vizzer.render import render_all
from vizzer.render.velocity import stage_merge_ledger, velocity_payload, velocity_summary


UTC = timezone.utc


def _velocity_tab_probe(html: str) -> dict:
    """Run the emitted Velocity tab, not a Python-side surrogate of it."""
    from test_render_constellation import _CONSTELLATION_COUNT_DOM_SHIM

    node = shutil.which("node")
    assert node is not None, "Node is required to execute the rendered constellation"
    driver = _CONSTELLATION_COUNT_DOM_SHIM.replace(
        "process.stdout.write(JSON.stringify(out));",
        "const velocity=ev(`(()=>{switchView('velocity');return {panel:viewPanel.innerHTML,"
        "wip:DATA.velocity.wip,window:DATA.velocity.window,recent:DATA.velocity.recent};})()`);"
        "process.stdout.write(JSON.stringify(velocity));",
    )
    result = subprocess.run(
        [node, "-e", driver], input=html, text=True, capture_output=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _event(at: str, detail: str) -> dict[str, str]:
    return {
        "at": at,
        "kind": "lifecycle",
        "source": "story lifecycle header",
        "detail": detail,
    }


def test_lifecycle_velocity_uses_persisted_events_not_current_status() -> None:
    history = {
        "items": {
            "story:released": {
                "status": "shipped",
                "events": [
                    _event("2026-09-01T10:00:00Z", "ready → in-flight"),
                    _event("2026-09-04T10:00:00Z", "in-flight → shipped"),
                ],
            },
            "story:in-progress": {
                "status": "building",
                "events": [_event("2026-09-05T10:00:00Z", "ready → building")],
            },
            "story:malformed": {
                "status": "shipped",
                "events": [{"kind": "checkpoint", "detail": "not lifecycle"}],
            },
        },
    }

    transitions = velocity.lifecycle_transitions(history)

    assert [transition.target for transition in transitions] == [
        "in-flight", "shipped", "building",
    ]
    assert velocity.work_in_progress(history) == ["story:in-progress"]
    assert velocity.lead_times(transitions) == {
        "story:released": (datetime(2026, 9, 4, 10, tzinfo=UTC), 3.0),
    }


def test_merge_visibility_is_configured_by_portable_source_roots() -> None:
    log = "\n".join((
        "M\t1789601797\tRendered API update (#42)",
        "",
        "src/vizzer/velocity.py",
        "tests/test_velocity.py",
        "M\t1789596590\tDocumentation only (#41)",
        "",
        "docs/velocity.md",
        "M\t1789580000\tMerge pull request #40 from example/feature",
        "",
        "src/vizzer/tests/helper.py",
    ))

    merges = velocity.parse_merge_log(log, visible_roots=("src/",))

    assert [(merge.number, merge.visible) for merge in merges] == [
        (40, False), (41, False), (42, True),
    ]
    assert velocity.classify_paths(
        ["plugin/runtime.py"], visible_roots=("plugin/",),
    ) == "visible"
    assert velocity.classify_paths(
        ["plugin/tests/runtime.py"], visible_roots=("plugin/",),
    ) == "infra"


def test_malformed_events_and_merge_records_are_ignored_without_shifting_valid_data() -> None:
    history = {
        "items": {
            "story:valid": {"status": "shipped", "events": [
                _event("2026-09-03T00:00:00Z", "ready \u2192 building"),
                _event("2026-09-05T00:00:00Z", "building \u2192 shipped"),
            ]},
            "story:broken": {"status": "shipped", "events": [
                _event("not-a-date", "ready \u2192 shipped"),
                _event("2026-09-04T00:00:00Z", "not a transition"),
                "not an event",
            ]},
        },
    }
    log = "\n".join((
        "M\tnot-an-epoch\tBad timestamp (#10)",
        "src/vizzer/nope.py",
        "M\t1788566400",  # torn log marker; must not abort later valid evidence
        "M\t1788652800\tUseful source change (#12)",
        "src/vizzer/velocity.py",
    ))

    transitions = velocity.lifecycle_transitions(history)
    assert [(item.item_id, item.target) for item in transitions] == [
        ("story:valid", "building"), ("story:valid", "shipped"),
    ]
    assert velocity.lead_times(transitions)["story:valid"][1] == 2.0
    assert [(merge.number, merge.visible) for merge in velocity.parse_merge_log(log)] == [(12, True)]


def test_lead_time_requires_a_recorded_start_and_respects_ship_window() -> None:
    transitions = [
        velocity.Transition("story:a", datetime(2026, 9, 1, tzinfo=UTC), "ready", "building"),
        velocity.Transition("story:b", datetime(2026, 9, 2, tzinfo=UTC), "ready", "shipped"),
        velocity.Transition("story:a", datetime(2026, 9, 4, tzinfo=UTC), "building", "shipped"),
        velocity.Transition("story:c", datetime(2026, 9, 4, tzinfo=UTC), "ready", "in-flight"),
        velocity.Transition("story:c", datetime(2026, 9, 8, tzinfo=UTC), "in-flight", "shipped"),
    ]
    leads = velocity.lead_times(transitions)

    assert set(leads) == {"story:a", "story:c"}
    assert velocity.median_lead_time(leads) == (3.5, 2)
    assert velocity.median_lead_time(
        leads, since=datetime(2026, 9, 5, tzinfo=UTC),
    ) == (4.0, 1)
    assert velocity.median_lead_time(
        leads, until=datetime(2026, 9, 4, tzinfo=UTC),
    ) == (None, 0)


def test_spend_build_and_daily_aggregation_keep_unknowns_unknown() -> None:
    # The file reader is covered below; this input focuses on the semantic parser.
    spend = velocity.parse_spend_log([
        {"date": "2026-09-01", "host": "  alpha  ", "tokens_m": 2},
        {"date": "2026-09-01", "host": "alpha", "tokens_m": True},  # last row wins
        {"date": "2026-09-02", "host": "alpha", "tokens_m": float("nan")},
        {"date": "invalid", "host": "ignored", "tokens_m": 1},
    ])
    assert [(entry.day, entry.host, entry.tokens_m) for entry in spend] == [
        (date(2026, 9, 1), "alpha", None),
        (date(2026, 9, 2), "alpha", None),
    ]
    builds = velocity.build_stamps([
        {"at": "2026-09-02T00:00:00Z", "build": "10", "sha": "a" * 12},
        {"at": "2026-09-02T23:59:59+00:00", "build": 11, "sha": "b" * 12},
        {"at": "2026-09-02T23:59:59+00:00", "build": True, "sha": "bad"},
        {"at": "bad", "build": "12", "sha": "c" * 12},
    ], UTC)
    rows = velocity.day_rows(
        3, date(2026, 9, 3), [], [], spend, builds, UTC,
    )
    assert [row.host for row in rows] == ["alpha", "alpha", "alpha"]
    assert [row.builds for row in rows] == [0, 2, 0]
    assert velocity.host_summaries(rows, {}, UTC)[0].tokens_m is None


def test_jsonl_warnings_and_host_changes_do_not_rewrite_evidence(tmp_path) -> None:
    log = tmp_path / "velocity.jsonl"
    log.write_text(
        "\n".join((
            '{"date":"2026-09-01","host":"alpha","tokens_m":1}',
            "not json",
            "[]",
            '{"date":"2026-09-03","host":"beta","tokens_m":2}',
        )), encoding="utf-8",
    )
    raw, warnings = velocity.read_jsonl(log)
    rows = velocity.day_rows(
        4, date(2026, 9, 4), [], [], velocity.parse_spend_log(raw), {}, UTC,
    )

    assert len(raw) == 2
    assert warnings == [
        "velocity.jsonl: line 2 is not JSON",
        "velocity.jsonl: line 3 is not an object",
    ]
    assert [row.host for row in rows] == ["alpha", "alpha", "beta", "beta"]
    assert velocity.host_cuts(rows) == {2}
    assert velocity.sparkline([0.0, 2.0, 1.0, 2.0], {2}).count("|") == 1


def test_spend_corrections_do_not_misattribute_a_multi_host_day() -> None:
    entries = velocity.parse_spend_log([
        {"date": "2026-09-01", "host": "alpha", "tokens_m": 1, "note": "first"},
        {"date": "2026-09-01", "host": "alpha", "tokens_m": 2, "note": "correction"},
        {"date": "2026-09-02", "host": "alpha", "tokens_m": 1},
        {"date": "2026-09-02", "host": "beta", "tokens_m": 1},
        {"date": "2026-09-02", "host": "beta", "tokens_m": 3},
    ])

    assert [(entry.host, entry.tokens_m, entry.note) for entry in entries] == [
        ("alpha", 2.0, "correction"),
        ("unrecorded", None, "ambiguous hosts"),
    ]


def test_invalid_timezone_fails_instead_of_silently_rebucketing_evidence(tmp_path) -> None:
    cfg = Config(data=deep_merge(DEFAULTS, {"velocity": {"timezone": "Not/AZone"}}))

    with pytest.raises(ValueError, match="timezone"):
        velocity_summary(Graph(vocab=cfg.vocab), cfg, tmp_path)


def test_main_line_prefers_named_main_over_a_stale_remote_head(tmp_path, monkeypatch) -> None:
    seen: list[str] = []

    class Result:
        def __init__(self, returncode: int):
            self.returncode = returncode

    def probe(command, **_kwargs):
        ref = command[-1]
        seen.append(ref)
        return Result(0 if ref == "main" else 1)

    monkeypatch.setattr(velocity.subprocess, "run", probe)
    assert velocity.main_line_ref(tmp_path) == "main"
    assert seen == ["origin/main", "main"]


def test_anchor_and_rolling_series_are_evidence_bounded() -> None:
    assert velocity.anchor_day([], [], [], {}, UTC) is None
    transitions = [velocity.Transition(
        "story:x", datetime(2026, 9, 3, 23, 0, tzinfo=UTC), "building", "shipped",
    )]
    assert velocity.anchor_day(transitions, [], [], {}, UTC) == date(2026, 9, 3)
    assert velocity.rolling_average([1.0, 3.0, 8.0, 0.0], 3) == [1.0, 2.0, 4.0, 11 / 3]


def test_velocity_render_uses_synthetic_persisted_evidence_and_escapes_host_text(tmp_path, monkeypatch) -> None:
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer/velocity-log.jsonl").write_text(
        '{"date":"2026-09-04","host":"a|b`\\nnext","tokens_m":2}', encoding="utf-8",
    )
    graph = Graph.from_dict({"schema": 1, "groups": [], "items": []})
    graph.progress_history = {"updatedAt": "2026-09-04T12:00:00Z", "items": {
            "story:fixture": {"status": "building", "events": [
                _event("2026-09-03T12:00:00Z", "ready \u2192 building"),
                _event("2026-09-04T12:00:00Z", "building \u2192 shipped"),
            ]},
        }}
    cfg = Config(data=deep_merge(DEFAULTS, {"velocity": {"window_days": 4, "rolling_days": 2}}))
    (tmp_path / "vizzer").mkdir(exist_ok=True)
    (tmp_path / "vizzer/velocity-merges.json").write_text(velocity.merge_ledger_text(
        [velocity.Merge(77, datetime(2026, 9, 4, tzinfo=UTC), True)], "fixture/main"), encoding="utf-8")

    summary = velocity_summary(graph, cfg, tmp_path)
    rendered = render_all(graph, cfg, tmp_path, only={"velocity", "dashboard", "constellation"})
    payload = velocity_payload(summary)

    assert summary["recent_shipped"] == 1
    assert summary["recent_prs"] == 1
    assert summary["wip"] == ["story:fixture"]
    assert payload["window"]["shipped"] == 1
    assert "a&#124;b&#96; next" in rendered["velocity.md"]
    assert "bug-open=0" not in rendered["velocity.md"]
    assert "finished-but-uncredited" not in rendered["velocity.md"]


def test_velocity_tab_executes_the_exported_wip_and_window_contract(tmp_path, monkeypatch) -> None:
    graph = Graph(
        items=[Item(id="story:fixture", title="Fixture", status="ready")],
        vocab=Config(data=DEFAULTS).vocab,
        owner_questions=[OwnerQuestion(
            id="question:velocity", story_id="story:fixture", owner="Fixture",
            prompt="Can the DOM fixture open the Velocity route?",
            options=[OwnerQuestionOption(id="yes", label="Yes", tradeoff="Runs the real tab.")],
            recommendation=OwnerQuestionRecommendation(
                option_id="yes", rationale="The shared DOM fixture needs one question.",
            ),
            falsifier="The generated tab fails to boot.",
            evidence=["tests/test_velocity.py"],
        )],
    )
    graph.progress_history = {"updatedAt": "2026-09-04T12:00:00Z", "items": {
        "story:shipped": {"status": "shipped", "events": [
            _event("2026-09-03T12:00:00Z", "ready \u2192 building"),
            _event("2026-09-04T12:00:00Z", "building \u2192 shipped"),
        ]},
        "story:wip": {"status": "building", "events": [
            _event("2026-09-04T08:00:00Z", "ready \u2192 building"),
        ]},
    }}
    cfg = Config(data=deep_merge(DEFAULTS, {"velocity": {"window_days": 4, "rolling_days": 2}}))
    (tmp_path / "vizzer").mkdir(exist_ok=True)
    (tmp_path / "vizzer/velocity-merges.json").write_text(velocity.merge_ledger_text(
        [velocity.Merge(88, datetime(2026, 9, 4, tzinfo=UTC), True)], "fixture/main"), encoding="utf-8")

    summary = velocity_summary(graph, cfg, tmp_path)
    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]
    tab = _velocity_tab_probe(html)

    assert tab["wip"] == summary["wip"] == ["story:wip"]
    assert tab["window"]["shipped"] == summary["recent_shipped"] == 1
    assert tab["recent"]["prs"] == summary["recent_prs"] == 1
    assert "<h1>Velocity</h1>" in tab["panel"]
    assert ">1</strong><span>in flight now</span>" in tab["panel"]
    assert "not evidence of completion" in tab["panel"]
    assert "finished-but-uncredited" not in tab["panel"]


def test_velocity_summary_memoizes_only_matching_graph_root_and_config(tmp_path, monkeypatch) -> None:
    calls: list[tuple] = []
    cfg = Config(data=deep_merge(DEFAULTS, {"velocity": {"window_days": 1, "rolling_days": 1}}))
    graph = Graph.from_dict({"schema": 1, "groups": [], "items": []})
    monkeypatch.setattr(
        "vizzer.render.velocity.read_merge_ledger",
        lambda *args: (calls.append(args) or ([], "fixture/main", [])),
    )

    assert velocity_summary(graph, cfg, tmp_path) is velocity_summary(graph, cfg, tmp_path)
    assert len(calls) == 1
    assert velocity_summary(Graph.from_dict({"schema": 1, "groups": [], "items": []}), cfg, tmp_path)
    assert len(calls) == 2


@pytest.mark.parametrize("settings", [
    {"window_days": 0, "rolling_days": 1},
    {"window_days": 7, "rolling_days": 8},
    {"window_days": 367, "rolling_days": 7},
    {"visible_roots": ["../outside"]},
    {"log_path": "../outside.jsonl"},
])
def test_velocity_rejects_unbounded_or_escaping_configuration(tmp_path, settings) -> None:
    cfg = Config(data=deep_merge(DEFAULTS, {"velocity": settings}))

    with pytest.raises(ValueError):
        velocity_summary(Graph(vocab=cfg.vocab), cfg, tmp_path)


# Merge ledger: committed views read merges from a refresh-written ledger, never
# Git. Regression: renderers counted "(#N)" merges live, so the squash merge that
# landed a refreshed view added a PR to "today" and `check` reported it stale.

def _git(root, *args, when=None):
    env = {"GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "f@example.invalid",
           "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "f@example.invalid",
           "PATH": __import__("os").environ["PATH"]}
    if when is not None:
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S+0000")
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    subprocess.run(["git", "-C", str(root), *args], check=True, env=env, capture_output=True)


def _merge_commit(root, number, path, when):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"change {number}\n", encoding="utf-8")
    _git(root, "add", path)
    _git(root, "commit", "-qm", f"Change {number} (#{number})", when=when)


def test_union_keeps_recorded_entries_and_prunes_by_newest_merge() -> None:
    at = lambda day: datetime(2026, 9, day, 12, tzinfo=UTC)  # noqa: E731
    recorded = [velocity.Merge(1, at(1), True), velocity.Merge(2, at(10), False)]
    observed = [velocity.Merge(2, at(11), True), velocity.Merge(3, at(20), False)]
    merged = velocity.union_merges(recorded, observed, keep_days=15)
    assert [m.number for m in merged] == [2, 3]
    assert merged[0] == velocity.Merge(2, at(10), False)


def test_merge_ledger_round_trips_and_rejects_malformed_entries(tmp_path) -> None:
    path = tmp_path / "velocity-merges.json"
    merges = [velocity.Merge(7, datetime(2026, 9, 3, 1, 2, 3, tzinfo=UTC), True)]
    path.write_text(velocity.merge_ledger_text(merges, "origin/main"), encoding="utf-8")
    assert velocity.read_merge_ledger(path) == (merges, "origin/main", [])
    path.write_text(json.dumps({"schema": 1, "ref": None, "merges": [{"pr": "x"}]}), encoding="utf-8")
    read, ref, warnings = velocity.read_merge_ledger(path)
    assert (read, ref, len(warnings)) == ([], None, 1)


def test_committed_render_never_reads_git(tmp_path, monkeypatch) -> None:
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer/velocity-merges.json").write_text(velocity.merge_ledger_text(
        [velocity.Merge(41, datetime(2026, 9, 4, 20, tzinfo=UTC), True),
         velocity.Merge(42, datetime(2026, 9, 4, 21, tzinfo=UTC), False)], "origin/main"),
        encoding="utf-8")
    cfg = Config(data=deep_merge(DEFAULTS, {"velocity": {"window_days": 4, "rolling_days": 2}}))

    def tripwire(*args, **kwargs):
        raise AssertionError("committed render consulted Git")

    monkeypatch.setattr(subprocess, "run", tripwire)
    graph = Graph.from_dict({"schema": 1, "groups": [], "items": []})
    summary = velocity_summary(graph, cfg, tmp_path)
    assert summary["recent_prs"] == 2
    assert summary["merge_ref"] == "origin/main"


def test_a_merge_after_refresh_does_not_restale_the_committed_view(tmp_path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is required for the refresh fixture")
    _git(tmp_path, "init", "-q", "-b", "main")
    base = datetime.now(UTC).replace(microsecond=0) - timedelta(days=2)
    _merge_commit(tmp_path, 101, "src/a.py", base)
    _merge_commit(tmp_path, 102, "docs/b.md", base + timedelta(hours=1))
    cfg = Config(data=DEFAULTS)
    empty = {"schema": 1, "groups": [], "items": []}

    graph = Graph.from_dict(empty)
    staged = stage_merge_ledger(graph, cfg, tmp_path)
    assert staged is not None
    path, content = staged
    assert path == tmp_path / "vizzer/velocity-merges.json"
    refreshed = render_all(graph, cfg, tmp_path, only={"velocity"})["velocity.md"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    assert '"pr": 101' in content and '"pr": 102' in content

    # The squash merge that lands the refresh is a new (#N) commit.
    _merge_commit(tmp_path, 103, "vizzer/views/velocity.md", base + timedelta(hours=2))
    checked = render_all(Graph.from_dict(empty), cfg, tmp_path, only={"velocity"})["velocity.md"]
    assert checked == refreshed

    _, content = stage_merge_ledger(Graph.from_dict(empty), cfg, tmp_path)
    assert '"pr": 103' in content
