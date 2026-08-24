"""Deterministic age budgets for authored, unanswered owner questions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .model import OwnerQuestion
from .render.perspective_common import git_introduced, parse_time


DEFAULT_BUDGET_HOURS = 72


@dataclass(frozen=True)
class QuestionAge:
    question: OwnerQuestion
    raised_at: str | None
    source: str
    age_hours: int | None
    over_budget: bool


def raised_at_overrides(cfg, root: Path) -> dict[str, str]:
    activity_path = cfg.get("activity.path", "")
    if not isinstance(activity_path, str) or not activity_path:
        return {}
    try:
        payload = json.loads((root / activity_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    questions = payload.get("questions", []) if isinstance(payload, dict) else []
    if not isinstance(questions, list):
        return {}
    return {
        raw["id"]: raw["raisedAt"]
        for raw in questions
        if isinstance(raw, dict)
        and isinstance(raw.get("id"), str)
        and isinstance(raw.get("raisedAt"), str)
        and parse_time(raw["raisedAt"]) is not None
    }


def _raised_at(
    question_id: str, overrides: dict[str, str], activity_path: str, root: Path,
) -> tuple[str | None, str]:
    if question_id in overrides:
        return overrides[question_id], "raisedAt"
    introduced = (
        git_introduced(str(root.resolve()), activity_path, question_id)
        if activity_path else None
    )
    if introduced and parse_time(introduced):
        return introduced, "git"
    return None, "unknown"


def question_ages(graph, cfg, root: Path, anchor: datetime) -> list[QuestionAge]:
    budget = int(cfg.get("questions.age_budget_hours", DEFAULT_BUDGET_HOURS))
    activity_path = str(cfg.get("activity.path", ""))
    overrides = raised_at_overrides(cfg, root)
    result = []
    for question in graph.owner_questions:
        raised, source = _raised_at(question.id, overrides, activity_path, root)
        parsed = parse_time(raised)
        hours = (
            max(0, int((anchor - parsed).total_seconds() // 3600))
            if parsed is not None else None
        )
        result.append(QuestionAge(
            question=question,
            raised_at=raised,
            source=source,
            age_hours=hours,
            over_budget=hours is not None and hours > budget,
        ))
    return sorted(result, key=lambda value: (
        not value.over_budget, value.age_hours is None,
        -(value.age_hours or 0), value.question.id,
    ))


def overdue_warning_lines(ages: list[QuestionAge], budget_hours: int) -> list[str]:
    return [
        f"check: WARNING overdue owner question {age.question.id}: unanswered "
        f"for {age.age_hours}h (budget {budget_hours}h) — {age.question.prompt}"
        for age in ages if age.over_budget
    ]
