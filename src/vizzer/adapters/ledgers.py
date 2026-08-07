"""Adapter for continuity ledgers."""
from __future__ import annotations

import re
from pathlib import Path

from ..model import Group, Item
from . import ScanResult, slugify


_CHECKBOX_RE = re.compile(r"^\s*- \[(x|→|->| )\]\s+(.+?)\s*$", re.MULTILINE)
_PHASE_HEADING_RE = re.compile(
    r"^##[ \t]+(Done|Now|Next|Remaining)(?:[ \t]+.*?)?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_H2_RE = re.compile(r"^##[ \t]+", re.MULTILINE)
_LIST_ENTRY_RE = re.compile(r"^\s*(?:-\s+|\d+[.)]\s+)(.+?)\s*$", re.MULTILINE)


def _ledger_slug(path: Path) -> str:
    stem = path.stem
    for prefix in ("CONTINUITY_CLAUDE-", "CONTINUITY_"):
        if stem.startswith(prefix):
            return stem[len(prefix):]
    return stem


def _section(text: str, name: str) -> str:
    match = re.search(rf"^##\s+{re.escape(name)}\s*$", text,
                      re.IGNORECASE | re.MULTILINE)
    if not match:
        return ""
    following = text[match.end():]
    next_heading = re.search(r"^##\s+", following, re.MULTILINE)
    return following[:next_heading.start()] if next_heading else following


def _goal(text: str) -> str:
    for line in _section(text, "Goal").splitlines():
        stripped = line.strip()
        if stripped:
            return " ".join(stripped.split())
    return ""


def _heading_phases(text: str) -> list[tuple[str, str]]:
    status_map = {"done": "shipped", "now": "building",
                  "next": "backlog", "remaining": "backlog"}
    phases = []
    for heading in _PHASE_HEADING_RE.finditer(text):
        next_heading = _H2_RE.search(text, heading.end())
        end = next_heading.start() if next_heading else len(text)
        section = text[heading.end():end]
        entries = [match.group(1) for match in _LIST_ENTRY_RE.finditer(section)]
        status = status_map[heading.group(1).lower()]
        phases.extend((status, title) for title in entries)

        if status == "building" and not entries:
            prose = " ".join(section.split())
            if prose:
                phases.append((status, prose[:120]))
    return phases


def scan(cfg, root: Path) -> ScanResult:
    """Scan configured continuity ledgers into groups and phase items."""
    root = Path(root)
    pattern = cfg.get("sources.ledgers.glob", "")
    groups = []
    items = []
    warnings = []

    try:
        paths = sorted(root.glob(pattern)) if pattern else []
    except (OSError, ValueError) as exc:
        return ScanResult(warnings=[f"ledger glob unavailable: {exc}"])

    for path in paths:
        if not path.is_file():
            continue
        relpath = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            warnings.append(f"{relpath}: unreadable")
            continue

        ledger_slug = _ledger_slug(path)
        group_id = f"ledger:{ledger_slug}"
        open_questions = sum(
            line.startswith("- ")
            for line in _section(text, "Open Questions").splitlines()
        )
        groups.append(Group(
            id=group_id,
            kind="ledger",
            title=ledger_slug.replace("-", " ").title(),
            meta={
                "goal": _goal(text),
                "open_questions": open_questions,
                "path": relpath,
            },
        ))

        checkbox_matches = list(_CHECKBOX_RE.finditer(text))
        if checkbox_matches:
            status_map = {"x": "shipped", "→": "building", "->": "building",
                          " ": "backlog"}
            phases = [(status_map[match.group(1)], match.group(2))
                      for match in checkbox_matches]
        else:
            phases = _heading_phases(text)

        for index, (status, title) in enumerate(phases, 1):
            items.append(Item(
                id=(f"phase:{ledger_slug}/{index:02d}-"
                    f"{slugify(title)}"),
                title=title,
                status=status,
                group=group_id,
                source={"adapter": "ledgers", "path": relpath},
            ))

    return ScanResult(groups=groups, items=items, warnings=warnings)
