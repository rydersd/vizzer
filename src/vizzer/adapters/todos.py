"""Adapter for Markdown TODO files."""
from __future__ import annotations

import re
from pathlib import Path

from ..model import Group, Item
from . import ScanResult, slugify


_CHECKBOX_RE = re.compile(r"^\s*- \[(x| )\]\s+(.+?)\s*$", re.MULTILINE)


def scan(cfg, root: Path) -> ScanResult:
    """Scan configured TODO files into groups and checkbox items."""
    root = Path(root)
    paths = set()
    warnings = []

    for pattern in cfg.get("sources.todos.globs", []):
        try:
            paths.update(path for path in root.glob(pattern) if path.is_file())
        except (OSError, ValueError) as exc:
            warnings.append(f"todo glob unavailable: {exc}")

    groups = []
    items = []
    for path in sorted(paths, key=lambda candidate: candidate.relative_to(root).as_posix()):
        relpath = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            warnings.append(f"{relpath}: unreadable")
            continue

        group_id = f"todo-file:{relpath}"
        groups.append(Group(id=group_id, kind="folder", title=path.name))

        file_stem = path.stem.lower()
        for index, match in enumerate(_CHECKBOX_RE.finditer(text), 1):
            marker, title = match.groups()
            items.append(Item(
                id=f"todo:{file_stem}/{index:02d}-{slugify(title)}",
                title=title,
                status="shipped" if marker == "x" else "backlog",
                group=group_id,
                source={"adapter": "todos", "path": relpath},
            ))

    return ScanResult(groups=groups, items=items, warnings=warnings)
