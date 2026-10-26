"""Validated, project-local redirects for retired Story IDs and question history."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .config import Config


def load_story_aliases(
    root: Path, cfg: Config, item_ids: set[str],
) -> tuple[dict[str, str], set[str], list[dict[str, str]], list[str]]:
    """Load safe aliases and explicitly historical question dispositions.

    Alias targets resolve through chains to a current Story. Bad entries are
    rejected individually with warnings; malformed or unsafe files fail closed.
    Historical question IDs are never inferred from a missing Story target.
    """
    configured = cfg.get("render.story_aliases", "")
    if not isinstance(configured, str) or not configured.strip():
        return {}, set(), [], []
    project_root = root.resolve()
    candidate = Path(configured)
    if candidate.is_absolute():
        return {}, set(), [], [f"story alias file {configured} must be a relative in-project path"]
    path = (project_root / candidate).resolve()
    try:
        path.relative_to(project_root)
    except ValueError:
        return {}, set(), [], [f"story alias file {configured} escapes the project root (ignored)"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}, set(), [], [f"story alias file {configured} is unreadable or malformed"]
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        return {}, set(), [], [f"story alias file {configured} must be a schema-1 JSON object"]
    raw = payload.get("aliases")
    if not isinstance(raw, dict):
        return {}, set(), [], [f"story alias file {configured} must contain an aliases object"]

    warnings: list[str] = []
    aliases: dict[str, str] = {}
    for old, target in raw.items():
        if not (isinstance(old, str) and isinstance(target, str)
                and old.startswith("story:") and target.startswith("story:")):
            warnings.append(f"story alias entry {old!r} must map Story IDs (alias rejected)")
            continue
        if old in item_ids:
            warnings.append(f"story alias {old} shadows a current item (alias rejected)")
            continue
        aliases[old] = target

    resolved: dict[str, str] = {}
    for old in aliases:
        cursor = old
        seen: set[str] = set()
        while cursor in aliases:
            if cursor in seen:
                warnings.append(f"story alias {old} has a cycle (alias rejected)")
                break
            seen.add(cursor)
            cursor = aliases[cursor]
        else:
            if cursor in item_ids:
                resolved[old] = cursor
            else:
                warnings.append(f"story alias {old} targets unknown item {cursor} (alias rejected)")

    raw_ids = payload.get("historical_question_ids", [])
    raw_history = payload.get("historical_questions", [])
    if raw_ids is None and raw_history is None:
        raw_ids, raw_history = [], []
    if not isinstance(raw_ids, list) or not isinstance(raw_history, list):
        warnings.append("story alias file historical question dispositions must be arrays")
        return resolved, set(), [], warnings
    declared = {value for value in raw_ids if isinstance(value, str)
                and value.startswith("question:")}
    historical_ids: set[str] = set()
    history: list[dict[str, str]] = []
    seen_history: set[str] = set()
    for entry in raw_history:
        if not isinstance(entry, dict):
            warnings.append("historical question disposition must be an object (ignored)")
            continue
        question_id, old_story, target = entry.get("id"), entry.get("story_id"), entry.get("canonical_target")
        reason = entry.get("source_reason")
        valid = (
            isinstance(question_id, str) and question_id in declared
            and question_id.startswith("question:") and question_id not in seen_history
            and entry.get("status") == "historical"
            and isinstance(old_story, str) and isinstance(target, str)
            and resolved.get(old_story) == target and target in item_ids
            and isinstance(reason, str) and bool(reason.strip()) and len(reason) <= 2_000
        )
        if not valid:
            warnings.append("historical question disposition is malformed or targets an unvalidated Story (ignored)")
            continue
        seen_history.add(question_id)
        historical_ids.add(question_id)
        history.append({"id": question_id, "story_id": old_story, "canonical_target": target,
                        "status": "historical", "source_reason": reason})
    if historical_ids != declared:
        warnings.append("historical question ID list does not match validated dispositions")
    return resolved, historical_ids, history, warnings
