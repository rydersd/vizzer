"""Owner comments on story text, kept in vizzer/story-comments.json.

The file is a JSON list of entries. Every field is stored and served as plain
text; nothing here builds markup. Writes are atomic (temp file, then rename)
and callers hold the served mutation lock. A store that cannot be parsed is
never overwritten.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .story_files import read_capped, resolve_story_file

STORE_RELPATH = "vizzer/story-comments.json"
QUOTE_MAX = 2000
COMMENT_MAX = 4000
MAX_COMMENTS = 2000
MAX_STORE_BYTES = 4 * 1024 * 1024
_REQUIRED = {"storyId", "path", "quote", "comment", "clientTime"}
_OPTIONAL = {"questionId", "heading"}


class StoryCommentError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _size_check(size: int) -> None:
    if size > MAX_STORE_BYTES:
        raise StoryCommentError(
            f"store over limit: {STORE_RELPATH} is larger than {MAX_STORE_BYTES} bytes; left untouched", 413)


def load_store(root: Path) -> list[dict]:
    """The one capped loader (API and renderer): bytes and count enforced, read via one descriptor."""
    path = root / STORE_RELPATH
    try:
        os.lstat(path)
    except FileNotFoundError:
        return []
    except OSError:
        raise StoryCommentError(f"{STORE_RELPATH} is unreadable; left untouched", 500) from None
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        raise StoryCommentError(f"{STORE_RELPATH} is unreadable; left untouched", 500) from None
    try:
        _size_check(os.fstat(fd).st_size)
        data = read_capped(fd, MAX_STORE_BYTES)
        if len(data) > MAX_STORE_BYTES:
            raise StoryCommentError(
                f"store over limit: {STORE_RELPATH} is larger than {MAX_STORE_BYTES} bytes; left untouched", 413)
        entries = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise StoryCommentError(f"{STORE_RELPATH} is unreadable; left untouched", 500) from None
    finally:
        os.close(fd)
    if not isinstance(entries, list):
        raise StoryCommentError(f"{STORE_RELPATH} is not a list; left untouched", 500)
    if len(entries) > MAX_COMMENTS:
        raise StoryCommentError(
            f"store over limit: {STORE_RELPATH} holds more than {MAX_COMMENTS} comments; left untouched", 413)
    return entries


def _write(root: Path, entries: list[dict]) -> None:
    encoded = json.dumps(entries, indent=2, ensure_ascii=False) + "\n"
    if len(encoded.encode("utf-8")) > MAX_STORE_BYTES:
        raise StoryCommentError(
            f"story comment store size limit ({MAX_STORE_BYTES} bytes) reached; nothing was saved", 413)
    destination = root / STORE_RELPATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".story-comments.", dir=str(destination.parent))
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _text(body: dict, key: str, limit: int, *, required: bool = False) -> str:
    value = body.get(key, "")
    if not isinstance(value, str):
        raise StoryCommentError(f"{key} must be text")
    if required and not value.strip():
        raise StoryCommentError(f"{key} must not be empty")
    if len(value) > limit:
        raise StoryCommentError(f"{key} is longer than {limit} characters")
    return value


def add_comment(root: Path, cfg, body: dict) -> dict:
    unknown = sorted(set(body) - _REQUIRED - _OPTIONAL)
    missing = sorted(_REQUIRED - set(body))
    if unknown or missing:
        raise StoryCommentError(f"unknown or missing field: {(unknown or missing)[0]}")
    story_id = _text(body, "storyId", 200, required=True)
    path, reason = resolve_story_file(root, cfg, story_id)
    if path is None:
        raise StoryCommentError(reason, 404)
    relative = str(path.relative_to(root.resolve()))
    if _text(body, "path", 500, required=True) != relative:
        raise StoryCommentError(f"path does not match the story file {relative}")
    entry = {
        "id": str(uuid.uuid4()),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "open",
        "storyId": story_id,
        "path": relative,
        "questionId": _text(body, "questionId", 200),
        "quote": _text(body, "quote", QUOTE_MAX, required=True),
        "heading": _text(body, "heading", 500),
        "comment": _text(body, "comment", COMMENT_MAX, required=True),
        "clientTime": _text(body, "clientTime", 64, required=True),
    }
    entries = load_store(root)
    if len(entries) >= MAX_COMMENTS:
        raise StoryCommentError(
            f"story comment limit ({MAX_COMMENTS}) reached; nothing was saved", 409)
    entries.append(entry)
    _write(root, entries)
    return entry


def list_comments(root: Path, story_id: str) -> list[dict]:
    return [entry for entry in load_store(root)
            if isinstance(entry, dict) and entry.get("storyId") == story_id]


def delete_comment(root: Path, comment_id: str) -> None:
    entries = load_store(root)
    for index, entry in enumerate(entries):
        if isinstance(entry, dict) and entry.get("id") == comment_id:
            if entry.get("status") != "open":
                raise StoryCommentError("only open comments can be deleted", 409)
            del entries[index]
            _write(root, entries)
            return
    raise StoryCommentError("comment not found", 404)


def _quote_lines(text: str) -> list[str]:
    return ["> " + line for line in text.splitlines() or [""]]


def render_comments_markdown(entries: list[dict]) -> str:
    """One page of open comments, grouped by story, for a grill session."""
    open_entries = [e for e in entries if isinstance(e, dict) and e.get("status") == "open"]
    lines = ["# Story comments", "",
             "Owner comments on story text, open only. Source: `vizzer/story-comments.json`.", ""]
    if not open_entries:
        return "\n".join(lines + ["No open story comments.", ""])
    by_story: dict[str, list[dict]] = {}
    for entry in open_entries:
        by_story.setdefault(str(entry.get("storyId", "")), []).append(entry)
    for story_id in sorted(by_story):
        group = by_story[story_id]
        lines += [f"## {story_id}", "", f"File: `{group[0].get('path', '')}`", ""]
        for entry in sorted(group, key=lambda e: str(e.get("createdAt", ""))):
            lines += [f"### {entry.get('heading') or '(no heading)'} · {entry.get('createdAt', '')}", ""]
            if entry.get("questionId"):
                lines += [f"Opened from `{entry['questionId']}` · comment `{entry.get('id', '')}`", ""]
            else:
                lines += [f"Comment `{entry.get('id', '')}`", ""]
            lines += _quote_lines(str(entry.get("quote", "")))
            lines += ["", "Comment:", ""]
            lines += ["    " + line for line in str(entry.get("comment", "")).splitlines() or [""]]
            lines.append("")
    return "\n".join(lines)
