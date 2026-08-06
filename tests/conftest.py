import os
import shutil
import subprocess
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_DATE = "2026-01-02T03:04:05Z"


def run_git(repo, *args, env=None):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Fixture",
         "-c", "user.email=fx@example.com", *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


@pytest.fixture
def make_repo():
    def _make_repo(tmp_path, fixture: str) -> Path:
        repo = tmp_path / "proj"
        shutil.copytree(FIXTURES / fixture, repo)
        run_git(repo, "init", "-b", "main")
        run_git(repo, "add", "-A")
        run_git(
            repo,
            "commit",
            "-m",
            "fixture",
            env={"GIT_AUTHOR_DATE": FIXTURE_DATE,
                 "GIT_COMMITTER_DATE": FIXTURE_DATE},
        )
        return repo

    return _make_repo
