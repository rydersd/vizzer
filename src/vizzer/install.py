"""Install a self-contained copy of vizzer into another project."""
from __future__ import annotations

import re
import shutil
from pathlib import Path


_ENGINE_MAIN = "from vizzer.cli import main\nraise SystemExit(main())\n"
_BLOCK_BEGIN = "<!-- vizzer:begin"
_MANAGED_BLOCK = """<!-- vizzer:begin (managed — do not hand-edit; `update` rewrites this block) -->
## Vizzer — project work-graph views
- `vizzer/vizzer-graph.json` is the normalized index of this project's work items
  (from specs/ledgers/docs). Read it for orientation; NEVER hand-edit — it's derived.
- After merging work or changing any status: run
  `python3 vizzer/engine sync && python3 vizzer/engine render`.
- `python3 vizzer/engine check` gates staleness (CI/pre-commit friendly).
- Views live in `vizzer/views/` — dashboard.md answers "what next";
  constellation.html is the 3D map.
<!-- vizzer:end -->"""
_CLAUDE_SKILL = """---
name: vizzer
description: Regenerate the project work-graph and views; read vizzer/views/dashboard.md for what's next
---

# Vizzer

- Run `python3 vizzer/engine sync` after specs, ledgers, docs, or statuses change.
- Run `python3 vizzer/engine render` after syncing to regenerate the project views.
- Run `python3 vizzer/engine check` in CI or before committing to detect stale output.
"""


# How deep below the project root a `.../stories/<item>.md` tree may sit and still be
# auto-detected. Deeper trees are still usable — the user points `glob` at them by hand.
_MAX_SPEC_DEPTH = 10


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
        return {"glob": "", "levels": []}

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
    return {"glob": "/".join(glob_parts), "levels": levels}


def detect(root: Path) -> dict:
    """Detect supported work-item sources below *root*."""
    root = Path(root)
    loose_docs = [pattern for pattern in ("docs/**/*.md", "wiki/**/*.md")
                  if _matches(root, pattern)]
    return {
        "spec_tree": _spec_tree(root),
        "ledgers": _matches(root, "thoughts/ledgers/CONTINUITY_*.md"),
        "loose_docs": loose_docs,
        "todos": ["TODO.md"] if (root / "TODO.md").is_file() else [],
    }


def _detection_summary(found: dict) -> str:
    """Human-readable scan result — silent non-detection is a support burden."""
    lines = []
    glob = found["spec_tree"]["glob"]
    lines.append(f"  spec_tree:  {glob}" if glob else "  spec_tree:  none found")
    lines.append("  ledgers:    thoughts/ledgers/CONTINUITY_*.md"
                 if found["ledgers"] else "  ledgers:    none found")
    lines.append(f"  loose_docs: {', '.join(found['loose_docs'])}"
                 if found["loose_docs"] else "  loose_docs: none found")
    lines.append(f"  todos:      {', '.join(found['todos'])}"
                 if found["todos"] else "  todos:      none found")
    header = "install: detected sources"
    if not (glob or found["ledgers"] or found["loose_docs"] or found["todos"]):
        header = ("install: no sources detected — edit vizzer/vizzer.toml to point "
                  "vizzer at your work-tracking files")
    return "\n".join([header, *lines])


def _string_array(values: list[str]) -> str:
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"


def _config_text(target: Path, found: dict) -> str:
    spec_tree = found["spec_tree"]
    loose_docs = found["loose_docs"]
    todos = found["todos"]
    project_name = target.resolve().name.replace('"', "'")
    return f"""# Vizzer configuration. Re-run detection manually before changing source globs.

[project]
# Human-readable project name used in generated views.
name = "{project_name}"

[sources.spec_tree]
# Scan hierarchical story specifications when a matching tree was detected.
enabled = {str(bool(spec_tree["glob"])).lower()}
# Repository-relative story file pattern.
glob = "{spec_tree["glob"]}"
# Group names captured by each directory wildcard.
levels = {_string_array(spec_tree["levels"])}
# Kind prefix used for story item identifiers.
item_kind = "story"
# Optional legacy DAG import path.
dag_import = ""

[sources.ledgers]
# Scan continuity ledgers when matching files were detected.
enabled = {str(found["ledgers"]).lower()}
# Repository-relative continuity-ledger pattern.
glob = "thoughts/ledgers/CONTINUITY_*.md"

[sources.loose_docs]
# Scan Markdown documentation when matching files were detected.
enabled = {str(bool(loose_docs)).lower()}
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
# Files searched for references to work-item names.
mention_globs = {_string_array(loose_docs)}
# Age threshold used to flag stale work.
staleness_days = 14

[archive]
# Source adapters whose files may be archived.
adapters = ["todos"]
"""


def _vendor(engine: Path) -> None:
    import vizzer

    package_dir = Path(vizzer.__file__).parent
    engine.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        package_dir,
        engine / "vizzer",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (engine / "__main__.py").write_text(_ENGINE_MAIN, encoding="utf-8")


def _write_version(target: Path) -> None:
    import vizzer

    (target / "vizzer" / "VERSION").write_text(
        f"{vizzer.__version__}\n", encoding="utf-8"
    )


def _ensure_archive_ignored(target: Path) -> None:
    path = target / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if any(line.strip() == "vizzer/archive/" for line in text.splitlines()):
        return
    separator = "" if not text or text.endswith("\n") else "\n"
    path.write_text(f"{text}{separator}vizzer/archive/\n", encoding="utf-8")


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
            harness: str = "auto") -> int:
    """Install vizzer into *target* and generate its initial graph and views."""
    target = Path(target)
    engine = target / "vizzer" / "engine"
    if engine.exists():
        print("install: vizzer is already installed; run 'update' instead")
        return 2

    found = detect(target)
    print(_detection_summary(found))
    engine.parent.mkdir(parents=True, exist_ok=True)
    _vendor(engine)
    _write_version(target)
    (target / "vizzer" / "vizzer.toml").write_text(
        _config_text(target, found), encoding="utf-8"
    )
    _ensure_archive_ignored(target)
    _upsert_managed_block(_harness_doc(target, harness))

    if claude_skill:
        skill_path = target / ".claude" / "skills" / "vizzer" / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(_CLAUDE_SKILL, encoding="utf-8")

    from .cli import main as cli_main

    cli_main(["sync", "--root", str(target)])
    cli_main(["render", "--root", str(target)])
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
    _write_version(target)
    harness_doc = _doc_with_block(target) or _harness_doc(target, "auto")
    _upsert_managed_block(harness_doc)
    print(f"update: refreshed vizzer in {target}")
    return 0
