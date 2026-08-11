"""Install a self-contained copy of vizzer into another project."""
from __future__ import annotations

import json
import os
import re
import shutil
import warnings
import zipfile
from pathlib import Path


_ENGINE_MAIN = "from vizzer.cli import main\nraise SystemExit(main())\n"
_BLOCK_BEGIN = "<!-- vizzer:begin"
_CONTEXT_DOCS = (
    "story-sizing-and-portfolio-selection.md",
    "prds-and-living-product-specs.md",
)
_MANAGED_BLOCK = """<!-- vizzer:begin (managed — do not hand-edit; `update` rewrites this block) -->
## Vizzer — project work-graph views
- `vizzer/vizzer-graph.json` is the normalized index of this project's work items
  (from configured sources). Read it for orientation; NEVER hand-edit — it's derived.
- Configured source files remain authoritative; importing a DAG does not make the
  derived graph or rendered views a write-back source. <!-- codex-sequence-2026-08-08 -->
- `[[source_area]]` names semantic project regions; never assume folders are
  literally named `wiki` or `product-spec`. Use `python3 vizzer/engine configure`
  when source roles or locations change, and inspect its match-count preview.
- Update the authoritative source story/issue/ledger first. After completing work,
  finding an issue, or changing a story's status or dependencies, run
  `python3 vizzer/engine refresh`. A shipped story stays shipped; record follow-up
  issues as separate work or flags rather than downgrading its source status.
- If `activity.path` is configured, update the named checkpoint feed when work
  starts, advances, blocks, pauses, or completes; activity never changes lifecycle
  or priority truth. <!-- codex-sequence-2026-08-08 -->
- If workstreams are enabled, register every live Claude, Codex, human, or script
  session with `sessions start`; renew its lease with `sessions heartbeat`; stop it
  explicitly. Use versioned workstreams for objectives/story/path ownership and the
  discussion log for peer review. Only reversible implementation decisions may be
  resolved peer-to-peer; product, scope, and contract choices become researched
  owner questions. Direct concurrent JSON edits are forbidden.
- At task start and whenever work blocks, scan specs, plans, active work, and
  implementation evidence for unresolved owner decisions. Read the surrounding
  contracts; do not infer a question from `blocked` or keywords. For each real
  decision, research 2–3 options with tradeoffs, recommend one, name a falsifier
  and evidence, and add it to the feed's explicit `questions` array while
  continuing work that does not depend on the answer.
- Questions and accepted answers are model-neutral repo records. Claude, Codex,
  Gemini, other agents, and the served UI must use the same validated answer
  schema; the model or chat session is never the decision authority. Static
  `file://` constellation output is read-only; use `python3 vizzer/engine serve`
  for interactive Answer controls. A served answer atomically appends a structured
  evolution event to its source story. If answers were authored directly in the
  ledger, run `python3 vizzer/engine decisions --all --yes`; read
  `vizzer/views/decision-journal.md` before shaping or implementing related work.
  After the accepted decision is actually applied, run
  `python3 vizzer/engine decisions <question-id> --apply --summary <outcome>
  --evidence <path> --yes`; acceptance and lifecycle remain separate gates.
- If `planning.enabled` is true, the accepted planning overlay composes over the
  target manifest. Use the refreshed graph's ranked recommendations for next-task
  selection. Analyze tradeoffs before applying a course change; never rewrite story
  headers, dependency truth, or the target manifest as a side effect.
- Delivery assessment is deterministic and model-neutral. Read
  `graph.assessment.items` plus the assessed portfolio; keep size, impact,
  uncertainty, and parallel safety separate. An agent may propose researched
  evidence, but it must not invent a universal AI speed multiplier or silently
  promote an inference into fact. Context lives in `vizzer/docs/`.
- To persist researched sizing evidence, refresh first, copy the item's current
  `scope_fingerprint` into `assessment.signals_path` as `scopeFingerprint`, add
  only authored/proposed `signals`, then refresh again. Source changes make the
  entry stale. Observed sizes and executed-test claims are adapter-owned and may
  not be self-certified by Claude, Codex, Gemini, or any other model.
- `python3 vizzer/engine check` gates staleness (CI/pre-commit friendly).
- Views live in `vizzer/views/` — dashboard.md answers "what next";
  decision-journal.md preserves owner rationale; constellation.html is the 3D map.
<!-- vizzer:end -->"""
_CLAUDE_SKILL = """---
name: vizzer
description: Regenerate the project work-graph and views; read vizzer/views/dashboard.md for what's next
---

# Vizzer

- Treat configured source stories, issues, and ledgers as authoritative; never edit
  the generated graph or views. A shipped story stays shipped: capture regressions
  as separate work or flags, not a source-status downgrade.
- Run `python3 vizzer/engine refresh` after task completion, issue discovery, or a
  story status/dependency change. It syncs and renders one newly built graph.
- Read semantic `source_area` configuration instead of assuming a `wiki`,
  `product-spec`, or any other fixed folder name.
- When configured, update the activity feed at named checkpoints; checkpoint
  progress is an overlay and never substitutes for story acceptance.
- When workstreams are enabled, claim a versioned workstream and start a leased
  session before editing. Heartbeat while active and stop on handoff. Use peer
  discussion for reversible implementation choices; escalate product, scope, and
  contract decisions through the existing researched owner-question channel.
- Scan repository specs, plans, activity, and implementation evidence for real
  unresolved owner decisions. Do not equate `blocked` with a question. Research
  2–3 options, tradeoffs, a recommendation, falsifier, and evidence before adding
  an explicit activity-feed question; keep progressing independent work.
- Treat the configured question-answer overlay as model-neutral repo authority.
  Any agent may author its validated schema; do not treat chat memory as the
  accepted decision. Static constellation files are read-only; interactive
  answering requires `python3 vizzer/engine serve`. Served answers append
  evolution events to their source stories. After direct ledger authorship, run
  `python3 vizzer/engine decisions --all --yes`; inspect
  `vizzer/views/decision-journal.md` for accepted rationale and pending application.
- When assessment is enabled, use `graph.assessment.items` and its portfolio;
  keep size, impact, uncertainty, and parallel safety separate. Never invent a
  universal AI speed multiplier. Read `vizzer/docs/story-sizing-and-portfolio-selection.md`
  and `vizzer/docs/prds-and-living-product-specs.md` for the reasoning contract.
- Persist sizing research only in the configured schema-1 assessment-signals
  overlay, bound to the current base scope fingerprint. Do not self-certify
  observed size or executed tests from chat or prose evidence.
- Run `python3 vizzer/engine check` in CI or before committing to detect stale output.
"""


# How deep below the project root a `.../stories/<item>.md` tree may sit and still be
# auto-detected. Deeper trees are still usable — the user points `glob` at them by hand.
_MAX_SPEC_DEPTH = 10
_MAX_DAG_DEPTH = 10
_MAX_DAG_BYTES = 50 * 1024 * 1024
_MAX_DAG_JSON_DEPTH = 8
_MAX_DAG_JSON_NODES = 20_000
_WORK_ITEM_KEYS = {"deps", "status", "release", "wave"}


def _matches(root: Path, pattern: str) -> bool:
    return any(path.is_file() for path in root.glob(pattern))


def _singularize(name: str) -> str:
    if name.endswith("ies"):
        return f"{name[:-3]}y"
    if name.endswith("s"):
        return name[:-1]
    return name


def _spec_tree(root: Path) -> dict:
    candidates = []
    for path in root.rglob("*.md"):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        parts = rel.parts
        if not path.is_file() or not parts or parts[0] == "vizzer":
            continue
        if len(parts) < 3 or parts[-2] != "stories":
            continue

        stories_index = len(parts) - 2
        if not 1 <= stories_index <= _MAX_SPEC_DEPTH:
            continue
        candidates.append(rel)

    if not candidates:
        return {"glob": "", "levels": [], "root": ""}

    observed = min(candidates, key=lambda path: path.as_posix())
    parts = list(observed.parts)
    stories_index = len(parts) - 2
    container_indexes = [stories_index]
    candidate_index = stories_index - 2
    while candidate_index >= 0 and parts[candidate_index].endswith("s"):
        container_indexes.append(candidate_index)
        candidate_index -= 2
    wildcard_indexes = {index + 1 for index in container_indexes}

    glob_parts = ["*.md" if index == len(parts) - 1 else "*"
                  if index in wildcard_indexes else part
                  for index, part in enumerate(parts)]
    level_indexes = sorted(index for index in container_indexes
                           if index != stories_index)
    levels = [_singularize(parts[index]) for index in level_indexes]
    root_parts = parts[:min(level_indexes)] if level_indexes else parts[:stories_index]
    return {
        "glob": "/".join(glob_parts), "levels": levels,
        "root": Path(*root_parts).as_posix() if root_parts else "",
    }


def _looks_like_dag(data) -> bool:
    visited = 0
    slug_records = 0
    has_work_record = False

    def walk(node, depth: int) -> None:
        nonlocal visited, slug_records, has_work_record
        if visited >= _MAX_DAG_JSON_NODES:
            return
        visited += 1

        if (isinstance(node, dict) and isinstance(node.get("slug"), str)
                and node["slug"].strip()):
            slug_records += 1
            if _WORK_ITEM_KEYS.intersection(node):
                has_work_record = True
        if depth >= _MAX_DAG_JSON_DEPTH:
            return

        if isinstance(node, list):
            children = node
        elif isinstance(node, dict):
            children = node.values()
        else:
            return

        for child in children:
            walk(child, depth + 1)
            if visited >= _MAX_DAG_JSON_NODES:
                break

    walk(data, 0)
    # The work-item signal alone is the discriminator: a content manifest carries
    # slugs but never deps/status/release/wave. Counting records instead would
    # wrongly reject a small but legitimate DAG.
    return slug_records > 0 and has_work_record


def _dag_import(root: Path) -> str:
    matches = []
    skipped_dirs = {"vizzer", "node_modules", ".git"}
    for directory, dirnames, filenames in os.walk(root):
        path = Path(directory)
        try:
            depth = len(path.relative_to(root).parts)
        except ValueError:
            continue
        dirnames[:] = sorted(name for name in dirnames
                             if name not in skipped_dirs and depth < _MAX_DAG_DEPTH)
        if depth > _MAX_DAG_DEPTH:
            continue

        for filename in sorted(filenames):
            if not filename.endswith(".json"):
                continue
            candidate = path / filename
            try:
                if candidate.stat().st_size > _MAX_DAG_BYTES:
                    continue
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            except ValueError as exc:
                warnings.warn(
                    f"{candidate.relative_to(root).as_posix()}: unusable DAG: {exc}",
                    RuntimeWarning,
                )
                continue
            except (OSError, UnicodeError, RecursionError):
                continue
            if _looks_like_dag(data):
                matches.append(candidate.relative_to(root))

    if not matches:
        return ""
    preferred = ".shape-spec-dag.json"
    return min(matches, key=lambda path: (path.name != preferred, path.as_posix())).as_posix()


def detect(root: Path) -> dict:
    """Detect supported work-item sources below *root*."""
    root = Path(root)
    loose_docs = [pattern for pattern in ("docs/**/*.md", "wiki/**/*.md")
                  if _matches(root, pattern)]
    spec_tree = _spec_tree(root)
    spec_tree["dag_import"] = _dag_import(root)
    return {
        "spec_tree": spec_tree,
        "ledgers": _matches(root, "thoughts/ledgers/CONTINUITY_*.md"),
        "loose_docs": loose_docs,
        "todos": ["TODO.md"] if (root / "TODO.md").is_file() else [],
    }


def _detection_summary(found: dict) -> str:
    """Human-readable scan result — silent non-detection is a support burden."""
    lines = []
    glob = found["spec_tree"]["glob"]
    dag_import = found["spec_tree"].get("dag_import", "")
    has_structured_sources = bool(
        glob or dag_import or found["ledgers"] or found["todos"]
    )
    lines.append(f"  spec_tree:  {glob}" if glob else "  spec_tree:  none found")
    if dag_import:
        lines.append(f"  dag_import: {dag_import}")
    lines.append("  ledgers:    thoughts/ledgers/CONTINUITY_*.md"
                 if found["ledgers"] else "  ledgers:    none found")
    if found["loose_docs"]:
        suffix = " (disabled — fallback only)" if has_structured_sources else ""
        lines.append(f"  loose_docs: {', '.join(found['loose_docs'])}{suffix}")
    else:
        lines.append("  loose_docs: none found")
    lines.append(f"  todos:      {', '.join(found['todos'])}"
                 if found["todos"] else "  todos:      none found")
    header = "install: detected sources"
    if not (glob or dag_import or found["ledgers"] or found["loose_docs"] or
            found["todos"]):
        header = ("install: no sources detected — edit vizzer/vizzer.toml to point "
                  "vizzer at your work-tracking files")
    return "\n".join([header, *lines])


def _string_array(values: list[str]) -> str:
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"


def _config_text(target: Path, found: dict) -> str:
    spec_tree = found["spec_tree"]
    spec_tree_enabled = bool(spec_tree["glob"] or spec_tree.get("dag_import", ""))
    loose_docs = found["loose_docs"]
    todos = found["todos"]
    loose_docs_enabled = bool(loose_docs) and (
        bool(found.get("explicit_loose_docs"))
        or not (spec_tree_enabled or found["ledgers"] or todos)
    )
    project_name = found.get("project_name", target.resolve().name).replace('"', "'")
    source_areas = list(found.get("source_areas", []))
    if not source_areas:
        spec_root = spec_tree.get("root", "")
        if spec_root:
            title = Path(spec_root).name.replace("-", " ").title()
            source_areas.append({
                "id": re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-"),
                "title": title, "role": "delivery", "path": spec_root,
                "adapter": "spec_tree",
            })
        for pattern in loose_docs:
            folder = pattern.split("/", 1)[0]
            title = folder.replace("-", " ").title()
            area_id = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
            if folder and all(area["id"] != area_id for area in source_areas):
                source_areas.append({
                    "id": area_id, "title": title, "role": "knowledge",
                    "path": folder, "adapter": "loose_docs",
                })
    source_area_text = "\n".join(
        "\n".join((
            "[[source_area]]",
            f'id = "{area["id"].replace(chr(34), chr(39))}"',
            f'title = "{area["title"].replace(chr(34), chr(39))}"',
            f'role = "{area["role"]}"',
            f'path = "{area["path"]}"',
            f'adapter = "{area["adapter"]}"',
            "",
        )) for area in source_areas
    )
    item_kind = spec_tree.get("item_kind", "story").replace('"', "'")
    return f"""# Vizzer configuration. Re-run detection manually before changing source globs.

[project]
# Human-readable project name used in generated views.
name = "{project_name}"

# Semantic source map. Folder names are project data: Product Spec,
# Experience Spec, handbook, wiki, ADRs, and research are all valid answers.
{source_area_text}

[sources.spec_tree]
# Scan hierarchical story specifications when a matching tree was detected.
enabled = {str(spec_tree_enabled).lower()}
# Repository-relative story file pattern.
glob = "{spec_tree["glob"]}"
# Group names captured by each directory wildcard.
levels = {_string_array(spec_tree["levels"])}
# Kind prefix used for story item identifiers.
item_kind = "{item_kind}"
# Import dependency edges from an existing DAG file when one was detected.
dag_import = "{spec_tree.get("dag_import", "")}"

[sources.ledgers]
# Scan continuity ledgers when matching files were detected.
enabled = {str(found["ledgers"]).lower()}
# Repository-relative continuity-ledger pattern.
glob = "thoughts/ledgers/CONTINUITY_*.md"

[sources.loose_docs]
# Fallback for repos with no structured sources; when enabled, docs also appear in manifest.json.
enabled = {str(loose_docs_enabled).lower()}
# Repository-relative documentation patterns.
globs = {_string_array(loose_docs)}

[sources.todos]
# Scan TODO files when one was detected.
enabled = {str(bool(todos)).lower()}
# Repository-relative TODO file patterns.
globs = {_string_array(todos)}

[render]
# Directory where generated views are written.
output_dir = "vizzer/views"
# Release lanes shown in roadmap views.
releases = ["R0", "R1", "R2", "R3"]
# Item IDs pinned as recommendations.
recommended = []
# Embed absolute-path obsidian:// links in the constellation (local vaults only).
obsidian_links = false
# Optional title override for generated views.
title = ""

[reconcile]
# Source priority used when multiple adapters describe the same item.
precedence = ["spec_tree", "dag_import", "ledgers", "todos", "loose_docs"]
# Optional field-specific dependency winner during a staged authority migration.
# codex-sequence-2026-08-08
dependency_authority = ""
# Files searched for references to work-item names.
mention_globs = {_string_array(loose_docs)}
# Age threshold used to flag stale work.
staleness_days = 14

[archive]
# Source adapters whose files may be archived.
adapters = ["todos"]

# codex-sequence-2026-08-08: optional target-scoped, explainable uptake ranking.
[priority]
enabled = false
# Strongest target tier: a repo-relative schema-1 JSON file with directTargetIds.
target_manifest = ""
target_items = []
target_milestones = []
target_releases = []
limit = 10
eligible_roles = ["ready", "active", "regression"]
exclude_flags = ["blocked", "triage", "needs-triage", "stale"]

[priority.role_bias]
regression = 80
active = 50
ready = 0

[priority.appetite_cost]
small = 0
medium = 20
large = 50
default = 25

# Model-neutral delivery sizing and balanced portfolio suggestions. Assessment
# never changes source appetite, lifecycle, dependencies, or owner course.
[assessment]
enabled = true
signals_path = "vizzer/assessment-signals.json"
small_limit = 4
anchor_limit = 2
question_limit = 1
verification_globs = ["tests/**/*", "test/**/*", "tests-ui/**/*"]

# Owner-authored, audited course changes compose with priority target authority.
# Static views are read-only; use `vizzer serve` or `vizzer plan` to write safely.
[planning]
enabled = false
overlay_path = "vizzer/planning-overlay.json"

# Optional agent-work overlay. It never mutates status, readiness, or priority.
[activity]
path = ""
stale_after_minutes = 120
trail_rounds = 5

# Versioned workstream intent plus machine-local leased sessions. Agents use the
# CLI/server writer; they do not race by editing the JSON stores directly.
[workstreams]
enabled = false
definitions_path = "vizzer/workstreams.json"
runtime_path = ".vizzer/runtime/sessions.json"
lease_minutes = 30

# Optional lifecycle metadata. `next` permits configured transitions; omitting it
# keeps the status unconstrained for backwards compatibility.  # codex-sequence-2026-08-08
# [[status]]
# name = "building"
# emoji = "🔧"
# done = false
# role = "active"
# description = "Implementation is underway."
# next = ["shipped", "parked"]

# Add a hierarchy level the directory tree does not encode, without moving files.
# [[group]]
# id = "product:time"
# title = "Time"
# contains = ["capability:billing", "capability:first-session"]
"""


def _vendor(engine: Path) -> None:
    """Copy this package into *engine*, whether we run from disk or from a .pyz.

    The published distributable is a zipapp, so `vizzer.__file__` may point inside a
    zip archive where copytree cannot reach; zipimport exposes the archive path on the
    loader, and the package's files are extracted from there instead.
    """
    import vizzer

    engine.mkdir(parents=True, exist_ok=True)
    archive = getattr(getattr(vizzer, "__loader__", None), "archive", None)

    if archive:
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if not name.startswith("vizzer/") or name.endswith("/"):
                    continue
                if name.startswith("vizzer/context/"):
                    # Context is installed once at vizzer/docs; keeping a
                    # second engine copy would break source/vendor parity.
                    continue
                if "__pycache__" in name or name.endswith((".pyc", ".DS_Store")):
                    continue
                dest = engine / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
    else:
        shutil.copytree(
            Path(vizzer.__file__).parent,
            engine / "vizzer",
            # codex-sequence-2026-08-08: never vendor local interpreter/OS debris.
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        )

    (engine / "__main__.py").write_text(_ENGINE_MAIN, encoding="utf-8")


def _write_context_docs(target: Path) -> None:
    """Install the portable assessment/spec guidance beside project data."""
    import vizzer

    destination = target / "vizzer" / "docs"
    destination.mkdir(parents=True, exist_ok=True)
    archive = getattr(getattr(vizzer, "__loader__", None), "archive", None)
    if archive:
        with zipfile.ZipFile(archive) as zf:
            for name in _CONTEXT_DOCS:
                (destination / name).write_bytes(zf.read(f"vizzer/context/{name}"))
        return

    package_root = Path(vizzer.__file__).resolve().parent
    candidates = (
        package_root.parent.parent / "docs" / "context",
        package_root / "context",
        package_root.parent.parent / "docs",
    )
    source = next(
        (candidate for candidate in candidates
         if all((candidate / name).is_file() for name in _CONTEXT_DOCS)),
        None,
    )
    if source is None:
        raise FileNotFoundError("Vizzer assessment context documents are missing")
    for name in _CONTEXT_DOCS:
        shutil.copyfile(source / name, destination / name)


def _write_version(target: Path) -> None:
    import vizzer

    (target / "vizzer" / "VERSION").write_text(
        f"{vizzer.__version__}\n", encoding="utf-8"
    )


def _ensure_archive_ignored(target: Path) -> None:
    path = target / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    required = ("vizzer/archive/", ".vizzer/runtime/")
    existing = {line.strip() for line in text.splitlines()}
    missing = [entry for entry in required if entry not in existing]
    if not missing:
        return
    separator = "" if not text or text.endswith("\n") else "\n"
    path.write_text(
        f"{text}{separator}" + "".join(f"{entry}\n" for entry in missing),
        encoding="utf-8",
    )


def _doc_with_block(target: Path) -> Path | None:
    for name in ("CLAUDE.md", "AGENTS.md"):
        path = target / name
        if path.is_file() and _BLOCK_BEGIN in path.read_text(encoding="utf-8"):
            return path
    return None


def _harness_doc(target: Path, harness: str) -> Path:
    if harness == "claude":
        return target / "CLAUDE.md"
    if harness == "agents":
        return target / "AGENTS.md"
    if (target / "CLAUDE.md").is_file():
        return target / "CLAUDE.md"
    if (target / "AGENTS.md").is_file():
        return target / "AGENTS.md"
    return target / "AGENTS.md"


def _upsert_managed_block(path: Path) -> None:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    pattern = re.compile(r"<!-- vizzer:begin.*?<!-- vizzer:end -->", re.DOTALL)
    if pattern.search(text):
        updated = pattern.sub(_MANAGED_BLOCK, text, count=1)
    elif text:
        updated = f"{text.rstrip()}\n\n{_MANAGED_BLOCK}\n"
    else:
        updated = f"{_MANAGED_BLOCK}\n"
    path.write_text(updated, encoding="utf-8")


def install(target: Path, *, claude_skill: bool = False,
            harness: str = "auto", configuration: dict | None = None) -> int:
    """Install vizzer into *target* and generate its initial graph and views."""
    target = Path(target)
    engine = target / "vizzer" / "engine"
    if engine.exists():
        print("install: vizzer is already installed; run 'update' instead")
        return 2

    found = configuration or detect(target)
    print(_detection_summary(found))
    engine.parent.mkdir(parents=True, exist_ok=True)
    _vendor(engine)
    _write_context_docs(target)
    _write_version(target)
    config_text = found.get("config_text") or _config_text(target, found)
    (target / "vizzer" / "vizzer.toml").write_text(config_text, encoding="utf-8")
    _ensure_archive_ignored(target)
    _upsert_managed_block(_harness_doc(target, harness))

    if claude_skill:
        skill_path = target / ".claude" / "skills" / "vizzer" / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(_CLAUDE_SKILL, encoding="utf-8")

    from .cli import main as cli_main

    if cli_main(["refresh", "--root", str(target)]) != 0:
        print("install: initial refresh failed")
        return 2
    print(f"install: installed vizzer in {target}")
    return 0


def update(target: Path) -> int:
    """Replace a target project's vendored engine without touching its data."""
    target = Path(target)
    engine = target / "vizzer" / "engine"
    if not engine.exists():
        print("update: vizzer is not installed")
        return 2

    shutil.rmtree(engine)
    _vendor(engine)
    _write_context_docs(target)
    _write_version(target)
    harness_doc = _doc_with_block(target) or _harness_doc(target, "auto")
    _upsert_managed_block(harness_doc)
    print(f"update: refreshed vizzer in {target}")
    return 0
