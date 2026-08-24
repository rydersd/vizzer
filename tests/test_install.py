import pytest
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
    frontend = repo / "vizzer" / "engine" / "vizzer" / "render" / "constellation"
    assert (frontend / "shell.html").is_file()
    assert (frontend / "state.js").is_file()
    assert (frontend / "canvas.js").is_file()
    assert not (repo / "vizzer" / "engine" / "vizzer" / ".DS_Store").exists()
    assert (repo / "vizzer" / "VERSION").read_text().strip() == vizzer.__version__
    assert (repo / "vizzer" / "RENDER_ID").read_text().strip() == vizzer.render_id(repo)
    toml = (repo / "vizzer" / "vizzer.toml").read_text()
    assert "spec_tree" in toml and "enabled = true" in toml
    assert 'dependency_authority = ""' in toml  # codex-sequence-2026-08-08
    assert "[assessment]" in toml and "small_limit = 4" in toml
    gi = (repo / ".gitignore").read_text()
    assert "vizzer/archive/" in gi
    agents = (repo / "AGENTS.md").read_text()
    assert "<!-- vizzer:begin" in agents and "python3 vizzer/engine refresh" in agents
    assert "source story/issue/ledger first" in agents
    assert (repo / "vizzer" / "vizzer-graph.json").exists()      # install ran refresh
    assert (repo / "vizzer" / "views" / "dashboard.md").exists()
    assert (repo / "vizzer" / "docs" /
            "story-sizing-and-portfolio-selection.md").is_file()
    assert (repo / "vizzer" / "docs" /
            "prds-and-living-product-specs.md").is_file()
    assert "model-neutral" in (repo / "vizzer" / "docs" /
                               "story-sizing-and-portfolio-selection.md").read_text().casefold()

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
    context = repo / "vizzer" / "docs" / "story-sizing-and-portfolio-selection.md"
    context.write_text("stale")
    assert main(["update", str(repo)]) == 0
    assert "clobbered" not in marker.read_text()
    assert context.read_text() != "stale"
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
    assert "A shipped story stays shipped" in (repo / "CLAUDE.md").read_text()


def test_auto_install_updates_both_existing_provider_instruction_files(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    (repo / "CLAUDE.md").write_text("# Claude rules\n")
    (repo / "AGENTS.md").write_text("# Codex rules\n")
    assert main(["install", str(repo)]) == 0
    for name in ("CLAUDE.md", "AGENTS.md"):
        text = (repo / name).read_text()
        assert text.count("vizzer:begin") == 1
        assert "vizzer/views/discussion-queue.md" in text


def test_detect_finds_dag_json_for_migration(tmp_path):
    """A repo whose deps live in a DAG JSON must get dag_import wired automatically."""
    import json
    from vizzer.install import detect

    stories = tmp_path / "spec" / "capabilities" / "draw" / "epics" / "tools" / "stories"
    stories.mkdir(parents=True)
    (stories / "a.md").write_text("# Story: A\n")
    dag = tmp_path / "spec-ops" / "shaping" / ".shape-spec-dag.json"
    dag.parent.mkdir(parents=True)
    dag.write_text(json.dumps({"capabilities": [
        {"id": "CAP-draw", "epics": [{"id": "EPIC-tools", "stories": [
            {"slug": "a", "deps": ["b"]}]}]}]}))
    assert detect(tmp_path)["spec_tree"]["dag_import"] == "spec-ops/shaping/.shape-spec-dag.json"


def test_dag_only_project_enables_the_adapter(tmp_path):
    """A repo whose work lives only in a DAG must get spec_tree enabled, not disabled."""
    import json
    from vizzer.install import _config_text, detect

    dag = tmp_path / ".shape-spec-dag.json"
    dag.write_text(json.dumps({"capabilities": [
        {"id": "CAP-a", "epics": [{"id": "EPIC-b", "stories": [{"slug": "s", "deps": []}]}]}]}))
    found = detect(tmp_path)
    assert found["spec_tree"]["glob"] == ""
    assert found["spec_tree"]["dag_import"] == ".shape-spec-dag.json"
    text = _config_text(tmp_path, found)
    spec_section = text.split("[sources.spec_tree]")[1].split("[sources.")[0]
    assert "enabled = true" in spec_section


def test_loose_docs_is_a_fallback_not_an_always_on_source(tmp_path):
    """Docs are corpus, not work items.

    Auto-enabling them alongside a real spec tree drowned the views on two real
    repos (111 of 154 items on one, 738 of 1498 on another) and produced
    meaningless progress rows like `wiki/concepts 0/18`. loose_docs is the floor
    for repos that have nothing else — not an always-on adapter.
    """
    from vizzer.install import _config_text, detect

    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    (stories / "a.md").write_text("# Story: A\n\n> Status: specced\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "note.md").write_text("# Note\n")

    found = detect(tmp_path)
    assert found["spec_tree"]["glob"], "precondition: spec tree detected"
    section = _config_text(tmp_path, found).split(
        "[sources.loose_docs]")[1].split("[sources.")[0]
    assert "enabled = false" in section

    # with no spec tree, todos or ledgers, docs remain the useful fallback
    bare = tmp_path / "bare"
    (bare / "docs").mkdir(parents=True)
    (bare / "docs" / "n.md").write_text("# N\n")
    found_bare = detect(bare)
    bare_section = _config_text(bare, found_bare).split(
        "[sources.loose_docs]")[1].split("[sources.")[0]
    assert "enabled = true" in bare_section


def test_dag_detection_tolerates_alternative_nestings(tmp_path):
    """A DAG is recognized by story-like records, not by one exact key path.

    The first implementation matched only capabilities → epics → stories, so a real
    project whose DAG nested differently was silently missed and its ready queue came
    out flat and non-dependency-aware.
    """
    import json
    from vizzer.install import detect

    shapes = {
        # the real shape that was missed in the field: collections keyed by slug
        "dict_keyed": {"capabilities": {"billing": {"title": "Billing", "epics": {
            "ui": {"stories": [{"slug": "a", "deps": [], "status": "specced"}]}}}}},
        "epics_omitted": {"capabilities": [{"id": "C", "stories": [
            {"slug": "a", "deps": []}]}]},
        "top_level_stories": {"stories": [{"slug": "a", "deps": ["b"]},
                                          {"slug": "b", "deps": []}]},
        "wrapped": {"dag": {"capabilities": [{"epics": [{"stories": [
            {"slug": "a", "deps": []}]}]}]}},
    }
    for name, payload in shapes.items():
        root = tmp_path / name
        (root / "spec-ops").mkdir(parents=True)
        (root / "spec-ops" / ".shape-spec-dag.json").write_text(json.dumps(payload))
        found = detect(root)["spec_tree"]["dag_import"]
        assert found == "spec-ops/.shape-spec-dag.json", f"{name}: not detected"


def test_unrelated_json_is_not_mistaken_for_a_dag(tmp_path):
    """Shape tolerance must not turn lockfiles and configs into work-item sources."""
    import json
    from vizzer.install import detect

    (tmp_path / "package-lock.json").write_text(json.dumps(
        {"name": "x", "lockfileVersion": 3,
         "packages": {"": {"dependencies": {"left-pad": "^1.0.0"}}}}))
    (tmp_path / "tsconfig.json").write_text(json.dumps(
        {"compilerOptions": {"strict": True}, "include": ["src"]}))
    assert detect(tmp_path)["spec_tree"]["dag_import"] == ""


def test_content_manifest_with_three_slugs_is_not_mistaken_for_a_dag(tmp_path):
    import json
    from vizzer.install import detect

    (tmp_path / "content.json").write_text(json.dumps({
        "pages": [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}],
    }))

    assert detect(tmp_path)["spec_tree"]["dag_import"] == ""


@pytest.mark.skipif(sys.version_info < (3, 11),
                    reason="int digit limit only exists on 3.11+")
def test_dag_detection_skips_oversized_json_integer(tmp_path, recwarn):
    from vizzer.install import detect

    (tmp_path / "hostile.json").write_text(
        '{"stories": ['
        '{"slug": "a", "status": "ready"},'
        '{"slug": "b", "status": "ready"},'
        '{"slug": "c", "status": "ready"}'
        '], "hostile": ' + ("9" * 5000) + "}"
    )

    assert detect(tmp_path)["spec_tree"]["dag_import"] == ""
    assert any("hostile.json" in str(warning.message) for warning in recwarn)
