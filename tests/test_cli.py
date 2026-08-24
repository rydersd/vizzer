import http.client
import json, shutil
import threading
from pathlib import Path
from vizzer.cli import main
from vizzer.model import SCHEMA

GOLDEN = Path(__file__).parent / "golden" / "mixed"

def _views(root):
    return sorted((root / "vizzer" / "views").iterdir())

def test_sync_render_check_archive(tmp_path, make_repo, capsys):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "conflicts" in out
    graph = json.loads((repo / "vizzer" / "vizzer-graph.json").read_text())
    assert graph["schema"] == SCHEMA and len(graph["items"]) > 5

    assert main(["render", "--root", str(repo)]) == 0
    names = [p.name for p in _views(repo)]
    assert names == sorted(["roadmap.md", "feature-index.md", "dashboard.md",
                            "completion-sheet.md", "ledger-table.md",
                            "decision-journal.md", "discussion-queue.md", "manifest.json",
                            "constellation.html"])

    assert main(["check", "--root", str(repo), "--structural"]) == 0

    # golden comparison (deterministic thanks to fixed fixture commit dates)
    for golden in sorted(GOLDEN.iterdir()):
        produced = (repo / "vizzer" / ("vizzer-graph.json" if golden.name == "vizzer-graph.json"
                                       else f"views/{golden.name}")).read_text()
        assert produced == golden.read_text(), f"drift in {golden.name}"

    # archive: default scope is todos only, requires --yes
    assert main(["archive", "--root", str(repo)]) == 1
    assert (repo / "TODO.md").exists()
    assert main(["archive", "--root", str(repo), "--yes"]) == 0
    assert not (repo / "TODO.md").exists()
    assert (repo / "vizzer" / "archive" / "TODO.md").exists()

def test_render_without_graph_errors(tmp_path, make_repo, capsys):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["render", "--root", str(repo)]) == 2
    assert "sync" in capsys.readouterr().out


def test_open_rejects_unknown_graph_item_without_launching(tmp_path, make_repo, capsys, monkeypatch):
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    monkeypatch.setattr(cli, "_open_source", lambda source: (_ for _ in ()).throw(
        AssertionError("unknown item launched an opener")
    ))

    assert main(["open", "story:missing", "--root", str(repo)]) == 2
    assert "unknown item" in capsys.readouterr().out


def test_open_rejects_graph_source_escape_and_missing_file(tmp_path, make_repo, capsys, monkeypatch):
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    graph_path = repo / "vizzer" / "vizzer-graph.json"
    graph = json.loads(graph_path.read_text())
    target = next(item for item in graph["items"] if item["id"] == "story:canvas-core")
    target["source"]["path"] = "../outside.md"
    graph_path.write_text(json.dumps(graph))
    monkeypatch.setattr(cli, "_open_source", lambda source: (_ for _ in ()).throw(
        AssertionError("outside source launched an opener")
    ))

    assert main(["open", "story:canvas-core", "--root", str(repo)]) == 2
    assert "outside the project" in capsys.readouterr().out

    target["source"]["path"] = "missing.md"
    graph_path.write_text(json.dumps(graph))
    assert main(["open", "story:canvas-core", "--root", str(repo)]) == 2
    assert "unavailable" in capsys.readouterr().out


def test_open_uses_platform_default_app_with_only_the_resolved_source(tmp_path, make_repo, monkeypatch):
    import sys
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda args, check: calls.append((args, check)))

    assert main(["open", "story:canvas-core", "--root", str(repo)]) == 0
    source = (repo / "spec/drawing/epics/tools/stories/canvas-core.md").resolve()
    expected = "open" if sys.platform == "darwin" else "xdg-open"
    assert calls == [([expected, str(source)], True)]


def test_loopback_serve_open_endpoint_accepts_only_known_item_ids(tmp_path, make_repo, monkeypatch):
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    assert main(["render", "--root", str(repo)]) == 0
    graph = cli._read_graph(repo)
    opened = []
    monkeypatch.setattr(cli, "_open_source", lambda source: opened.append(source))
    server = cli._make_serve_server(repo, graph, repo / "vizzer" / "views", 0)
    assert server.server_address[0] == "127.0.0.1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address[:2], timeout=2)
        connection.request("POST", "/api/open/story%3Acanvas-core")
        response = connection.getresponse()
        assert response.status == 200
        response.read()
        connection.request("POST", "/api/open/capability%3Adrawing")
        response = connection.getresponse()
        assert response.status == 200
        response.read()
        connection.request("POST", "/api/open/story%3Amissing")
        response = connection.getresponse()
        assert response.status == 404
        response.read()
        connection.request("POST", "/api/open/story%3Acanvas-core?path=../outside.md")
        response = connection.getresponse()
        assert response.status == 404
        response.read()
        connection.request("GET", "/api/open/story%3Acanvas-core")
        response = connection.getresponse()
        assert response.status == 405
        response.read()
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 302
        assert response.getheader("Location") == "/constellation.html"
        response.read()
        connection.request("GET", "/?v=review-smoke")
        response = connection.getresponse()
        assert response.status == 302
        assert response.getheader("Location") == "/constellation.html?v=review-smoke"
        response.read()
        connection.request("GET", "/constellation.html")
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/html; charset=utf-8"
        html = response.read().decode("utf-8")
        assert html.startswith('<meta charset="utf-8">')
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert opened == [
        (repo / "spec/drawing/epics/tools/stories/canvas-core.md").resolve(),
        (repo / "spec/drawing/drawing.md").resolve(),
    ]


def test_serve_can_open_the_constellation_in_the_system_browser(
    tmp_path, make_repo, monkeypatch, capsys
):
    """codex-sequence-2026-08-08: one command enables default-app story opening."""
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    assert main(["render", "--root", str(repo)]) == 0
    capsys.readouterr()

    class FakeServer:
        server_address = ("127.0.0.1", 43123)
        closed = False

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    server = FakeServer()
    opened = []
    monkeypatch.setattr(cli, "_make_serve_server", lambda *args: server)
    monkeypatch.setattr(cli, "_open_browser", opened.append)

    assert main([
        "serve", "--root", str(repo), "--port", "0", "--open-browser"
    ]) == 0
    assert opened == ["http://127.0.0.1:43123/constellation.html"]
    assert server.closed
    assert "serve: http://127.0.0.1:43123/constellation.html" in capsys.readouterr().out


def test_serve_uses_configured_port_and_cli_override(
    tmp_path, make_repo, monkeypatch, capsys
):
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer" / "vizzer.toml"
    config.write_text(config.read_text() + "\n[server]\nport = 43124\n")
    assert main(["sync", "--root", str(repo)]) == 0
    assert main(["render", "--root", str(repo)]) == 0
    capsys.readouterr()

    ports = []

    class FakeServer:
        server_address = ("127.0.0.1", 43124)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    def make_server(root, graph, views, port, cfg):
        ports.append(port)
        return FakeServer()

    monkeypatch.setattr(cli, "_make_serve_server", make_server)
    assert main(["serve", "--root", str(repo)]) == 0
    assert main(["serve", "--root", str(repo), "--port", "0"]) == 0
    assert ports == [43124, 0]


def test_refresh_syncs_and_renders_one_fresh_graph(tmp_path, make_repo, capsys):
    """The normal lifecycle command leaves one coherent graph/view snapshot."""
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["refresh", "--root", str(repo)]) == 0
    output = capsys.readouterr().out
    assert "refresh:" in output and "wrote 9 files" in output
    assert (repo / "vizzer" / "vizzer-graph.json").is_file()
    assert main(["check", "--root", str(repo), "--structural"]) == 0


def test_check_rejects_partial_install_with_stale_version_marker(
    tmp_path, make_repo, capsys
):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["refresh", "--root", str(repo)]) == 0
    capsys.readouterr()
    marker = repo / "vizzer" / "VERSION"
    marker.write_text("0.0.0\n", encoding="utf-8")

    assert main(["check", "--root", str(repo)]) == 1
    assert "stale: vizzer/VERSION" in capsys.readouterr().out


def test_refresh_does_not_render_a_stale_graph_when_sync_fails(
    tmp_path, make_repo, capsys
):
    """codex-sequence-2026-08-08: a failed build must not re-render old state."""
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["refresh", "--root", str(repo)]) == 0
    capsys.readouterr()
    graph_path = repo / "vizzer" / "vizzer-graph.json"
    dashboard_path = repo / "vizzer" / "views" / "dashboard.md"
    previous_graph = graph_path.read_text()
    previous_dashboard = dashboard_path.read_text()

    config_path = repo / "vizzer" / "vizzer.toml"
    config_path.write_text(config_path.read_text() + '''
[[status]]
name = "building"
emoji = "🔧"
done = false
next = ["not-configured"]
''')

    assert main(["refresh", "--root", str(repo)]) == 2
    output = capsys.readouterr().out
    assert "refresh: configuration error" in output
    assert "wrote" not in output
    assert graph_path.read_text() == previous_graph
    assert dashboard_path.read_text() == previous_dashboard


def test_decisions_command_backfills_story_evolution_event(
    tmp_path, make_repo, capsys
):
    from vizzer.config import Config
    from vizzer.cli import _read_graph
    from vizzer.model import owner_question_fingerprint
    from vizzer.question_answers import append_answer

    repo = make_repo(tmp_path, "mixed_proj")
    config_path = repo / "vizzer/vizzer.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + '\n[activity]\npath = "vizzer/active-work.json"\n',
        encoding="utf-8",
    )
    (repo / "vizzer/active-work.json").write_text(json.dumps({
        "schema": 1,
        "work": [],
        "questions": [{
            "id": "question:route",
            "storyId": "story:canvas-core",
            "owner": "Ryder",
            "prompt": "Which route wins?",
            "options": [
                {"id": "shared", "label": "Shared", "tradeoff": "Portable."},
                {"id": "native", "label": "Native", "tradeoff": "Coupled."},
            ],
            "recommendation": {
                "optionId": "shared", "rationale": "One truth path.",
            },
            "falsifier": "A required surface cannot consume it.",
            "evidence": ["spec/canvas-core.md"],
        }],
    }), encoding="utf-8")
    assert main(["refresh", "--root", str(repo)]) == 0
    graph = _read_graph(repo)
    question = graph.owner_questions[0]
    append_answer(
        graph, Config.load(repo), repo, question.id,
        expected_revision=0,
        expected_fingerprint=owner_question_fingerprint(question),
        kind="option", option_id="shared",
    )
    story = repo / "spec/drawing/epics/tools/stories/canvas-core.md"
    before = story.read_bytes()

    assert main(["decisions", "--all", "--root", str(repo)]) == 1
    assert story.read_bytes() == before
    assert "rerun with --yes" in capsys.readouterr().out

    assert main([
        "decisions", "--all", "--yes", "--root", str(repo)
    ]) == 0
    text = story.read_text(encoding="utf-8")
    assert "question:route" in text
    assert "## Evolution event — owner decision" in text
    assert main(["check", "--root", str(repo)]) == 0

    assert main([
        "decisions", "question:route", "--apply",
        "--summary", "Routed the real output through the shared authority.",
        "--evidence", "src/shared.py", "--root", str(repo),
    ]) == 1
    assert "rerun with --yes" in capsys.readouterr().out
    assert main([
        "decisions", "question:route", "--apply",
        "--summary", "Routed the real output through the shared authority.",
        "--evidence", "src/shared.py", "--yes", "--root", str(repo),
    ]) == 0
    text = story.read_text(encoding="utf-8")
    assert "## Decision application — question:route" in text
    assert "Routed the real output through the shared authority." in text
    journal = (repo / "vizzer/views/decision-journal.md").read_text(encoding="utf-8")
    assert "Normative application:** applied" in journal
    assert main(["check", "--root", str(repo)]) == 0


def test_refresh_renderer_failure_does_not_publish_graph_without_views(
    tmp_path, make_repo, capsys, monkeypatch
):
    """codex-sequence-2026-08-08: render failure is before the snapshot commit."""
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["refresh", "--root", str(repo)]) == 0
    capsys.readouterr()
    graph_path = repo / "vizzer" / "vizzer-graph.json"
    dashboard_path = repo / "vizzer" / "views" / "dashboard.md"
    before = {path: path.read_bytes() for path in (graph_path, dashboard_path)}

    def broken_renderer(*args, **kwargs):
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(cli, "render_all", broken_renderer)
    assert main(["refresh", "--root", str(repo)]) == 2
    output = capsys.readouterr().out
    assert "renderer exploded" in output
    assert "traceback" not in output.lower()
    assert {path: path.read_bytes() for path in before} == before


def test_refresh_rolls_back_when_a_view_replace_fails(
    tmp_path, make_repo, capsys, monkeypatch
):
    """codex-sequence-2026-08-08: one failed view cannot leave a mixed snapshot."""
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["refresh", "--root", str(repo)]) == 0
    capsys.readouterr()
    artifacts = [repo / "vizzer" / "vizzer-graph.json"] + sorted(
        (repo / "vizzer" / "views").iterdir()
    )
    before = {path: path.read_bytes() for path in artifacts}
    real_replace = cli.os.replace

    def fail_dashboard(source, destination):
        if Path(destination).name == "dashboard.md" and ".bak." not in str(source):
            raise OSError("simulated dashboard replacement failure")
        return real_replace(source, destination)

    monkeypatch.setattr(cli.os, "replace", fail_dashboard)
    assert main(["refresh", "--root", str(repo)]) == 2
    output = capsys.readouterr().out
    assert "could not write derived artifacts" in output
    assert {path: path.read_bytes() for path in before} == before


def test_sync_adapter_failure_is_a_clean_error_and_preserves_graph(
    tmp_path, make_repo, capsys, monkeypatch
):
    """codex-sequence-2026-08-08: extension failures do not traceback or truncate graph."""
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    capsys.readouterr()
    graph_path = repo / "vizzer" / "vizzer-graph.json"
    before = graph_path.read_bytes()

    monkeypatch.setattr(cli, "_build", lambda *args: (_ for _ in ()).throw(RuntimeError("adapter exploded")))
    assert main(["sync", "--root", str(repo)]) == 2
    output = capsys.readouterr().out
    assert "adapter exploded" in output
    assert "traceback" not in output.lower()
    assert graph_path.read_bytes() == before


def test_archive_refuses_paths_outside_the_project(tmp_path, make_repo):
    """A source glob may resolve outside the root; archiving must never move such files in."""
    import json
    repo = make_repo(tmp_path, "mixed_proj")
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "TODO.md"
    victim.write_text("# outside\n\n- [ ] do not move me\n")

    assert main(["sync", "--root", str(repo)]) == 0
    graph_path = repo / "vizzer" / "vizzer-graph.json"
    graph = json.loads(graph_path.read_text())
    graph["items"].append({
        "id": "todo:evil/01-x", "title": "x", "one_liner": None, "status": "backlog",
        "release": None, "wave": None, "group": None, "deps": [], "appetite": None,
        "flags": [], "source": {"adapter": "todos", "path": "../outside/TODO.md"},
        "activity": {}})
    graph_path.write_text(json.dumps(graph, indent=2) + "\n")

    main(["archive", "--root", str(repo), "--yes"])
    assert victim.exists(), "archive moved a file from outside the project"
    assert not (repo / "vizzer" / "archive" / ".." / "outside" / "TODO.md").exists()


def test_archive_does_not_silently_overwrite_an_existing_archived_file(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    archived = repo / "vizzer" / "archive" / "TODO.md"
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_text("PRECIOUS EARLIER ARCHIVE\n")

    main(["archive", "--root", str(repo), "--yes"])
    assert "PRECIOUS EARLIER ARCHIVE" in archived.read_text()


def test_malformed_graph_degrades_instead_of_crashing(tmp_path, make_repo, capsys):
    """A corrupt or non-dict graph file must produce a clear error, never a traceback."""
    repo = make_repo(tmp_path, "mixed_proj")
    graph_path = repo / "vizzer" / "vizzer-graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)

    for payload in ("null", "[]", "{not json", '{"schema": 1, "items": "nope"}'):
        graph_path.write_text(payload)
        for verb in ("render", "check", "archive"):
            args = [verb, "--root", str(repo)]
            if verb == "archive":
                args.append("--yes")
            code = main(args)          # must not raise
            assert code != 0, f"{verb} accepted malformed graph {payload!r}"
        out = capsys.readouterr().out.lower()
        assert "graph" in out


def test_output_dir_cannot_escape_the_project(tmp_path, make_repo, capsys):
    """render must refuse an output_dir outside the project, per the documented safety claim."""
    repo = make_repo(tmp_path, "mixed_proj")
    cfg = repo / "vizzer" / "vizzer.toml"
    cfg.write_text(cfg.read_text() + '\n[render]\noutput_dir = "../escaped"\n')
    assert main(["sync", "--root", str(repo)]) == 0
    code = main(["render", "--root", str(repo)])
    assert code != 0
    assert not (tmp_path / "escaped").exists()


def test_check_rejects_an_output_dir_outside_the_project(tmp_path, make_repo, capsys):
    """codex-sequence-2026-08-08: check shares render's path safety boundary."""
    repo = make_repo(tmp_path, "mixed_proj")
    cfg = repo / "vizzer" / "vizzer.toml"
    cfg.write_text(cfg.read_text() + '\n[render]\noutput_dir = "../escaped-check"\n')
    assert main(["sync", "--root", str(repo)]) == 0
    assert main(["check", "--root", str(repo)]) == 2
    assert "outside the project" in capsys.readouterr().out
    assert not (tmp_path / "escaped-check").exists()


def test_check_accepts_documented_relative_dot_root(
    tmp_path, make_repo, monkeypatch
):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["refresh", "--root", str(repo)]) == 0
    monkeypatch.chdir(repo)

    assert main(["check", "--root", "."]) == 0


def test_structural_check_ignores_activity_only_changes(tmp_path, make_repo):
    """An unrelated commit changes commit counts; --structural must not fail on that alone."""
    import subprocess
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    assert main(["render", "--root", str(repo)]) == 0
    assert main(["check", "--root", str(repo), "--structural"]) == 0

    # a commit that touches a tracked doc without changing any graph structure
    doc = repo / "docs" / "roadmap-notes.md"
    doc.write_text(doc.read_text() + "\n<!-- inert -->\n")
    g = ["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fx@example.com"]
    subprocess.run(g + ["add", "-A"], check=True, capture_output=True)
    subprocess.run(g + ["commit", "-m", "inert"], check=True, capture_output=True)

    assert main(["check", "--root", str(repo), "--structural"]) == 0, \
        "structural check failed on activity-only drift"


def test_check_rejects_unlinked_blocker_unless_exact_revision_is_grandfathered(
    tmp_path, make_repo, capsys,
):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        + '\n[activity]\npath = "vizzer/active-work.json"\n'
        + "stale_after_minutes = 30\n",
        encoding="utf-8",
    )
    record = {
        "storyId": "story:canvas-core", "agent": "Agent",
        "task": "Legacy block", "state": "blocked",
        "checkpoints": {"completed": 0, "total": 1},
        "updatedAt": "2026-08-08T17:00:00Z",
    }
    (repo / "vizzer/active-work.json").write_text(json.dumps({
        "schema": 1, "work": [record],
    }), encoding="utf-8")
    assert main(["sync", "--root", str(repo)]) == 0
    assert main(["render", "--root", str(repo)]) == 0
    capsys.readouterr()

    assert main(["check", "--root", str(repo)]) == 1
    output = capsys.readouterr().out
    assert "unresolved blocker [unlinked]" in output
    assert "add an owner question" in output

    (repo / "vizzer/blocked-gate-grandfathered.json").write_text(json.dumps({
        "schema": 1,
        "records": [{
            "storyId": record["storyId"], "agent": record["agent"],
            "task": record["task"], "updatedAt": record["updatedAt"],
        }],
    }), encoding="utf-8")
    assert main(["check", "--root", str(repo)]) == 0
    assert "1 grandfathered blocked-record" in capsys.readouterr().out


def test_question_age_budget_warns_and_optionally_fails_check(
    tmp_path, make_repo, capsys,
):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        + '\n[activity]\npath = "vizzer/active-work.json"\n'
        + '\n[questions]\nanswers_path = "vizzer/question-answers.json"\n'
        + "age_budget_hours = 1\nage_budget_hard_fail = true\n",
        encoding="utf-8",
    )
    question = {
        "id": "question:old-route", "storyId": "story:canvas-core",
        "owner": "Owner", "prompt": "Which route?",
        "raisedAt": "2026-08-01T00:00:00Z",
        "options": [
            {"id": "one", "label": "One", "tradeoff": "Lower coupling."},
            {"id": "two", "label": "Two", "tradeoff": "Faster delivery."},
        ],
        "recommendation": {"optionId": "one", "rationale": "One authority."},
        "falsifier": "The route cannot meet the contract.",
        "evidence": ["spec/story.md:12"],
    }
    (repo / "vizzer/active-work.json").write_text(json.dumps({
        "schema": 1, "work": [], "questions": [question],
    }), encoding="utf-8")
    assert main(["refresh", "--root", str(repo)]) == 0
    capsys.readouterr()

    assert main(["check", "--root", str(repo)]) == 1
    assert "WARNING overdue owner question question:old-route" in capsys.readouterr().out

    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "age_budget_hard_fail = true", "age_budget_hard_fail = false"
        ),
        encoding="utf-8",
    )
    assert main(["check", "--root", str(repo)]) == 0
    assert "WARNING overdue owner question" in capsys.readouterr().out


def test_source_links_resolve_from_a_deeper_output_dir(tmp_path, make_repo):
    """Link depth must follow output_dir, not a hardcoded two levels."""
    repo = make_repo(tmp_path, "mixed_proj")
    cfg = repo / "vizzer" / "vizzer.toml"
    cfg.write_text(cfg.read_text() + '\n[render]\noutput_dir = "vizzer/views/deep"\n')
    assert main(["sync", "--root", str(repo)]) == 0
    assert main(["render", "--root", str(repo)]) == 0
    roadmap = (repo / "vizzer" / "views" / "deep" / "roadmap.md").read_text()
    link = [l for l in roadmap.splitlines() if "canvas-core" in l and "](" in l][0]
    target = link.split("](")[1].split(")")[0]
    resolved = (repo / "vizzer" / "views" / "deep" / target).resolve()
    assert resolved.exists(), f"broken link {target!r} from a deeper output dir"


def test_sync_hints_when_a_spec_tree_yields_no_dependency_edges(tmp_path, make_repo, capsys):
    """Zero edges across many items almost always means deps live in a DAG file.

    Two real deployments silently produced a flat, non-dependency-aware ready queue
    because dag_import was never set; nothing in the output said so.
    """
    repo = make_repo(tmp_path, "spec_proj")
    (repo / "vizzer").mkdir(parents=True, exist_ok=True)
    (repo / "vizzer" / "vizzer.toml").write_text(
        '[sources.spec_tree]\nenabled = true\n'
        'glob = "spec/*/epics/*/stories/*.md"\nlevels = ["capability", "epic"]\n')
    # strip the Deps: line so the tree has items but no edges
    story = repo / "spec/drawing/epics/tools/stories/snap-to-grid.md"
    story.write_text("\n".join(l for l in story.read_text().splitlines()
                               if not l.startswith("> Deps:")))
    # the hint only fires above a small-project threshold, so add a few more stories
    stories_dir = repo / "spec/drawing/epics/tools/stories"
    for n in range(4):
        (stories_dir / f"extra-{n}.md").write_text(
            f"# Story: Extra {n}\n\n> Status: specced · Release: R0\n")
    assert main(["sync", "--root", str(repo)]) == 0
    out = capsys.readouterr().out.lower()
    assert "dag_import" in out and "dependenc" in out


def test_sync_warns_when_a_source_directory_is_gitignored(tmp_path, make_repo, capsys):
    """Views derived from ignored files cannot be reproduced by CI or teammates."""
    repo = make_repo(tmp_path, "mixed_proj")
    (repo / ".gitignore").write_text("thoughts/\n")
    assert main(["sync", "--root", str(repo)]) == 0
    out = capsys.readouterr().out.lower()
    assert "gitignore" in out and "thoughts" in out


def test_render_rejects_cyclic_group_graph_without_traceback(tmp_path, make_repo, capsys):
    repo = make_repo(tmp_path, "mixed_proj")
    graph_path = repo / "vizzer" / "vizzer-graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps({
        "schema": 1,
        "groups": [
            {"id": "epic:a", "kind": "epic", "title": "A", "parent": "epic:b"},
            {"id": "epic:b", "kind": "epic", "title": "B", "parent": "epic:a"},
        ],
        "items": [],
    }))

    assert main(["render", "--root", str(repo)]) != 0
    captured = capsys.readouterr()
    assert "cycle" in captured.out.lower()
    assert "traceback" not in (captured.out + captured.err).lower()


def test_archive_refuses_symlink_archive_directory(tmp_path, make_repo, capsys):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    capsys.readouterr()
    outside = tmp_path / "outside-archive"
    outside.mkdir()
    archive = repo / "vizzer" / "archive"
    archive.symlink_to(outside, target_is_directory=True)

    assert main(["archive", "--root", str(repo), "--yes"]) != 0

    assert (repo / "TODO.md").is_file()
    assert list(outside.iterdir()) == []
    assert "symlink" in capsys.readouterr().out.lower()


def test_archive_fallback_rechecks_for_symlink_swap(
    tmp_path, make_repo, capsys, monkeypatch
):
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    capsys.readouterr()
    archive = repo / "vizzer" / "archive"
    outside = tmp_path / "outside-fallback"
    outside.mkdir()
    real_islink = cli.os.path.islink
    archive_checks = 0

    def swap_before_final_check(path):
        nonlocal archive_checks
        if Path(path) == archive:
            archive_checks += 1
            if archive_checks == 3:
                archive.rmdir()
                archive.symlink_to(outside, target_is_directory=True)
        return real_islink(path)

    monkeypatch.setattr(cli, "_archive_dir_fd_supported", lambda: False)
    monkeypatch.setattr(cli.os.path, "islink", swap_before_final_check)

    main(["archive", "--root", str(repo), "--yes"])

    assert (repo / "TODO.md").is_file()
    assert list(outside.iterdir()) == []
    assert "warning" in capsys.readouterr().out.lower()
