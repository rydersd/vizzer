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
        return cls(
            groups=[Group(**g) for g in d.get("groups", [])],
            items=[Item(**i) for i in d.get("items", [])],
            conflicts=list(d.get("conflicts", [])),
            warnings=list(d.get("warnings", [])),
            vocab=dict(d.get("vocab", {})),
        )

    def item_map(self) -> dict[str, Item]:
        return {i.id: i for i in self.items}
