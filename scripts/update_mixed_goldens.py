"""Explicitly regenerate the mixed fixture's existing golden outputs.

Run from a stable candidate, then inspect the diff; this is not a test or an
automatic acceptance update. Temporary source and outputs honor TMPDIR.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vizzer.cli import main


def regenerate():
    with tempfile.TemporaryDirectory(prefix="vizzer-golden-") as temp:
        repo = Path(temp) / "proj"
        shutil.copytree(ROOT / "tests/fixtures/mixed_proj", repo)
        env = {**os.environ, "GIT_AUTHOR_DATE": "2026-01-02T03:04:05Z",
               "GIT_COMMITTER_DATE": "2026-01-02T03:04:05Z"}
        for args in (("init", "-b", "main"), ("add", "-A"), ("commit", "-m", "fixture")):
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                            "-c", "user.email=fx@example.com", *args],
                           check=True, capture_output=True, env=env)
        if main(["sync", "--root", str(repo)]) or main(["render", "--root", str(repo)]):
            raise RuntimeError("fixture generation failed")
        for target in sorted((ROOT / "tests/golden/mixed").iterdir()):
            source = repo / "vizzer" / ("vizzer-graph.json" if target.name == "vizzer-graph.json"
                                       else f"views/{target.name}")
            target.write_bytes(source.read_bytes())


if __name__ == "__main__":
    regenerate()
