import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_build_pyz(tmp_path):
    out = tmp_path / "vizzer.pyz"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_pyz.py"), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert "__main__.py" in names and "vizzer/model.py" in names
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
    assert (project / "vizzer" / "engine" / "vizzer" / "render"
            / "constellation_template.html").exists()
    assert (project / "vizzer" / "views" / "dashboard.md").exists()

    # the engine vendored out of the zip must itself run
    r2 = subprocess.run([sys.executable, "vizzer/engine", "check", "--structural"],
                        cwd=project, capture_output=True, text=True)
    assert r2.returncode == 0, r2.stdout + r2.stderr
