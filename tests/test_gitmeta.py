# tests/test_gitmeta.py
import subprocess
from vizzer.gitmeta import collect

def _git(repo, *args, date=None):
    env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}
    import os
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                    "-c", "user.email=fx@example.com", *args],
                   check=True, capture_output=True, env={**os.environ, **env})

def test_collect_dates_counts_mentions(tmp_path):
    repo = tmp_path / "r"; repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "a.md").write_text("alpha")
    (repo / "notes.md").write_text("about snap-to-grid work")
    _git(repo, "add", "-A"); _git(repo, "commit", "-m", "one", date="2026-01-01T00:00:00Z")
    (repo / "a.md").write_text("alpha v2")
    _git(repo, "add", "-A"); _git(repo, "commit", "-m", "two", date="2026-02-01T00:00:00Z")

    meta, warnings = collect(repo, ["notes.md"])
    assert warnings == []
    assert meta.commits("a.md") == 2
    assert meta.created("a.md").startswith("2026-01-01")
    assert meta.modified("a.md").startswith("2026-02-01")
    assert meta.last_touched("a.md") > meta.last_touched("notes.md") == 1767225600
    assert meta.mentions("snap-to-grid") == 1
    assert meta.mentions("absent-slug") == 0

def test_collect_degrades_without_git(tmp_path):
    meta, warnings = collect(tmp_path, [])
    assert meta.commits("x") == 0 and meta.created("x") is None
    assert warnings == ["git history unavailable — dates/activity omitted"]
