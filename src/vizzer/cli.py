"""Command-line interface for synchronizing and rendering project work graphs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .adapters import get_adapters
from .config import Config
from .model import Graph
from .reconcile import build_graph
from .render import render_all


GRAPH_RELPATH = Path("vizzer/vizzer-graph.json")


def _build(cfg: Config, root: Path) -> Graph:
    scans = [
        (name, adapter.scan(cfg, root))
        for name, adapter in get_adapters(cfg)
    ]
    return build_graph(cfg, root, scans)


def _read_graph(root: Path) -> Graph | None:
    path = root / GRAPH_RELPATH
    if not path.is_file():
        return None
    try:
        return Graph.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _sync(root: Path) -> int:
    cfg = Config.load(root)
    graph = _build(cfg, root)
    path = root / GRAPH_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(graph.dumps(), encoding="utf-8")

    print(
        f"sync: {len(graph.items)} items, {len(graph.groups)} groups, "
        f"{len(graph.conflicts)} conflicts, {len(graph.warnings)} warnings"
    )
    for conflict in graph.conflicts:
        kept = conflict.get("kept", {})
        dropped = conflict.get("dropped", {})
        print(
            f"conflict: {conflict.get('item', '')} {conflict.get('field', '')}: "
            f"kept {kept.get('adapter', '')}={kept.get('value')!r}; "
            f"dropped {dropped.get('adapter', '')}={dropped.get('value')!r}"
        )
    for warning in graph.warnings:
        print(f"warning: {warning}")
    return 0


def _render(root: Path, only_value: str | None) -> int:
    graph = _read_graph(root)
    if graph is None:
        print("render: run 'sync' first")
        return 2

    cfg = Config.load(root)
    only = None
    if only_value is not None:
        only = {name.strip() for name in only_value.split(",") if name.strip()}
    try:
        rendered = render_all(graph, cfg, root, only=only)
    except ValueError as exc:
        print(f"render: {exc}")
        return 2

    output_dir = root / cfg.get("render.output_dir", "vizzer/views")
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in rendered.items():
        (output_dir / filename).write_text(content, encoding="utf-8")
    print(f"render: wrote {len(rendered)} files")
    return 0


def _structural_graph(data: dict) -> dict:
    structural = dict(data)
    structural["warnings"] = []
    structural["items"] = []
    for item in data.get("items", []):
        stripped = dict(item)
        stripped["activity"] = {}
        structural["items"].append(stripped)
    return structural


def _check(root: Path, structural: bool) -> int:
    cfg = Config.load(root)
    expected_graph = _build(cfg, root)
    expected_views = render_all(expected_graph, cfg, root)
    graph_path = root / GRAPH_RELPATH
    stale: set[str] = set()

    try:
        disk_text = graph_path.read_text(encoding="utf-8")
        disk_data = json.loads(disk_text)
    except (OSError, UnicodeError, json.JSONDecodeError):
        stale.add(GRAPH_RELPATH.as_posix())
    else:
        if structural:
            if _structural_graph(expected_graph.to_dict()) != _structural_graph(disk_data):
                stale.add(GRAPH_RELPATH.as_posix())
        elif expected_graph.dumps() != disk_text:
            stale.add(GRAPH_RELPATH.as_posix())

    output_relpath = Path(cfg.get("render.output_dir", "vizzer/views"))
    for filename, expected in expected_views.items():
        if structural and filename == "manifest.json":
            continue
        path = root / output_relpath / filename
        try:
            actual = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            stale.add((output_relpath / filename).as_posix())
            continue
        if actual != expected:
            stale.add((output_relpath / filename).as_posix())

    if stale:
        for relpath in sorted(stale):
            print(f"stale: {relpath}")
        return 1

    print("check: up to date")
    return 0


def _archive(root: Path, confirmed: bool) -> int:
    graph = _read_graph(root)
    if graph is None:
        print("archive: run 'sync' first")
        return 2

    cfg = Config.load(root)
    adapters = set(cfg.get("archive.adapters", []))
    relpaths = sorted({
        Path(item.source["path"])
        for item in graph.items
        if item.source.get("adapter") in adapters and item.source.get("path")
    }, key=lambda path: path.as_posix())

    for relpath in relpaths:
        print(relpath.as_posix())
    if not confirmed:
        print("archived files leave git tracking")
        return 1

    moved = 0
    for relpath in relpaths:
        source = root / relpath
        if not source.exists():
            continue
        destination = root / "vizzer" / "archive" / relpath
        os.renames(source, destination)
        moved += 1
    print(f"archive: moved {moved} files")
    return 0


def _stub(_args: argparse.Namespace) -> int:
    print("not yet implemented")
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vizzer")
    subparsers = parser.add_subparsers(dest="command")

    sync = subparsers.add_parser("sync")
    sync.add_argument("--root", default=".")
    sync.set_defaults(handler=lambda args: _sync(Path(args.root)))

    render = subparsers.add_parser("render")
    render.add_argument("--root", default=".")
    render.add_argument("--only")
    render.set_defaults(handler=lambda args: _render(Path(args.root), args.only))

    check = subparsers.add_parser("check")
    check.add_argument("--root", default=".")
    check.add_argument("--structural", action="store_true")
    check.set_defaults(handler=lambda args: _check(Path(args.root), args.structural))

    archive = subparsers.add_parser("archive")
    archive.add_argument("--root", default=".")
    archive.add_argument("--yes", action="store_true")
    archive.set_defaults(handler=lambda args: _archive(Path(args.root), args.yes))

    for name in ("install", "update"):
        stub = subparsers.add_parser(name)
        stub.set_defaults(handler=_stub)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the vizzer CLI and return a process exit code."""
    parser = _parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    return args.handler(args)
