from datetime import datetime, timedelta, timezone
import json

from vizzer import cli
from vizzer.cli import main
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


def _history_repo(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer" / "vizzer.toml"
    config.write_text(config.read_text() + '\n[progress]\nhistory_path = "vizzer/progress-history.json"\n',
                      encoding="utf-8")
    return repo, repo / "spec/drawing/epics/tools/stories/snap-to-grid.md"


def _snap_record(repo):
    graph = json.loads((repo / "vizzer" / "vizzer-graph.json").read_text())
    item = next(item for item in graph["items"] if item["id"].endswith("snap-to-grid"))
    history = json.loads((repo / "vizzer" / "progress-history.json").read_text())
    return item, history["items"][item["id"]]


def test_shipped_story_with_later_non_withdrawing_edits_stays_shipped(tmp_path, make_repo):
    # Shipped is withdrawn only by the project's lifecycle policy (a status
    # header edit). Body and Deps edits that keep the header leave the story
    # shipped and record no lifecycle event. Driven through the real parser.
    repo, story = _history_repo(tmp_path, make_repo)
    story.write_text(story.read_text().replace("> Status: building", "> Status: shipped"), encoding="utf-8")
    assert main(["refresh", "--root", str(repo)]) == 0
    item, _ = _snap_record(repo)
    assert item["status"] == "shipped"

    story.write_text(story.read_text()
                     .replace("> Deps: canvas-core", "> Deps: []")
                     .replace("configured grid.", "configured grid, with a new paragraph of detail."),
                     encoding="utf-8")
    assert main(["refresh", "--root", str(repo)]) == 0
    item, record = _snap_record(repo)
    assert item["status"] == "shipped"
    assert record["status"] == "shipped"
    assert not item["deps"]
    assert [event for event in record["events"] if event["kind"] == "lifecycle"] == []


def test_check_never_writes_the_ledger_and_stamps_an_unpersisted_flip_at_its_updated_at(
    tmp_path, make_repo, capsys, monkeypatch
):
    repo, story = _history_repo(tmp_path, make_repo)
    story.write_text(story.read_text().replace("> Status: building", "> Status: ready"), encoding="utf-8")
    assert main(["refresh", "--root", str(repo)]) == 0
    ledger = repo / "vizzer" / "progress-history.json"
    # Age the ledger so a clock-stamped event can never equal its updatedAt.
    anchor = "2026-01-01T00:00:00Z"
    aged = json.loads(ledger.read_text())
    aged["updatedAt"] = anchor
    ledger.write_text(json.dumps(aged), encoding="utf-8")
    before = ledger.read_bytes()

    staged = []
    real = cli.prepare_progress_history

    def recording(*args, **kwargs):
        result = real(*args, **kwargs)
        staged.append(result.content)
        return result

    monkeypatch.setattr(cli, "prepare_progress_history", recording)
    story.write_text(story.read_text().replace("> Status: ready", "> Status: building"), encoding="utf-8")
    outputs = []
    for _ in range(2):
        capsys.readouterr()
        outputs.append((main(["check", "--root", str(repo)]), capsys.readouterr().out))
        assert ledger.read_bytes() == before, "check must never write the progress ledger"

    assert outputs[0] == outputs[1] and outputs[0][0] == 1
    assert "stale: vizzer/progress-history.json" in outputs[0][1]
    assert len(staged) == 2 and staged[0] == staged[1], "two consecutive checks must agree"
    events = json.loads(staged[0])["items"]
    flip = [event for record in events.values() for event in record["events"]
            if event["kind"] == "lifecycle" and event["detail"] == "ready → building"]
    assert [event["at"] for event in flip] == [anchor]


def test_non_observer_without_persisted_updated_at_stages_nothing(tmp_path):
    graph = _graph("building", done=1)
    staged = prepare_progress_history(graph, _cfg(), tmp_path, observer=False)
    assert staged.content is None
    assert any("has no updatedAt yet" in warning for warning in graph.warnings)
