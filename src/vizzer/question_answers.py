"""Audited owner-question answers and reconciliation.

Answers are durable source input, not derived graph data.  The ledger therefore
lives beside the planning overlay and is only projected into ``Graph`` during a
refresh.  A question id is not a sufficient identity: every write also compares
the canonical question fingerprint so a stale page cannot answer revised prose.
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import tempfile

from .model import (
    Graph, OwnerDecision, OwnerQuestion, owner_question_fingerprint,
    owner_question_from_dict,
)
from .decision_journal import decision_is_journaled


SCHEMA = 1
MAX_ANSWERS = 10000
MAX_FREEFORM_LENGTH = 2000
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class QuestionAnswerError(ValueError):
    """The question answer request or ledger is invalid."""


class QuestionAnswerConflict(QuestionAnswerError):
    """The request lost its revision/fingerprint compare-and-swap."""


class QuestionNotFoundError(QuestionAnswerError):
    """The requested open question does not exist."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def answers_path(cfg, root: Path) -> Path:
    raw = cfg.get("questions.answers_path", "vizzer/question-answers.json")
    if not isinstance(raw, str) or not raw:
        raise QuestionAnswerError(
            "questions.answers_path must be a non-empty string"
        )
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise QuestionAnswerError("question answers path must stay inside the project")
    project_root = root.resolve()
    lexical = project_root / relative
    try:
        parent = lexical.parent.resolve()
        parent.relative_to(project_root)
    except (OSError, ValueError):
        raise QuestionAnswerError(
            "question answers path must stay inside the project"
        ) from None
    if lexical.is_symlink():
        raise QuestionAnswerError(
            "question answers ledger must be a regular file, not a symlink"
        )
    return parent / lexical.name


def empty_ledger() -> dict:
    return {"schema": SCHEMA, "revision": 0, "answers": []}


def _validate_answer(entry: object, previous_revision: int,
                     seen: set[tuple[str, str]]) -> dict:
    if not isinstance(entry, dict):
        raise QuestionAnswerError("question answer entries must be objects")
    allowed = {
        "revision", "questionId", "question", "fingerprint", "answeredAt",
        "answeredBy", "kind", "optionId", "text",
    }
    unknown = sorted(set(entry) - allowed)
    missing = sorted(allowed - set(entry))
    if unknown or missing:
        field = (unknown or missing)[0]
        raise QuestionAnswerError(
            f"question answer entry has unknown or missing field: {field}"
        )
    revision = entry["revision"]
    if (isinstance(revision, bool) or not isinstance(revision, int)
            or revision != previous_revision + 1):
        raise QuestionAnswerError(
            "question answer revisions must be contiguous and increasing"
        )
    question_id = entry["questionId"]
    if (not isinstance(question_id, str) or not question_id
            or ":" not in question_id):
        raise QuestionAnswerError("question answer questionId must be a typed id")
    if not isinstance(entry["question"], dict):
        raise QuestionAnswerError("question answer question snapshot must be an object")
    try:
        question = owner_question_from_dict(entry["question"])
    except ValueError as exc:
        raise QuestionAnswerError(f"invalid question answer snapshot: {exc}") from exc
    if question.id != question_id:
        raise QuestionAnswerError(
            "question answer questionId must match its question snapshot"
        )
    fingerprint = entry["fingerprint"]
    if not isinstance(fingerprint, str) or not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise QuestionAnswerError(
            "question answer fingerprint must be lowercase SHA-256"
        )
    if fingerprint != owner_question_fingerprint(question):
        raise QuestionAnswerError(
            "question answer fingerprint must match its question snapshot"
        )
    identity = (question_id, fingerprint)
    if identity in seen:
        raise QuestionAnswerError(
            f"question {question_id} already has an answer for this fingerprint"
        )
    for field in ("answeredAt", "answeredBy", "kind"):
        if not isinstance(entry[field], str) or not entry[field]:
            raise QuestionAnswerError(
                f"question answer {field} must be a non-empty string"
            )
    kind = entry["kind"]
    option_id = entry["optionId"]
    text = entry["text"]
    if kind == "option":
        if not isinstance(option_id, str) or not option_id or text is not None:
            raise QuestionAnswerError(
                "option answers require optionId and must not contain text"
            )
        if option_id not in {option.id for option in question.options}:
            raise QuestionAnswerError(
                "option answer must select an option in its question snapshot"
            )
    elif kind == "freeform":
        if (option_id is not None or not isinstance(text, str) or not text.strip()
                or len(text) > MAX_FREEFORM_LENGTH):
            raise QuestionAnswerError(
                f"freeform answers require 1..{MAX_FREEFORM_LENGTH} text characters"
            )
    else:
        raise QuestionAnswerError("question answer kind must be option or freeform")
    seen.add(identity)
    return dict(entry)


def _validate_ledger(data: object) -> dict:
    if not isinstance(data, dict) or set(data) != {"schema", "revision", "answers"}:
        raise QuestionAnswerError(
            "question answers ledger must be a schema-1 JSON object"
        )
    if data.get("schema") != SCHEMA:
        raise QuestionAnswerError(
            "question answers ledger must be a schema-1 JSON object"
        )
    revision = data.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise QuestionAnswerError(
            "question answers revision must be a non-negative integer"
        )
    raw_answers = data.get("answers")
    if not isinstance(raw_answers, list) or len(raw_answers) > MAX_ANSWERS:
        raise QuestionAnswerError(
            f"question answers must be an array of at most {MAX_ANSWERS} entries"
        )
    answers = []
    seen: set[tuple[str, str]] = set()
    previous = 0
    for raw in raw_answers:
        answer = _validate_answer(raw, previous, seen)
        previous = answer["revision"]
        answers.append(answer)
    if revision != previous:
        raise QuestionAnswerError(
            "question answers revision must equal the latest answer revision"
        )
    return {"schema": SCHEMA, "revision": revision, "answers": answers}


def read_answers(cfg, root: Path, *, strict: bool = True) -> tuple[dict | None, list[str]]:
    """Read ``(ledger, warnings)``; a missing ledger is revision zero."""
    try:
        path = answers_path(cfg, root)
        if not path.exists():
            return empty_ledger(), []
        if path.is_symlink() or not path.is_file():
            raise QuestionAnswerError(
                "question answers ledger must be a regular file, not a symlink"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return _validate_ledger(data), []
    except (OSError, UnicodeError, json.JSONDecodeError, QuestionAnswerError) as exc:
        error = exc if isinstance(exc, QuestionAnswerError) \
            else QuestionAnswerError(str(exc))
        if strict:
            raise error
        return None, [f"question answers ignored: {error}"]


def _decision(answer: dict) -> OwnerDecision:
    return OwnerDecision(
        question=owner_question_from_dict(answer["question"]),
        fingerprint=answer["fingerprint"],
        revision=answer["revision"],
        answered_at=answer["answeredAt"],
        answered_by=answer["answeredBy"],
        kind=answer["kind"],
        option_id=answer["optionId"],
        text=answer["text"],
    )


def reconcile_answers(graph: Graph, cfg, root: Path) -> list[str]:
    """Partition current questions into open questions and accepted decisions.

    Historical answers whose fingerprint is no longer current remain in the
    append-only ledger but do not suppress the revised question.
    """
    ledger, warnings = read_answers(cfg, root, strict=False)
    graph.owner_decisions = []
    if ledger is None:
        return warnings
    by_identity = {
        (answer["questionId"], answer["fingerprint"]): answer
        for answer in ledger["answers"]
    }
    open_questions = []
    decisions = []
    for question in graph.owner_questions:
        fingerprint = owner_question_fingerprint(question)
        answer = by_identity.get((question.id, fingerprint))
        if answer is None:
            open_questions.append(question)
            continue
        decisions.append(_decision(answer))
    graph.owner_questions = sorted(open_questions, key=lambda value: value.id)
    graph.owner_decisions = sorted(decisions, key=lambda value: value.question.id)
    for decision in graph.owner_decisions:
        if not decision_is_journaled(graph, root, decision):
            warnings.append(
                f"accepted decision {decision.question.id} revision "
                f"{decision.revision} is not journaled in its source story"
            )
    return warnings


def question_to_api(question: OwnerQuestion) -> dict:
    return {
        "id": question.id,
        "storyId": question.story_id,
        "owner": question.owner,
        "prompt": question.prompt,
        "options": [
            {"id": option.id, "label": option.label, "tradeoff": option.tradeoff}
            for option in question.options
        ],
        "recommendation": {
            "optionId": question.recommendation.option_id,
            "rationale": question.recommendation.rationale,
        },
        "falsifier": question.falsifier,
        "evidence": list(question.evidence),
        "fingerprint": owner_question_fingerprint(question),
    }


def decision_to_api(decision: OwnerDecision) -> dict:
    return {
        "question": question_to_api(decision.question),
        "fingerprint": decision.fingerprint,
        "revision": decision.revision,
        "answeredAt": decision.answered_at,
        "answeredBy": decision.answered_by,
        "kind": decision.kind,
        "optionId": decision.option_id,
        "text": decision.text,
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def ledger_snapshot(cfg, root: Path) -> bytes | None:
    """Return exact durable bytes for transaction rollback."""
    path = answers_path(cfg, root)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise QuestionAnswerError(
            "question answers ledger must be a regular file, not a symlink"
        )
    return path.read_bytes()


def restore_answers(cfg, root: Path, snapshot: bytes | None) -> None:
    path = answers_path(cfg, root)
    if snapshot is None:
        path.unlink(missing_ok=True)
    else:
        _atomic_write(path, snapshot)


def append_answers(graph: Graph, cfg, root: Path, answers: list[dict], *,
                   expected_revision: int) -> tuple[dict, list[OwnerDecision]]:
    """Validate and atomically append one or more owner answers."""
    if (isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
            or expected_revision < 0):
        raise QuestionAnswerError("expectedRevision must be a non-negative integer")
    if not isinstance(answers, list) or not answers or len(answers) > 100:
        raise QuestionAnswerError("answers must contain 1..100 question answers")
    ledger, _ = read_answers(cfg, root)
    assert ledger is not None
    if expected_revision != ledger["revision"]:
        raise QuestionAnswerConflict(
            f"stale question answer revision {expected_revision}; "
            f"current is {ledger['revision']}"
        )
    open_by_id = {question.id: question for question in graph.owner_questions}
    prior_by_id = {
        decision.question.id: decision for decision in graph.owner_decisions
    }
    seen: set[str] = set()
    new_entries = []
    answered_at = _now()
    for offset, answer in enumerate(answers, start=1):
        if not isinstance(answer, dict):
            raise QuestionAnswerError("each answer must be a JSON object")
        required = {"questionId", "expectedFingerprint", "kind"}
        allowed = required | {"optionId", "text"}
        missing = sorted(required - set(answer))
        unknown = sorted(set(answer) - allowed)
        if missing or unknown:
            field = (missing or unknown)[0]
            raise QuestionAnswerError(
                f"answer has unknown or missing field: {field}"
            )
        question_id = answer["questionId"]
        if not isinstance(question_id, str) or not question_id:
            raise QuestionAnswerError("answer questionId must be a non-empty string")
        if question_id in seen:
            raise QuestionAnswerError(f"duplicate answer for question {question_id}")
        seen.add(question_id)
        expected_fingerprint = answer["expectedFingerprint"]
        if (not isinstance(expected_fingerprint, str)
                or not _FINGERPRINT_RE.fullmatch(expected_fingerprint)):
            raise QuestionAnswerError(
                "expectedFingerprint must be lowercase SHA-256"
            )
        question = open_by_id.get(question_id)
        if question is None:
            prior = prior_by_id.get(question_id)
            if prior is not None:
                raise QuestionAnswerConflict(
                    f"question {question_id} is already answered at revision "
                    f"{prior.revision}"
                )
            raise QuestionNotFoundError(f"unknown open question: {question_id}")
        fingerprint = owner_question_fingerprint(question)
        if expected_fingerprint != fingerprint:
            raise QuestionAnswerConflict(
                f"stale question fingerprint for {question_id}; reload required"
            )
        kind = answer["kind"]
        option_id = answer.get("optionId")
        text = answer.get("text")
        if kind == "option":
            option_ids = {option.id for option in question.options}
            if option_id not in option_ids or text is not None:
                raise QuestionAnswerError(
                    "option answer must select a current option only"
                )
        elif kind == "freeform":
            if (option_id is not None or not isinstance(text, str)
                    or not text.strip() or len(text) > MAX_FREEFORM_LENGTH):
                raise QuestionAnswerError(
                    f"freeform answer must contain 1..{MAX_FREEFORM_LENGTH} characters"
                )
            text = text.strip()
        else:
            raise QuestionAnswerError("answer kind must be option or freeform")
        new_entries.append({
            "revision": ledger["revision"] + offset,
            "questionId": question.id,
            "question": asdict(question),
            "fingerprint": fingerprint,
            "answeredAt": answered_at,
            "answeredBy": "owner",
            "kind": kind,
            "optionId": option_id,
            "text": text,
        })
    revision = ledger["revision"] + len(new_entries)
    updated = {
        "schema": SCHEMA,
        "revision": revision,
        "answers": [*ledger["answers"], *new_entries],
    }
    normalized = _validate_ledger(updated)
    payload = (json.dumps(normalized, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    _atomic_write(answers_path(cfg, root), payload)
    return normalized, [_decision(entry) for entry in new_entries]


def append_answer(graph: Graph, cfg, root: Path, question_id: str, *,
                  expected_revision: int, expected_fingerprint: str,
                  kind: str, option_id: str | None = None,
                  text: str | None = None) -> tuple[dict, OwnerDecision]:
    """Compatibility wrapper for one-answer callers."""
    ledger, decisions = append_answers(
        graph, cfg, root, [{
            "questionId": question_id,
            "expectedFingerprint": expected_fingerprint,
            "kind": kind,
            "optionId": option_id,
            "text": text,
        }], expected_revision=expected_revision,
    )
    return ledger, decisions[0]
