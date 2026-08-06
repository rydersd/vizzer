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
