"""Command-line interface for synchronizing and rendering project work graphs."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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


def _gitignored_source_directories(graph: Graph, root: Path) -> list[str]:
    directories = set()
    for item in graph.items:
        source_path = item.source.get("path")
        if not source_path:
            continue
        path = Path(source_path)
        if path.is_absolute() or len(path.parts) < 2 or path.parts[0] in (".", ".."):
            continue
        directories.add(path.parts[0])

    ignored = []
    for directory in sorted(directories):
        try:
            result = subprocess.run(
                [
                    "git", "-C", str(root), "check-ignore", "--no-index", "-q",
                    directory,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            continue
        if result.returncode == 0:
            ignored.append(directory)
    return ignored


def _print_sync_hints(cfg: Config, graph: Graph) -> None:
    item_kind = cfg.get("sources.spec_tree.item_kind", "story")
    kind_prefix = f"{item_kind}:"
    item_count = sum(item.id.startswith(kind_prefix) for item in graph.items)
    edge_count = sum(len(item.deps) for item in graph.items)
    if item_count >= 5 and edge_count == 0:
        print(
            f"hint: {item_count} items, 0 dependency edges — if your dependencies "
            "live in a DAG file,\n"
            "      set sources.spec_tree.dag_import in vizzer/vizzer.toml"
        )


def _read_graph(root: Path) -> Graph | None:
    path = root / GRAPH_RELPATH
    if not path.is_file():
        return None
    try:
        return Graph.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        AttributeError,
        ValueError,
    ) as exc:
        print(f"graph: could not load {path}: {exc}; re-run 'sync'")
        return None


def _output_dir(cfg: Config, root: Path) -> Path | None:
    value = cfg.get("render.output_dir", "vizzer/views")
    try:
        resolved_root = root.resolve()
        resolved_output = (resolved_root / Path(value)).resolve()
    except (OSError, TypeError, ValueError):
        print(f"render: invalid output_dir {value!r}")
        return None
    if not resolved_output.is_relative_to(resolved_root):
        print(f"render: output_dir {value!r} is outside the project")
        return None
    return resolved_output


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
    _print_sync_hints(cfg, graph)
    for directory in _gitignored_source_directories(graph, root):
        print(
            f"warning: {directory} is gitignored — views derived from it cannot be "
            "reproduced by CI or teammates"
        )
    return 0


def _render(root: Path, only_value: str | None) -> int:
    graph = _read_graph(root)
    if graph is None:
        print("render: run 'sync' first")
        return 2

    cfg = Config.load(root)
    output_dir = _output_dir(cfg, root)
    if output_dir is None:
        return 2
    only = None
    if only_value is not None:
        only = {name.strip() for name in only_value.split(",") if name.strip()}
    try:
        rendered = render_all(graph, cfg, root, only=only)
    except ValueError as exc:
        print(f"render: {exc}")
        return 2

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
    disk_graph = _read_graph(root)
    if disk_graph is None:
        print("check: run 'sync' first")
        return 2

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
            if _structural_graph(expected_graph.to_dict()) != _structural_graph(
                disk_graph.to_dict()
            ):
                stale.add(GRAPH_RELPATH.as_posix())
        elif expected_graph.dumps() != disk_text:
            stale.add(GRAPH_RELPATH.as_posix())

    output_relpath = Path(cfg.get("render.output_dir", "vizzer/views"))
    for filename, expected in expected_views.items():
        if structural and filename in {
            "manifest.json",
            "constellation.html",
            "ledger-table.md",
        }:
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


def _archive_dir_fd_supported() -> bool:
    functions = (os.open, os.mkdir, os.link, os.unlink)
    return (
        hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and all(function in os.supports_dir_fd for function in functions)
        and os.link in os.supports_follow_symlinks
    )


def _directory_open_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_archive_parent(archive_fd: int, parent: Path) -> int:
    """Open/create *parent* below archive_fd without following symlinks."""
    current_fd = os.dup(archive_fd)
    try:
        for part in parent.parts:
            if part in {"", ".", ".."}:
                raise OSError(f"unsafe archive directory component: {part!r}")
            try:
                os.mkdir(part, dir_fd=current_fd)
            except FileExistsError:
                pass
            next_fd = os.open(part, _directory_open_flags(), dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _remove_empty_source_parents(source: Path, root: Path) -> None:
    parent = source.parent
    while parent != root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


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

    resolved_root = root.resolve()
    archive_root = resolved_root / "vizzer" / "archive"
    moved = skipped = 0
    candidates = []
    for relpath in relpaths:
        source = (resolved_root / relpath).resolve()
        if not source.is_relative_to(resolved_root):
            print(f"warning: archive path is outside the project: {relpath.as_posix()}")
            skipped += 1
            continue
        if not source.exists():
            skipped += 1
            continue
        if not source.is_file():
            print(f"warning: archive source is not a file: {relpath.as_posix()}")
            skipped += 1
            continue

        source_relpath = source.relative_to(resolved_root)
        candidates.append((relpath, source, source_relpath))

    if os.path.islink(archive_root):
        print(f"warning: archive directory is a symlink: {archive_root}")
        return 2
    if archive_root.exists() and not archive_root.is_dir():
        print(f"warning: archive path is not a directory: {archive_root}")
        return 2
    try:
        resolved_archive_root = archive_root.resolve()
    except OSError as exc:
        print(f"warning: archive directory is unavailable: {exc}")
        return 2
    if not resolved_archive_root.is_relative_to(resolved_root):
        print(f"warning: archive directory is outside the project: {archive_root}")
        return 2

    if candidates:
        archive_root.mkdir(parents=True, exist_ok=True)

    if candidates and _archive_dir_fd_supported():
        root_fd = archive_fd = None
        try:
            root_fd = os.open(resolved_root, _directory_open_flags())
            archive_fd = os.open(archive_root, _directory_open_flags())
        except OSError as exc:
            if archive_fd is not None:
                os.close(archive_fd)
            if root_fd is not None:
                os.close(root_fd)
            print(f"warning: archive directory is unsafe or unavailable: {exc}")
            return 2

        try:
            for relpath, source, source_relpath in candidates:
                destination = archive_root / source_relpath
                try:
                    parent_fd = _open_archive_parent(archive_fd, source_relpath.parent)
                except OSError as exc:
                    print(f"warning: archive destination is unsafe: {destination}: {exc}")
                    skipped += 1
                    continue
                try:
                    try:
                        os.link(
                            source_relpath.as_posix(),
                            source_relpath.name,
                            src_dir_fd=root_fd,
                            dst_dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                    except FileExistsError:
                        print(f"warning: archive destination already exists: {destination}")
                        skipped += 1
                        continue
                    except OSError as exc:
                        print(f"warning: could not archive {relpath.as_posix()}: {exc}")
                        skipped += 1
                        continue
                    try:
                        os.unlink(source_relpath.as_posix(), dir_fd=root_fd)
                    except OSError:
                        os.unlink(source_relpath.name, dir_fd=parent_fd)
                        raise
                finally:
                    os.close(parent_fd)
                _remove_empty_source_parents(source, resolved_root)
                moved += 1
        finally:
            os.close(archive_fd)
            os.close(root_fd)
    else:
        for relpath, source, source_relpath in candidates:
            destination = archive_root / source_relpath
            if os.path.islink(archive_root) or not archive_root.is_dir():
                print(f"warning: archive directory changed before move: {relpath.as_posix()}")
                skipped += 1
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            resolved_destination = destination.resolve()
            if (
                os.path.islink(archive_root)
                or not archive_root.is_dir()
                or not resolved_destination.is_relative_to(archive_root.resolve())
                or not resolved_destination.is_relative_to(resolved_root)
            ):
                print(f"warning: archive destination is outside the project: {relpath.as_posix()}")
                skipped += 1
                continue
            try:
                os.link(source, destination)
            except FileExistsError:
                print(f"warning: archive destination already exists: {destination}")
                skipped += 1
                continue
            try:
                source.unlink()
            except OSError:
                destination.unlink(missing_ok=True)
                raise
            _remove_empty_source_parents(source, resolved_root)
            moved += 1
    print(f"archive: moved {moved} files")
    print(f"archive: skipped {skipped} files")
    return 0


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

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("path")
    install_parser.add_argument("--claude-skill", action="store_true")
    install_parser.add_argument(
        "--harness", choices=("auto", "claude", "agents"), default="auto"
    )

    def install_handler(args: argparse.Namespace) -> int:
        from .install import install

        return install(
            Path(args.path),
            claude_skill=args.claude_skill,
            harness=args.harness,
        )

    install_parser.set_defaults(handler=install_handler)

    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("path")

    def update_handler(args: argparse.Namespace) -> int:
        from .install import update

        return update(Path(args.path))

    update_parser.set_defaults(handler=update_handler)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the vizzer CLI and return a process exit code."""
    parser = _parser()
    if argv is None and not sys.argv[1:]:
        from .install import detect, install

        target_text = input("Project path [.]: ").strip()
        target = Path(target_text or ".")
        print(json.dumps(detect(target), indent=2, sort_keys=True))
        if input("Install vizzer? [y/N] ").strip().lower() not in {"y", "yes"}:
            print("install: cancelled")
            return 1
        return install(target)

    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    return args.handler(args)
