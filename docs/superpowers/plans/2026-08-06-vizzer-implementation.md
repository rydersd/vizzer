# Vizzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Delegation routing (owner's Model Selection Grid):** Tasks marked **[CODEX LANE]** are implemented by `codex exec` with the task's test code and interface contract pasted verbatim into a self-contained prompt (codex sees nothing else). Claude verifies tests actually run and pass, then commits. Tasks marked **[CLAUDE]** stay in-session (shared-type anchors, taste-bearing surfaces). Cross-vendor review before merge: codex code → Claude review; Claude code → `codex review`.

**Goal:** Build vizzer — a public, stdlib-only Python tool that ingests a project's work-tracking sources (spec trees, continuity ledgers, loose docs, TODOs) into a normalized checked-in graph and renders seven regenerable views, installing itself as a self-contained `vizzer/` directory with LLM-harness registration.

**Architecture:** Adapter → normalized graph (`vizzer-graph.json`) → renderer pipeline. Adapters only read and emit; the reconciler owns merging/conflicts/writes; renderers are pure functions over the graph. An installer vendors the engine into target projects and maintains a managed block in CLAUDE.md/AGENTS.md.

**Tech Stack:** Python ≥3.10, stdlib only (no runtime deps). pytest for tests (dev-only dep). GitHub Actions CI. zipapp (`.pyz`) distribution.

**Spec:** `docs/superpowers/specs/2026-08-06-vizzer-portable-spec-views-design.md`

## Global Constraints

- Python ≥ 3.10; **runtime stdlib only** (tomllib is 3.11+, so config uses the bundled TOML-subset parser in Task 2 — never import tomllib).
- All generated artifacts are **deterministic**: stable sort orders, no wall-clock timestamps (git supplies dates; constellation's `now` = max `last_touched` across nodes).
- No the source project or personal content in code, fixtures, or defaults. Synthetic fixtures only. No absolute paths in default output.
- Vizzer never executes project code — reads files and git history only.
- MIT license. Public repo hygiene throughout.
- Malformed source files never crash: degrade to `status: "unknown"` + warning.
- Commit after every task (repo already initialized, branch `main`). No Claude attribution in commits.
- Package import name is `vizzer`; all intra-package imports are relative (`from ..model import Item`) so the vendored copy works unrenamed.

## File Structure

```
pyproject.toml                    # T1; console script + pytest dev dep
LICENSE                           # T1 (MIT)
README.md                         # T15
.github/workflows/ci.yml          # T15
scripts/build_pyz.py              # T15
src/vizzer/
  __init__.py                     # T1: __version__ = "0.1.0"
  __main__.py                     # T1: from .cli import main; SystemExit(main())
  model.py                        # T1  [CLAUDE anchor]
  config.py                       # T2  [CLAUDE anchor]
  gitmeta.py                      # T3  [CODEX]
  adapters/__init__.py            # T4: ScanResult + registry
  adapters/spec_tree.py           # T4  [CODEX]
  adapters/ledgers.py             # T5  [CODEX]
  adapters/loose_docs.py          # T6  [CODEX]
  adapters/todos.py               # T7  [CODEX]
  reconcile.py                    # T8  [CODEX]
  render/__init__.py              # T9: registry + render_all
  render/common.py                # T9  [CODEX]
  render/roadmap.py               # T9  [CODEX]
  render/feature_index.py         # T9  [CODEX]
  render/dashboard.py             # T10 [CODEX]
  render/completion_sheet.py      # T10 [CODEX]
  render/ledger_table.py          # T11 [CODEX]
  render/manifest.py              # T11 [CODEX]
  render/constellation.py         # T12 [CLAUDE — taste]
  render/constellation_template.html  # T12 [CLAUDE — ported]
  cli.py                          # T13 [CODEX, Claude reviews UX copy]
  install.py                      # T14 [CODEX core + Claude for harness-block copy]
tests/
  test_model.py … test_install.py # per task
  fixtures/spec_proj/  ledger_proj/  docs_proj/  todo_proj/  mixed_proj/
  golden/mixed/                   # T13 golden views
```

**Shared test helper** (created in T3, used everywhere): `tests/conftest.py` provides `make_repo(tmp_path, fixture_name)` — copies a fixture dir into tmp, runs `git init`, one commit with **fixed** `GIT_AUTHOR_DATE=2026-01-02T03:04:05Z GIT_COMMITTER_DATE=2026-01-02T03:04:05Z` and author `Fixture <fx@example.com>` — so git-derived fields are identical on every machine (golden tests stay deterministic).

---

### Task 1: Scaffold + graph model  **[CLAUDE — shared-type anchor]**

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `src/vizzer/__init__.py`, `src/vizzer/__main__.py`, `src/vizzer/model.py`
- Test: `tests/test_model.py`

**Interfaces (produced — every later task consumes these types):**
- `Group(id, kind, title, parent=None, meta={})`
- `Item(id, title, one_liner=None, status="unknown", release=None, wave=None, group=None, deps=[], appetite=None, flags=[], source={}, activity={})`
- `Graph(groups, items, conflicts, warnings, vocab)` with `.to_dict()`, `.dumps()`, `Graph.from_dict(d)`, `.item_map()`
- Module constant `SCHEMA = 1`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model.py
import json
from vizzer.model import Graph, Group, Item, SCHEMA

def _graph():
    return Graph(
        groups=[Group(id="epic:b", kind="epic", title="B"),
                Group(id="epic:a", kind="epic", title="A", meta={"goal": "g"})],
        items=[Item(id="story:z", title="Z", deps=["story:a"]),
               Item(id="story:a", title="A", status="shipped", group="epic:a")],
        conflicts=[{"item": "story:z", "field": "status",
                    "kept": {"adapter": "spec_tree", "value": "building"},
                    "dropped": {"adapter": "dag_import", "value": "specced"}}],
        warnings=["w2", "w1"],
        vocab={"statuses": [{"name": "shipped", "emoji": "✅", "done": True}]},
    )

def test_to_dict_is_stable_sorted():
    d = _graph().to_dict()
    assert d["schema"] == SCHEMA
    assert [g["id"] for g in d["groups"]] == ["epic:a", "epic:b"]
    assert [i["id"] for i in d["items"]] == ["story:a", "story:z"]
    assert d["warnings"] == ["w1", "w2"]

def test_dumps_roundtrip():
    g = _graph()
    d = json.loads(g.dumps())
    g2 = Graph.from_dict(d)
    assert g2.dumps() == g.dumps()          # deterministic fixpoint
    assert g.dumps().endswith("\n")
    assert g2.item_map()["story:a"].status == "shipped"

def test_defaults():
    it = Item(id="x", title="X")
    assert it.status == "unknown" and it.deps == [] and it.activity == {}
    assert Group(id="g", kind="epic", title="T").meta == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ryders/Developer/GitHub/project_vizzer && python3 -m pytest tests/test_model.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: vizzer`

- [ ] **Step 3: Write the scaffold + implementation**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "vizzer"
version = "0.1.0"
description = "Portable work-graph views: normalize a project's specs/ledgers/docs into one graph and render roadmap, dashboard, and a 3D constellation."
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}

[project.scripts]
vizzer = "vizzer.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`LICENSE`: standard MIT text, copyright `2026 Ryder Sondgeroth`.

`src/vizzer/__init__.py`:

```python
__version__ = "0.1.0"
```

`src/vizzer/__main__.py`:

```python
from .cli import main
raise SystemExit(main())
```

(cli.py doesn't exist until T13 — that's fine; `__main__` is only imported when executed.)

`src/vizzer/model.py` — full reference implementation:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_model.py -v` — Expected: 3 PASS. (If pytest missing: `python3 -m pip install pytest`.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml LICENSE src/vizzer tests/test_model.py
git commit -m "feat: scaffold + normalized graph model with deterministic serialization"
```

---

### Task 2: Config — TOML-subset parser, defaults, vocabulary  **[CLAUDE — shared-type anchor]**

**Files:**
- Create: `src/vizzer/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_toml_subset(text: str) -> dict` (raises `ConfigError` with line numbers); `deep_merge(base: dict, over: dict) -> dict` (new dict; `over` wins; nested dicts merge, lists replace); `Config` with `.get("dotted.path", default=None)`, `.vocab -> dict` (`{"statuses": [...]}`), `.status_meta(name) -> dict` (unknown names → `{"name": name, "emoji": "❔", "done": False}`), `.done_statuses() -> set[str]`, `.gates() -> dict[item_id, reason]`, `Config.load(root: Path) -> Config` (reads `<root>/vizzer/vizzer.toml`, merged over `DEFAULTS`; missing file → pure defaults); module constants `DEFAULTS`, `DEFAULT_STATUSES`.
- TOML subset (the config contract, documented in the module docstring): `#` comments, `[section]` / `[a.b]`, `[[array-of-tables]]` (single-segment name), `key = "string" | true | false | int | ["strings", …]`. Nothing else.
- `DEFAULT_STATUSES` (order matters — lifecycle order): idea 💡, backlog 📋, specced 📝, ready 🟢, building 🔧, in-flight ✈️, bug-gap 🐛, shipped ✅(done), verified 🏁(done), parked ⏸️, unknown ❔. Only shipped/verified have `done: True`.
- `DEFAULTS` keys (exact): `project.name="project"`; `sources.spec_tree.{enabled=False, glob="", levels=[], item_kind="story", dag_import=""}`; `sources.ledgers.{enabled=False, glob="thoughts/ledgers/CONTINUITY_*.md"}`; `sources.loose_docs.{enabled=False, globs=[]}`; `sources.todos.{enabled=False, globs=["TODO.md"]}`; `render.{output_dir="vizzer/views", releases=["R0","R1","R2","R3"], recommended=[], obsidian_links=False, title=""}`; `reconcile.{precedence=["spec_tree","dag_import","ledgers","todos","loose_docs"], mention_globs=[], staleness_days=14}`; `archive.adapters=["todos"]`.
- `[[status]]` tables in user config REPLACE the default vocabulary entirely when present. `[[gates]]` tables have keys `item`, `reason`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path
import pytest
from vizzer.config import (Config, ConfigError, DEFAULT_STATUSES, DEFAULTS,
                           deep_merge, parse_toml_subset)

SAMPLE = '''
# comment
[project]
name = "demo"          # trailing comment
[sources.spec_tree]
enabled = true
glob = "spec/*/stories/*.md"
levels = ["capability"]
[reconcile]
staleness_days = 30
[[gates]]
item = "story:x"
reason = "decision D#1 pending"
[[status]]
name = "todo"
emoji = "🔲"
done = false
[[status]]
name = "done"
emoji = "✅"
done = true
'''

def test_parse_subset():
    d = parse_toml_subset(SAMPLE)
    assert d["project"]["name"] == "demo"
    assert d["sources"]["spec_tree"]["enabled"] is True
    assert d["sources"]["spec_tree"]["levels"] == ["capability"]
    assert d["reconcile"]["staleness_days"] == 30
    assert d["gates"] == [{"item": "story:x", "reason": "decision D#1 pending"}]
    assert [s["name"] for s in d["status"]] == ["todo", "done"]

def test_parse_errors_carry_line_numbers():
    with pytest.raises(ConfigError, match="line 1"):
        parse_toml_subset('key = {inline = "no"}')

def test_hash_inside_string_is_not_comment():
    assert parse_toml_subset('k = "a#b"')["k"] == "a#b"

def test_deep_merge():
    out = deep_merge({"a": {"x": 1, "y": 1}, "l": [1]}, {"a": {"y": 2}, "l": [2]})
    assert out == {"a": {"x": 1, "y": 2}, "l": [2]}

def test_config_load_defaults_when_missing(tmp_path):
    cfg = Config.load(tmp_path)
    assert cfg.get("render.output_dir") == "vizzer/views"
    assert cfg.get("nope.nope", 7) == 7
    assert {s["name"] for s in cfg.vocab["statuses"]} == {s["name"] for s in DEFAULT_STATUSES}
    assert cfg.done_statuses() == {"shipped", "verified"}
    assert cfg.status_meta("nonexistent") == {"name": "nonexistent", "emoji": "❔", "done": False}

def test_config_load_merges_and_overrides_vocab(tmp_path):
    (tmp_path / "vizzer").mkdir()
    (tmp_path / "vizzer" / "vizzer.toml").write_text(SAMPLE)
    cfg = Config.load(tmp_path)
    assert cfg.get("project.name") == "demo"
    assert cfg.get("reconcile.precedence") == DEFAULTS["reconcile"]["precedence"]
    assert cfg.done_statuses() == {"done"}
    assert cfg.gates() == {"story:x": "decision D#1 pending"}
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_config.py -v` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `src/vizzer/config.py`** — full reference implementation:

```python
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

    @classmethod
    def load(cls, root: Path) -> "Config":
        path = Path(root) / "vizzer" / "vizzer.toml"
        data = copy.deepcopy(DEFAULTS)
        if path.is_file():
            data = deep_merge(data, parse_toml_subset(path.read_text(encoding="utf-8")))
        return cls(data=data, path=path if path.is_file() else None)
```

- [ ] **Step 4: Run** `python3 -m pytest tests/test_config.py tests/test_model.py -v` — Expected: all PASS.

- [ ] **Step 5: Commit** — `git add src/vizzer/config.py tests/test_config.py && git commit -m "feat: config with bundled TOML-subset parser, default vocabulary, gates"`

---

### Task 3: Git metadata + shared fixture helper  **[CODEX LANE]**

**Files:**
- Create: `src/vizzer/gitmeta.py`, `tests/conftest.py`
- Test: `tests/test_gitmeta.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `collect(root: Path, mention_globs: list[str]) -> tuple[GitMeta, list[str]]` (warnings list; on any git failure returns empty GitMeta + one warning `"git history unavailable — dates/activity omitted"`). `GitMeta` methods, all keyed by repo-relative POSIX path: `.created(relpath) -> str|None` (ISO-8601 of oldest commit touching the file), `.modified(relpath) -> str|None` (newest), `.commits(relpath) -> int`, `.last_touched(relpath) -> int` (epoch, 0 if unknown), `.mentions(needle: str) -> int` (number of mention-glob files whose text contains `needle`; files are read once at collect time, `errors="ignore"`).
- Git invocation (exact): `git -C <root> log --format=C%x09%ct%x09%ad --date=iso-strict --name-only` — lines starting `C\t` carry epoch+iso for the commit; following non-blank lines are file paths. Newest-first: first sighting of a path = modified/last_touched; final sighting = created.
- `tests/conftest.py` produces fixture factory `make_repo(tmp_path, fixture: str) -> Path`: copies `tests/fixtures/<fixture>` into `tmp_path/proj`, then `git init -b main`, `git add -A`, one commit `"fixture"` with env `GIT_AUTHOR_DATE=GIT_COMMITTER_DATE=2026-01-02T03:04:05Z`, author/committer `Fixture <fx@example.com>` (set via `-c user.name/-c user.email`). Returns the repo path. Also `run_git(repo, *args, env=None)` helper.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gitmeta.py
import subprocess
from vizzer.gitmeta import collect

def _git(repo, *args, date=None):
    env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}
    import os
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                    "-c", "user.email=fx@example.com", *args],
                   check=True, capture_output=True, env={**os.environ, **env})

def test_collect_dates_counts_mentions(tmp_path):
    repo = tmp_path / "r"; repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "a.md").write_text("alpha")
    (repo / "notes.md").write_text("about snap-to-grid work")
    _git(repo, "add", "-A"); _git(repo, "commit", "-m", "one", date="2026-01-01T00:00:00Z")
    (repo / "a.md").write_text("alpha v2")
    _git(repo, "add", "-A"); _git(repo, "commit", "-m", "two", date="2026-02-01T00:00:00Z")

    meta, warnings = collect(repo, ["notes.md"])
    assert warnings == []
    assert meta.commits("a.md") == 2
    assert meta.created("a.md").startswith("2026-01-01")
    assert meta.modified("a.md").startswith("2026-02-01")
    assert meta.last_touched("a.md") > meta.last_touched("notes.md") == 1767225600
    assert meta.mentions("snap-to-grid") == 1
    assert meta.mentions("absent-slug") == 0

def test_collect_degrades_without_git(tmp_path):
    meta, warnings = collect(tmp_path, [])
    assert meta.commits("x") == 0 and meta.created("x") is None
    assert warnings == ["git history unavailable — dates/activity omitted"]
```

(`1767225600` = 2026-01-01T00:00:00Z.)

- [ ] **Step 2: Run** `python3 -m pytest tests/test_gitmeta.py -v` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** `src/vizzer/gitmeta.py` per the interface contract above (single `subprocess.run`, parse into four dicts + cached mention texts; `GitMeta` is a plain class holding them), and `tests/conftest.py` per its contract. Codex prompt = this task's Files/Interfaces/tests verbatim + Global Constraints.

- [ ] **Step 4: Run** `python3 -m pytest tests/test_gitmeta.py -v` — Expected: 2 PASS.

- [ ] **Step 5: Commit** — `git add src/vizzer/gitmeta.py tests/conftest.py tests/test_gitmeta.py && git commit -m "feat: one-pass git metadata (dates, counts, mentions) + deterministic fixture helper"`

---

### Task 4: Adapter registry + spec-tree adapter  **[CODEX LANE]**

**Files:**
- Create: `src/vizzer/adapters/__init__.py`, `src/vizzer/adapters/spec_tree.py`, fixture `tests/fixtures/spec_proj/`
- Test: `tests/test_spec_tree.py`

**Interfaces:**
- `adapters/__init__.py` produces: `@dataclass ScanResult(groups: list = [], items: list = [], warnings: list = [])` and `get_adapters(cfg) -> list[tuple[str, module]]` — enabled adapters ordered by `reconcile.precedence` (skip `dag_import`; it is not a module — spec_tree emits its items).
- `spec_tree.scan(cfg, root: Path) -> ScanResult`. Behavior contract:
  - Glob `sources.spec_tree.glob` relative to root, sorted; skip basenames starting `_`.
  - Group chain: match the file's relative path against the glob pattern split on `/`; each single-`*` DIRECTORY component captures that path segment as a group slug. `levels` names them in order (e.g. `["capability","epic"]`). Group id = `<level>:<seg1>/<seg2…>` (cumulative path for uniqueness), parent = previous level's id, kind = level name, title = slug with `-`→` ` and `.title()` — unless an overview doc `<dir>/<dirname>.md` exists whose H1 provides the title.
  - Item: id `<item_kind>:<filename-stem>`; title = first H1, with a leading `Word:` label stripped (`# Story: Foo` → `Foo`); fallback stem. `one_liner` = first paragraph line under `## Intent` (whitespace-collapsed, ≤140 chars) or front-matter `summary`. Status: front-matter `status` wins, else `> Status: ([a-zA-Z-]+)`, else `"unknown"` + warning `"<relpath>: no status"`. Release `Release:\s*([A-Za-z0-9.?]+)`; wave `Wave:\s*([A-Za-z0-9]+)`; appetite `[Aa]ppetite:\s*\**\s*([a-z-]+)`; flag `debt` when `^> Debt:` matches. Deps: front-matter `deps` list, else a `Deps:` line (comma-separated slugs, `—`/`-`/empty → none); normalize each dep slug to `<item_kind>:<slug>`.
  - Front-matter subset parser (module-private): leading `---` block; `key: value` scalars and `key:` + `- entry` lists. Malformed → ignored (raw content parsed instead).
  - Unreadable file → warning, skip. Never raise.
  - `dag_import`: when `sources.spec_tree.dag_import` names a JSON file (the source project-shape: `{"capabilities":[{"epics":[{"stories":[{"slug","title","oneLiner","deps","release","status"}]}]}]}`), emit each story as an Item with `source={"adapter":"dag_import","path":<dag path>}` — same id scheme — so the reconciler can merge/conflict them. DAG stories are returned in the same ScanResult.
- Fixture `tests/fixtures/spec_proj/` (synthetic):
  - `spec/drawing/epics/tools/stories/snap-to-grid.md`:
    ```markdown
    # Story: Snap to grid

    > Status: building · Release: R0
    > Deps: canvas-core
    > Debt: hover flicker on retina

    Appetite: medium

    ## Intent
    Dragging an object snaps its edges to the configured grid.
    ```
  - `spec/drawing/epics/tools/stories/canvas-core.md`:
    ```markdown
    ---
    status: shipped
    deps: []
    summary: Core canvas surface with pan and zoom.
    ---
    # Story: Canvas core

    Release: R0
    ```
  - `spec/drawing/epics/tools/tools.md`: `# Epic: Drawing tools`
  - `spec/drawing/drawing.md`: `# Capability: Drawing`
  - `spec/drawing/epics/tools/stories/_Index_of_stories.md`: `ignored`
  - `dag.json` (top level of fixture): the the source project-shape JSON declaring `snap-to-grid` with `status: "specced"` (a deliberate conflict with the file's `building`) and `canvas-core` with `status: "shipped"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spec_tree.py
from pathlib import Path
from vizzer.adapters import spec_tree, get_adapters
from vizzer.config import Config, DEFAULTS, deep_merge

FIX = Path(__file__).parent / "fixtures" / "spec_proj"

def cfg(dag=""):
    d = deep_merge(DEFAULTS, {"sources": {"spec_tree": {
        "enabled": True, "glob": "spec/*/epics/*/stories/*.md",
        "levels": ["capability", "epic"], "dag_import": dag}}})
    return Config(data=d)

def test_scan_items_and_groups():
    res = spec_tree.scan(cfg(), FIX)
    items = {i.id: i for i in res.items}
    snap = items["story:snap-to-grid"]
    assert snap.title == "Snap to grid"
    assert snap.status == "building" and snap.release == "R0"
    assert snap.deps == ["story:canvas-core"]
    assert snap.appetite == "medium" and "debt" in snap.flags
    assert snap.one_liner.startswith("Dragging an object snaps")
    core = items["story:canvas-core"]
    assert core.status == "shipped" and core.one_liner == "Core canvas surface with pan and zoom."
    gids = {g.id: g for g in res.groups}
    assert gids["capability:drawing"].title == "Capability: Drawing".removeprefix("Capability: ")
    assert gids["epic:drawing/tools"].parent == "capability:drawing"
    assert gids["epic:drawing/tools"].title == "Drawing tools"
    assert snap.group == "epic:drawing/tools"
    assert "story:_Index_of_stories" not in items

def test_dag_import_emits_parallel_items():
    res = spec_tree.scan(cfg(dag="dag.json"), FIX)
    dag_items = [i for i in res.items if i.source["adapter"] == "dag_import"]
    assert {i.id for i in dag_items} == {"story:snap-to-grid", "story:canvas-core"}
    assert {i.status for i in dag_items if i.id == "story:snap-to-grid"} == {"specced"}

def test_registry_orders_by_precedence():
    c = cfg()
    assert [name for name, _ in get_adapters(c)] == ["spec_tree"]
```

- [ ] **Step 2: Run** — Expected: FAIL (fixture + modules missing).
- [ ] **Step 3: Implement** fixture files exactly as specified, `adapters/__init__.py`, and `spec_tree.py` per contract. (Overview-doc title: strip `Epic:`/`Capability:`-style `^\w+:` label from H1, hence "Drawing tools".)
- [ ] **Step 4: Run** `python3 -m pytest tests/test_spec_tree.py -v` — Expected: 3 PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: adapter registry + spec-tree adapter with dag-import and front-matter support"` (add `src/vizzer/adapters tests/fixtures/spec_proj tests/test_spec_tree.py`).

---

### Task 5: Ledgers adapter  **[CODEX LANE]**

**Files:**
- Create: `src/vizzer/adapters/ledgers.py`, fixture `tests/fixtures/ledger_proj/thoughts/ledgers/CONTINUITY_CLAUDE-widget-refactor.md`
- Test: `tests/test_ledgers.py`

**Interfaces:**
- `ledgers.scan(cfg, root) -> ScanResult`. Contract:
  - Glob `sources.ledgers.glob`. Ledger slug = filename between `CONTINUITY_CLAUDE-` (or `CONTINUITY_`) and `.md`.
  - Group: id `ledger:<slug>`, kind `ledger`, title = slug `-`→` ` titled; `meta = {"goal": <first paragraph line under "## Goal", or "">, "open_questions": <count of "- " lines under "## Open Questions">, "path": <relpath>}`.
  - Items: every `- [x|→|->| ] <text>` checkbox in the file, in order. id `phase:<slug>/<NN>-<slugified-text≤40>` (NN = 2-digit index from 01). Status map: `[x]`→`shipped`, `[→]`/`[->]`→`building`, `[ ]`→`backlog`. `group` = ledger group id. Title = checkbox text.
- Fixture content:
  ```markdown
  # Continuity — widget refactor

  ## Goal
  Ship the widget refactor with zero regressions.

  ## State
  - Done:
    - [x] Phase 1: Extract widget core
  - Now: [→] Phase 2: Port call sites
  - Remaining:
    - [ ] Phase 3: Delete legacy shims

  ## Open Questions
  - UNCONFIRMED: does the cache need invalidation?
  ```
  Note `- Now: [→] …` is NOT a `- [→]` checkbox (checkbox regex requires `[` immediately after `- `), so the fixture also needs the Now line as a real checkbox to be counted — change the State block to:
  ```markdown
  - [x] Phase 1: Extract widget core
  - [→] Phase 2: Port call sites
  - [ ] Phase 3: Delete legacy shims
  ```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ledgers.py
from pathlib import Path
from vizzer.adapters import ledgers
from vizzer.config import Config, DEFAULTS, deep_merge

FIX = Path(__file__).parent / "fixtures" / "ledger_proj"

def test_scan_ledger():
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"ledgers": {"enabled": True}}}))
    res = ledgers.scan(cfg, FIX)
    [g] = res.groups
    assert g.id == "ledger:widget-refactor" and g.kind == "ledger"
    assert g.meta["goal"] == "Ship the widget refactor with zero regressions."
    assert g.meta["open_questions"] == 1
    sts = [(i.id, i.status) for i in res.items]
    assert sts == [
        ("phase:widget-refactor/01-phase-1-extract-widget-core", "shipped"),
        ("phase:widget-refactor/02-phase-2-port-call-sites", "building"),
        ("phase:widget-refactor/03-phase-3-delete-legacy-shims", "backlog"),
    ]
    assert all(i.group == "ledger:widget-refactor" for i in res.items)
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** module + fixture. Slugify: lowercase, non-alphanumeric runs → `-`, strip `-`, truncate 40. **Step 4: Run** — PASS. **Step 5: Commit** `"feat: continuity-ledger adapter (goals, phase checkboxes, open questions)"`.

---

### Task 6: Loose-docs adapter  **[CODEX LANE]**

**Files:** Create `src/vizzer/adapters/loose_docs.py`, fixture `tests/fixtures/docs_proj/docs/` (3 files); Test `tests/test_loose_docs.py`.

**Interfaces:**
- `loose_docs.scan(cfg, root) -> ScanResult`. Globs from `sources.loose_docs.globs` (each `glob.glob(..., recursive=True)`), sorted, deduped, skip `_`-prefixed basenames. Item id `doc:<relpath minus .md>` (POSIX, e.g. `doc:docs/design/tokens`). Group per containing directory: id `folder:<reldir>`, kind `folder`, title = dir name (root-level docs → group `folder:.` titled `docs`… no: title = reldir or `"."`→ project name from cfg). Front-matter (reuse the parser by importing from `.spec_tree`) supplies `status`/`deps`/`release`/`tags` (tags → `flags`); else `> Status:` line; else status stays `"unknown"` with NO warning (docs legitimately lack status). Title = front-matter `title`, else first H1, else stem. `one_liner` = front-matter `summary`, else first `> Brief: …` line, else None.
- Fixture: `docs/design/tokens.md` (front-matter: `status: shipped`, `summary: Color tokens.`, `tags:` list `[reference]` written as YAML list lines), `docs/roadmap-notes.md` (H1 + `> Brief: Where we're heading.`, no status), `docs/_Index_of_docs.md` (ignored).

- [ ] **Step 1: Failing test**

```python
# tests/test_loose_docs.py
from pathlib import Path
from vizzer.adapters import loose_docs
from vizzer.config import Config, DEFAULTS, deep_merge

FIX = Path(__file__).parent / "fixtures" / "docs_proj"

def test_scan_docs():
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"loose_docs": {
        "enabled": True, "globs": ["docs/**/*.md"]}}}))
    res = loose_docs.scan(cfg, FIX)
    items = {i.id: i for i in res.items}
    tok = items["doc:docs/design/tokens"]
    assert tok.status == "shipped" and tok.one_liner == "Color tokens."
    assert "reference" in tok.flags and tok.group == "folder:docs/design"
    notes = items["doc:docs/roadmap-notes"]
    assert notes.status == "unknown" and notes.one_liner == "Where we're heading."
    assert "doc:docs/_Index_of_docs" not in items
    assert res.warnings == []
```

- [ ] **Steps 2–5:** Run (FAIL) → implement module + fixture → run (PASS) → commit `"feat: loose-docs adapter (front-matter aware corpus floor)"`.

---

### Task 7: Todos adapter  **[CODEX LANE]**

**Files:** Create `src/vizzer/adapters/todos.py`, fixture `tests/fixtures/todo_proj/TODO.md`; Test `tests/test_todos.py`.

**Interfaces:**
- `todos.scan(cfg, root) -> ScanResult`. For each file in `sources.todos.globs` (sorted glob): group id `todo-file:<relpath>`, kind `folder`, title = filename. Checkboxes `- [x| ] text` → items id `todo:<file-stem-lower>/<NN>-<slugified-text≤40>`, status `shipped` when checked else `backlog`, group = file's group id. Same slugify as ledgers (share it: put `slugify()` in `adapters/__init__.py`, re-export; update ledgers.py to import it — include that edit in this task).
- Fixture `TODO.md`: `# TODO`, `- [x] Set up CI`, `- [ ] Write install docs`.

- [ ] **Step 1: Failing test**

```python
# tests/test_todos.py
from pathlib import Path
from vizzer.adapters import todos
from vizzer.config import Config, DEFAULTS, deep_merge

FIX = Path(__file__).parent / "fixtures" / "todo_proj"

def test_scan_todos():
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"todos": {"enabled": True}}}))
    res = todos.scan(cfg, FIX)
    assert [g.id for g in res.groups] == ["todo-file:TODO.md"]
    sts = [(i.id, i.status) for i in res.items]
    assert sts == [("todo:todo/01-set-up-ci", "shipped"),
                   ("todo:todo/02-write-install-docs", "backlog")]
```

- [ ] **Steps 2–5:** FAIL → implement (+ move `slugify` into `adapters/__init__.py`; keep ledgers tests green) → PASS (`python3 -m pytest tests/ -v` all green) → commit `"feat: todos adapter; share slugify across adapters"`.

---

### Task 8: Reconciler  **[CODEX LANE]**

**Files:** Create `src/vizzer/reconcile.py`; Test `tests/test_reconcile.py`.

**Interfaces:**
- Consumes: `ScanResult`, `Config`, `gitmeta.collect`, model types.
- Produces: `build_graph(cfg: Config, root: Path, scans: list[tuple[str, ScanResult]]) -> Graph`. `scans` arrive already precedence-ordered EXCEPT that spec_tree's result may contain both `spec_tree`- and `dag_import`-sourced items; treat each ITEM's `source["adapter"]` as its precedence key (position in `reconcile.precedence`; unknown adapter → lowest). Contract:
  1. Sort all items by (precedence index, id) before merging.
  2. **File-claim rule:** if an item's `source.path` was already claimed by a different item id, drop the newcomer silently (higher-precedence adapter owns the file).
  3. **Same-id merge:** first (highest-precedence) item is kept. For fields `status, release, wave, title, one_liner, appetite`: if keeper's field is empty (`None`/`""`/`"unknown"`) and newcomer's isn't, fill it. If BOTH are non-empty and differ and the field is `status`, append a conflict record `{"item", "field": "status", "kept": {"adapter", "value"}, "dropped": {"adapter", "value"}}`. Empty keeper `deps` are filled from newcomer.
  4. Dangling deps (target id absent) → warning `"dangling dep <id> → <dep> (edge dropped)"`, edge removed.
  5. Groups: first writer wins by id.
  6. Activity: `gitmeta.collect(root, cfg.get("reconcile.mention_globs"))`; for items with a source path: `{"commits", "mentions" (needle = id's last `/`-segment after the `kind:` prefix… use the plain file stem for spec/doc items, the checkbox slug for phase/todo items — i.e. `item.id.split(":",1)[1].split("/")[-1]`), "last_touched", "created", "modified"}`.
  7. Graph.warnings = sorted set of all adapter + reconciler + gitmeta warnings. Graph.vocab = `cfg.vocab`.

- [ ] **Step 1: Failing test**

```python
# tests/test_reconcile.py
from vizzer.adapters import ScanResult
from vizzer.config import Config, DEFAULTS
from vizzer.model import Group, Item
from vizzer.reconcile import build_graph

def _cfg():
    return Config(data=DEFAULTS)

def _item(id, adapter, path, **kw):
    return Item(id=id, title=kw.pop("title", id), source={"adapter": adapter, "path": path}, **kw)

def test_status_conflict_recorded_higher_precedence_wins(tmp_path):
    scans = [("spec_tree", ScanResult(items=[
        _item("story:a", "spec_tree", "s/a.md", status="building"),
        _item("story:a", "dag_import", "dag.json", status="specced", release="R1"),
    ]))]
    g = build_graph(_cfg(), tmp_path, scans)
    [a] = [i for i in g.items if i.id == "story:a"]
    assert a.status == "building" and a.release == "R1"      # conflict kept + gap filled
    assert g.conflicts == [{"item": "story:a", "field": "status",
                            "kept": {"adapter": "spec_tree", "value": "building"},
                            "dropped": {"adapter": "dag_import", "value": "specced"}}]

def test_file_claim_drops_lower_precedence_duplicate(tmp_path):
    scans = [("spec_tree", ScanResult(items=[_item("story:a", "spec_tree", "x.md")])),
             ("loose_docs", ScanResult(items=[_item("doc:x", "loose_docs", "x.md")]))]
    g = build_graph(_cfg(), tmp_path, scans)
    assert [i.id for i in g.items] == ["story:a"]

def test_dangling_dep_dropped_with_warning(tmp_path):
    scans = [("spec_tree", ScanResult(items=[
        _item("story:a", "spec_tree", "a.md", deps=["story:ghost"])]))]
    g = build_graph(_cfg(), tmp_path, scans)
    assert g.item_map()["story:a"].deps == []
    assert "dangling dep story:a → story:ghost (edge dropped)" in g.warnings

def test_groups_first_writer_wins_and_vocab_attached(tmp_path):
    scans = [("spec_tree", ScanResult(groups=[Group(id="g", kind="epic", title="One")])),
             ("ledgers", ScanResult(groups=[Group(id="g", kind="epic", title="Two")]))]
    g = build_graph(_cfg(), tmp_path, scans)
    assert [gr.title for gr in g.groups] == ["One"]
    assert any(s["name"] == "shipped" for s in g.vocab["statuses"])
```

- [ ] **Steps 2–5:** FAIL → implement per contract → `python3 -m pytest tests/ -v` all PASS → commit `"feat: reconciler — precedence merge, file claims, visible conflicts, dangling-dep pruning"`.

---

### Task 9: Render registry + roadmap + feature-index  **[CODEX LANE]**

**Files:** Create `src/vizzer/render/__init__.py`, `render/common.py`, `render/roadmap.py`, `render/feature_index.py`; Test `tests/test_render_roadmap.py`.

**Interfaces:**
- `render/__init__.py`: `RENDERERS: dict[str, module]` in canonical order `roadmap, feature_index, dashboard, completion_sheet, ledger_table, manifest, constellation` (import lazily inside `render_all` so partially-built stages don't break earlier tasks); `render_all(graph, cfg, root, only: set[str]|None = None) -> dict[str, str]` mapping output FILENAME → content (merges each module's `render()` dict; unknown `only` names raise `ValueError`).
- Every renderer module: `render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]`.
- `common.py`: `emoji(cfg, status) -> str`; `status_cell(cfg, status) -> str` (`"✅ shipped"`); `item_link(item) -> str` — `[<id-tail>](../../<source.path>)` when path present else id tail (views live two levels below root at `vizzer/views/`); `bar(done, total, width=12) -> str` (`█`/`░`, the source project port); `topo(items: list[Item], all_deps: dict[id, list[id]]) -> list[Item]` — Kahn-style with deterministic tiebreak (sorted by id within each wave), cycle fallback appends the remainder sorted by id.
- `roadmap.py` output `roadmap.md`: header `# Roadmap (dependency-ordered release waves)`, note line naming the generator, legend from vocab (all statuses `emoji name` joined by ` · `). One `## <release>` section per `render.releases` entry present in the graph plus trailing `R?`-style unknowns bucket `## Unscheduled`; items = graph items with that `release`, topo-ordered; table `| # | Status | Item | Group | Deps |` — Deps = comma-joined dep id-tails or `—`, truncated to 80 chars. Skip phase/todo items (kinds `phase:`/`todo:` prefixes) — roadmap covers planned work, not checkboxes.
- `feature_index.py` output `feature-index.md`: `# Feature Index`, count line `N groups · M items`, then per TOP-LEVEL group (groups with `parent=None`, sorted by id) an `##` section, its child groups as `###` subsections with table `| Behavior | Status | Rel | Item |` (behavior = one_liner or title, `|` escaped); items directly under a top-level group render in an implicit `### (root)` table. Skip ledger/todo-file groups (kinds `ledger`, `folder`) entirely — they have their own views.

- [ ] **Step 1: Failing test**

```python
# tests/test_render_roadmap.py
from pathlib import Path
from vizzer.config import Config, DEFAULTS
from vizzer.model import Graph, Group, Item
from vizzer.render import render_all
from vizzer.render.common import topo

def _graph():
    return Graph(
        groups=[Group(id="capability:d", kind="capability", title="Drawing"),
                Group(id="epic:d/t", kind="epic", title="Tools", parent="capability:d")],
        items=[Item(id="story:b", title="B", status="specced", release="R0",
                    deps=["story:a"], group="epic:d/t",
                    source={"adapter": "spec_tree", "path": "spec/b.md"}),
               Item(id="story:a", title="A", one_liner="Does A.", status="shipped",
                    release="R0", group="epic:d/t",
                    source={"adapter": "spec_tree", "path": "spec/a.md"})],
        vocab=Config(data=DEFAULTS).vocab)

def test_topo_orders_deps_first_and_tolerates_cycles():
    a = Item(id="a", title="a"); b = Item(id="b", title="b", deps=["a"])
    assert [i.id for i in topo([b, a], {"a": [], "b": ["a"]})] == ["a", "b"]
    c1 = Item(id="c1", title="", deps=["c2"]); c2 = Item(id="c2", title="", deps=["c1"])
    assert {i.id for i in topo([c1, c2], {"c1": ["c2"], "c2": ["c1"]})} == {"c1", "c2"}

def test_roadmap_and_index(tmp_path):
    out = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                     only={"roadmap", "feature_index"})
    rm = out["roadmap.md"]
    assert "## R0" in rm
    assert rm.index("[a](../../spec/a.md)") < rm.index("[b](../../spec/b.md)")
    assert "✅ shipped" in rm
    fi = out["feature-index.md"]
    assert "## Drawing" in fi and "### Tools" in fi and "Does A." in fi

def test_render_all_rejects_unknown_view(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        render_all(_graph(), Config(data=DEFAULTS), tmp_path, only={"nope"})
```

- [ ] **Steps 2–5:** FAIL → implement → PASS → commit `"feat: render registry, roadmap (topo waves), feature index"`.

---

### Task 10: Dashboard + completion-sheet renderers  **[CODEX LANE]**

**Files:** Create `render/dashboard.py`, `render/completion_sheet.py`; Test `tests/test_render_dashboard.py`.

**Interfaces:**
- `dashboard.py` → `dashboard.md`. Sections, in order (planned items only — same skip rule as roadmap):
  1. `# Dashboard — what to work on`
  2. `## In progress` — items whose status is neither done (per `cfg.done_statuses()`) nor in `{"idea","backlog","specced","ready","parked","unknown"}` (i.e. active statuses like building/in-flight/bug-gap), sorted by id; `- <emoji status> <link> — <one_liner or title>`.
  3. `## Ready queue` — for the EARLIEST release in `render.releases` having any not-done item: not-started items whose deps are all done (missing dep target = satisfied), topo-ordered. Gated items (id in `cfg.gates()`) are EXCLUDED here and listed under…
  4. `## Blocked on decisions` — `- <link> — <gate reason>`.
  5. `## Progress` — per release line `R0 ██████░░░░░░ 3/6` using `common.bar`; then per top-level group same format.
- `completion_sheet.py` → `completion-sheet.md`: `# Completion sheet`; `## Overall` status count table (statuses in vocab order, then `MISSING`-style others, then Total); `## Post-ship health` (Verified count, Shipped incl. verified = counts of done statuses, Verified-rate %.1f — 0.0 when denominator 0, Debt = items with `debt` flag); `## By group` — one row per TOP-LEVEL group: columns = vocab statuses + other + debt + total (counts roll up descendants); `## Full list` table `| Group | Item | Status | Release | Wave | Debt |` sorted by (group, id) — ALL items including phases/todos.

- [ ] **Step 1: Failing test**

```python
# tests/test_render_dashboard.py
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Graph, Group, Item
from vizzer.render import render_all

def _graph():
    g = [Group(id="capability:c", kind="capability", title="Cap")]
    mk = lambda i, st, dep=None: Item(id=f"story:{i}", title=i.upper(), status=st,
                                      release="R0", deps=[f"story:{dep}"] if dep else [],
                                      group="capability:c",
                                      source={"adapter": "spec_tree", "path": f"s/{i}.md"})
    return Graph(groups=g, vocab=Config(data=DEFAULTS).vocab, items=[
        mk("done1", "shipped"),
        mk("wip", "building"),
        mk("ready", "specced", dep="done1"),
        mk("blocked", "specced", dep="wip"),
        mk("gated", "specced"),
        Item(id="story:debty", title="D", status="verified", release="R0",
             flags=["debt"], group="capability:c",
             source={"adapter": "spec_tree", "path": "s/d.md"}),
    ])

def _cfg():
    return Config(data=deep_merge(DEFAULTS, {"gates": [
        {"item": "story:gated", "reason": "await pricing decision"}]}))

def test_dashboard(tmp_path):
    d = render_all(_graph(), _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]
    inprog = d.split("## In progress")[1].split("##")[0]
    assert "wip" in inprog and "ready" not in inprog
    ready = d.split("## Ready queue")[1].split("##")[0]
    assert "[ready]" in ready and "[blocked]" not in ready and "[gated]" not in ready
    assert "await pricing decision" in d.split("## Blocked on decisions")[1].split("##")[0]
    assert "2/6" in d.split("## Progress")[1]     # done statuses: done1 (shipped) + debty (verified)

def test_completion_sheet(tmp_path):
    c = render_all(_graph(), _cfg(), tmp_path, only={"completion_sheet"})["completion-sheet.md"]
    assert "| verified | 1 |" in c
    assert "| Verified-rate | 50.0% |" in c       # 1 verified / (1 shipped + 1 verified)
    assert "| Debt (flagged items) | 1 |" in c
    assert "story:debty" not in c                  # links use id tails, not raw ids
    assert "[debty](../../s/d.md)" in c
```

- [ ] **Steps 2–5:** FAIL → implement → PASS → commit `"feat: dashboard (ready queue, gates) + completion sheet renderers"`.

---

### Task 11: Ledger-table + manifest renderers  **[CODEX LANE]**

**Files:** Create `render/ledger_table.py`, `render/manifest.py`; Test `tests/test_render_ledger_manifest.py`.

**Interfaces:**
- `ledger_table.py` → `ledger-table.md`: `# Ledger table` + one row per group of kind `ledger`, sorted by id: `| Ledger | Goal | Phase | Progress | Open Qs | Last touched | Stale |`. Phase = title of the first child item with an ACTIVE status (not done, not in the not-started set of Task 10) else `—`; Progress = `<bar> d/t` over child items (done = `cfg.done_statuses()`); Last touched = max child `activity.modified` date (YYYY-MM-DD prefix) else `—`; Stale = `⚠️` when every child's `activity.last_touched` is older than `reconcile.staleness_days` before the NEWEST `last_touched` anywhere in the graph (deterministic reference point — never wall clock), else empty. If no ledger groups exist: render the header + `_No continuity ledgers found._`.
- `manifest.py` → `manifest.json` (deterministic, `indent=2`, trailing newline): `{"generated_by": "vizzer", "schema": 1, "doc_count": N, "docs": [...]}` — one entry per item that has a `source.path`, sorted by path then id: `{path, kind (= id prefix before ":"), id, title, status, group, synopsis (= one_liner), created, modified}` (dates from `activity`, may be null).

- [ ] **Step 1: Failing test**

```python
# tests/test_render_ledger_manifest.py
import json
from vizzer.config import Config, DEFAULTS
from vizzer.model import Graph, Group, Item
from vizzer.render import render_all

def _graph():
    return Graph(
        groups=[Group(id="ledger:wr", kind="ledger", title="Wr",
                      meta={"goal": "Ship it.", "open_questions": 2, "path": "t/l.md"})],
        vocab=Config(data=DEFAULTS).vocab,
        items=[Item(id="phase:wr/01-a", title="Extract core", status="shipped",
                    group="ledger:wr", source={"adapter": "ledgers", "path": "t/l.md"},
                    activity={"modified": "2026-02-01T00:00:00+00:00", "last_touched": 100,
                              "created": "2026-01-01T00:00:00+00:00", "commits": 1, "mentions": 0}),
               Item(id="phase:wr/02-b", title="Port sites", status="building",
                    group="ledger:wr", source={"adapter": "ledgers", "path": "t/l.md"},
                    activity={"modified": "2026-02-01T00:00:00+00:00", "last_touched": 100,
                              "created": "2026-01-01T00:00:00+00:00", "commits": 1, "mentions": 0})])

def test_ledger_table(tmp_path):
    md = render_all(_graph(), Config(data=DEFAULTS), tmp_path, only={"ledger_table"})["ledger-table.md"]
    assert "Ship it." in md and "Port sites" in md
    assert "1/2" in md and "| 2 |" in md and "2026-02-01" in md

def test_manifest(tmp_path):
    out = render_all(_graph(), Config(data=DEFAULTS), tmp_path, only={"manifest"})["manifest.json"]
    m = json.loads(out)
    assert m["doc_count"] == 2 and m["docs"][0]["kind"] == "phase"
    assert m["docs"][0]["synopsis"] is None
    assert out.endswith("\n") and out == json.dumps(m, indent=2, ensure_ascii=False) + "\n"

def test_ledger_table_empty(tmp_path):
    g = Graph(vocab=Config(data=DEFAULTS).vocab)
    md = render_all(g, Config(data=DEFAULTS), tmp_path, only={"ledger_table"})["ledger-table.md"]
    assert "No continuity ledgers" in md
```

- [ ] **Steps 2–5:** FAIL → implement → PASS → commit `"feat: ledger table + corpus manifest renderers"`.

---

### Task 12: Constellation  **[CLAUDE — taste-bearing port]**

**Files:** Create `render/constellation.py`, `render/constellation_template.html`; Test `tests/test_render_constellation.py`.

**Steps (this task is a port, not TDD-from-scratch — test first anyway):**

- [ ] **Step 1: Failing test**

```python
# tests/test_render_constellation.py
import json, re
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Graph, Group, Item
from vizzer.render import render_all

def _graph():
    return Graph(groups=[Group(id="capability:c", kind="capability", title="Cap")],
                 vocab=Config(data=DEFAULTS).vocab,
                 items=[Item(id="story:a", title="A", status="shipped", release="R0",
                             group="capability:c", appetite="large",
                             source={"adapter": "spec_tree", "path": "s/a.md"},
                             activity={"commits": 3, "mentions": 1, "last_touched": 500}),
                        Item(id="story:b", title="B", status="specced", release="R0",
                             deps=["story:a"], group="capability:c",
                             source={"adapter": "spec_tree", "path": "s/b.md"},
                             activity={"commits": 1, "mentions": 0, "last_touched": 900})])

def _data(html):
    return json.loads(re.search(r"const DATA=(\{.*?\});\n", html, re.S).group(1))

def test_constellation_injects_data(tmp_path):
    cfg = Config(data=deep_merge(DEFAULTS, {"project": {"name": "demo"},
                                            "render": {"recommended": ["story:b"]}}))
    html = render_all(_graph(), cfg, tmp_path, only={"constellation"})["constellation.html"]
    assert "__DATA__" not in html and "__TITLE__" not in html and "demo" in html
    d = _data(html)
    assert len(d["nodes"]) == 2 and d["edges"] == [[0, 1]]
    assert d["now"] == 900                       # max last_touched — deterministic, no wall clock
    assert d["nodes"][1]["rec"] == 1
    assert d["nodes"][0]["w"] > d["nodes"][1]["w"]   # appetite large > default
    assert "root" not in d                       # no absolute paths unless obsidian_links=true
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Port + implement.** Copy `/Users/ryders/Developer/GitHub/the source project/scripts/dev/spec-constellation-template.html` → `src/vizzer/render/constellation_template.html`, then make exactly these edits: (a) `<title>` and the `#title` header text → `__TITLE__` placeholder; (b) delete/neutralize any remaining literal `the source project` strings (grep to verify: `grep -i the source project constellation_template.html` → no hits); (c) the dossier's `obsidian://` link code becomes conditional on `DATA.root` being present. `constellation.py::render`: build the same node shape as the source project (`s` = id tail, `t` = title ≤80, `st`, `c` = top-level group id tail, `e` = immediate group title ≤40, `r`, `p` = source.path, `w` = 0.72+0.36×appetite-weight with weights small=1.0/medium=1.9/large=2.9/default=1.4, `ac`/`am`/`ts` from activity, `rec: 1` for ids in `render.recommended`); edges from deps (indexes, `[from, to]`); `caps` = per-top-group `{total, shipped}` (shipped = done statuses); `now` = max node `ts` (0 if none); include `root: str(root)` ONLY when `render.obsidian_links` is true. Inject via `template.replace("__DATA__", "const DATA=" + json.dumps(data, separators=(",", ":")) + ";\n")` — wait: template already has `const DATA=__DATA__;` — keep the source project's convention: replace the `__DATA__` token with the compact JSON and ensure the test's regex (`const DATA=({...});\n`) matches the emitted line; adjust the template line to end with `;\n` after the token. Title: `render.title` if set else `project.name` + " — constellation". Skip nothing: phase/todo items ARE included (the constellation is the whole-graph view).
- [ ] **Step 4: Run** `python3 -m pytest tests/test_render_constellation.py -v` — PASS. Then open a rendered file manually once (`python3 -c ...` on the mixed fixture after T13) for a visual sanity check — record result in the PR/commit body.
- [ ] **Step 5: Commit** — `"feat: 3D constellation renderer (ported template, config-driven title, deterministic now)"`.

---

### Task 13: Engine CLI + mixed fixture + golden end-to-end  **[CODEX LANE — Claude reviews UX copy]**

**Files:** Create `src/vizzer/cli.py`, fixture `tests/fixtures/mixed_proj/` (spec_proj's spec/ + ledger_proj's thoughts/ + docs_proj's docs/ + todo_proj's TODO.md + a `vizzer/vizzer.toml` enabling all four with the Task-4 glob/levels and `mention_globs=["docs/**/*.md"]`), golden dir `tests/golden/mixed/`; Test `tests/test_cli.py`.

**Interfaces:**
- `main(argv: list[str] | None = None) -> int`. Subcommands (argparse, `prog="vizzer"`):
  - `sync [--root PATH]` — load config, run `get_adapters` scans, `build_graph`, write `<root>/vizzer/vizzer-graph.json` (via `Graph.dumps()`). Print `sync: N items, M groups, K conflicts, W warnings`, then each conflict and warning line. Exit 0 (conflicts are visible, not fatal).
  - `render [--root PATH] [--only a,b]` — read graph file (error exit 2 if missing: `run 'sync' first`), `render_all`, write files into `<root>/<render.output_dir>/`, print `render: wrote <n> files`.
  - `check [--root PATH] [--structural]` — recompute graph in memory + re-render; compare with on-disk graph + view files. `--structural` strips every item's `activity` and graph `warnings` before comparing graphs and skips view comparison for `manifest.json` (carries dates); constellation IS compared (deterministic). Print each stale path; exit 1 if any, else `check: up to date`, exit 0.
  - `archive [--root PATH] --yes` — move files whose claiming item's `source.adapter` ∈ `archive.adapters` to `<root>/vizzer/archive/<relpath>` (`os.renames`); without `--yes` print the file list + warning `archived files leave git tracking` and exit 1 without moving.
  - `install` / `update` — defined in T14; until then, stub subparsers that print `not yet implemented` and exit 2 (replaced in T14 — note: this stub is allowed scaffolding because T14 in this same plan replaces it; tests don't cover it).
  - Root default: cwd; `--root` overrides. All output relative paths in messages.
- Golden files: `tests/golden/mixed/vizzer-graph.json` + one golden per view. **Generated once during Step 3 via the harness below, then reviewed by eye and committed** — from then on they pin every format.

- [ ] **Step 1: Failing test**

```python
# tests/test_cli.py
import json, shutil
from pathlib import Path
from vizzer.cli import main

GOLDEN = Path(__file__).parent / "golden" / "mixed"

def _views(root):
    return sorted((root / "vizzer" / "views").iterdir())

def test_sync_render_check_archive(tmp_path, make_repo, capsys):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "conflicts" in out
    graph = json.loads((repo / "vizzer" / "vizzer-graph.json").read_text())
    assert graph["schema"] == 1 and len(graph["items"]) > 5

    assert main(["render", "--root", str(repo)]) == 0
    names = [p.name for p in _views(repo)]
    assert names == sorted(["roadmap.md", "feature-index.md", "dashboard.md",
                            "completion-sheet.md", "ledger-table.md",
                            "manifest.json", "constellation.html"])

    assert main(["check", "--root", str(repo), "--structural"]) == 0

    # golden comparison (deterministic thanks to fixed fixture commit dates)
    for golden in sorted(GOLDEN.iterdir()):
        produced = (repo / "vizzer" / ("vizzer-graph.json" if golden.name == "vizzer-graph.json"
                                       else f"views/{golden.name}")).read_text()
        assert produced == golden.read_text(), f"drift in {golden.name}"

    # archive: default scope is todos only, requires --yes
    assert main(["archive", "--root", str(repo)]) == 1
    assert (repo / "TODO.md").exists()
    assert main(["archive", "--root", str(repo), "--yes"]) == 0
    assert not (repo / "TODO.md").exists()
    assert (repo / "vizzer" / "archive" / "TODO.md").exists()

def test_render_without_graph_errors(tmp_path, make_repo, capsys):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["render", "--root", str(repo)]) == 2
    assert "sync" in capsys.readouterr().out
```

(`make_repo` must also learn to skip copying nothing — it already copies the whole fixture including `vizzer/vizzer.toml`.)

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** cli.py + assemble `mixed_proj` fixture + generate goldens: run sync+render on a `make_repo`-style temp checkout (small throwaway script or `python3 - <<'EOF'` harness using conftest logic), copy outputs into `tests/golden/mixed/`, **eyeball every golden file** (this is the format review). **Step 4: Run** `python3 -m pytest tests/ -v` — all PASS. **Step 5: Commit** `"feat: engine CLI (sync/render/check/archive) + mixed-fixture golden suite"`.

---

### Task 14: Installer — vendor, detect, register  **[CODEX core; Claude authors the harness-block/skill copy]**

**Files:** Create `src/vizzer/install.py`; Modify `src/vizzer/cli.py` (replace install/update stubs); Test `tests/test_install.py`.

**Interfaces:**
- `detect(root: Path) -> dict` — `{"spec_tree": {"glob": <best guess or "">, "levels": [...]}, "ledgers": bool, "loose_docs": [globs], "todos": [files]}`. Heuristics: ledgers = any `thoughts/ledgers/CONTINUITY_*.md`; todos = `TODO.md` exists; loose_docs = `docs/**/*.md` or `wiki/**/*.md` non-empty (propose those globs); spec_tree = search for `*/stories/*.md` up to depth 6 — if found, reconstruct a single-star glob from the observed path shape and name levels by the literal directory names between wildcards (e.g. observed `wiki/product-spec/capabilities/X/epics/Y/stories/Z.md` → glob `wiki/product-spec/capabilities/*/epics/*/stories/*.md`, levels `["capability", "epic"]` from the singularized parent dir names).
- `install(target: Path, *, claude_skill: bool = False, harness: str = "auto") -> int`:
  1. Refuse (exit 2, message) if `target/vizzer/engine` already exists (say: use `update`).
  2. Vendor: copy the installed `vizzer` package dir (`Path(vizzer.__file__).parent`) → `target/vizzer/engine/vizzer` (ignore `__pycache__`); write `target/vizzer/engine/__main__.py` = `from vizzer.cli import main\nraise SystemExit(main())\n`; write `target/vizzer/VERSION` = `vizzer.__version__`.
  3. Write `target/vizzer/vizzer.toml` from `detect()` — a commented file enabling detected sources (template string in `install.py`, comments explaining every key).
  4. Append `vizzer/archive/` to `target/.gitignore` (create if missing; skip if line present).
  5. Harness block: `harness="auto"` → prefer existing `CLAUDE.md`, else existing `AGENTS.md`, else create `AGENTS.md`. Upsert the managed block between `<!-- vizzer:begin` / `<!-- vizzer:end -->` markers (replace if present, else append with a blank line). Block text EXACTLY as in the spec's "Harness registration" section, with the invocation path `python3 vizzer/engine`.
  6. If `claude_skill`: write `.claude/skills/vizzer/SKILL.md` (frontmatter name `vizzer`, description "Regenerate the project work-graph and views; read vizzer/views/dashboard.md for what's next", body = the three commands + when to run them).
  7. Run `sync` + `render` via `cli.main` with `--root target`; print a summary.
- `update(target: Path) -> int` — replace `engine/` wholesale, rewrite VERSION + managed block; NEVER touch `vizzer.toml`, graph, views. Error exit 2 if `engine/` missing (not installed).
- cli.py wiring: `vizzer install <path> [--claude-skill] [--harness auto|claude|agents]`, `vizzer update <path>`; bare `vizzer` (no argv) → interactive: prompt for path (`input()`), show detect() results, confirm `y/N`, then install.

- [ ] **Step 1: Failing test**

```python
# tests/test_install.py
import subprocess, sys
from pathlib import Path
from vizzer.cli import main
import vizzer

def test_install_vendors_and_registers(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    # strip fixture's own config so detect() writes one
    (repo / "vizzer" / "vizzer.toml").unlink()
    assert main(["install", str(repo)]) == 0
    assert (repo / "vizzer" / "engine" / "vizzer" / "model.py").exists()
    assert (repo / "vizzer" / "VERSION").read_text().strip() == vizzer.__version__
    toml = (repo / "vizzer" / "vizzer.toml").read_text()
    assert "spec_tree" in toml and "enabled = true" in toml
    gi = (repo / ".gitignore").read_text()
    assert "vizzer/archive/" in gi
    agents = (repo / "AGENTS.md").read_text()
    assert "<!-- vizzer:begin" in agents and "python3 vizzer/engine sync" in agents
    assert (repo / "vizzer" / "vizzer-graph.json").exists()      # install ran sync+render
    assert (repo / "vizzer" / "views" / "dashboard.md").exists()

    # vendored engine runs standalone via `python3 vizzer/engine`
    r = subprocess.run([sys.executable, "vizzer/engine", "check", "--structural"],
                       cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

def test_install_twice_refuses_update_replaces(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    (repo / "vizzer" / "vizzer.toml").unlink()
    assert main(["install", str(repo)]) == 0
    assert main(["install", str(repo)]) == 2
    marker = repo / "vizzer" / "engine" / "vizzer" / "model.py"
    marker.write_text("clobbered")
    assert main(["update", str(repo)]) == 0
    assert "clobbered" not in marker.read_text()
    toml_before = (repo / "vizzer" / "vizzer.toml").read_text()
    assert (repo / "vizzer" / "vizzer.toml").read_text() == toml_before

def test_managed_block_upsert_prefers_existing_claude_md(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    (repo / "vizzer" / "vizzer.toml").unlink()
    (repo / "CLAUDE.md").write_text("# Project rules\n")
    assert main(["install", str(repo)]) == 0
    txt = (repo / "CLAUDE.md").read_text()
    assert txt.startswith("# Project rules") and txt.count("vizzer:begin") == 1
    assert not (repo / "AGENTS.md").exists()
    assert main(["update", str(repo)]) == 0
    assert (repo / "CLAUDE.md").read_text().count("vizzer:begin") == 1   # idempotent
```

- [ ] **Steps 2–5:** FAIL → implement (`detect`'s singularize: strip trailing `s` from dir name — `capabilities`→`capability`) → `python3 -m pytest tests/ -v` all PASS → commit `"feat: installer — vendor engine, detect sources, register harness block, update verb"`.

---

### Task 15: Packaging, CI, README  **[CODEX for CI yaml; CLAUDE for README]**

**Files:** Create `scripts/build_pyz.py`, `.github/workflows/ci.yml`, `README.md`; Test: extend `tests/test_packaging.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_packaging.py
import subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent

def test_build_pyz(tmp_path):
    out = tmp_path / "vizzer.pyz"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_pyz.py"), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert "__main__.py" in names and "vizzer/model.py" in names
    r2 = subprocess.run([sys.executable, str(out), "--help"], capture_output=True, text=True)
    assert r2.returncode == 0 and "sync" in r2.stdout
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
  - `scripts/build_pyz.py`: stage `src/vizzer` + a top-level `__main__.py` (`from vizzer.cli import main; raise SystemExit(main())`) into a temp dir, `zipapp.create_archive(staging, target=argv[1], interpreter="/usr/bin/env python3")`, skip `__pycache__`.
  - `.github/workflows/ci.yml`: on push/PR; job `test` — matrix `python-version: ["3.10", "3.11", "3.12", "3.13"]`, steps: checkout, setup-python, `pip install pytest`, `git config --global user.email ci@example.com && git config --global user.name CI` (fixture commits need identity), `python -m pytest tests/ -v`; job `pyz` — build `vizzer.pyz` via the script and upload-artifact.
  - `README.md` [CLAUDE — public voice]: what vizzer is (2 sentences), 60-second quickstart (`curl -LO …vizzer.pyz && python3 vizzer.pyz` → interactive install), the seven views with one line each, the graph file contract (derived, never hand-edit), config reference table (every `vizzer.toml` key from `DEFAULTS` + `[[status]]`/`[[gates]]`), the archive warning, "how agents use this" section quoting the managed block, MIT footer. Constellation screenshot deferred until first real render (note as an issue, not a TODO in README — README ships complete without it).
- [ ] **Step 4: Run** `python3 -m pytest tests/ -v` — all PASS.
- [ ] **Step 5: Commit** `"feat: pyz build, CI matrix, README"` — then final full-suite run + `codex review` cross-vendor pass over the whole branch before calling the build done.

---

## Self-Review (performed at write time)

1. **Spec coverage:** derived graph ✓(T1/T8), installer+vendoring+pyz ✓(T14/T15), harness registration ✓(T14), 4 adapters ✓(T4–T7), dag_import migration path ✓(T4), conflicts visible ✓(T8), 7 renderers ✓(T9–T12), ledger table ✓(T11), gates-as-config ✓(T2/T10), obsidian links opt-in ✓(T12), archive opt-in gitignored ✓(T13/T14), check/CI ✓(T13/T15), deterministic outputs ✓(fixed fixture dates T3, `now`=max ts T12), synthetic fixtures ✓, MIT ✓. Interactive no-arg install flow ✓(T14). Gap check: `update` in the downloadable tool = same `update` verb ✓.
2. **Placeholder scan:** T13's install/update stubs are explicitly replaced by T14 (allowed). No TBDs remain.
3. **Type consistency:** `ScanResult(groups, items, warnings)` used identically in T4–T8; `render(graph, cfg, root) -> dict[str,str]` uniform in T9–T12; `Config.load(root)` reads `<root>/vizzer/vizzer.toml` consistently (T2, T13, T14); `Group.meta` added in T1 and consumed in T5/T11; `slugify` moved to `adapters/__init__.py` in T7 with ledgers updated.
```
