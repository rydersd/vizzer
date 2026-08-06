import subprocess
import sys
from pathlib import Path

import vizzer
from vizzer.cli import main


def test_install_vendors_and_registers(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    # strip fixture's own config so detect() writes one
    (repo / "vizzer" / "vizzer.toml").unlink()
    assert main(["install", str(repo)]) == 0
    assert (repo / "vizzer" / "engine" / "vizzer" / "model.py").exists()
    assert (repo / "vizzer" / "VERSION").read_text().strip() == vizzer.__version__
    toml = (repo / "vizzer" / "vizzer.toml").read_text()
    assert "spec_tree" in toml and "enabled = true" in toml
    gi = (repo / ".gitignore").read_text()
    assert "vizzer/archive/" in gi
    agents = (repo / "AGENTS.md").read_text()
    assert "<!-- vizzer:begin" in agents and "python3 vizzer/engine sync" in agents
    assert (repo / "vizzer" / "vizzer-graph.json").exists()      # install ran sync+render
    assert (repo / "vizzer" / "views" / "dashboard.md").exists()

    # vendored engine runs standalone via `python3 vizzer/engine`
    r = subprocess.run([sys.executable, "vizzer/engine", "check", "--structural"],
                       cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_install_twice_refuses_update_replaces(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    (repo / "vizzer" / "vizzer.toml").unlink()
    assert main(["install", str(repo)]) == 0
    assert main(["install", str(repo)]) == 2
    marker = repo / "vizzer" / "engine" / "vizzer" / "model.py"
    marker.write_text("clobbered")
    assert main(["update", str(repo)]) == 0
    assert "clobbered" not in marker.read_text()
    toml_before = (repo / "vizzer" / "vizzer.toml").read_text()
    assert (repo / "vizzer" / "vizzer.toml").read_text() == toml_before


def test_detect_finds_deeply_nested_spec_tree(tmp_path):
    from vizzer.install import detect

    deep = tmp_path / "a" / "b" / "c" / "capabilities" / "x" / "epics" / "y" / "stories"
    deep.mkdir(parents=True)
    (deep / "s.md").write_text("# Story: S\n")
    found = detect(tmp_path)
    assert found["spec_tree"]["glob"] == "a/b/c/capabilities/*/epics/*/stories/*.md"
    assert found["spec_tree"]["levels"] == ["capability", "epic"]


def test_install_reports_what_it_detected(tmp_path, make_repo, capsys):
    repo = make_repo(tmp_path, "mixed_proj")
    (repo / "vizzer" / "vizzer.toml").unlink()
    assert main(["install", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "spec_tree" in out and "ledgers" in out


def test_install_warns_when_nothing_detected(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["install", str(empty)]) == 0
    out = capsys.readouterr().out
    assert "no sources detected" in out.lower()


def test_managed_block_upsert_prefers_existing_claude_md(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    (repo / "vizzer" / "vizzer.toml").unlink()
    (repo / "CLAUDE.md").write_text("# Project rules\n")
    assert main(["install", str(repo)]) == 0
    txt = (repo / "CLAUDE.md").read_text()
    assert txt.startswith("# Project rules") and txt.count("vizzer:begin") == 1
    assert not (repo / "AGENTS.md").exists()
    assert main(["update", str(repo)]) == 0
    assert (repo / "CLAUDE.md").read_text().count("vizzer:begin") == 1   # idempotent
