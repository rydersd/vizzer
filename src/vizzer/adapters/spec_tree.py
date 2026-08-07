"""Adapter for hierarchical spec trees and optional legacy DAG imports."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..model import Group, Item
from . import ScanResult


_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_LABEL_RE = re.compile(r"^\w+:\s*")
_MARKDOWN_LINK_RE = re.compile(r"^\[([^\]\r\n]+)\]\([^\r\n]*\)$")
_CODE_SPAN_RE = re.compile(r"^(`+)(.*?)\1$", re.DOTALL)
_KIND_PREFIX_RE = re.compile(r"^[A-Za-z0-9_-]+:")
_DEP_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _front_matter(text: str) -> tuple[dict, str]:
    """Parse the deliberately small front-matter subset used by adapters."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    try:
        end = next(i for i, line in enumerate(lines[1:], 1)
                   if line.strip() == "---")
    except StopIteration:
        return {}, text

    data: dict = {}
    list_key: str | None = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        if re.match(r"^\s*-\s+", line):
            if list_key is None:
                return {}, text
            data[list_key].append(re.sub(r"^\s*-\s+", "", line).strip())
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if not match:
            return {}, text
        key, raw = match.group(1), (match.group(2) or "").strip()
        if not raw:
            data[key] = []
            list_key = key
        else:
            data[key] = _front_value(raw)
            list_key = None

    return data, "\n".join(lines[end + 1:])


def _front_value(raw: str):
    if raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_unquote(part.strip()) for part in inner.split(",")]
    return _unquote(raw)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _first_h1(text: str) -> str | None:
    match = _H1_RE.search(text)
    return match.group(1).strip() if match else None


def _display_title(text: str) -> str | None:
    title = _first_h1(text)
    return _LABEL_RE.sub("", title).strip() if title else None


def _one_liner(body: str, front: dict) -> str | None:
    intent = re.search(r"^##\s+Intent\s*$", body, re.IGNORECASE | re.MULTILINE)
    if intent:
        for line in body[intent.end():].splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                break
            if stripped:
                return _collapse(stripped)[:140]
    summary = front.get("summary")
    if isinstance(summary, str) and summary.strip():
        return _collapse(summary)[:140]
    return None


def _collapse(value: str) -> str:
    return " ".join(value.split())


def _match_value(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


def _dep_ids(value, item_kind: str) -> list[str]:
    if isinstance(value, list):
        slugs = value
    elif isinstance(value, str):
        if value.strip() in {"", "-", "—"}:
            return []
        slugs = value.split(",")
    else:
        return []

    deps = []
    for raw in slugs:
        entry = str(raw).strip()
        if not entry or entry in {"-", "—"}:
            continue

        link = _MARKDOWN_LINK_RE.fullmatch(entry)
        if link:
            entry = link.group(1)

        entry = entry.strip()
        code_span = _CODE_SPAN_RE.fullmatch(entry)
        if code_span:
            entry = code_span.group(2).strip()
        entry = _KIND_PREFIX_RE.sub("", entry, count=1)

        if _DEP_SLUG_RE.fullmatch(entry):
            deps.append(f"{item_kind}:{entry}")
    return deps


def _body_deps(body: str):
    match = re.search(r"^>?\s*Deps:\s*(.*?)\s*$", body,
                      re.IGNORECASE | re.MULTILINE)
    return match.group(1) if match else None


def _group_chain(root: Path, rel: Path, pattern: str, levels: list[str],
                 groups: dict[str, Group], warnings: list[str]) -> str | None:
    pattern_parts = Path(pattern).as_posix().split("/")
    rel_parts = rel.as_posix().split("/")
    captures = [(index, rel_parts[index])
                for index, part in enumerate(pattern_parts[:-1])
                if part == "*" and index < len(rel_parts) - 1]

    parent = None
    cumulative = []
    for level, (index, slug) in zip(levels, captures):
        cumulative.append(slug)
        group_id = f"{level}:{'/'.join(cumulative)}"
        if group_id not in groups:
            title = slug.replace("-", " ").title()
            directory = root.joinpath(*rel_parts[:index + 1])
            overview = directory / f"{slug}.md"
            if overview.is_file():
                try:
                    title = _display_title(overview.read_text(encoding="utf-8")) or title
                except OSError:
                    warnings.append(f"{overview.relative_to(root).as_posix()}: unreadable")
            groups[group_id] = Group(id=group_id, kind=level, title=title,
                                     parent=parent)
        parent = group_id
    return parent


def _scan_file(path: Path, root: Path, pattern: str, levels: list[str],
               item_kind: str, groups: dict[str, Group],
               warnings: list[str]) -> Item | None:
    rel = path.relative_to(root)
    relpath = rel.as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        warnings.append(f"{relpath}: unreadable")
        return None

    front, body = _front_matter(text)
    stem = path.stem
    title = _display_title(body) or stem
    group = _group_chain(root, rel, pattern, levels, groups, warnings)

    status = front.get("status")
    if not isinstance(status, str) or not status:
        status = _match_value(r"^>\s*Status:\s*([a-zA-Z-]+)", body)
    if not status:
        status = "unknown"
        warnings.append(f"{relpath}: no status")

    release = front.get("release")
    if not isinstance(release, str) or not release:
        release = _match_value(r"Release:\s*([A-Za-z0-9.?]+)", body)
    wave = front.get("wave")
    if not isinstance(wave, str) or not wave:
        wave = _match_value(r"Wave:\s*([A-Za-z0-9]+)", body)
    appetite = _match_value(r"[Aa]ppetite:\s*\**\s*([a-z-]+)", body)
    deps_value = front["deps"] if "deps" in front else _body_deps(body)
    flags = ["debt"] if re.search(r"^>\s*Debt:", body, re.MULTILINE) else []

    return Item(
        id=f"{item_kind}:{stem}",
        title=title,
        one_liner=_one_liner(body, front),
        status=status,
        release=release,
        wave=wave,
        group=group,
        deps=_dep_ids(deps_value, item_kind),
        appetite=appetite,
        flags=flags,
        source={"adapter": "spec_tree", "path": relpath},
    )


def _dag_items(root: Path, dag_relpath: str, item_kind: str,
               warnings: list[str]) -> list[Item]:
    path = root / dag_relpath
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        warnings.append(f"{Path(dag_relpath).as_posix()}: unreadable or malformed DAG")
        return []

    capabilities = data.get("capabilities", []) if isinstance(data, dict) else []
    if not isinstance(capabilities, list):
        warnings.append(f"{Path(dag_relpath).as_posix()}: malformed DAG entries ignored")
        return []
    items = []
    malformed = not isinstance(data, dict)
    for capability in capabilities:
        if not isinstance(capability, dict):
            malformed = True
            continue
        epics = capability.get("epics", [])
        if not isinstance(epics, list):
            malformed = True
            continue
        for epic in epics:
            if not isinstance(epic, dict):
                malformed = True
                continue
            stories = epic.get("stories", [])
            if not isinstance(stories, list):
                malformed = True
                continue
            for story in stories:
                if not isinstance(story, dict) or not story.get("slug"):
                    malformed = True
                    continue
                slug = str(story["slug"])
                items.append(Item(
                    id=f"{item_kind}:{slug}",
                    title=str(story.get("title") or slug),
                    one_liner=(str(story["oneLiner"])
                               if story.get("oneLiner") is not None else None),
                    status=str(story.get("status") or "unknown"),
                    release=(str(story["release"])
                             if story.get("release") is not None else None),
                    deps=_dep_ids(story.get("deps", []), item_kind),
                    source={"adapter": "dag_import",
                            "path": Path(dag_relpath).as_posix()},
                ))
    if malformed:
        warnings.append(f"{Path(dag_relpath).as_posix()}: malformed DAG entries ignored")
    return sorted(items, key=lambda item: item.id)


def scan(cfg, root: Path) -> ScanResult:
    """Scan configured spec-tree files and an optional legacy DAG."""
    root = Path(root)
    pattern = cfg.get("sources.spec_tree.glob", "")
    levels = list(cfg.get("sources.spec_tree.levels", []))
    item_kind = cfg.get("sources.spec_tree.item_kind", "story")
    warnings = []
    groups: dict[str, Group] = {}
    items = []

    if pattern:
        try:
            paths = sorted(root.glob(pattern), key=lambda path: path.as_posix())
        except (NotImplementedError, ValueError, OSError):
            warnings.append(f"spec tree glob unusable: {pattern}")
            paths = []
        for path in paths:
            if path.name.startswith("_") or not path.is_file():
                continue
            item = _scan_file(path, root, pattern, levels, item_kind,
                              groups, warnings)
            if item is not None:
                items.append(item)

    dag_relpath = cfg.get("sources.spec_tree.dag_import", "")
    if dag_relpath:
        items.extend(_dag_items(root, dag_relpath, item_kind, warnings))

    return ScanResult(groups=list(groups.values()), items=items, warnings=warnings)
