"""Adapter for loosely structured Markdown documentation."""
from __future__ import annotations

import glob
import re
from pathlib import Path

from ..model import Group, Item
from . import ScanResult
from .spec_tree import _front_matter


_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_STATUS_RE = re.compile(r"^>\s*Status:\s*([a-zA-Z-]+)", re.MULTILINE)
_BRIEF_RE = re.compile(r"^>\s*Brief:\s*(.+?)\s*$", re.MULTILINE)


def _string(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _list(value) -> list[str]:
    if isinstance(value, list):
        return [str(entry).strip() for entry in value if str(entry).strip()]
    scalar = _string(value)
    return [scalar] if scalar else []


def _scan_file(path: Path, root: Path, groups: dict[str, Group],
               warnings: list[str], cfg) -> Item | None:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    relpath = rel.as_posix()

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        warnings.append(f"{relpath}: unreadable")
        return None

    front, body = _front_matter(text)
    reldir = rel.parent.as_posix()
    group_id = f"folder:{reldir}"
    if group_id not in groups:
        title = (str(cfg.get("project.name", "project"))
                 if reldir == "." else reldir)
        groups[group_id] = Group(id=group_id, kind="folder", title=title)

    title = _string(front.get("title"))
    if title is None:
        match = _H1_RE.search(body)
        title = match.group(1).strip() if match else path.stem

    status = _string(front.get("status"))
    if status is None:
        match = _STATUS_RE.search(body)
        status = match.group(1) if match else "unknown"

    one_liner = _string(front.get("summary"))
    if one_liner is None:
        match = _BRIEF_RE.search(body)
        one_liner = match.group(1).strip() if match else None

    item_path = relpath[:-3] if relpath.endswith(".md") else relpath
    return Item(
        id=f"doc:{item_path}",
        title=title,
        one_liner=one_liner,
        status=status,
        release=_string(front.get("release")),
        group=group_id,
        deps=_list(front.get("deps")),
        role=str(cfg.get("sources.loose_docs.item_role", "reference")),
        tags=_list(front.get("tags")),
        source={"adapter": "loose_docs", "path": relpath},
    )


def scan(cfg, root: Path) -> ScanResult:
    """Scan configured Markdown globs into document items and folder groups."""
    root = Path(root)
    warnings = []
    groups: dict[str, Group] = {}
    matches = set()

    for pattern in cfg.get("sources.loose_docs.globs", []):
        try:
            matches.update(glob.glob(str(root / pattern), recursive=True))
        except OSError as exc:
            warnings.append(f"loose docs glob unavailable: {exc}")

    items = []
    for match in sorted(matches):
        path = Path(match)
        if path.name.startswith("_") or not path.is_file():
            continue
        item = _scan_file(path, root, groups, warnings, cfg)
        if item is not None:
            items.append(item)

    return ScanResult(groups=list(groups.values()), items=items, warnings=warnings)
