"""Interactive, testable project-source configuration.

Vizzer asks about semantic roles and then writes adapter configuration.  It does
not require a directory named ``wiki`` or ``product-spec``; those are common
answers, not a data model.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable


class ConfigurationError(ValueError):
    pass


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not result:
        raise ConfigurationError("source area titles need at least one letter or number")
    return result


def _relative_folder(root: Path, value: object, subject: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{subject} must be a non-empty folder")
    relative = Path(value.strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigurationError(f"{subject} must stay inside the project")
    candidate = root / relative
    if not candidate.is_dir():
        raise ConfigurationError(f"{subject} does not exist: {relative.as_posix()}")
    return relative.as_posix().rstrip("/")


def _relative_file(root: Path, value: object, subject: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ConfigurationError(f"{subject} must be a repository-relative file")
    relative = Path(value.strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigurationError(f"{subject} must stay inside the project")
    if not (root / relative).is_file():
        raise ConfigurationError(f"{subject} does not exist: {relative.as_posix()}")
    return relative.as_posix()


def _relative_glob(root: Path, value: object, folder: str) -> tuple[str, int]:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("structured story glob must be non-empty")
    pattern = value.strip()
    relative = Path(pattern)
    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigurationError("structured story glob must stay inside the project")
    matches = sorted(path for path in root.glob(pattern) if path.is_file())
    if not matches:
        raise ConfigurationError(f"structured story glob matches no files: {pattern}")
    area_root = (root / folder).resolve()
    for match in matches:
        try:
            match.resolve().relative_to(area_root)
        except ValueError:
            raise ConfigurationError(
                "structured story glob must stay inside its configured source area"
            ) from None
    return pattern, len(matches)


def _source_area(area_id: str, title: str, role: str, path: str, adapter: str) -> dict:
    return {
        "id": area_id, "title": title.strip(), "role": role,
        "path": path, "adapter": adapter,
    }


def configure_from_answers(root: Path, answers: dict) -> tuple[str, dict]:
    """Validate structured answers and return ``(vizzer.toml, preview)``."""
    from .install import _config_text

    root = Path(root).resolve()
    if not isinstance(answers, dict):
        raise ConfigurationError("configuration answers must be a JSON object")
    project_name = answers.get("projectName")
    if not isinstance(project_name, str) or not project_name.strip():
        raise ConfigurationError("projectName must be non-empty")

    source_areas = []
    loose_docs = []
    seen_area_ids: set[str] = set()
    structured = answers.get("structuredSpec")
    if structured is None:
        spec_tree = {"glob": "", "levels": [], "dag_import": "", "root": ""}
        story_count = 0
    else:
        if not isinstance(structured, dict):
            raise ConfigurationError("structuredSpec must be an object or null")
        folder = _relative_folder(root, structured.get("folder"), "structured spec folder")
        title = structured.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ConfigurationError("structured spec title must be non-empty")
        pattern, story_count = _relative_glob(root, structured.get("storyGlob"), folder)
        levels = structured.get("levels")
        if not isinstance(levels, list) or not all(
            isinstance(level, str) and level.strip() for level in levels
        ):
            raise ConfigurationError("structured spec levels must be non-empty strings")
        item_kind = structured.get("itemKind", "story")
        if not isinstance(item_kind, str) or not item_kind.strip():
            raise ConfigurationError("structured spec itemKind must be non-empty")
        dag_import = _relative_file(
            root, structured.get("dagImport", ""), "dependency DAG"
        )
        area_id = _slug(title)
        seen_area_ids.add(area_id)
        source_areas.append(_source_area(area_id, title, "delivery", folder, "spec_tree"))
        spec_tree = {
            "glob": pattern, "levels": [value.strip() for value in levels],
            "dag_import": dag_import, "root": folder,
            "item_kind": item_kind.strip(),
        }

    knowledge = answers.get("knowledge", [])
    if not isinstance(knowledge, list):
        raise ConfigurationError("knowledge must be an array")
    for index, entry in enumerate(knowledge, 1):
        if not isinstance(entry, dict):
            raise ConfigurationError(f"knowledge area #{index} must be an object")
        folder = _relative_folder(root, entry.get("folder"), f"knowledge area #{index}")
        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ConfigurationError(f"knowledge area #{index} title must be non-empty")
        area_id = _slug(title)
        if area_id in seen_area_ids:
            raise ConfigurationError(f"duplicate source area id {area_id!r}")
        seen_area_ids.add(area_id)
        include_items = entry.get("includeItems", False)
        if not isinstance(include_items, bool):
            raise ConfigurationError(
                f"knowledge area #{index} includeItems must be true or false"
            )
        adapter = "loose_docs" if include_items else "none"
        source_areas.append(_source_area(area_id, title, "knowledge", folder, adapter))
        if include_items:
            loose_docs.append(f"{folder}/**/*.md")

    if not source_areas:
        raise ConfigurationError("configuration needs at least one source area")
    found = {
        "project_name": project_name.strip(),
        "spec_tree": spec_tree,
        "ledgers": False,
        "loose_docs": loose_docs,
        "explicit_loose_docs": bool(loose_docs),
        "todos": [],
        "source_areas": source_areas,
    }
    return _config_text(root, found), {
        "projectName": project_name.strip(),
        "storyCount": story_count,
        "sourceAreas": source_areas,
    }


def _answer(input_fn: Callable[[str], str], prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input_fn(f"{prompt}{suffix}: ").strip()
    return value or default


def _detected_spec_root(spec_tree: dict) -> str:
    explicit = spec_tree.get("root", "")
    if explicit:
        return explicit
    parts = Path(spec_tree.get("glob", "")).parts
    prefix = []
    for part in parts:
        if any(token in part for token in "*?["):
            break
        prefix.append(part)
    return Path(*prefix).as_posix() if prefix else ""


def grill(root: Path, *, input_fn: Callable[[str], str] = input,
          output_fn: Callable[[str], None] = print) -> dict:
    """Ask a bounded source-authority interview and return normalized answers."""
    from .install import detect

    root = Path(root).resolve()
    detected = detect(root)
    project_name = _answer(input_fn, "Project name", root.name)
    spec_default = _detected_spec_root(detected["spec_tree"])
    spec_folder = _answer(
        input_fn,
        "Structured delivery specification folder (blank means none)",
        spec_default,
    )
    structured = None
    if spec_folder:
        default_title = Path(spec_folder).name.replace("-", " ").title()
        spec_title = _answer(input_fn, "What should Vizzer call this source?", default_title)
        default_glob = detected["spec_tree"].get("glob", "")
        if not default_glob or not default_glob.startswith(spec_folder.rstrip("/") + "/"):
            default_glob = f"{spec_folder.rstrip('/')}/**/stories/*.md"
        story_glob = _answer(input_fn, "Story/work-item glob", default_glob)
        default_levels = ", ".join(detected["spec_tree"].get("levels", []))
        hierarchy = _answer(input_fn, "Hierarchy labels, comma separated", default_levels)
        levels = [value.strip() for value in hierarchy.split(",") if value.strip()]
    knowledge_defaults = []
    for pattern in detected.get("loose_docs", []):
        root_part = pattern.split("/", 1)[0]
        if root_part and root_part not in knowledge_defaults:
            knowledge_defaults.append(root_part)
    knowledge_raw = _answer(
        input_fn, "Knowledge/documentation folders, comma separated",
        ", ".join(knowledge_defaults),
    )
    knowledge = []
    for folder in [value.strip() for value in knowledge_raw.split(",") if value.strip()]:
        default_title = Path(folder).name.replace("-", " ").title()
        title = _answer(input_fn, f"What should Vizzer call {folder}?", default_title)
        include_items = _answer(
            input_fn,
            f"Include every Markdown page under {folder} as a graph reference item?",
            "n",
        ).casefold() in {"y", "yes"}
        knowledge.append({
            "folder": folder, "title": title, "includeItems": include_items,
        })
    dag_default = detected["spec_tree"].get("dag_import", "")
    dag_import = _answer(input_fn, "Dependency DAG file (optional)", dag_default)
    if spec_folder:
        structured = {
            "folder": spec_folder, "title": spec_title, "storyGlob": story_glob,
            "levels": levels, "itemKind": "story", "dagImport": dag_import,
        }
    text, preview = configure_from_answers(root, {
        "projectName": project_name,
        "structuredSpec": structured,
        "knowledge": knowledge,
    })
    count = preview["storyCount"]
    output_fn(
        f"Preview: {count} structured work item{'s' if count != 1 else ''}; "
        f"{len(preview['sourceAreas'])} semantic source area(s)."
    )
    if _answer(input_fn, "Write this configuration?", "n").casefold() not in {"y", "yes"}:
        raise ConfigurationError("configuration cancelled")
    preview["configText"] = text
    return {
        "project_name": project_name,
        "spec_tree": {
            "glob": structured["storyGlob"] if structured else "",
            "levels": structured["levels"] if structured else [],
            "dag_import": structured["dagImport"] if structured else "",
            "root": structured["folder"] if structured else "",
            "item_kind": "story",
        },
        "ledgers": False,
        "loose_docs": [
            f"{entry['folder']}/**/*.md" for entry in knowledge
            if entry["includeItems"]
        ],
        "explicit_loose_docs": any(entry["includeItems"] for entry in knowledge),
        "todos": [],
        "source_areas": preview["sourceAreas"],
        "config_text": text,
    }
