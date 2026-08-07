"""Normalized work graph: dataclasses + deterministic (de)serialization."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

SCHEMA = 1


@dataclass
class Group:
    id: str
    kind: str
    title: str
    parent: str | None = None
    meta: dict = field(default_factory=dict)


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
    appetite: str | None = None
    flags: list[str] = field(default_factory=list)
    source: dict = field(default_factory=dict)
    activity: dict = field(default_factory=dict)


def _group_from_dict(data: dict) -> Group:
    group = Group(**data)
    if not all(isinstance(value, str) for value in (group.id, group.kind, group.title)):
        raise ValueError("graph group id, kind, and title must be strings")
    if group.parent is not None and not isinstance(group.parent, str):
        raise ValueError("graph group parent must be a string or null")
    if not isinstance(group.meta, dict):
        raise ValueError("graph group meta must be an object")
    return group


def _item_from_dict(data: dict) -> Item:
    item = Item(**data)
    if not isinstance(item.id, str) or not isinstance(item.title, str):
        raise ValueError("graph item id and title must be strings")
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
    if not isinstance(item.source, dict) or not isinstance(item.activity, dict):
        raise ValueError("graph item source and activity must be objects")
    for field_name in ("adapter", "path"):
        value = item.source.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"graph item source {field_name} must be a string or null")
    return item


@dataclass
class Graph:
    groups: list[Group] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    vocab: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "groups": sorted((asdict(g) for g in self.groups), key=lambda g: g["id"]),
            "items": sorted((asdict(i) for i in self.items), key=lambda i: i["id"]),
            "conflicts": sorted(self.conflicts,
                                key=lambda c: (c.get("item", ""), c.get("field", ""))),
            "warnings": sorted(self.warnings),
            "vocab": self.vocab,
        }

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, d: dict) -> "Graph":
        if not isinstance(d, dict):
            raise ValueError("graph must be a JSON object")

        groups = d.get("groups", [])
        items = d.get("items", [])
        if not isinstance(groups, list):
            raise ValueError("graph groups must be a list")
        if not isinstance(items, list):
            raise ValueError("graph items must be a list")

        conflicts = d.get("conflicts", [])
        warnings = d.get("warnings", [])
        vocab = d.get("vocab", {})
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
        statuses = vocab.get("statuses")
        if statuses is not None and (
            not isinstance(statuses, list)
            or not all(
                isinstance(value, dict) and isinstance(value.get("name"), str)
                for value in statuses
            )
        ):
            raise ValueError("graph vocab statuses must be named objects")

        return cls(
            groups=[_group_from_dict(g) for g in groups if isinstance(g, dict)],
            items=[_item_from_dict(i) for i in items if isinstance(i, dict)],
            conflicts=list(conflicts),
            warnings=list(warnings),
            vocab=dict(vocab),
        )

    def item_map(self) -> dict[str, Item]:
        return {i.id: i for i in self.items}
