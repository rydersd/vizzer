"""Resolve an owner question's story id to its markdown file on disk.

Story files are the ones the project's `[sources.spec_tree] glob` selects
(vizzer.toml), read straight from the working tree, so new, untracked stories
resolve exactly like committed ones. The id is never used as a path: only its
slug is matched against files that glob selects, and a match must stay inside
the project after symlink resolution.
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from .story_aliases import load_story_aliases

_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


MAX_ALIAS_BYTES = 1024 * 1024


def _aliases(root: Path, cfg, item_ids) -> dict[str, str]:
    """The engine's validated aliases: in-project schema-1 file, no shadows, cycles or unknown targets.

    A request never waits on or loads an unbounded alias file: anything but a regular file of at most
    MAX_ALIAS_BYTES is ignored before the loader reads it.
    """
    if cfg is None:
        return {}
    configured = cfg.get("render.story_aliases", "")
    if not isinstance(configured, str) or not configured.strip():
        return {}
    try:
        info = os.stat(root / configured)
    except (OSError, ValueError):
        return {}
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ALIAS_BYTES:
        return {}
    aliases, _, _, _ = load_story_aliases(root, cfg, set(item_ids))
    return aliases


def _slug(story_id: str) -> str | None:
    slug = story_id[len("story:"):] if story_id.startswith("story:") else story_id
    return slug if _SLUG.match(slug) and ".." not in slug else None


def resolve_story_file(root: Path, cfg, story_id: str, item_ids=()) -> tuple[Path | None, str]:
    """Return (path, "") for the story's markdown, or (None, plain reason).

    `item_ids` are the current graph's ids; an alias applies only when it leads to one of them.
    """
    if not isinstance(story_id, str) or not story_id.startswith("story:") \
            or _slug(story_id) is None:
        return None, f"'{story_id}' is not a valid story id"
    target = _aliases(root, cfg, item_ids).get(story_id, story_id)
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


def story_payload(root: Path, cfg, story_id: str, item_ids=()) -> tuple[int, dict]:
    path, reason = resolve_story_file(root, cfg, story_id, item_ids)
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
