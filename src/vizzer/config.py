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

from .model import ITEM_ROLES


SOURCE_AREA_ROLES = {"delivery", "knowledge", "planning", "evidence", "operations"}
SOURCE_AREA_ADAPTERS = {"spec_tree", "loose_docs", "ledgers", "todos", "none"}


class ConfigError(Exception):
    pass


DEFAULT_STATUSES = [
    # codex-sequence-2026-08-08: roles make dashboard lifecycle buckets data.
    {"name": "idea", "emoji": "💡", "done": False, "role": "ready"},
    {"name": "backlog", "emoji": "📋", "done": False, "role": "ready"},
    {"name": "specced", "emoji": "📝", "done": False, "role": "ready"},
    {"name": "ready", "emoji": "🟢", "done": False, "role": "ready"},
    {"name": "building", "emoji": "🔧", "done": False, "role": "active"},
    {"name": "in-flight", "emoji": "✈️", "done": False, "role": "active"},
    {"name": "bug-gap", "emoji": "🐛", "done": False, "role": "active"},
    {"name": "shipped", "emoji": "✅", "done": True, "role": "done"},
    {"name": "verified", "emoji": "🏁", "done": True, "role": "done"},
    {"name": "parked", "emoji": "⏸️", "done": False, "role": "hold"},
    {"name": "unknown", "emoji": "❔", "done": False, "role": "ready"},
]

DEFAULTS = {
    "project": {"name": "project"},
    # Zero preserves portable ephemeral binding; projects may pin a bookmarkable
    # loopback port without teaching every invocation the number.
    "server": {"port": 0},
    "sources": {
        "spec_tree": {"enabled": False, "glob": "", "levels": [],
                      "item_kind": "story", "dag_import": "",
                      "foundation_index": "",
                      "product_tags": []},
        "ledgers": {"enabled": False, "glob": "thoughts/ledgers/CONTINUITY_*.md"},
        "loose_docs": {"enabled": False, "globs": [], "item_role": "reference"},
        "todos": {"enabled": False, "globs": ["TODO.md"]},
    },
    "render": {"output_dir": "vizzer/views",
               "releases": ["R0", "R1", "R2", "R3"],
               "recommended": [], "obsidian_links": False, "title": ""},
    # Optional precompiled developer-object graph. Core has no Node/React runtime.
    "developer_flow": {
        "enabled": False,
        "materialization_cap": 1_200,
        "direction": "RIGHT",
    },
    "reconcile": {"precedence": ["spec_tree", "dag_import", "ledgers", "todos", "loose_docs"],
                  # codex-sequence-2026-08-08: optional field-specific migration seam.
                  "dependency_authority": "", "group_parent_authority": "",
                  "retire_empty_groups": [],
                  "mention_globs": [], "staleness_days": 14},
    "archive": {"adapters": ["todos"]},
    # codex-sequence-2026-08-08: target-scoped, explainable uptake; opt-in.
    "priority": {
        "enabled": False,
        "target_manifest": "",
        "target_items": [],
        "target_milestones": [],
        "target_releases": [],
        "limit": 10,
        "eligible_roles": ["ready", "active", "regression"],
        "exclude_flags": ["blocked", "triage", "needs-triage", "stale"],
        "role_bias": {"regression": 80, "active": 50, "ready": 0},
    },
    # Delivery assessment is orthogonal to uptake priority. It normalizes the
    # authored appetite, records uncertainty/evidence, and proposes a feasible
    # mixed-size portfolio without inventing an AI productivity multiplier.
    "assessment": {
        "enabled": False,
        "signals_path": "vizzer/assessment-signals.json",
        "small_limit": 4,
        "anchor_limit": 2,
        "question_limit": 1,
        "verification_globs": ["tests/**/*", "test/**/*", "tests-ui/**/*"],
    },
    # Accepted owner course changes compose over target authority; they never
    # rewrite story headers, lifecycle, releases, or dependency edges.
    "planning": {"enabled": False,
                 "overlay_path": "vizzer/planning-overlay.json"},
    # Accepted owner answers are source input in a separate audited ledger.
    "questions": {"answers_path": "vizzer/question-answers.json"},
    # Provider lanes select which future agent session should discuss a Story.
    "discussions": {"queue_path": "vizzer/discussion-queue.json"},
    # codex-sequence-2026-08-08: optional live-work lens, isolated from priority.
    "activity": {"path": "", "stale_after_minutes": 120, "trail_rounds": 5},
    # Durable workstream intent is repo data; leased live sessions are local runtime.
    "workstreams": {
        "enabled": False,
        "definitions_path": "vizzer/workstreams.json",
        "runtime_path": ".vizzer/runtime/sessions.json",
        "lease_minutes": 30,
    },
    # Review plans are authored acceptance instructions. Agent and owner runs
    # are append-only evidence in separate per-plan ledgers.
    "reviews": {
        "enabled": False,
        "plans_dir": "vizzer/reviews/plans",
        "runs_dir": "vizzer/reviews/runs",
        "evidence_dir": "vizzer/reviews/evidence",
        "adapters_path": "vizzer/reviews/adapters.json",
    },
    # Semantic project map. Folder names are user data, not Vizzer conventions.
    "source_area": [],
    # Optional named navigation slices over any item facet. Array-of-tables is
    # used because the bundled TOML subset deliberately avoids inline objects.
    "area": [],
    # Optional generated semantic history; prose and raw git timestamps are excluded.
    "progress": {"history_path": "", "hot_window_days": 7,
                 "stalled_after_days": 14, "stall_max_days": 90,
                 "backfill_days": 7, "backfill_max_commits_per_story": 48},
}

_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*=\s*(.+)$")


# codex-sequence-2026-08-08: source-independent lifecycle validation boundary.
def _validate_statuses(statuses: object) -> None:
    """Validate optional lifecycle metadata without constraining source prose.

    A configured vocabulary is authoritative only for its own declarations.
    Source adapters may still encounter an unfamiliar status and record it as
    such; rejecting a whole refresh for a stray document label would break the
    graceful-degradation contract.  ``next`` is therefore validated here, at
    the configuration boundary, rather than while ingesting items.
    """
    if not isinstance(statuses, list) or not statuses:
        raise ConfigError("status vocabulary must be a non-empty table array")

    names: set[str] = set()
    by_name: dict[str, dict] = {}
    for index, status in enumerate(statuses, 1):
        label = f"status #{index}"
        if not isinstance(status, dict):
            raise ConfigError(f"{label} must be a table")
        name = status.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"{label} needs a non-empty name")
        if name in names:
            raise ConfigError(f"duplicate status name {name!r}")
        names.add(name)
        by_name[name] = status

        for field in ("emoji", "role", "description"):
            if field in status and (
                not isinstance(status[field], str) or not status[field].strip()
            ):
                raise ConfigError(f"status {name!r} {field} must be a non-empty string")
        if "done" in status and not isinstance(status["done"], bool):
            raise ConfigError(f"status {name!r} done must be true or false")

        transitions = status.get("next")
        if transitions is not None:
            if not isinstance(transitions, list) or not all(
                isinstance(target, str) and target.strip() for target in transitions
            ):
                raise ConfigError(
                    f"status {name!r} next must be an array of non-empty status names"
                )
            if len(set(transitions)) != len(transitions):
                raise ConfigError(f"status {name!r} next contains duplicate targets")
            if name in transitions:
                raise ConfigError(f"status {name!r} cannot transition to itself")

    for name, status in by_name.items():
        for target in status.get("next", []):
            if target not in by_name:
                raise ConfigError(
                    f"status {name!r} declares undefined next status {target!r}"
                )
            if status.get("done", False) and not by_name[target].get("done", False):
                raise ConfigError(
                    f"done status {name!r} cannot transition to unfinished {target!r}"
                )


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
        # Presence, rather than truthiness, distinguishes an omitted
        # vocabulary from an explicitly empty one.  The latter must not
        # silently resurrect the defaults after validation was bypassed by a
        # caller constructing Config(data=...) directly.
        statuses = self.data["status"] if "status" in self.data else DEFAULT_STATUSES
        return {"statuses": [dict(s) for s in statuses]}

    def validate(self) -> None:
        """Validate status metadata supplied by ``vizzer.toml``.

        Omitting ``[[status]]`` intentionally selects the built-in vocabulary;
        a present vocabulary replaces it, matching the existing configuration
        contract.
        """
        statuses = self.data["status"] if "status" in self.data else DEFAULT_STATUSES
        _validate_statuses(statuses)
        server_port = self.get("server.port", 0)
        if (isinstance(server_port, bool) or not isinstance(server_port, int)
                or not 0 <= server_port <= 65535):
            raise ConfigError("server.port must be an integer from 0 through 65535")
        activity_path = self.get("activity.path", "")
        if not isinstance(activity_path, str):
            raise ConfigError("activity.path must be a string")
        answers_path = self.get("questions.answers_path")
        if not isinstance(answers_path, str) or not answers_path:
            raise ConfigError("questions.answers_path must be a non-empty string")
        discussion_path = self.get("discussions.queue_path")
        if not isinstance(discussion_path, str) or not discussion_path.strip():
            raise ConfigError("discussions.queue_path must be a non-empty string")
        discussion_relative = Path(discussion_path)
        if discussion_relative.is_absolute() or ".." in discussion_relative.parts:
            raise ConfigError("discussions.queue_path must stay inside the project")
        retired_groups = self.get("reconcile.retire_empty_groups", [])
        if (not isinstance(retired_groups, list)
                or not all(isinstance(group_id, str) and group_id.strip()
                           for group_id in retired_groups)):
            raise ConfigError(
                "reconcile.retire_empty_groups must contain non-empty group ids"
            )
        if len(set(retired_groups)) != len(retired_groups):
            raise ConfigError("reconcile.retire_empty_groups contains duplicate group ids")
        loose_doc_role = self.get("sources.loose_docs.item_role")
        if loose_doc_role not in ITEM_ROLES:
            raise ConfigError(
                f"sources.loose_docs.item_role must be one of {sorted(ITEM_ROLES)}"
            )
        product_tags = self.get("sources.spec_tree.product_tags")
        if not isinstance(product_tags, list) or not all(
            isinstance(value, str) and value for value in product_tags
        ):
            raise ConfigError("sources.spec_tree.product_tags must be non-empty strings")
        seen_areas = set()
        for index, area in enumerate(self.data.get("area", []), 1):
            if not isinstance(area, dict):
                raise ConfigError(f"area #{index} must be a table")
            area_id, title, facet = area.get("id"), area.get("title"), area.get("facet")
            values = area.get("values")
            if not all(isinstance(value, str) and value for value in (area_id, title, facet)):
                raise ConfigError(f"area #{index} requires non-empty id, title, and facet")
            if area_id in seen_areas:
                raise ConfigError(f"duplicate area id {area_id!r}")
            seen_areas.add(area_id)
            if not isinstance(values, list) or not values or not all(
                isinstance(value, str) and value for value in values
            ):
                raise ConfigError(f"area {area_id!r} values must be non-empty strings")
        if not isinstance(self.get("assessment.enabled"), bool):
            raise ConfigError("assessment.enabled must be true or false")
        if not isinstance(self.get("developer_flow.enabled"), bool):
            raise ConfigError("developer_flow.enabled must be true or false")
        developer_cap = self.get("developer_flow.materialization_cap")
        if (isinstance(developer_cap, bool) or not isinstance(developer_cap, int)
                or not 100 <= developer_cap <= 5_000):
            raise ConfigError(
                "developer_flow.materialization_cap must be an integer from 100 through 5000"
            )
        if self.get("developer_flow.direction") not in {"RIGHT", "DOWN"}:
            raise ConfigError("developer_flow.direction must be RIGHT or DOWN")
        signals_path = self.get("assessment.signals_path")
        if not isinstance(signals_path, str) or not signals_path:
            raise ConfigError("assessment.signals_path must be a non-empty string")
        for key in ("small_limit", "anchor_limit", "question_limit"):
            value = self.get(f"assessment.{key}")
            if (isinstance(value, bool) or not isinstance(value, int)
                    or value < 0):
                raise ConfigError(f"assessment.{key} must be a non-negative integer")
        verification_globs = self.get("assessment.verification_globs")
        if (not isinstance(verification_globs, list)
                or not all(isinstance(value, str) and value
                           for value in verification_globs)):
            raise ConfigError(
                "assessment.verification_globs must be non-empty strings"
            )
        stale_minutes = self.get("activity.stale_after_minutes", 120)
        if (isinstance(stale_minutes, bool) or not isinstance(stale_minutes, int)
                or stale_minutes <= 0):
            raise ConfigError("activity.stale_after_minutes must be a positive integer")
        trail_rounds = self.get("activity.trail_rounds", 5)
        if (isinstance(trail_rounds, bool) or not isinstance(trail_rounds, int)
                or not 2 <= trail_rounds <= 8):
            raise ConfigError("activity.trail_rounds must be an integer from 2 through 8")
        history_path = self.get("progress.history_path", "")
        if not isinstance(history_path, str):
            raise ConfigError("progress.history_path must be a string")
        for key in ("hot_window_days", "stalled_after_days", "stall_max_days",
                    "backfill_days", "backfill_max_commits_per_story"):
            value = self.get(f"progress.{key}")
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ConfigError(f"progress.{key} must be a positive integer")
        if self.get("progress.stall_max_days") < self.get("progress.stalled_after_days"):
            raise ConfigError("progress.stall_max_days must be at least stalled_after_days")
        seen_source_areas: set[str] = set()
        for index, area in enumerate(self.data.get("source_area", []), 1):
            if not isinstance(area, dict):
                raise ConfigError(f"source area #{index} must be a table")
            required = ("id", "title", "role", "path", "adapter")
            if not all(isinstance(area.get(field), str) and area[field].strip()
                       for field in required):
                raise ConfigError(
                    f"source area #{index} requires non-empty id, title, role, path, and adapter"
                )
            if area["id"] in seen_source_areas:
                raise ConfigError(f"duplicate source area id {area['id']!r}")
            seen_source_areas.add(area["id"])
            if area["role"] not in SOURCE_AREA_ROLES:
                raise ConfigError(
                    f"source area {area['id']!r} role must be one of "
                    f"{sorted(SOURCE_AREA_ROLES)}"
                )
            if area["adapter"] not in SOURCE_AREA_ADAPTERS:
                raise ConfigError(
                    f"source area {area['id']!r} adapter must be one of "
                    f"{sorted(SOURCE_AREA_ADAPTERS)}"
                )
            relative = Path(area["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ConfigError(
                    f"source area {area['id']!r} path must stay inside the project"
                )
        if not isinstance(self.get("workstreams.enabled"), bool):
            raise ConfigError("workstreams.enabled must be true or false")
        for field in ("definitions_path", "runtime_path"):
            value = self.get(f"workstreams.{field}")
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"workstreams.{field} must be a non-empty string")
            relative = Path(value)
            if relative.is_absolute() or ".." in relative.parts:
                raise ConfigError(f"workstreams.{field} must stay inside the project")
        lease_minutes = self.get("workstreams.lease_minutes")
        if (isinstance(lease_minutes, bool) or not isinstance(lease_minutes, int)
                or lease_minutes <= 0):
            raise ConfigError("workstreams.lease_minutes must be a positive integer")
        if not isinstance(self.get("reviews.enabled"), bool):
            raise ConfigError("reviews.enabled must be true or false")
        review_paths = []
        for field in ("plans_dir", "runs_dir", "evidence_dir"):
            value = self.get(f"reviews.{field}")
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"reviews.{field} must be a non-empty string")
            relative = Path(value)
            if (relative == Path(".") or relative.is_absolute()
                    or ".." in relative.parts):
                raise ConfigError(f"reviews.{field} must stay inside the project")
            review_paths.append(relative)
        for index, first in enumerate(review_paths):
            for second in review_paths[index + 1:]:
                if first == second or first in second.parents or second in first.parents:
                    raise ConfigError(
                        "review plan, run, and evidence directories must not overlap"
                    )
        adapters_path = self.get("reviews.adapters_path")
        if not isinstance(adapters_path, str):
            raise ConfigError("reviews.adapters_path must be a string")
        if adapters_path:
            relative = Path(adapters_path)
            if (relative == Path(".") or relative.is_absolute()
                    or ".." in relative.parts):
                raise ConfigError("reviews.adapters_path must stay inside the project")

    def status_meta(self, name: str) -> dict:
        for s in self.vocab["statuses"]:
            if s.get("name") == name:
                return {"name": name, "emoji": s.get("emoji", "❔"),
                        "done": bool(s.get("done", False))}
        return {"name": name, "emoji": "❔", "done": False}

    def done_statuses(self) -> set[str]:
        return {s["name"] for s in self.vocab["statuses"] if s.get("done")}

    def status_role(self, name: str) -> str:
        """Return the configured dashboard bucket for a lifecycle status."""
        for status in self.vocab["statuses"]:
            if status.get("name") != name:
                continue
            role = status.get("role")
            if isinstance(role, str) and role:
                return role
            if status.get("done"):
                return "done"
            # Backwards compatibility for custom vocabularies written before roles.
            if name in {"idea", "backlog", "specced", "ready", "unknown"}:
                return "ready"
            if name == "parked":
                return "hold"
            return "active"
        return "unknown"

    def transition_allowed(self, current: str, proposed: str) -> bool:
        """Whether configured lifecycle metadata permits a status change.

        ``next`` is opt-in: an omitted value preserves the prior unconstrained
        vocabulary behavior, while ``next = []`` is an explicit terminal state.
        Vizzer does not write status changes; this helper gives integrations and
        future source editors one shared semantic instead of each inventing one.
        """
        statuses = {status.get("name"): status for status in self.vocab["statuses"]}
        current_status = statuses.get(current)
        proposed_status = statuses.get(proposed)
        if current_status is None or proposed_status is None:
            return False
        if current_status.get("done", False) and not proposed_status.get("done", False):
            return False
        if "next" not in current_status:
            return True
        return proposed in current_status["next"]

    def gates(self) -> dict:
        return {g["item"]: g.get("reason", "") for g in self.data.get("gates", [])
                if isinstance(g, dict) and g.get("item")}

    def groups(self) -> list[dict]:
        groups = self.data.get("group", [])
        if not isinstance(groups, list):
            return []
        return [dict(group) for group in groups if isinstance(group, dict)]

    def areas(self) -> list[dict]:
        return [
            {"id": area["id"], "title": area["title"],
             "facet": area["facet"], "values": list(area["values"])}
            for area in self.data.get("area", [])
            if isinstance(area, dict)
        ]

    def source_areas(self) -> list[dict]:
        return [
            {field: area[field] for field in ("id", "title", "role", "path", "adapter")}
            for area in self.data.get("source_area", [])
            if isinstance(area, dict)
        ]

    def source_area_ids_for(self, source_path: str) -> list[str]:
        """Return the most-specific semantic areas containing a source path.

        Areas may be nested (for example ``wiki/product-spec`` inside ``wiki``).
        The child is the source's meaning; the parent remains a useful map entry
        but must not relabel delivery work as generic knowledge.
        """
        try:
            candidate = Path(source_path)
            if candidate.is_absolute() or ".." in candidate.parts:
                return []
        except TypeError:
            return []
        matches: list[tuple[int, str]] = []
        for area in self.source_areas():
            root = Path(area["path"])
            if candidate == root or root in candidate.parents:
                matches.append((len(root.parts), area["id"]))
        if not matches:
            return []
        deepest = max(depth for depth, _ in matches)
        return [area_id for depth, area_id in matches if depth == deepest]

    @classmethod
    def load(cls, root: Path) -> "Config":
        path = Path(root) / "vizzer" / "vizzer.toml"
        data = copy.deepcopy(DEFAULTS)
        if path.is_file():
            data = deep_merge(data, parse_toml_subset(path.read_text(encoding="utf-8")))
        config = cls(data=data, path=path if path.is_file() else None)
        config.validate()
        return config
