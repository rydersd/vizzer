import json

from vizzer.cli import main


def test_plan_cli_analyzes_applies_rejects_stale_and_undoes(
    tmp_path, make_repo, capsys
):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(config.read_text() + "\n[planning]\nenabled = true\n")

    assert main([
        "plan", "analyze", "--root", str(repo),
        "--promote", "story:canvas-core", "--order", "story:canvas-core",
    ]) == 0
    analyzed = capsys.readouterr().out
    assert '"baseRevision": 0' in analyzed
    assert not (repo / "vizzer/planning-overlay.json").exists()

    assert main([
        "plan", "apply", "--root", str(repo),
        "--promote", "story:canvas-core", "--order", "story:canvas-core",
        "--expected-revision", "0", "--rationale", "Customer proof first",
    ]) == 0
    capsys.readouterr()
    overlay = json.loads((repo / "vizzer/planning-overlay.json").read_text())
    assert overlay["revision"] == 1
    assert overlay["state"]["promote"] == ["story:canvas-core"]

    assert main([
        "plan", "apply", "--root", str(repo),
        "--expected-revision", "0", "--rationale", "stale",
    ]) == 3
    assert "stale planning revision" in capsys.readouterr().out

    assert main([
        "plan", "undo", "--root", str(repo), "--expected-revision", "1",
        "--rationale", "Restore accepted course",
    ]) == 0
    capsys.readouterr()
    undone = json.loads((repo / "vizzer/planning-overlay.json").read_text())
    assert undone["revision"] == 2
    assert undone["state"] == {"promote": [], "defer": [], "order": []}


def test_plan_apply_rolls_back_overlay_when_derived_refresh_fails(
    tmp_path, make_repo, monkeypatch, capsys
):
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(config.read_text() + "\n[planning]\nenabled = true\n")
    monkeypatch.setattr(cli, "_refresh", lambda root: 2)

    assert main([
        "plan", "apply", "--root", str(repo),
        "--promote", "story:canvas-core", "--expected-revision", "0",
        "--rationale", "This must roll back",
    ]) == 2

    overlay = json.loads((repo / "vizzer/planning-overlay.json").read_text())
    assert overlay["revision"] == 0
    assert overlay["state"] == {"promote": [], "defer": [], "order": []}
    assert "rolled back" in capsys.readouterr().out
