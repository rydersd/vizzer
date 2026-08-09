"""Command-line interface for synchronizing and rendering project work graphs."""
from __future__ import annotations

import argparse
import http.server
import json
import os
import secrets
import tempfile
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .adapters import get_adapters
from .config import Config, ConfigError
from .model import Graph
from .progress_history import ProgressHistory, prepare_progress_history
from .reconcile import build_graph
from .render import render_all
from .planning import (
    PlanningError, StaleRevisionError, analyze_change, apply_change,
    read_overlay, restore_overlay, undo_change, validate_state,
)


GRAPH_RELPATH = Path("vizzer/vizzer-graph.json")


# codex-sequence-2026-08-08: source opening is graph-id-only and root-contained.
def _resolve_item_source(root: Path, graph: Graph, item_id: str) -> tuple[Path | None, str]:
    """Resolve an existing regular source file for an item in *graph*.

    Never accept a caller-provided pathname.  Graph JSON is user-editable too,
    so it is still untrusted: absolute paths, traversal, and symlinks leaving
    the project are all rejected after resolution.
    """
    item = graph.item_map().get(item_id)
    if item is None:
        return None, "unknown item"
    raw_path = item.source.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None, "item has no source file"
    try:
        relative = Path(raw_path)
        if relative.is_absolute():
            return None, "source path is not relative"
        project_root = root.resolve()
        source = (project_root / relative).resolve()
        source.relative_to(project_root)
    except (OSError, ValueError):
        return None, "source path is outside the project"
    if not source.is_file():
        return None, "source file is unavailable"
    return source, ""


def _opener_args(source: Path) -> list[str]:
    """Return the default-app opener command without involving a shell."""
    return (["open", str(source)] if sys.platform == "darwin"
            else ["xdg-open", str(source)])


def _open_source(source: Path) -> None:
    subprocess.run(_opener_args(source), check=True)


def _open_browser(url: str) -> None:
    """Open the loopback constellation URL in the system web browser."""
    command = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.run([command, url], check=True)


def _open_item(root: Path, item_id: str) -> int:
    graph = _read_graph(root)
    if graph is None:
        print("open: run 'sync' first")
        return 2
    source, error = _resolve_item_source(root, graph, item_id)
    if source is None:
        print(f"open: {error}")
        return 2
    try:
        _open_source(source)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"open: could not launch source file: {exc}")
        return 2
    return 0


def _serve_handler(root: Path, graph: Graph, views: Path, cfg: Config,
                   csrf_token: str):
    """Build a static loopback handler with an item-ID-only open endpoint."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(views), **kwargs)

        def log_message(self, format, *args):  # pragma: no cover - keeps CLI quiet
            return

        def _send_json(self, status: int, body: dict) -> None:
            payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _same_origin(self) -> bool:
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin", "")
            hostname = host.rsplit(":", 1)[0].strip("[]").lower()
            return (
                hostname in {"127.0.0.1", "localhost", "::1"}
                and origin == f"http://{host}"
                and self.headers.get("X-Vizzer-CSRF", "") == csrf_token
            )

        def _read_json_body(self) -> dict:
            raw_length = self.headers.get("Content-Length", "")
            try:
                length = int(raw_length)
            except ValueError:
                raise PlanningError("request needs a valid Content-Length") from None
            if length <= 0 or length > 65536:
                raise PlanningError("planning request body must be 1..65536 bytes")
            if self.headers.get_content_type() != "application/json":
                raise PlanningError("planning request must be application/json")
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                raise PlanningError("planning request is malformed JSON") from None
            if not isinstance(value, dict):
                raise PlanningError("planning request must be a JSON object")
            return value

        def _planning_post(self, action: str) -> None:
            if not self._same_origin():
                self._send_json(403, {"error": "same-origin CSRF check failed"})
                return
            try:
                built = _build_fresh_graph(root, "plan")
                if built is None:
                    self._send_json(500, {"error": "current work graph could not be built"})
                    return
                live_cfg, live_graph, _ = built
                if not bool(live_cfg.get("planning.enabled", False)):
                    self._send_json(404, {"error": "planning is disabled"})
                    return
                body = self._read_json_body()
                state = validate_state(body.get("state"), live_graph)
                analysis = analyze_change(live_graph, live_cfg, root, state)
                if action == "analyze":
                    self._send_json(200, {"analysis": analysis})
                    return
                expected = body.get("expectedRevision")
                if isinstance(expected, bool) or not isinstance(expected, int):
                    raise PlanningError("expectedRevision must be an integer")
                previous, _ = read_overlay(live_cfg, root, live_graph)
                overlay = apply_change(
                    live_graph, live_cfg, root, state, expected_revision=expected,
                    rationale=body.get("rationale", ""), analysis=analysis,
                )
                if _refresh(root) != 0:
                    restore_overlay(live_cfg, root, previous)
                    self._send_json(500, {
                        "error": "course was not accepted because derived views could not refresh",
                        "revision": previous["revision"],
                    })
                    return
                self._send_json(200, {
                    "overlay": overlay, "analysis": analysis, "reloadRequired": True,
                })
            except StaleRevisionError as exc:
                self._send_json(409, {"error": str(exc)})
            except PlanningError as exc:
                self._send_json(400, {"error": str(exc)})

        def do_POST(self):
            parsed = urlsplit(self.path)
            if not parsed.query and parsed.path in {
                "/api/plan/analyze", "/api/plan/apply"
            }:
                self._planning_post(parsed.path.rsplit("/", 1)[1])
                return
            prefix = "/api/open/"
            if parsed.query or not parsed.path.startswith(prefix):
                self._send_json(404, {"error": "not found"})
                return
            item_id = unquote(parsed.path[len(prefix):])
            if not item_id:
                self._send_json(404, {"error": "not found"})
                return
            source, error = _resolve_item_source(root, graph, item_id)
            if source is None:
                self._send_json(404, {"error": error})
                return
            try:
                _open_source(source)
            except (OSError, subprocess.SubprocessError):
                self._send_json(500, {"error": "could not open source"})
                return
            self._send_json(200, {"opened": item_id})

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/api/plan" and not parsed.query:
                built = _build_fresh_graph(root, "plan")
                if built is None:
                    self._send_json(500, {"error": "current work graph could not be built"})
                    return
                live_cfg, live_graph, _ = built
                if not bool(live_cfg.get("planning.enabled", False)):
                    self._send_json(404, {"error": "planning is disabled"})
                    return
                try:
                    overlay, _ = read_overlay(live_cfg, root, live_graph)
                except PlanningError as exc:
                    self._send_json(500, {"error": str(exc)})
                    return
                self._send_json(200, {"csrfToken": csrf_token, "overlay": overlay})
                return
            if parsed.path.startswith("/api/open/"):
                self._send_json(405, {"error": "POST required"})
                return
            # codex-sequence-2026-08-08: the human entry point is the map, not
            # a raw directory listing that looks like Vizzer failed to load.
            if parsed.path == "/" and not parsed.query:
                self.send_response(302)
                self.send_header("Location", "/constellation.html")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            super().do_GET()

    return Handler


def _make_serve_server(root: Path, graph: Graph, views: Path, port: int,
                       cfg: Config | None = None, csrf_token: str | None = None):
    cfg = cfg or _load_config(root, "serve")
    if cfg is None:
        raise OSError("could not load Vizzer configuration")
    return http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), _serve_handler(
            root, graph, views, cfg, csrf_token or secrets.token_urlsafe(32)
        )
    )


def _serve(root: Path, port: int, open_browser: bool = False) -> int:
    if not 0 <= port <= 65535:
        print("serve: port must be between 0 and 65535")
        return 2
    graph = _read_graph(root)
    if graph is None:
        print("serve: run 'sync' and 'render' first")
        return 2
    cfg = _load_config(root, "serve")
    if cfg is None:
        return 2
    views = _output_dir(cfg, root, "serve")
    if views is None or not views.is_dir():
        print("serve: run 'render' first")
        return 2
    try:
        server = _make_serve_server(root, graph, views, port, cfg)
    except OSError as exc:
        print(f"serve: could not bind loopback server: {exc}")
        return 2
    host, actual_port = server.server_address[:2]
    url = f"http://{host}:{actual_port}/constellation.html"
    print(f"serve: {url}", flush=True)
    if open_browser:
        try:
            _open_browser(url)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"serve: could not open browser: {exc}")
            server.server_close()
            return 2
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("serve: stopped")
    finally:
        server.server_close()
    return 0


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


def _output_dir(cfg: Config, root: Path, command: str = "render") -> Path | None:
    value = cfg.get("render.output_dir", "vizzer/views")
    try:
        resolved_root = root.resolve()
        resolved_output = (resolved_root / Path(value)).resolve()
    except (OSError, TypeError, ValueError):
        print(f"{command}: invalid output_dir {value!r}")
        return None
    if not resolved_output.is_relative_to(resolved_root):
        print(f"{command}: output_dir {value!r} is outside the project")
        return None
    return resolved_output


def _load_config(root: Path, command: str) -> Config | None:
    try:
        return Config.load(root)
    except (ConfigError, OSError, UnicodeError) as exc:
        print(f"{command}: configuration error: {exc}")
        return None


def _build_fresh_graph(root: Path, command: str) -> tuple[Config, Graph, ProgressHistory] | None:
    """Load config and build a graph before writing any derived artifact."""
    cfg = _load_config(root, command)
    if cfg is None:
        return None
    try:
        graph = _build(cfg, root)
    # Adapters are project extensions.  A broken adapter must make the command
    # fail cleanly, rather than emit a traceback after possibly doing work.
    except Exception as exc:
        print(f"{command}: sync failed: {exc}")
        return None
    progress = prepare_progress_history(graph, cfg, root)
    return cfg, graph, progress


def _artifact_temp_path(parent: Path, prefix: str) -> Path:
    """Reserve a same-directory path for an atomic artifact write."""
    fd, name = tempfile.mkstemp(prefix=prefix, dir=str(parent))
    os.close(fd)
    path = Path(name)
    path.unlink()
    return path


def _write_artifacts(entries: list[tuple[Path, str]], command: str) -> bool:
    """Commit several files as one recoverable snapshot.

    All content is prepared before any destination is replaced.  Existing
    files are moved to same-directory backups, and a failed replacement rolls
    every already-moved destination back.  This keeps refresh from publishing
    a graph or view set that is only half new.
    """
    staged: list[tuple[Path, Path]] = []
    records: list[tuple[Path, Path | None, bool]] = []
    try:
        seen: set[Path] = set()
        for target, content in entries:
            target = Path(target)
            if target in seen:
                raise OSError(f"duplicate artifact path: {target}")
            seen.add(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = _artifact_temp_path(target.parent, f".{target.name}.")
            try:
                temporary.write_text(content, encoding="utf-8")
            except BaseException:
                with suppress(OSError):
                    temporary.unlink()
                raise
            staged.append((temporary, target))

        for temporary, target in staged:
            backup = None
            if target.exists() or target.is_symlink():
                backup = _artifact_temp_path(target.parent, f".{target.name}.bak.")
                os.replace(target, backup)
            record = [target, backup, False]
            records.append(record)  # type: ignore[arg-type]
            os.replace(temporary, target)
            record[2] = True
        for _, backup, _ in records:
            if backup is not None:
                with suppress(OSError):
                    backup.unlink()
    except Exception as exc:
        # Reverse order matters when a caller supplied nested paths.
        for target, backup, installed in reversed(records):
            if installed and (target.exists() or target.is_symlink()):
                with suppress(OSError):
                    target.unlink()
            if backup is not None and backup.exists():
                with suppress(OSError):
                    os.replace(backup, target)
        for temporary, _ in staged:
            with suppress(OSError):
                temporary.unlink()
        print(f"{command}: could not write derived artifacts: {exc}")
        return False
    return True


def _write_graph(root: Path, graph: Graph, progress: ProgressHistory, command: str) -> bool:
    entries = [(root / GRAPH_RELPATH, graph.dumps())]
    if progress.path is not None and progress.content is not None:
        entries.append((progress.path, progress.content))
    return _write_artifacts(entries, command)


def _report_sync(cfg: Config, graph: Graph, root: Path, command: str) -> None:

    print(
        f"{command}: {len(graph.items)} items, {len(graph.groups)} groups, "
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


def _sync(root: Path) -> int:
    result = _build_fresh_graph(root, "sync")
    if result is None:
        return 2
    cfg, graph, progress = result
    if not _write_graph(root, graph, progress, "sync"):
        return 2
    _report_sync(cfg, graph, root, "sync")
    return 0


def _render_graph(cfg: Config, graph: Graph, root: Path, only_value: str | None,
                  command: str) -> int:
    output_dir = _output_dir(cfg, root, command)
    if output_dir is None:
        return 2
    only = None
    if only_value is not None:
        only = {name.strip() for name in only_value.split(",") if name.strip()}
    try:
        rendered = render_all(graph, cfg, root, only=only)
    except Exception as exc:
        print(f"{command}: {exc}")
        return 2

    entries = []
    for filename, content in rendered.items():
        relative = Path(filename)
        if relative.is_absolute() or ".." in relative.parts:
            print(f"{command}: renderer returned unsafe output path {filename!r}")
            return 2
        entries.append((output_dir / relative, content))
    if not _write_artifacts(entries, command):
        return 2
    print(f"{command}: wrote {len(rendered)} files")
    return 0


def _render(root: Path, only_value: str | None) -> int:
    graph = _read_graph(root)
    if graph is None:
        print("render: run 'sync' first")
        return 2
    cfg = _load_config(root, "render")
    if cfg is None:
        return 2
    return _render_graph(cfg, graph, root, only_value, "render")


# codex-sequence-2026-08-08: refresh never delegates to disk-reading render.
def _refresh(root: Path) -> int:
    """Synchronize then render the graph built in this invocation.

    Deliberately do not call ``_render``: it reads the last on-disk graph, so a
    failed sync could otherwise render stale state and falsely look current.
    """
    result = _build_fresh_graph(root, "refresh")
    if result is None:
        return 2
    cfg, graph, progress = result
    output_dir = _output_dir(cfg, root, "refresh")
    if output_dir is None:
        return 2
    try:
        rendered = render_all(graph, cfg, root)
    except Exception as exc:
        print(f"refresh: {exc}")
        return 2
    entries = [(root / GRAPH_RELPATH, graph.dumps())]
    if progress.path is not None and progress.content is not None:
        entries.append((progress.path, progress.content))
    for filename, content in rendered.items():
        relative = Path(filename)
        if relative.is_absolute() or ".." in relative.parts:
            print(f"refresh: renderer returned unsafe output path {filename!r}")
            return 2
        entries.append((output_dir / relative, content))
    if not _write_artifacts(entries, "refresh"):
        return 2
    _report_sync(cfg, graph, root, "refresh")
    print(f"refresh: wrote {len(rendered)} files")
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

    cfg = _load_config(root, "check")
    if cfg is None:
        return 2
    output_dir = _output_dir(cfg, root, "check")
    if output_dir is None:
        return 2
    try:
        expected_graph = _build(cfg, root)
        progress = prepare_progress_history(expected_graph, cfg, root)
        expected_views = render_all(expected_graph, cfg, root)
    except Exception as exc:
        print(f"check: could not build current graph: {exc}")
        return 2
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

    if progress.path is not None:
        try:
            history_relpath = progress.path.relative_to(root.resolve()).as_posix()
        except ValueError:
            print("check: progress history path is outside the project")
            return 2
        try:
            actual_history = progress.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            stale.add(history_relpath)
        else:
            if progress.content is None or actual_history != progress.content:
                stale.add(history_relpath)

    for filename, expected in expected_views.items():
        if structural and filename in {
            "manifest.json",
            "constellation.html",
            "ledger-table.md",
        }:
            continue
        path = output_dir / filename
        try:
            actual = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            stale.add(path.relative_to(root).as_posix())
            continue
        if actual != expected:
            stale.add(path.relative_to(root).as_posix())

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

    cfg = _load_config(root, "archive")
    if cfg is None:
        return 2
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


def _course_state_from_args(current: dict, args: argparse.Namespace) -> dict:
    """Apply concise CLI edits to the current full course state."""
    state = {key: list(current[key]) for key in ("promote", "defer", "order")}
    for item_id in args.promote or []:
        if item_id not in state["promote"]:
            state["promote"].append(item_id)
        if item_id in state["defer"]:
            state["defer"].remove(item_id)
    for item_id in args.defer or []:
        if item_id not in state["defer"]:
            state["defer"].append(item_id)
        if item_id in state["promote"]:
            state["promote"].remove(item_id)
    if args.order is not None:
        state["order"] = list(args.order)
    if getattr(args, "clear_order", False):
        state["order"] = []
    return state


def _plan(root: Path, args: argparse.Namespace) -> int:
    built = _build_fresh_graph(root, "plan")
    if built is None:
        return 2
    cfg, graph, _ = built
    if not bool(cfg.get("planning.enabled", False)):
        print("plan: enable [planning] enabled = true first")
        return 2
    try:
        current, _ = read_overlay(cfg, root, graph)
        if args.plan_action == "undo":
            overlay = undo_change(
                graph, cfg, root, expected_revision=args.expected_revision,
                rationale=args.rationale,
            )
            if _refresh(root) != 0:
                restore_overlay(cfg, root, current)
                print("plan: undo was rolled back because derived views could not refresh")
                return 2
            print(json.dumps({"overlay": overlay}, indent=2, ensure_ascii=False))
            return 0
        state = validate_state(_course_state_from_args(current["state"], args), graph)
        analysis = analyze_change(graph, cfg, root, state)
        if args.plan_action == "analyze":
            print(json.dumps(analysis, indent=2, ensure_ascii=False))
            return 0
        previous = current
        overlay = apply_change(
            graph, cfg, root, state,
            expected_revision=args.expected_revision,
            rationale=args.rationale,
            analysis=analysis,
        )
        if _refresh(root) != 0:
            restore_overlay(cfg, root, previous)
            print("plan: course was rolled back because derived views could not refresh")
            return 2
        print(json.dumps({"overlay": overlay, "analysis": analysis},
                         indent=2, ensure_ascii=False))
        return 0
    except StaleRevisionError as exc:
        print(f"plan: {exc}")
        return 3
    except PlanningError as exc:
        print(f"plan: {exc}")
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

    refresh = subparsers.add_parser(
        "refresh",
        help="re-read sources and regenerate all views from the newly built graph",
    )
    refresh.add_argument("--root", default=".")
    refresh.set_defaults(handler=lambda args: _refresh(Path(args.root)))

    open_parser = subparsers.add_parser("open", help="open an item's canonical source file")
    open_parser.add_argument("item_id")
    open_parser.add_argument("--root", default=".")
    open_parser.set_defaults(handler=lambda args: _open_item(Path(args.root), args.item_id))

    serve = subparsers.add_parser("serve", help="serve views on loopback with safe source opening")
    serve.add_argument("--root", default=".")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument(
        "--open-browser", action="store_true",
        help="open the constellation after the loopback helper starts",
    )
    serve.set_defaults(handler=lambda args: _serve(
        Path(args.root), args.port, args.open_browser
    ))

    check = subparsers.add_parser("check")
    check.add_argument("--root", default=".")
    check.add_argument("--structural", action="store_true")
    check.set_defaults(handler=lambda args: _check(Path(args.root), args.structural))

    archive = subparsers.add_parser("archive")
    archive.add_argument("--root", default=".")
    archive.add_argument("--yes", action="store_true")
    archive.set_defaults(handler=lambda args: _archive(Path(args.root), args.yes))

    plan = subparsers.add_parser(
        "plan", help="analyze or accept an owner-authored course change"
    )
    plan_subparsers = plan.add_subparsers(dest="plan_action", required=True)

    def course_arguments(command, *, applying: bool = False) -> None:
        command.add_argument("--root", default=".")
        command.add_argument("--promote", action="append", metavar="ITEM")
        command.add_argument("--defer", action="append", metavar="ITEM")
        command.add_argument("--order", action="append", metavar="ITEM")
        command.add_argument("--clear-order", action="store_true")
        if applying:
            command.add_argument("--expected-revision", type=int, required=True)
            command.add_argument("--rationale", required=True)
        command.set_defaults(handler=lambda args: _plan(Path(args.root), args))

    plan_analyze = plan_subparsers.add_parser(
        "analyze", help="show dependency and opportunity-cost effects without writing"
    )
    course_arguments(plan_analyze)
    plan_apply = plan_subparsers.add_parser(
        "apply", help="write an accepted course after analysis"
    )
    course_arguments(plan_apply, applying=True)
    plan_undo = plan_subparsers.add_parser(
        "undo", help="restore the prior accepted course as a new audited revision"
    )
    plan_undo.add_argument("--root", default=".")
    plan_undo.add_argument("--expected-revision", type=int, required=True)
    plan_undo.add_argument("--rationale", required=True)
    plan_undo.set_defaults(handler=lambda args: _plan(Path(args.root), args))

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
