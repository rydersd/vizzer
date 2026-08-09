from datetime import datetime, timedelta, timezone
import json

from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import ActiveWork, Graph, Item
from vizzer.progress_history import prepare_progress_history
import vizzer.progress_history as progress_history


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _cfg(**progress):
    return Config(data=deep_merge(DEFAULTS, {"progress": {
        "history_path": "vizzer/progress-history.json", **progress,
    }}))


def _graph(status="ready", deps=None, done=0):
    graph = Graph(items=[Item(id="story:a", title="A", status=status, deps=deps or [])])
    if done is not None:
        graph.active_work = [ActiveWork(
            story_id="story:a", agent="Ada", task="Implement", state="active",
            completed=done, total=3, updated_at="2026-08-09T12:00:00Z",
            stale_at="2026-08-09T14:00:00Z",
        )]
    return graph


def _write_history(tmp_path, content):
    path = tmp_path / "vizzer" / "progress-history.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_first_observation_is_baseline_not_false_progress_or_stall(tmp_path):
    graph = _graph(status="specced", done=None)
    staged = prepare_progress_history(graph, _cfg(), tmp_path, NOW)
    assert graph.items[0].progress == {}
    assert staged.content is not None
    payload = json.loads(staged.content)
    assert payload["items"]["story:a"]["events"] == []


def test_forward_lifecycle_and_removed_dep_make_durable_progress_events(tmp_path):
    before = _graph("ready", ["story:b"], done=1)
    first = prepare_progress_history(before, _cfg(), tmp_path, NOW)
    _write_history(tmp_path, first.content)

    after = _graph("building", [], done=2)
    staged = prepare_progress_history(after, _cfg(), tmp_path, NOW + timedelta(days=1))
    kinds = [event["kind"] for event in after.items[0].progress["events"]]
    assert kinds == ["checkpoint", "dependencies_resolved", "lifecycle"]
    assert {event["source"] for event in after.items[0].progress["events"]} == {
        "active-work checkpoint", "story Deps header", "story lifecycle header"
    }
    assert json.loads(staged.content)["items"]["story:a"]["status"] == "building"


def test_exact_hot_boundary_and_old_event_remain_low_intensity_trail(tmp_path):
    old = (NOW - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    _write_history(tmp_path, json.dumps({"schema": 1, "updatedAt": old, "items": {
        "story:a": {"status": "ready", "deps": [], "work": {}, "eligibleSince": old,
                    "eligibleSource": "recorded eligible lifecycle observation",
                    "events": [{"at": old, "kind": "lifecycle", "source": "story lifecycle header",
                                "detail": "specced → ready"}]}
    }}))
    graph = _graph("ready", done=None)
    prepare_progress_history(graph, _cfg(hot_window_days=7), tmp_path, NOW)
    event = graph.items[0].progress["events"][0]
    assert event["at"] == old
    assert graph.items[0].progress["hotWindowDays"] == 7

    graph2 = _graph("ready", done=None)
    prepare_progress_history(graph2, _cfg(hot_window_days=7), tmp_path, NOW + timedelta(seconds=1))
    assert graph2.items[0].progress == graph.items[0].progress


def test_only_recorded_started_work_can_stall_and_marker_has_exact_source(tmp_path):
    eligible = (NOW - timedelta(days=14)).isoformat().replace("+00:00", "Z")
    _write_history(tmp_path, json.dumps({"schema": 1, "updatedAt": eligible, "items": {
        "story:a": {"status": "ready", "deps": [], "work": {}, "eligibleSince": eligible,
                    "eligibleSource": "story lifecycle header", "events": []}
    }}))
    graph = _graph("ready", done=None)
    prepare_progress_history(graph, _cfg(stalled_after_days=14, stall_max_days=90), tmp_path, NOW)
    assert graph.items[0].progress["stall"] == {
        "since": eligible, "source": "story lifecycle header",
        "afterDays": 14, "maxDays": 90,
    }


def test_elapsed_time_alone_never_makes_graph_progress_stale(tmp_path):
    eligible = (NOW - timedelta(days=13)).isoformat().replace("+00:00", "Z")
    _write_history(tmp_path, json.dumps({"schema": 1, "updatedAt": eligible, "items": {
        "story:a": {"status": "ready", "deps": [], "work": {}, "eligibleSince": eligible,
                    "eligibleSource": "story lifecycle header", "events": []}
    }}))
    before = _graph("ready", done=None)
    prepare_progress_history(before, _cfg(stalled_after_days=14), tmp_path, NOW)
    after = _graph("ready", done=None)
    prepare_progress_history(after, _cfg(stalled_after_days=14), tmp_path, NOW + timedelta(days=30))
    assert before.dumps() == after.dumps()


def test_backlog_unknown_and_malformed_history_never_turn_into_false_green_or_stall(tmp_path):
    graph = _graph("backlog", done=None)
    prepare_progress_history(graph, _cfg(), tmp_path, NOW + timedelta(days=90))
    assert graph.items[0].progress == {}

    _write_history(tmp_path, "{not json")
    graph = _graph("ready", done=None)
    staged = prepare_progress_history(graph, _cfg(), tmp_path, NOW + timedelta(days=90))
    assert graph.items[0].progress == {}
    assert staged.content is None and "malformed" in graph.warnings[-1]


def test_git_backfill_reads_only_status_and_deps_headers_with_commit_provenance(tmp_path):
    old, new = "a" * 40, "b" * 40

    class Result:
        def __init__(self, stdout): self.stdout = stdout

    def fake_run(command, **_):
        if "log" in command:
            return Result(f"{new}\t2026-08-08T12:00:00+00:00\n{old}\t2026-08-07T12:00:00+00:00\n")
        reference = command[-1]
        if reference.startswith(old):
            return Result("# Story\n> Status: ready\n> Deps: story:base\nprose says delivered yesterday\n")
        return Result("# Story\n> Status: building\n> Deps: []\nprose changed, too\n")

    original = progress_history.subprocess.run
    progress_history.subprocess.run = fake_run
    try:
        graph = _graph("building", [], done=None)
        graph.items[0].source = {"adapter": "spec_tree", "path": "stories/a.md"}
        staged = prepare_progress_history(graph, _cfg(), tmp_path, NOW)
    finally:
        progress_history.subprocess.run = original

    events = graph.items[0].progress["events"]
    assert [event["kind"] for event in events] == ["dependencies_resolved", "lifecycle"]
    assert all(event["source"] == f"git story headers {new[:12]}" for event in events)
    assert json.loads(staged.content)["backfill"]["since"] == "2026-08-02T12:00:00Z"


def test_git_backfill_prose_only_commit_creates_no_progress_event(tmp_path):
    old, new = "c" * 40, "d" * 40

    class Result:
        def __init__(self, stdout): self.stdout = stdout

    def fake_run(command, **_):
        if "log" in command:
            return Result(f"{new}\t2026-08-08T12:00:00+00:00\n{old}\t2026-08-07T12:00:00+00:00\n")
        reference = command[-1]
        prose = "a completely different paragraph" if reference.startswith(new) else "old paragraph"
        return Result(f"# Story\n> Status: ready\n> Deps: []\n{prose}\n")

    original = progress_history.subprocess.run
    progress_history.subprocess.run = fake_run
    try:
        graph = _graph("ready", [], done=None)
        graph.items[0].source = {"adapter": "spec_tree", "path": "stories/a.md"}
        prepare_progress_history(graph, _cfg(), tmp_path, NOW)
    finally:
        progress_history.subprocess.run = original

    assert graph.items[0].progress["events"] == []
