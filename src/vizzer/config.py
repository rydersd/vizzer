"""vizzer.toml loading via a bundled TOML-subset parser (stdlib-only, py3.10-safe).

Supported subset — this is the config contract, full TOML is deliberately out:
  comments (#), [section] / [a.b], [[array-of-tables]] (single-segment name),
  key = "string" | true | false | integer | ["strings", ...].
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    pass


DEFAULT_STATUSES = [
    {"name": "idea", "emoji": "💡", "done": False},
    {"name": "backlog", "emoji": "📋", "done": False},
    {"name": "specced", "emoji": "📝", "done": False},
    {"name": "ready", "emoji": "🟢", "done": False},
    {"name": "building", "emoji": "🔧", "done": False},
    {"name": "in-flight", "emoji": "✈️", "done": False},
    {"name": "bug-gap", "emoji": "🐛", "done": False},
    {"name": "shipped", "emoji": "✅", "done": True},
    {"name": "verified", "emoji": "🏁", "done": True},
    {"name": "parked", "emoji": "⏸️", "done": False},
    {"name": "unknown", "emoji": "❔", "done": False},
]

DEFAULTS = {
    "project": {"name": "project"},
    "sources": {
        "spec_tree": {"enabled": False, "glob": "", "levels": [],
                      "item_kind": "story", "dag_import": ""},
        "ledgers": {"enabled": False, "glob": "thoughts/ledgers/CONTINUITY_*.md"},
        "loose_docs": {"enabled": False, "globs": []},
        "todos": {"enabled": False, "globs": ["TODO.md"]},
    },
    "render": {"output_dir": "vizzer/views",
               "releases": ["R0", "R1", "R2", "R3"],
               "recommended": [], "obsidian_links": False, "title": ""},
    "reconcile": {"precedence": ["spec_tree", "dag_import", "ledgers", "todos", "loose_docs"],
                  "mention_globs": [], "staleness_days": 14},
    "archive": {"adapters": ["todos"]},
}

_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*=\s*(.+)$")


def _strip_comment(line: str) -> str:
    out, in_quotes = [], False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        if ch == "#" and not in_quotes:
            break
        out.append(ch)
    return "".join(out)


def _parse_value(raw: str, n: int):
    raw = raw.strip()
    if raw in ("true", "false"):
        return raw == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw.startswith("["):
        if not raw.endswith("]"):
            raise ConfigError(f"line {n}: unterminated array")
        inner = raw[1:-1].strip()
        if not inner:
            return []
        out = []
        for part in (p.strip() for p in inner.split(",") if p.strip()):
            if not (part.startswith('"') and part.endswith('"')):
                raise ConfigError(f"line {n}: arrays may contain only strings")
            out.append(part[1:-1])
        return out
    raise ConfigError(f"line {n}: unsupported value {raw!r}")


def parse_toml_subset(text: str) -> dict:
    root: dict = {}
    target = root
    for n, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[["):
            if not line.endswith("]]"):
                raise ConfigError(f"line {n}: bad table-array header")
            name = line[2:-2].strip()
            if not name or "." in name:
                raise ConfigError(f"line {n}: table arrays must be single-segment")
            arr = root.setdefault(name, [])
            if not isinstance(arr, list):
                raise ConfigError(f"line {n}: {name!r} already defined as a value")
            target = {}
            arr.append(target)
        elif line.startswith("["):
            if not line.endswith("]"):
                raise ConfigError(f"line {n}: bad section header")
            target = root
            for part in line[1:-1].strip().split("."):
                target = target.setdefault(part, {})
                if not isinstance(target, dict):
                    raise ConfigError(f"line {n}: section conflicts with a value")
        else:
            m = _KEY_RE.match(line)
            if not m:
                raise ConfigError(f"line {n}: cannot parse {line!r}")
            target[m.group(1)] = _parse_value(m.group(2), n)
    return root


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@dataclass
class Config:
    data: dict
    path: Path | None = None

    def get(self, dotted: str, default=None):
        cur = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @property
    def vocab(self) -> dict:
        statuses = self.data.get("status") or DEFAULT_STATUSES
        return {"statuses": [dict(s) for s in statuses]}

    def status_meta(self, name: str) -> dict:
        for s in self.vocab["statuses"]:
            if s.get("name") == name:
                return {"name": name, "emoji": s.get("emoji", "❔"),
                        "done": bool(s.get("done", False))}
        return {"name": name, "emoji": "❔", "done": False}

    def done_statuses(self) -> set[str]:
        return {s["name"] for s in self.vocab["statuses"] if s.get("done")}

    def gates(self) -> dict:
        return {g["item"]: g.get("reason", "") for g in self.data.get("gates", [])
                if isinstance(g, dict) and g.get("item")}

    def groups(self) -> list[dict]:
        groups = self.data.get("group", [])
        if not isinstance(groups, list):
            return []
        return [dict(group) for group in groups if isinstance(group, dict)]

    @classmethod
    def load(cls, root: Path) -> "Config":
        path = Path(root) / "vizzer" / "vizzer.toml"
        data = copy.deepcopy(DEFAULTS)
        if path.is_file():
            data = deep_merge(data, parse_toml_subset(path.read_text(encoding="utf-8")))
        return cls(data=data, path=path if path.is_file() else None)
