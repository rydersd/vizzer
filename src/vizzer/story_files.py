"""Resolve an owner question's story id to its markdown file on disk.

Story files are the ones the project's `[sources.spec_tree] glob` selects
(vizzer.toml), read straight from the working tree, so new, untracked stories
resolve exactly like committed ones. The id is never used as a path: only its
slug is matched against files that glob selects, and a match must stay inside
the project after symlink resolution.
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _aliases(root: Path, cfg) -> dict[str, str]:
    relpath = cfg.get("render.story_aliases", "") if cfg is not None else ""
    if not relpath:
        return {}
    try:
        raw = json.loads((root / relpath).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}
    table = raw.get("aliases") if isinstance(raw, dict) else None
    if not isinstance(table, dict):
        return {}
    return {k: v for k, v in table.items() if isinstance(k, str) and isinstance(v, str)}


def _slug(story_id: str) -> str | None:
    slug = story_id[len("story:"):] if story_id.startswith("story:") else story_id
    return slug if _SLUG.match(slug) and ".." not in slug else None


def resolve_story_file(root: Path, cfg, story_id: str) -> tuple[Path | None, str]:
    """Return (path, "") for the story's markdown, or (None, plain reason)."""
    if not isinstance(story_id, str) or not story_id.startswith("story:") \
            or _slug(story_id) is None:
        return None, f"'{story_id}' is not a valid story id"
    aliases = _aliases(root, cfg)
    target, seen = story_id, set()
    while target in aliases and target not in seen:
        seen.add(target)
        target = aliases[target]
    slug = _slug(target)
    if slug is None:
        return None, f"{story_id} maps to an invalid story id"
    pattern = cfg.get("sources.spec_tree.glob", "") if cfg is not None else ""
    if not isinstance(pattern, str) or not pattern or pattern.startswith("/") \
            or ".." in pattern.split("/"):
        return None, "This project configures no story tree (sources.spec_tree.glob)."
    project = root.resolve()
    # Spec root: the literal directories before the glob's first wildcard.
    literal = []
    for part in pattern.split("/")[:-1]:
        if any(ch in part for ch in "*?["):
            break
        literal.append(part)
    spec_root = project.joinpath(*literal).resolve() if literal else project
    matches: list[Path] = []
    # Enumerate exactly what the configured glob selects, then filter by stem.
    for candidate in project.glob(pattern):
        if candidate.stem != slug or candidate.suffix != ".md":
            continue
        try:
            relative = candidate.relative_to(project)
            walk = project
            linked = False
            for part in relative.parts:
                walk = walk / part
                if walk.is_symlink():
                    linked = True
                    break
            if linked:
                continue
            resolved = candidate.resolve()
            resolved.relative_to(spec_root)
        except (OSError, ValueError):
            continue
        if resolved.suffix == ".md" and resolved.is_file():
            matches.append(resolved)
    if not matches:
        suffix = f" (crosswalk target {target})" if target != story_id else ""
        return None, (f"No story file named {slug}.md was found under "
                      f"the configured story tree for {story_id}{suffix}.")
    if len(matches) > 1:
        return None, (f"{story_id} matches more than one story file: "
                      + ", ".join(str(m.relative_to(project)) for m in sorted(matches)))
    return matches[0], ""


MAX_STORY_BYTES = 1024 * 1024


def _read_fd(fd: int, count: int) -> bytes:
    """Seam: every byte served from a story or store passes through here."""
    return os.read(fd, count)


def read_capped(fd: int, cap: int) -> bytes:
    """Read from an open descriptor, never more than cap + 1 bytes in total."""
    chunks, total = [], 0
    while total < cap + 1:
        chunk = _read_fd(fd, min(65536, cap + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def open_nofollow(project: Path, relative: Path) -> int:
    """Open project/relative as a regular file, refusing a symlink at any component.

    Walks from the project directory with dir_fd and O_NOFOLLOW, so a swap that
    happens after path validation fails here instead of being followed.
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(project, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0))
    try:
        parts = relative.parts
        for part in parts[:-1]:
            nxt = os.open(part, flags | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = nxt
        final = os.open(parts[-1], flags, dir_fd=fd)
    finally:
        os.close(fd)
    if not stat.S_ISREG(os.fstat(final).st_mode):
        os.close(final)
        raise OSError("not a regular file")
    return final


def _before_open(path: Path) -> None:
    """Seam for tests: runs between path validation and opening."""


def story_payload(root: Path, cfg, story_id: str) -> tuple[int, dict]:
    path, reason = resolve_story_file(root, cfg, story_id)
    if path is None:
        return 404, {"error": reason, "storyId": story_id}
    project = root.resolve()
    relative = path.relative_to(project)
    _before_open(path)
    try:
        fd = open_nofollow(project, relative)
    except OSError:
        return 404, {"error": f"{path.name} is not a regular story file", "storyId": story_id}
    try:
        too_big = {"error": f"{path.name} is larger than {MAX_STORY_BYTES} bytes and is not served",
                   "storyId": story_id}
        if os.fstat(fd).st_size > MAX_STORY_BYTES:
            return 413, too_big
        data = read_capped(fd, MAX_STORY_BYTES)
        if len(data) > MAX_STORY_BYTES:
            return 413, too_big
        markdown = data.decode("utf-8")
    except (OSError, UnicodeError):
        return 500, {"error": f"Could not read {path.name}", "storyId": story_id}
    finally:
        os.close(fd)
    return 200, {"storyId": story_id, "path": str(relative), "markdown": markdown}
