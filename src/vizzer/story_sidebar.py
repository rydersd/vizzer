"""Extract authored Markdown into the renderer-neutral object-detail contract."""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import Item
from .object_detail import object_detail_for, object_detail_identity


_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
_GHERKIN_RE = re.compile(r"```gherkin\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_CANONICAL_NAMES = {
    "review_steps": "reviewSteps",
    "acceptance": "acceptance",
    "definition_of_done": "definitionOfDone",
}


def _normalized_heading(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _section_after(markdown: str, match: re.Match[str]) -> str:
    level = len(match.group(1))
    tail = markdown[match.end():]
    boundary = re.search(rf"^#{{1,{level}}}\s+", tail, re.MULTILINE)
    return tail[:boundary.start() if boundary else len(tail)].strip()


def _kind(heading: str) -> str | None:
    words = set(_normalized_heading(heading).split())
    if (("review" in words
         and words & {"step", "steps", "instruction", "instructions", "checklist"})
            or {"owner", "test", "list"} <= words):
        return "review_steps"
    if ("dod" in words or {"definition", "done"} <= words
            or {"acceptance", "tests"} <= words
            or {"named", "tests"} <= words):
        return "definition_of_done"
    if "acceptance" in words and ("criteria" in words or len(words) == 1):
        return "acceptance"
    return None


def extract_story_sidebar_sections(markdown: str) -> dict[str, str | None]:
    """Return the first authored content block for each legacy sidebar key."""
    sections: dict[str, str | None] = {
        "review_steps": None,
        "acceptance": None,
        "definition_of_done": None,
    }
    for match in _HEADING_RE.finditer(markdown):
        kind = _kind(match.group(2))
        if kind and sections[kind] is None:
            content = _section_after(markdown, match)
            if content:
                sections[kind] = content
    if sections["acceptance"] is None:
        gherkin = _GHERKIN_RE.search(markdown)
        if gherkin and gherkin.group(1).strip():
            sections["acceptance"] = gherkin.group(1).strip()
    return sections


def canonical_story_sections(markdown: str) -> dict[str, str]:
    """Map authored sections to ``vizzer-object-detail/v1`` names."""
    extracted = extract_story_sidebar_sections(markdown)
    return {
        _CANONICAL_NAMES[name]: value
        for name, value in extracted.items()
        if value is not None
    }


def object_detail_providers(
    root: Path,
) -> tuple[Callable[[Item], dict[str, Any]], Callable[[Item], str]]:
    """Build a safe, cached provider shared by every renderer in one pass.

    Non-Markdown and non-project-relative sources still receive the normalized
    core detail; this adapter merely enriches sources it understands.
    """
    project_root = root.resolve()
    cache: dict[str, dict[str, str]] = {}

    def sections_for(item: Item) -> dict[str, str]:
        raw_path = item.source.get("path", "")
        sections: dict[str, str] = {}
        if isinstance(raw_path, str) and raw_path:
            try:
                relative = Path(raw_path)
                if relative.is_absolute() or relative.suffix.lower() != ".md":
                    raise ValueError("not a project-relative Markdown source")
                source = (project_root / relative).resolve()
                source.relative_to(project_root)
                cache_key = source.as_posix()
                if cache_key not in cache:
                    cache[cache_key] = canonical_story_sections(
                        source.read_text(encoding="utf-8")
                    )
                sections = cache[cache_key]
            except (OSError, UnicodeError, ValueError):
                sections = {}
        return sections

    def provide(item: Item) -> dict[str, Any]:
        return object_detail_for(item, sections=sections_for(item))

    def identify(item: Item) -> str:
        return object_detail_identity(item, sections=sections_for(item))

    return provide, identify


def object_detail_provider(root: Path) -> Callable[[Item], dict[str, Any]]:
    """Return the eager provider for renderers that materialize every dossier."""
    provide, _identify = object_detail_providers(root)
    return provide
