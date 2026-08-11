"""Normalized work graph: dataclasses + deterministic (de)serialization."""
from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass, field, asdict

SCHEMA = 2
SUPPORTED_SCHEMAS = {1, SCHEMA}
_ACTIVITY_TEXT_FIELDS = {"created", "modified"}
_RELATION_KIND_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_FACET_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
ITEM_ROLES = {"delivery", "coverage", "evidence", "decision", "reference"}


def _validate_id(value: str, subject: str) -> None:
    prefix, separator, suffix = value.partition(":")
    if not separator or not prefix.strip() or not suffix.strip():
        raise ValueError(
            f"graph {subject} id must contain non-empty kind and slug separated by ':'"
        )


@dataclass
class Group:
    id: str
    kind: str
    title: str
    parent: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class Relation:
    """A typed, nonblocking edge from an item to another item.

    Hard prerequisites deliberately remain in ``Item.deps``.  Keeping lineage
    here prevents a "revises" or "bug against" link from accidentally changing
    readiness while allowing renderers to show the fuller story graph.
    """

    kind: str
    target: str


# codex-sequence-2026-08-08: live work is an overlay, never lifecycle truth.
@dataclass
class ActiveWork:
    story_id: str
    agent: str
    task: str
    state: str
    completed: int
    total: int
    updated_at: str
    stale_at: str
    checkpoint: str | None = None
    related_story_ids: list[str] = field(default_factory=list)


@dataclass
class OwnerQuestionOption:
    id: str
    label: str
    tradeoff: str


@dataclass
class OwnerQuestionRecommendation:
    option_id: str
    rationale: str


@dataclass
class OwnerQuestion:
    id: str
    story_id: str
    owner: str
    prompt: str
    options: list[OwnerQuestionOption]
    recommendation: OwnerQuestionRecommendation
    falsifier: str
    evidence: list[str]


def owner_question_fingerprint(question: OwnerQuestion) -> str:
    """Return the canonical content identity used by answer compare-and-swap.

    The question id alone is deliberately insufficient: an agent may refine a
    prompt, option, recommendation, falsifier, or evidence while an older page
    remains open.  List order is meaningful presentation data, while object key
    order is not.
    """
    canonical = json.dumps(
        asdict(question), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass
class OwnerDecision:
    """An accepted answer reconciled against its exact current question."""

    question: OwnerQuestion
    fingerprint: str
    revision: int
    answered_at: str
    answered_by: str
    kind: str
    option_id: str | None = None
    text: str | None = None


@dataclass
class Item:
    id: str
    title: str
    one_liner: str | None = None
    status: str = "unknown"
    release: str | None = None
    wave: str | None = None
    group: str | None = None
    deps: list[str] = field(default_factory=list)
    # codex-sequence-2026-08-08: typed nonblocking story relationships.
    relations: list[Relation] = field(default_factory=list)
    appetite: str | None = None
    # What this item contributes to. Structural location and portfolio meaning
    # are deliberately separate: a ledger phase is evidence, not delivery work.
    role: str = "delivery"
    # Authored free labels stay distinct from operational flags such as blocked.
    tags: list[str] = field(default_factory=list)
    # Many-to-many project dimensions (for example product and capability).
    facets: dict[str, list[str]] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    source: dict = field(default_factory=dict)
    activity: dict = field(default_factory=dict)
    # Derived, explainable recommendation components. Empty when disabled.
    priority: dict = field(default_factory=dict)
    # Generated trail/stall evidence. Never a source lifecycle field.
    progress: dict = field(default_factory=dict)


# codex-sequence-2026-08-08: milestone membership is derived DAG metadata.
@dataclass
class MilestonePhase:
    name: str
    items: list[str] = field(default_factory=list)


@dataclass
class Milestone:
    id: str
    title: str
    goal: str = ""
    phases: list[MilestonePhase] = field(default_factory=list)


def _group_from_dict(data: dict) -> Group:
    group = Group(**data)
    if not all(isinstance(value, str) for value in (group.id, group.kind, group.title)):
        raise ValueError("graph group id, kind, and title must be strings")
    _validate_id(group.id, "group")
    if group.parent is not None and not isinstance(group.parent, str):
        raise ValueError("graph group parent must be a string or null")
    if not isinstance(group.meta, dict):
        raise ValueError("graph group meta must be an object")
    return group


def _item_from_dict(data: dict) -> Item:
    raw_relations = data.get("relations", [])
    if not isinstance(raw_relations, list):
        raise ValueError("graph item relations must be a list")
    relations = []
    for raw in raw_relations:
        if not isinstance(raw, dict):
            raise ValueError("graph item relation must be an object")
        kind = raw.get("kind")
        target = raw.get("target")
        if not isinstance(kind, str) or not _RELATION_KIND_RE.fullmatch(kind):
            raise ValueError("graph item relation kind must be a typed identifier")
        if not isinstance(target, str):
            raise ValueError("graph item relation target must be a string")
        _validate_id(target, "relation target")
        relations.append(Relation(kind=kind, target=target))

    item_data = dict(data)
    item_data["relations"] = relations
    if "role" not in item_data:
        prefix = str(item_data.get("id", "")).partition(":")[0]
        item_data["role"] = {
            "product-capability": "coverage",
            "phase": "evidence",
            "doc": "reference",
        }.get(prefix, "delivery")
    item = Item(**item_data)
    if not isinstance(item.id, str) or not isinstance(item.title, str):
        raise ValueError("graph item id and title must be strings")
    _validate_id(item.id, "item")
    if not isinstance(item.status, str):
        raise ValueError("graph item status must be a string")
    optional_strings = (
        item.one_liner,
        item.release,
        item.wave,
        item.group,
        item.appetite,
    )
    if any(value is not None and not isinstance(value, str) for value in optional_strings):
        raise ValueError("graph item optional text fields must be strings or null")
    if not isinstance(item.deps, list) or not all(
        isinstance(value, str) for value in item.deps
    ):
        raise ValueError("graph item deps must be a list of strings")
    if not isinstance(item.flags, list) or not all(
        isinstance(value, str) for value in item.flags
    ):
        raise ValueError("graph item flags must be a list of strings")
    if item.role not in ITEM_ROLES:
        raise ValueError(f"graph item role must be one of {sorted(ITEM_ROLES)}")
    if not isinstance(item.tags, list) or not all(
        isinstance(value, str) and value for value in item.tags
    ):
        raise ValueError("graph item tags must be a list of non-empty strings")
    if not isinstance(item.facets, dict):
        raise ValueError("graph item facets must be an object")
    for name, values in item.facets.items():
        if not isinstance(name, str) or not _FACET_NAME_RE.fullmatch(name):
            raise ValueError("graph item facet names must be typed identifiers")
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            raise ValueError("graph item facet values must be non-empty strings")
    if not isinstance(item.source, dict) or not isinstance(item.activity, dict):
        raise ValueError("graph item source and activity must be objects")
    if not isinstance(item.priority, dict) or not isinstance(item.progress, dict):
        raise ValueError("graph item priority and progress must be objects")
    for field_name in ("adapter", "path"):
        value = item.source.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"graph item source {field_name} must be a string or null")
    for field_name, value in item.activity.items():
        if field_name in _ACTIVITY_TEXT_FIELDS:
            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"graph item activity {field_name} must be a string or null"
                )
        elif value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise ValueError(
                f"graph item activity {field_name} must be numeric or null"
            )
    return item


def _validate_group_parents(groups: list[Group]) -> None:
    parents = {group.id: group.parent for group in groups}
    complete = set()
    for group in groups:
        current = group.id
        path = set()
        while current in parents and current not in complete:
            if current in path:
                raise ValueError("graph group parent cycle detected")
            path.add(current)
            current = parents[current]
        complete.update(path)


def _milestone_from_dict(data: dict) -> Milestone:
    phases = data.get("phases", [])
    if not isinstance(phases, list):
        raise ValueError("graph milestone phases must be a list")
    parsed_phases = []
    for phase in phases:
        if not isinstance(phase, dict) or not isinstance(phase.get("name"), str):
            raise ValueError("graph milestone phase must be a named object")
        items = phase.get("items", [])
        if not isinstance(items, list) or not all(isinstance(value, str) for value in items):
            raise ValueError("graph milestone phase items must be a list of strings")
        parsed_phases.append(MilestonePhase(name=phase["name"], items=list(items)))
    milestone = Milestone(
        id=data.get("id"),
        title=data.get("title"),
        goal=data.get("goal", ""),
        phases=parsed_phases,
    )
    if not all(isinstance(value, str) for value in (
        milestone.id, milestone.title, milestone.goal
    )):
        raise ValueError("graph milestone id, title, and goal must be strings")
    return milestone


def _active_work_from_dict(data: dict) -> ActiveWork:
    try:
        work = ActiveWork(**data)
    except TypeError as exc:
        raise ValueError("graph active work has unknown or missing fields") from exc
    text = (work.story_id, work.agent, work.task, work.state,
            work.updated_at, work.stale_at)
    if not all(isinstance(value, str) and value for value in text):
        raise ValueError("graph active work text fields must be non-empty strings")
    _validate_id(work.story_id, "active work story")
    if work.checkpoint is not None and not isinstance(work.checkpoint, str):
        raise ValueError("graph active work checkpoint must be a string or null")
    if (isinstance(work.completed, bool) or not isinstance(work.completed, int)
            or isinstance(work.total, bool) or not isinstance(work.total, int)
            or work.completed < 0 or work.total < 0 or work.completed > work.total):
        raise ValueError("graph active work requires 0 <= completed <= total")
    if not isinstance(work.related_story_ids, list) or not all(
        isinstance(value, str) for value in work.related_story_ids
    ):
        raise ValueError("graph active work related story ids must be strings")
    return work


def owner_question_from_dict(data: dict) -> OwnerQuestion:
    try:
        options_raw = data["options"]
        recommendation_raw = data["recommendation"]
        options = [OwnerQuestionOption(**value) for value in options_raw]
        recommendation = OwnerQuestionRecommendation(**recommendation_raw)
        question = OwnerQuestion(
            id=data["id"],
            story_id=data["story_id"],
            owner=data["owner"],
            prompt=data["prompt"],
            options=options,
            recommendation=recommendation,
            falsifier=data["falsifier"],
            evidence=data["evidence"],
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("graph owner question has unknown or missing fields") from exc
    text = (question.id, question.story_id, question.owner, question.prompt,
            question.recommendation.option_id, question.recommendation.rationale,
            question.falsifier)
    if not all(isinstance(value, str) and value for value in text):
        raise ValueError("graph owner question text fields must be non-empty strings")
    _validate_id(question.id, "owner question")
    _validate_id(question.story_id, "owner question story")
    if len(question.options) not in (2, 3):
        raise ValueError("graph owner question requires 2 or 3 options")
    option_ids = [option.id for option in question.options]
    if len(option_ids) != len(set(option_ids)):
        raise ValueError("graph owner question option ids must be unique")
    for option in question.options:
        if not all(isinstance(value, str) and value for value in (
            option.id, option.label, option.tradeoff
        )):
            raise ValueError("graph owner question options require non-empty text")
    if question.recommendation.option_id not in option_ids:
        raise ValueError("graph owner question recommendation must name an option")
    if not isinstance(question.evidence, list) or not question.evidence or not all(
        isinstance(value, str) and value for value in question.evidence
    ):
        raise ValueError("graph owner question evidence must be non-empty strings")
    return question


def owner_decision_from_dict(data: dict) -> OwnerDecision:
    try:
        allowed = {
            "question", "fingerprint", "revision", "answered_at", "answered_by",
            "kind", "option_id", "text",
        }
        if set(data) != allowed:
            raise TypeError
        decision = OwnerDecision(
            question=owner_question_from_dict(data["question"]),
            fingerprint=data["fingerprint"],
            revision=data["revision"],
            answered_at=data["answered_at"],
            answered_by=data["answered_by"],
            kind=data["kind"],
            option_id=data["option_id"],
            text=data["text"],
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("graph owner decision has unknown or missing fields") from exc
    if not isinstance(decision.fingerprint, str) or not re.fullmatch(
        r"[0-9a-f]{64}", decision.fingerprint
    ):
        raise ValueError("graph owner decision fingerprint must be lowercase SHA-256")
    if decision.fingerprint != owner_question_fingerprint(decision.question):
        raise ValueError("graph owner decision fingerprint does not match its question")
    if (isinstance(decision.revision, bool)
            or not isinstance(decision.revision, int) or decision.revision <= 0):
        raise ValueError("graph owner decision revision must be a positive integer")
    if not all(isinstance(value, str) and value for value in (
        decision.answered_at, decision.answered_by, decision.kind
    )):
        raise ValueError("graph owner decision audit fields must be non-empty strings")
    option_ids = {option.id for option in decision.question.options}
    if decision.kind == "option":
        if decision.option_id not in option_ids or decision.text is not None:
            raise ValueError("graph option decision must select a current option only")
    elif decision.kind == "freeform":
        if decision.option_id is not None or not isinstance(decision.text, str) \
                or not decision.text.strip():
            raise ValueError("graph freeform decision must contain text only")
    else:
        raise ValueError("graph owner decision kind must be option or freeform")
    return decision


@dataclass
class Graph:
    groups: list[Group] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    vocab: dict = field(default_factory=dict)
    # codex-sequence-2026-08-08: target provenance and ranked recommendation ids.
    priority: dict = field(default_factory=dict)
    # Deterministic delivery profiles and feasible portfolio suggestions.
    assessment: dict = field(default_factory=dict)
    # codex-sequence-2026-08-08: switchable, timestamped agent-activity lens.
    active_work: list[ActiveWork] = field(default_factory=list)
    # Explicit researched decisions. Generic blocked work is not a question.
    owner_questions: list[OwnerQuestion] = field(default_factory=list)
    # Accepted answers are separate from open questions and remain auditable.
    owner_decisions: list[OwnerDecision] = field(default_factory=list)
    activity: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        serialized_items = []
        for item in self.items:
            serialized = asdict(item)
            # Optional extensions stay absent when unused so schema-1 readers and
            # existing checked-in graphs remain byte-stable until enabled.
            if not serialized["relations"]:
                serialized.pop("relations")
            if not serialized["priority"]:
                serialized.pop("priority")
            if not serialized["progress"]:
                serialized.pop("progress")
            if not serialized["tags"]:
                serialized.pop("tags")
            if not serialized["facets"]:
                serialized.pop("facets")
            serialized_items.append(serialized)

        result = {
            "schema": SCHEMA,
            "groups": sorted((asdict(g) for g in self.groups), key=lambda g: g["id"]),
            "items": sorted(serialized_items, key=lambda i: i["id"]),
            "milestones": sorted(
                (asdict(milestone) for milestone in self.milestones),
                key=lambda milestone: milestone["id"],
            ),
            "conflicts": sorted(self.conflicts,
                                key=lambda c: (c.get("item", ""), c.get("field", ""))),
            "warnings": sorted(self.warnings),
            "vocab": self.vocab,
        }
        if self.priority:
            result["priority"] = self.priority
        if self.assessment:
            result["assessment"] = self.assessment
        if self.active_work:
            result["active_work"] = [
                asdict(work) for work in sorted(
                    self.active_work,
                    key=lambda work: (work.story_id, work.agent, work.task),
                )
            ]
        if self.owner_questions:
            result["owner_questions"] = [
                asdict(question) for question in sorted(
                    self.owner_questions,
                    key=lambda question: question.id,
                )
            ]
        if self.owner_decisions:
            result["owner_decisions"] = [
                asdict(decision) for decision in sorted(
                    self.owner_decisions,
                    key=lambda decision: (decision.question.id, decision.revision),
                )
            ]
        if self.activity:
            result["activity"] = self.activity
        return result

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, d: dict) -> "Graph":
        if not isinstance(d, dict):
            raise ValueError("graph must be a JSON object")
        schema = d.get("schema", 1)
        if schema not in SUPPORTED_SCHEMAS:
            raise ValueError(
                f"graph schema must be one of {sorted(SUPPORTED_SCHEMAS)}"
            )

        groups = d.get("groups", [])
        items = d.get("items", [])
        milestones = d.get("milestones", [])
        if not isinstance(groups, list):
            raise ValueError("graph groups must be a list")
        if not isinstance(items, list):
            raise ValueError("graph items must be a list")
        if not isinstance(milestones, list):
            raise ValueError("graph milestones must be a list")

        conflicts = d.get("conflicts", [])
        warnings = d.get("warnings", [])
        vocab = d.get("vocab", {})
        priority = d.get("priority", {})
        assessment = d.get("assessment", {})
        active_work = d.get("active_work", [])
        owner_questions = d.get("owner_questions", [])
        owner_decisions = d.get("owner_decisions", [])
        activity = d.get("activity", {})
        if not isinstance(conflicts, list) or not all(
            isinstance(value, dict) for value in conflicts
        ):
            raise ValueError("graph conflicts must be a list of objects")
        if not isinstance(warnings, list) or not all(
            isinstance(value, str) for value in warnings
        ):
            raise ValueError("graph warnings must be a list of strings")
        if not isinstance(vocab, dict):
            raise ValueError("graph vocab must be an object")
        if not isinstance(priority, dict):
            raise ValueError("graph priority must be an object")
        if not isinstance(assessment, dict):
            raise ValueError("graph assessment must be an object")
        if not isinstance(active_work, list) or not all(
            isinstance(value, dict) for value in active_work
        ):
            raise ValueError("graph active_work must be a list of objects")
        if not isinstance(owner_questions, list) or not all(
            isinstance(value, dict) for value in owner_questions
        ):
            raise ValueError("graph owner_questions must be a list of objects")
        if not isinstance(owner_decisions, list) or not all(
            isinstance(value, dict) for value in owner_decisions
        ):
            raise ValueError("graph owner_decisions must be a list of objects")
        if not isinstance(activity, dict):
            raise ValueError("graph activity must be an object")
        statuses = vocab.get("statuses")
        if statuses is not None and (
            not isinstance(statuses, list)
            or not all(
                isinstance(value, dict) and isinstance(value.get("name"), str)
                for value in statuses
            )
        ):
            raise ValueError("graph vocab statuses must be named objects")

        parsed_groups = [_group_from_dict(g) for g in groups if isinstance(g, dict)]
        parsed_items = [_item_from_dict(i) for i in items if isinstance(i, dict)]
        parsed_milestones = [
            _milestone_from_dict(milestone)
            for milestone in milestones
            if isinstance(milestone, dict)
        ]
        parsed_work = [_active_work_from_dict(work) for work in active_work]
        parsed_questions = [owner_question_from_dict(question)
                            for question in owner_questions]
        parsed_decisions = [owner_decision_from_dict(decision)
                            for decision in owner_decisions]
        question_ids = [question.id for question in parsed_questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("graph owner question ids must be unique")
        decision_ids = [decision.question.id for decision in parsed_decisions]
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("graph owner decision question ids must be unique")
        if set(question_ids) & set(decision_ids):
            raise ValueError("graph owner questions and decisions must be disjoint")
        item_ids = {item.id for item in parsed_items}
        orphan_questions = [question.id for question in parsed_questions
                            if question.story_id not in item_ids]
        if orphan_questions:
            raise ValueError("graph owner questions must reference existing items")
        orphan_decisions = [decision.question.id for decision in parsed_decisions
                            if decision.question.story_id not in item_ids]
        if orphan_decisions:
            raise ValueError("graph owner decisions must reference existing items")
        _validate_group_parents(parsed_groups)

        return cls(
            groups=parsed_groups,
            items=parsed_items,
            milestones=parsed_milestones,
            conflicts=list(conflicts),
            warnings=list(warnings),
            vocab=dict(vocab),
            priority=dict(priority),
            assessment=dict(assessment),
            active_work=parsed_work,
            owner_questions=parsed_questions,
            owner_decisions=parsed_decisions,
            activity=dict(activity),
        )

    def item_map(self) -> dict[str, Item]:
        return {i.id: i for i in self.items}
