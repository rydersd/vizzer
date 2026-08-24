import subprocess
import sys
import zipfile
import json
import re
from pathlib import Path

import vizzer

ROOT = Path(__file__).parent.parent
FRONTEND_RESOURCES = {
    "vizzer/render/constellation/shell.html",
    "vizzer/render/constellation/tokens.css",
    "vizzer/render/constellation/layout.css",
    "vizzer/render/constellation/views.css",
    "vizzer/render/constellation/boot.js",
    "vizzer/render/constellation/state.js",
    "vizzer/render/constellation/view_query.js",
    "vizzer/render/constellation/chrome_layout.js",
    "vizzer/render/constellation/filters.js",
    "vizzer/render/constellation/views.js",
    "vizzer/render/constellation/dossier.js",
    "vizzer/render/constellation/questions.js",
    "vizzer/render/constellation/planning.js",
    "vizzer/render/constellation/canvas.js",
    "vizzer/render/constellation/bootstrap.js",
}
DEVELOPER_FLOW_RESOURCES = {
    "vizzer/render/developer_flow_assets/shell.html",
    "vizzer/render/developer_flow_assets/app.css",
    "vizzer/render/developer_flow_assets/app.js",
    "vizzer/render/developer_flow_assets/THIRD_PARTY_NOTICES.md",
    "vizzer/render/developer_flow_assets/third-party/REACT_FLOW_LICENSE.txt",
    "vizzer/render/developer_flow_assets/third-party/REACT_LICENSE.txt",
    "vizzer/render/developer_flow_assets/third-party/REACT_DOM_LICENSE.txt",
    "vizzer/render/developer_flow_assets/third-party/ELKJS_LICENSE.md",
}


def test_project_metadata_matches_runtime_version():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', project, re.MULTILINE)
    assert match is not None
    assert match.group(1) == vizzer.__version__


def test_build_pyz(tmp_path):
    out = tmp_path / "vizzer.pyz"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_pyz.py"), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert "__main__.py" in names and "vizzer/model.py" in names
    assert "vizzer/assessment.py" in names
    assert "vizzer/discussion_queue.py" in names
    assert "vizzer/developer_store.py" in names
    assert "vizzer/context/story-sizing-and-portfolio-selection.md" in names
    assert "vizzer/context/prds-and-living-product-specs.md" in names
    assert FRONTEND_RESOURCES <= set(names)
    assert DEVELOPER_FLOW_RESOURCES <= set(names)
    assert not any(
        name.endswith((".DS_Store", ".pyc", ".pyo")) or ".egg-info/" in name
        for name in names
    )
    r2 = subprocess.run([sys.executable, str(out), "--help"], capture_output=True, text=True)
    assert r2.returncode == 0 and "sync" in r2.stdout


def test_install_from_pyz(tmp_path):
    """The published .pyz must be able to install itself — the primary distribution path."""
    pyz = tmp_path / "vizzer.pyz"
    build = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_pyz.py"), str(pyz)],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stderr

    project = tmp_path / "proj"
    project.mkdir()
    (project / "TODO.md").write_text("# TODO\n\n- [ ] Ship it\n")

    r = subprocess.run([sys.executable, str(pyz), "install", str(project)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (project / "vizzer" / "engine" / "vizzer" / "model.py").exists()
    assert (project / "vizzer" / "engine" / "vizzer" / "assessment.py").exists()
    assert (project / "vizzer" / "engine" / "vizzer" / "discussion_queue.py").exists()
    assert (project / "vizzer" / "engine" / "vizzer" / "developer_store.py").exists()
    installed_frontend = project / "vizzer" / "engine" / "vizzer" / "render" / "constellation"
    for relative in FRONTEND_RESOURCES:
        assert (installed_frontend / Path(relative).name).is_file()
    installed_developer_flow = (
        project / "vizzer" / "engine" / "vizzer" / "render" / "developer_flow_assets"
    )
    for relative in DEVELOPER_FLOW_RESOURCES:
        parts = Path(relative).parts
        suffix = Path(*parts[parts.index("developer_flow_assets") + 1:])
        assert (installed_developer_flow / suffix).is_file()
    assert (project / "vizzer" / "views" / "dashboard.md").exists()
    assert (project / "vizzer" / "views" / "discussion-queue.md").exists()
    assert (project / "vizzer" / "docs" /
            "story-sizing-and-portfolio-selection.md").exists()
    assert (project / "vizzer" / "docs" /
            "prds-and-living-product-specs.md").exists()
    config = (project / "vizzer" / "vizzer.toml").read_text()
    assert "[assessment]" in config and "enabled = true" in config
    assert "[discussions]" in config and 'queue_path = "vizzer/discussion-queue.json"' in config
    assert "[developer_flow]" in config
    assert "enabled = false" in config
    graph = json.loads((project / "vizzer" / "vizzer-graph.json").read_text())
    assert graph["assessment"]["method"] == "deterministic-delivery-assessment-v1"

    # the engine vendored out of the zip must itself run
    r2 = subprocess.run([sys.executable, "vizzer/engine", "check", "--structural"],
                        cwd=project, capture_output=True, text=True)
    assert r2.returncode == 0, r2.stdout + r2.stderr

    # Updating code/context must not rewrite project-authored config or overlays.
    sidecars = {
        "assessment-signals.json": '{"schema":1,"items":{}}\n',
        "planning-overlay.json": '{"schema":1,"revision":7}\n',
        "question-answers.json": '{"schema":1,"revision":3,"history":[]}\n',
        "discussion-queue.json": '{"schema":1,"revision":2,"updatedAt":"2026-08-11T00:00:00Z","queues":{"codex":[],"claude":[]},"history":[]}\n',
        "semantic-history.json": '{"schema":1,"events":[]}\n',
    }
    for name, content in sidecars.items():
        (project / "vizzer" / name).write_text(content)
    config_before = (project / "vizzer" / "vizzer.toml").read_bytes()
    updated = subprocess.run([sys.executable, str(pyz), "update", str(project)],
                             capture_output=True, text=True)
    assert updated.returncode == 0, updated.stdout + updated.stderr
    for relative in FRONTEND_RESOURCES:
        assert (installed_frontend / Path(relative).name).is_file()
    assert (project / "vizzer" / "vizzer.toml").read_bytes() == config_before
    for name, content in sidecars.items():
        assert (project / "vizzer" / name).read_text() == content
    refresh = subprocess.run([sys.executable, "vizzer/engine", "refresh"],
                             cwd=project, capture_output=True, text=True)
    assert refresh.returncode == 0, refresh.stdout + refresh.stderr
    full_check = subprocess.run([sys.executable, "vizzer/engine", "check"],
                                cwd=project, capture_output=True, text=True)
    assert full_check.returncode == 0, full_check.stdout + full_check.stderr


def test_pyz_build_is_reproducible(tmp_path):
    """Every entry must carry a fixed timestamp, so releases are byte-verifiable.

    Comparing two consecutive builds is not sufficient: ZIP stores mtimes with
    two-second granularity, so fast successive builds can match by luck.
    """
    import hashlib
    import zipfile

    out = tmp_path / "a.pyz"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_pyz.py"), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with zipfile.ZipFile(out) as z:
        stamps = {i.date_time for i in z.infolist()}
    assert len(stamps) == 1, f"entries carry varying timestamps: {sorted(stamps)}"

    # and the archive must be stable across a rebuild from identical sources
    out2 = tmp_path / "b.pyz"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_pyz.py"), str(out2)],
                   capture_output=True, text=True, check=True)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == \
        hashlib.sha256(out2.read_bytes()).hexdigest()
