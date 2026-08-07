"""One-pass Git metadata and cached source-mention collection."""
from __future__ import annotations

import subprocess
from pathlib import Path


class GitMeta:
    def __init__(
        self,
        created: dict[str, str] | None = None,
        modified: dict[str, str] | None = None,
        commit_counts: dict[str, int] | None = None,
        last_touched: dict[str, int] | None = None,
        mention_texts: list[str] | None = None,
    ):
        self._created = created or {}
        self._modified = modified or {}
        self._commit_counts = commit_counts or {}
        self._last_touched = last_touched or {}
        self._mention_texts = mention_texts or []

    def created(self, relpath: str) -> str | None:
        return self._created.get(relpath)

    def modified(self, relpath: str) -> str | None:
        return self._modified.get(relpath)

    def commits(self, relpath: str) -> int:
        return self._commit_counts.get(relpath, 0)

    def last_touched(self, relpath: str) -> int:
        return self._last_touched.get(relpath, 0)

    def mentions(self, needle: str) -> int:
        return sum(needle in text for text in self._mention_texts)


def collect(root: Path, mention_globs: list[str]) -> tuple[GitMeta, list[str]]:
    root = Path(root)
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "core.quotePath=false",
                "-c",
                "log.showSignature=false",
                "log",
                "--format=C%x09%ct%x09%ad",
                "--date=iso-strict",
                "--name-only",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return GitMeta(), ["git history unavailable — dates/activity omitted"]

    created: dict[str, str] = {}
    modified: dict[str, str] = {}
    commit_counts: dict[str, int] = {}
    last_touched: dict[str, int] = {}
    epoch = 0
    iso_date = ""

    for line in result.stdout.splitlines():
        if line.startswith("C\t"):
            _, raw_epoch, iso_date = line.split("\t", 2)
            epoch = int(raw_epoch)
        elif line and iso_date:
            if line not in modified:
                modified[line] = iso_date
                last_touched[line] = epoch
            created[line] = iso_date
            commit_counts[line] = commit_counts.get(line, 0) + 1

    mention_paths = {
        path
        for pattern in mention_globs
        for path in root.glob(pattern)
        if path.is_file()
    }
    mention_texts = []
    for path in sorted(mention_paths):
        try:
            mention_texts.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue

    return (
        GitMeta(created, modified, commit_counts, last_touched, mention_texts),
        [],
    )
