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
