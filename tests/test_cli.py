import json, shutil
from pathlib import Path
from vizzer.cli import main

GOLDEN = Path(__file__).parent / "golden" / "mixed"

def _views(root):
    return sorted((root / "vizzer" / "views").iterdir())

def test_sync_render_check_archive(tmp_path, make_repo, capsys):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "conflicts" in out
    graph = json.loads((repo / "vizzer" / "vizzer-graph.json").read_text())
    assert graph["schema"] == 1 and len(graph["items"]) > 5

    assert main(["render", "--root", str(repo)]) == 0
    names = [p.name for p in _views(repo)]
    assert names == sorted(["roadmap.md", "feature-index.md", "dashboard.md",
                            "completion-sheet.md", "ledger-table.md",
                            "manifest.json", "constellation.html"])

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
