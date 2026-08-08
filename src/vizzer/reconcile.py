"""Merge adapter scans into the normalized work graph."""
from __future__ import annotations

import copy
from pathlib import Path

from . import gitmeta
from .adapters import ScanResult
from .config import Config
from .model import Graph, Group, Item


_MERGE_FIELDS = ("status", "release", "wave", "title", "one_liner", "appetite")


def _adapter(item: Item) -> str:
    if isinstance(item.source, dict):
        return item.source.get("adapter", "")
    return ""


def _source_path(item: Item):
    if isinstance(item.source, dict):
        return item.source.get("path")
    return None


def _empty(value) -> bool:
    return value is None or value == "" or value == "unknown"


def _dependency_cycles(items_by_id):
    """Every dependency cycle, each reported once as a canonical rotation.

    A cycle cannot be topologically ordered, so the roadmap falls back to id order
    within it — which reads exactly like a real ordering. Saying so is the point.
    """
    deps = {i: [d for d in it.deps if d in items_by_id] for i, it in items_by_id.items()}
    WHITE, GREY, BLACK = 0, 1, 2
    color = {}
    found = set()

    def visit(node, stack):
        color[node] = GREY
        stack.append(node)
        for target in deps.get(node, []):
            state = color.get(target, WHITE)
            if state == GREY:
                loop = stack[stack.index(target):]
                # rotate to a stable starting point so one cycle is reported once
                start = loop.index(min(loop))
                found.add(tuple(loop[start:] + loop[:start]))
            elif state == WHITE:
                visit(target, stack)
        stack.pop()
        color[node] = BLACK

    for node in sorted(deps):
        if color.get(node, WHITE) == WHITE:
            visit(node, [])
    return [list(c) + [c[0]] for c in sorted(found)]


def _declared_groups(cfg: Config):
    """Normalize declarations into a stable order without mutating config data."""
    declarations = []
    for entry in cfg.groups():
        group_id = entry.get("id")
        if not isinstance(group_id, str) or not group_id.strip():
            continue
        title = entry.get("title")
        if not isinstance(title, str) or not title:
            slug = group_id.split(":", 1)[-1]
            title = slug.replace("-", " ").title()
        contains = entry.get("contains", [])
        if not isinstance(contains, list):
            contains = []
        child_ids = tuple(sorted({
            child_id for child_id in contains
            if isinstance(child_id, str) and child_id
        }))
        declarations.append((group_id, title, child_ids))
    return sorted(declarations)


def _would_create_group_cycle(groups_by_id, child_id: str, parent_id: str) -> bool:
    """Return whether assigning child_id beneath parent_id would close a loop."""
    current = parent_id
    seen = set()
    while current is not None and current not in seen:
        if current == child_id:
            return True
        seen.add(current)
        group = groups_by_id.get(current)
        current = group.parent if group is not None else None
    return current is not None


def _apply_declared_groups(cfg, groups_by_id, items_by_id, warnings) -> None:
    declarations = _declared_groups(cfg)
    scanned_group_ids = set(groups_by_id)

    # Materialize every parent first so declarations can refer to one another
    # regardless of their order in the config file.
    for group_id, title, _ in declarations:
        if group_id in scanned_group_ids:
            warnings.add(
                f"declared group {group_id} collides with a scanned group "
                "(scanned group kept)"
            )
        elif group_id not in groups_by_id:
            groups_by_id[group_id] = Group(
                id=group_id,
                kind=group_id.split(":", 1)[0],
                title=title,
                parent=None,
            )

    for parent_id, _, child_ids in declarations:
        for child_id in child_ids:
            child_group = groups_by_id.get(child_id)
            child_item = items_by_id.get(child_id)
            if child_group is None and child_item is None:
                warnings.add(
                    f"declared group {parent_id} contains unknown child {child_id}"
                )
                continue

            if child_group is not None:
                previous_parent = child_group.parent
                if _would_create_group_cycle(groups_by_id, child_id, parent_id):
                    warnings.add(
                        f"declared group {parent_id} cannot contain group {child_id}: "
                        "cycle (re-parenting skipped)"
                    )
                else:
                    if previous_parent is not None and previous_parent != parent_id:
                        warnings.add(
                            f"declared group {parent_id} re-parented group {child_id} "
                            f"from {previous_parent}"
                        )
                    child_group.parent = parent_id

            if child_item is not None:
                previous_group = child_item.group
                if previous_group is not None and previous_group != parent_id:
                    warnings.add(
                        f"declared group {parent_id} re-parented item {child_id} "
                        f"from {previous_group}"
                    )
                child_item.group = parent_id


def build_graph(
    cfg: Config,
    root: Path,
    scans: list[tuple[str, ScanResult]],
) -> Graph:
    """Reconcile precedence-ordered scan results into one deterministic graph."""
    precedence = cfg.get("reconcile.precedence", [])
    precedence_index = {}
    for index, adapter in enumerate(precedence):
        precedence_index.setdefault(adapter, index)
    lowest = len(precedence)

    all_items = [item for _, scan in scans for item in scan.items]
    all_items.sort(key=lambda item: (precedence_index.get(_adapter(item), lowest), item.id))

    items_by_id: dict[str, Item] = {}
    claimed_paths: dict[str, tuple[str, set[str]]] = {}
    conflicts: list[dict] = []
    warnings = {warning for _, scan in scans for warning in scan.warnings}

    for newcomer in all_items:
        path = _source_path(newcomer)
        keeper = items_by_id.get(newcomer.id)
        keeper_path = _source_path(keeper) if keeper is not None else None
        # Two files under ONE adapter yielding one id means data is silently lost.
        # The same id arriving from a DIFFERENT adapter is the designed merge path
        # (a dag_import restates every story id on purpose), so it is not a duplicate —
        # any real disagreement between them is already reported as a conflict below.
        if (keeper_path and path and keeper_path != path
                and _adapter(keeper) == _adapter(newcomer)):
            warnings.add(
                f"duplicate id {newcomer.id} — kept {keeper_path}, ignored {path}"
            )

        claim = claimed_paths.get(path) if path else None
        if claim is not None:
            owner_adapter, owner_ids = claim
            if newcomer.id not in owner_ids and _adapter(newcomer) != owner_adapter:
                continue

        if keeper is None:
            keeper = copy.deepcopy(newcomer)
            items_by_id[newcomer.id] = keeper
            if path:
                if claim is None:
                    claimed_paths[path] = (_adapter(newcomer), {newcomer.id})
                else:
                    claim[1].add(newcomer.id)
            continue

        for field_name in _MERGE_FIELDS:
            kept_value = getattr(keeper, field_name)
            dropped_value = getattr(newcomer, field_name)
            if _empty(kept_value) and not _empty(dropped_value):
                setattr(keeper, field_name, copy.deepcopy(dropped_value))
            elif (
                field_name == "status"
                and not _empty(kept_value)
                and not _empty(dropped_value)
                and kept_value != dropped_value
            ):
                conflicts.append({
                    "item": keeper.id,
                    "field": "status",
                    "kept": {"adapter": _adapter(keeper), "value": kept_value},
                    "dropped": {"adapter": _adapter(newcomer), "value": dropped_value},
                })

        if not keeper.deps and newcomer.deps:
            keeper.deps = copy.deepcopy(newcomer.deps)

    groups_by_id: dict[str, Group] = {}
    for _, scan in scans:
        for group in scan.groups:
            if group.id not in groups_by_id:
                groups_by_id[group.id] = copy.deepcopy(group)

    _apply_declared_groups(cfg, groups_by_id, items_by_id, warnings)

    known_ids = set(items_by_id)
    for item in items_by_id.values():
        kept_deps = []
        for dep in item.deps:
            if dep in known_ids:
                kept_deps.append(dep)
            else:
                warnings.add(f"dangling dep {item.id} → {dep} (edge dropped)")
        item.deps = kept_deps

    for cycle in _dependency_cycles(items_by_id):
        warnings.add("dependency cycle: " + " → ".join(cycle)
                     + " (roadmap order within the cycle is arbitrary)")

    meta, git_warnings = gitmeta.collect(
        root,
        cfg.get("reconcile.mention_globs", []),
    )
    warnings.update(git_warnings)
    for item in items_by_id.values():
        path = _source_path(item)
        if not path:
            continue
        needle = item.id.split(":", 1)[1].split("/")[-1]
        item.activity = {
            "commits": meta.commits(path),
            "mentions": meta.mentions(needle),
            "last_touched": meta.last_touched(path),
            "created": meta.created(path),
            "modified": meta.modified(path),
        }

    return Graph(
        groups=list(groups_by_id.values()),
        items=list(items_by_id.values()),
        conflicts=conflicts,
        warnings=sorted(warnings),
        vocab=cfg.vocab,
    )
