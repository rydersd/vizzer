"""Command-line interface for synchronizing and rendering project work graphs."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
import hashlib
import http.server
import json
import os
import secrets
import stat as stat_module
import tempfile
import subprocess
import sys
import dataclasses
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:  # Unix gets cross-process exclusion; other platforms retain process safety.
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

from .story_edits import read_edit, save_edit, StoryEditConflict
from .adapters import get_adapters
from . import (
    RenderIdError, __version__, process_render_id, process_render_id_reason,
    read_marker, render_id,
)
from .activity import (
    GRANDFATHER_RELPATH,
    answered_blocker_records,
    load_grandfathered_blockers,
    unresolved_blocker_records,
)
from .config import Config, ConfigError
from .developer_store import ensure_developer_store, prepare_developer_store
from .decision_journal import (
    DecisionJournalError, append_application_event, append_evolution_events,
    append_superseded_events, restore_story_snapshots, story_snapshots,
)
from .discussion_queue import (
    DiscussionQueueConflict, DiscussionQueueError, enqueue_discussion,
    discussion_queue_snapshot, read_discussion_queue, restore_discussion_queue,
)
from .model import Graph, owner_question_fingerprint
from .progress_history import ProgressHistory, prepare_progress_history
from .reconcile import build_graph
from .render import render_all
from .render.velocity import stage_merge_ledger
from .planning import (
    PlanningError, StaleRevisionError, analyze_change, apply_change,
    read_overlay, restore_overlay, undo_change, validate_state,
)
from .question_answers import (
    QuestionAnswerConflict, QuestionAnswerError, QuestionNotFoundError,
    answers_path, current_questions_and_decisions, decision_to_api,
    prepare_answers, question_to_api, read_answers, superseded_answers,
    superseded_to_api, write_answers,
)
from .question_aging import overdue_warning_lines, question_ages
from .review_contract import ReviewContractError
from .review_service import (
    ReviewServiceError, append_review_event, load_review_plans, review_state,
)
from .serve_extensions import SERVE_EXTENSIONS, ServeRequestContext
from .workstreams import (
    WorkstreamConflict, WorkstreamError, append_discussion, apply_workstreams,
    heartbeat_session, load_workstream_overlay, read_runtime, read_workstreams, restore_runtime,
    restore_workstreams, start_session, stop_session,
)


GRAPH_RELPATH = Path("vizzer/vizzer-graph.json")
_PROCESS_MUTATION_LOCK = threading.RLock()
_CAPTURED_AT_IMPORT = process_render_id()


def _serve_version_error(root: Path) -> str | None:
    """Explain when a long-running server no longer matches its installation."""
    running = process_render_id()
    if running is None:
        return (
            "Vizzer could not verify the engine this process is running: "
            f"{process_render_id_reason()}. Restart vizzer serve"
        )
    if not (root / "vizzer/engine/vizzer").is_dir():
        return None
    try:
        on_disk = render_id(root)
    except RenderIdError as exc:
        return f"Vizzer could not identify the installed engine: {exc}"
    marker = read_marker(root)
    if marker is None:
        return "vizzer/RENDER_ID is missing or malformed; run vizzer update"
    if marker.render_id != on_disk:
        return "the installed engine changed without updating vizzer/RENDER_ID"
    if on_disk != running:
        return (
            f"Vizzer server {running} is out of date; installed render ID is "
            f"{on_disk}. Restart vizzer serve"
        )
    return None


# Background derived-view refresh. An accepted answer is durable the moment
# its ledger entry is written; regenerating the derived views takes seconds to
# tens of seconds and must neither block the owner's click nor ever roll the
# answer back. One daemon worker per root, collapsing: N schedules while busy
# run one refresh over the latest state.
# Delays before retrying a failed background refresh (review 2026-09-25: a
# failed refresh left the views behind the answers until someone noticed).
# The last delay repeats until a refresh succeeds.
_REFRESH_RETRY_DELAYS = (30.0, 120.0, 600.0)
# ``_background_refresh_once`` result: a write overtook the build, or the
# refresh journaled a story note, so run again over the new state.
_REFRESH_RERUN = 1


class _RefreshWorker:
    """One collapsing refresh thread per project root, with retry state."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.pending = threading.Event()
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.failures = 0
        self.error: str | None = None
        self.failed_at: str | None = None
        self.next_retry: float | None = None  # time.monotonic()
        self.next_retry_at: str | None = None
        self.reason: str | None = None  # set by the failing refresh
        # When the views were first seen behind the ledger (ISO, UTC).
        self.behind_since: str | None = None

    def failure(self) -> dict | None:
        with self.lock:
            if not self.failures:
                return None
            return {"error": self.error, "failedAt": self.failed_at,
                    "attempts": self.failures, "nextRetryAt": self.next_retry_at}

    def views_behind_since(self, behind: bool) -> str | None:
        with self.lock:
            if not behind:
                self.behind_since = None
            elif self.behind_since is None:
                self.behind_since = _utc_now()
            return self.behind_since


_REFRESH_WORKERS: dict[Path, _RefreshWorker] = {}
_REFRESH_WORKERS_GUARD = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _refresh_worker(root: Path) -> _RefreshWorker:
    key = root.resolve()
    with _REFRESH_WORKERS_GUARD:
        worker = _REFRESH_WORKERS.get(key)
        if worker is None:
            worker = _REFRESH_WORKERS[key] = _RefreshWorker(root)
        return worker


# Bumped on every exit from ``_mutation_guard`` in this process. With the
# stored graph's and the answer ledger's mtimes it tells the background
# refresh whether anything was written while it was building without the lock
# (the ledger covers a writer in another process).
_MUTATION_GENERATION = 0


def _refresh_state_token(root: Path, cfg: Config) -> tuple:
    def mtime(path: Path) -> int | None:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None
    return (_MUTATION_GENERATION, mtime(root / GRAPH_RELPATH),
            mtime(answers_path(cfg, root)))


def _refresh_failed(root: Path, reason: str) -> int:
    _refresh_worker(root).reason = reason
    return 2


def _journal_superseded_answers(cfg: Config, graph: Graph, root: Path) -> list[Path]:
    """Append a "superseded" note for each answered question since reworded.

    Returns the story files changed. Never fails the refresh: a note that
    cannot be written is reported and retried by the next refresh.
    """
    try:
        ledger, _ = read_answers(cfg, root, strict=False)
        if ledger is None:
            return []
        superseded = [
            (decision, next(owner_question_fingerprint(question)
                            for question in graph.owner_questions
                            if question.id == decision.question.id))
            for decision in superseded_answers(graph.owner_questions, ledger)
        ]
        if not superseded:
            return []
        return append_superseded_events(
            graph, root, superseded, datetime.now(timezone.utc).date().isoformat())
    except (DecisionJournalError, OSError, UnicodeError, QuestionAnswerError) as exc:
        print(f"refresh: could not note a superseded answer: {exc}")
        return []


def _background_refresh_once(root: Path) -> int:
    """Rebuild the derived views without holding the mutation lock.

    A full rebuild takes 5-20 s on a large project; while it held the lock
    every answer POST queued behind it, long enough for a browser to give up. The build and render only
    READ, so they run unlocked; the lock is taken just to write. If anything
    was written while building, the result is stale: it is discarded and
    ``_REFRESH_RERUN`` asks the loop to run again, so the views always end up
    matching the latest state. Returns 0, ``_REFRESH_RERUN``, or 2 (failed;
    the reason is on the root's worker).
    """
    cfg = _load_config(root, "refresh")
    if cfg is None:
        return _refresh_failed(root, "could not load the vizzer configuration")
    token = _refresh_state_token(root, cfg)
    built = _build_fresh_graph(root, "refresh")
    if built is None:
        return _refresh_failed(root, "could not rebuild the work graph (see the serve log)")
    cfg, graph, progress = built
    prepared = _refresh_entries(root, cfg, graph, progress)
    if prepared is None:
        return _refresh_failed(root, "could not render the views (see the serve log)")
    entries, _ = prepared
    with _mutation_guard(root):
        if _refresh_state_token(root, cfg) != token:
            return _REFRESH_RERUN
        if _journal_superseded_answers(cfg, graph, root):
            # A story changed under this build: rebuild so the graph has it.
            return _REFRESH_RERUN
        _prepare_developer_store(cfg, graph, root)
        failures: list[str] = []
        if not _write_artifacts(entries, "refresh", failures):
            return _refresh_failed(
                root, "could not write derived artifacts: "
                + (failures[0] if failures else "see the serve log"))
    _report_sync(cfg, graph, root, "refresh")
    return 0


def _background_refresh_loop(worker: _RefreshWorker) -> None:
    """Run refreshes as they are scheduled; retry a failure with backoff.

    An accepted answer is already durable before any refresh runs, so a
    failure here only leaves the derived views behind. Each retry is logged,
    and ``GET /api/questions`` reports the failure so the page can say so.
    """
    while True:
        with worker.lock:
            retry = worker.next_retry
        timeout = None if retry is None else max(0.0, retry - time.monotonic())
        worker.pending.wait(timeout)
        worker.pending.clear()
        with worker.lock:
            attempt = worker.failures + 1
        if attempt > 1:
            print(f"serve: view refresh attempt {attempt} (retrying after failure)",
                  file=sys.stderr, flush=True)
        worker.reason = None
        try:
            code = _background_refresh_once(worker.root)
        except Exception as exc:  # never kill the worker: views are derived
            code, worker.reason = 2, f"refresh crashed: {exc}"
        if code == _REFRESH_RERUN:
            worker.pending.set()
            continue
        if code == 0:
            with worker.lock:
                recovered = worker.failures
                worker.failures, worker.error, worker.failed_at = 0, None, None
                worker.next_retry = worker.next_retry_at = None
            if recovered:
                print(f"serve: view refresh succeeded on attempt {attempt}; "
                      "views match the answers again", file=sys.stderr, flush=True)
            continue
        with worker.lock:
            worker.failures += 1
            delay = _REFRESH_RETRY_DELAYS[
                min(worker.failures, len(_REFRESH_RETRY_DELAYS)) - 1]
            worker.error = worker.reason or f"refresh exited with status {code}"
            worker.failed_at = _utc_now()
            worker.next_retry = time.monotonic() + delay
            worker.next_retry_at = datetime.fromtimestamp(
                time.time() + delay, timezone.utc).isoformat(timespec="seconds")
            error = worker.error
        print(f"serve: view refresh FAILED (attempt {attempt}): {error} — the "
              f"answers are already committed; retrying in {delay:g}s",
              file=sys.stderr, flush=True)


def _schedule_background_refresh(root: Path) -> None:
    worker = _refresh_worker(root)
    with _REFRESH_WORKERS_GUARD:
        if worker.thread is None or not worker.thread.is_alive():
            worker.thread = threading.Thread(
                target=_background_refresh_loop, args=(worker,),
                name="vizzer-derived-refresh", daemon=True,
            )
            worker.thread.start()
    worker.pending.set()


@contextmanager
def _mutation_guard(root: Path):
    """Serialize accepted owner mutations across threads and, on Unix, processes."""
    with _PROCESS_MUTATION_LOCK:
        digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:24]
        lock_path = Path(tempfile.gettempdir()) / f"vizzer-mutation-{digest}.lock"
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            global _MUTATION_GENERATION
            _MUTATION_GENERATION += 1
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


# codex-sequence-2026-08-08: source opening is graph-id-only and root-contained.
def _resolve_item_source(root: Path, graph: Graph, item_id: str) -> tuple[Path | None, str]:
    """Resolve an existing regular source file for an item or group in *graph*.

    Never accept a caller-provided pathname.  Graph JSON is user-editable too,
    so it is still untrusted: absolute paths, traversal, and symlinks leaving
    the project are all rejected after resolution.
    """
    item = graph.item_map().get(item_id)
    if item is not None:
        source_meta = item.source
    else:
        group = next((entry for entry in graph.groups if entry.id == item_id), None)
        if group is None:
            return None, "unknown item"
        source_meta = group.meta.get("source", {})
    raw_path = source_meta.get("path") if isinstance(source_meta, dict) else None
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

        def guess_type(self, path):
            media_type = super().guess_type(path)
            if media_type.startswith("text/"):
                return f"{media_type}; charset=utf-8"
            return media_type

        def log_message(self, format, *args):  # pragma: no cover - keeps CLI quiet
            return

        def end_headers(self):
            if not any(header.lower().startswith(b"cache-control:")
                       for header in getattr(self, "_headers_buffer", [])):
                self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _send_json(self, status: int, body: dict) -> None:
            payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_bytes(self, status: int, payload: bytes, media_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", media_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Disposition", "inline")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _extension_context(self) -> ServeRequestContext:
            return ServeRequestContext(
                root=root,
                cfg=cfg,
                graph=graph,
                csrf_token=csrf_token,
                current_engine=self._require_current_engine,
                same_origin=self._same_origin,
                read_json=self._read_json_body,
                mutation_guard=lambda: _mutation_guard(root),
                send_json=self._send_json,
                send_bytes=self._send_bytes,
            )

        def _loopback_host(self) -> bool:
            host = self.headers.get("Host", "")
            hostname = host.rsplit(":", 1)[0].strip("[]").lower()
            return hostname in {"127.0.0.1", "localhost", "::1"}

        def _same_origin(self) -> bool:
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin", "")
            return (
                self._loopback_host()
                and origin == f"http://{host}"
                and self.headers.get("X-Vizzer-CSRF", "") == csrf_token
            )

        def _require_current_engine(self) -> bool:
            error = _serve_version_error(root)
            if error is None:
                return True
            self._send_json(409, {
                "error": error,
                "runningEngineVersion": __version__,
                "renderId": process_render_id(),
            })
            return False

        def _read_json_body(self, subject: str = "planning",
                            maximum: int = 65536) -> dict:
            raw_length = self.headers.get("Content-Length", "")
            try:
                length = int(raw_length)
            except ValueError:
                raise QuestionAnswerError(
                    "request needs a valid Content-Length"
                ) from None
            if (isinstance(maximum, bool) or not isinstance(maximum, int)
                    or maximum <= 0):
                raise QuestionAnswerError("request byte budget is invalid")
            if length <= 0 or length > maximum:
                raise QuestionAnswerError(
                    f"{subject} request body must be 1..{maximum} bytes"
                )
            if self.headers.get_content_type() != "application/json":
                raise QuestionAnswerError(
                    f"{subject} request must be application/json"
                )
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                raise QuestionAnswerError(
                    f"{subject} request is malformed JSON"
                ) from None
            if not isinstance(value, dict):
                raise QuestionAnswerError(
                    f"{subject} request must be a JSON object"
                )
            return value

        def _planning_post(self, action: str) -> None:
            if not self._require_current_engine():
                return
            if not self._same_origin():
                self._send_json(403, {"error": "same-origin CSRF check failed"})
                return
            try:
                if action == "apply":
                    with _mutation_guard(root):
                        self._planning_post_inner(action)
                else:
                    self._planning_post_inner(action)
            except StaleRevisionError as exc:
                self._send_json(409, {"error": str(exc)})
            except (PlanningError, QuestionAnswerError) as exc:
                self._send_json(400, {"error": str(exc)})
            except OSError as exc:
                self._send_json(500, {"error": f"could not lock planning mutation: {exc}"})

        def _planning_post_inner(self, action: str) -> None:
            try:
                built = _build_fresh_graph(root, "plan")
                if built is None:
                    self._send_json(500, {"error": "current work graph could not be built"})
                    return
                live_cfg, live_graph, _ = built
                if not bool(live_cfg.get("planning.enabled", False)):
                    self._send_json(404, {"error": "planning is disabled"})
                    return
                body = self._read_json_body("planning")
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
                raise exc
            except (PlanningError, QuestionAnswerError) as exc:
                raise exc

        def _discussion_queue_post(self) -> None:
            if not self._require_current_engine():
                return
            if not self._same_origin():
                self._send_json(403, {"error": "same-origin CSRF check failed"})
                return
            try:
                body = self._read_json_body("discussion queue")
                required = {"expectedRevision", "provider", "storyId", "questions"}
                allowed = required | {"request"}
                missing = sorted(required - set(body))
                unknown = sorted(set(body) - allowed)
                if missing or unknown:
                    field = (missing or unknown)[0]
                    raise DiscussionQueueError(
                        f"discussion queue request has unknown or missing field: {field}"
                    )
                expected = body["expectedRevision"]
                if isinstance(expected, bool) or not isinstance(expected, int):
                    raise DiscussionQueueError("expectedRevision must be an integer")
                with _mutation_guard(root):
                    built = _build_fresh_graph(root, "discussion queue")
                    if built is None:
                        self._send_json(500, {"error": "current work graph could not be built"})
                        return
                    live_cfg, live_graph, _ = built
                    previous = discussion_queue_snapshot(live_cfg, root, live_graph)
                    queue, changed = enqueue_discussion(
                        live_cfg, root, live_graph,
                        provider=body["provider"], story_id=body["storyId"],
                        questions=body["questions"], request=body.get("request"),
                        expected_revision=expected,
                    )
                    if changed and _refresh(root) != 0:
                        restore_discussion_queue(live_cfg, root, previous)
                        self._send_json(500, {
                            "error": "discussion was not queued because derived views could not refresh",
                            "revision": 0 if previous is None else previous["revision"],
                        })
                        return
                self._send_json(200, {
                    "queue": queue, "changed": changed, "reloadRequired": False,
                })
            except DiscussionQueueConflict as exc:
                self._send_json(409, {"error": str(exc)})
            except (DiscussionQueueError, QuestionAnswerError) as exc:
                self._send_json(400, {"error": str(exc)})
            except OSError as exc:
                self._send_json(500, {"error": f"could not persist discussion queue: {exc}"})

        def _question_post(self, question_id: str) -> None:
            if not self._require_current_engine():
                return
            if not self._same_origin():
                self._send_json(403, {"error": "same-origin CSRF check failed"})
                return
            try:
                body = self._read_json_body("question answer")
                required = {"expectedRevision", "expectedFingerprint", "answer"}
                allowed = required
                missing = sorted(required - set(body))
                unknown = sorted(set(body) - allowed)
                if missing or unknown:
                    field = (missing or unknown)[0]
                    raise QuestionAnswerError(
                        f"question answer has unknown or missing field: {field}"
                    )
                answer = body["answer"]
                if not isinstance(answer, dict):
                    raise QuestionAnswerError("answer must be a JSON object")
                answer_required = {"kind"}
                answer_allowed = answer_required | {"optionId", "text"}
                answer_missing = sorted(answer_required - set(answer))
                answer_unknown = sorted(set(answer) - answer_allowed)
                if answer_missing or answer_unknown:
                    field = (answer_missing or answer_unknown)[0]
                    raise QuestionAnswerError(
                        f"answer has unknown or missing field: {field}"
                    )
                with _mutation_guard(root):
                    authority = _answer_authority(root)
                    if authority is None:
                        self._send_json(
                            500, {"error": "current work graph could not be built"}
                        )
                        return
                    live_cfg, live_graph = authority
                    try:
                        ledger, decisions = _record_answers(
                            live_cfg, live_graph, root, [{
                                "questionId": question_id,
                                "expectedFingerprint": body["expectedFingerprint"],
                                "kind": answer["kind"],
                                "optionId": answer.get("optionId"),
                                "text": answer.get("text"),
                            }], body["expectedRevision"],
                        )
                    except _AnswerNotRecorded as exc:
                        self._send_json(500, {
                            "error": f"answer was not accepted: {exc}",
                            "revision": body["expectedRevision"],
                        })
                        return
                    decision = decisions[0]
                # The answer is durable; the derived views catch up in the
                # background and a refresh failure never rolls it back.
                _schedule_background_refresh(root)
                self._send_json(200, {
                    "revision": ledger["revision"],
                    "decision": decision_to_api(decision),
                    "reloadRequired": True,
                })
            except QuestionAnswerConflict as exc:
                self._send_json(409, {"error": str(exc)})
            except QuestionNotFoundError as exc:
                self._send_json(404, {"error": str(exc)})
            except QuestionAnswerError as exc:
                self._send_json(400, {"error": str(exc)})
            except (OSError, UnicodeError) as exc:
                self._send_json(500, {"error": f"could not persist answer: {exc}"})

        def _question_batch_post(self) -> None:
            if not self._require_current_engine():
                return
            if not self._same_origin():
                self._send_json(403, {"error": "same-origin CSRF check failed"})
                return
            try:
                body = self._read_json_body("question answers")
                required = {"expectedRevision", "answers"}
                missing = sorted(required - set(body))
                unknown = sorted(set(body) - required)
                if missing or unknown:
                    field = (missing or unknown)[0]
                    raise QuestionAnswerError(
                        f"question answers have unknown or missing field: {field}"
                    )
                raw_answers = body["answers"]
                if not isinstance(raw_answers, list):
                    raise QuestionAnswerError("answers must be an array")
                flattened = []
                for raw in raw_answers:
                    if not isinstance(raw, dict):
                        raise QuestionAnswerError("each answer must be a JSON object")
                    answer_required = {
                        "questionId", "expectedFingerprint", "answer"
                    }
                    answer_missing = sorted(answer_required - set(raw))
                    answer_unknown = sorted(set(raw) - answer_required)
                    if answer_missing or answer_unknown:
                        field = (answer_missing or answer_unknown)[0]
                        raise QuestionAnswerError(
                            f"answer has unknown or missing field: {field}"
                        )
                    value = raw["answer"]
                    if not isinstance(value, dict):
                        raise QuestionAnswerError("answer must be a JSON object")
                    value_required = {"kind"}
                    value_allowed = value_required | {"optionId", "text"}
                    value_missing = sorted(value_required - set(value))
                    value_unknown = sorted(set(value) - value_allowed)
                    if value_missing or value_unknown:
                        field = (value_missing or value_unknown)[0]
                        raise QuestionAnswerError(
                            f"answer value has unknown or missing field: {field}"
                        )
                    flattened.append({
                        "questionId": raw["questionId"],
                        "expectedFingerprint": raw["expectedFingerprint"],
                        "kind": value["kind"],
                        "optionId": value.get("optionId"),
                        "text": value.get("text"),
                    })
                with _mutation_guard(root):
                    authority = _answer_authority(root)
                    if authority is None:
                        self._send_json(
                            500, {"error": "current work graph could not be built"}
                        )
                        return
                    live_cfg, live_graph = authority
                    try:
                        ledger, decisions = _record_answers(
                            live_cfg, live_graph, root, flattened,
                            body["expectedRevision"],
                        )
                    except _AnswerNotRecorded as exc:
                        self._send_json(500, {
                            "error": f"answers were not accepted: {exc}",
                            "revision": body["expectedRevision"],
                        })
                        return
                # Same durability contract as the single-answer path.
                _schedule_background_refresh(root)
                self._send_json(200, {
                    "revision": ledger["revision"],
                    "decisions": [decision_to_api(value) for value in decisions],
                    "reloadRequired": False,
                })
            except QuestionAnswerConflict as exc:
                self._send_json(409, {"error": str(exc)})
            except QuestionNotFoundError as exc:
                self._send_json(404, {"error": str(exc)})
            except QuestionAnswerError as exc:
                self._send_json(400, {"error": str(exc)})
            except (OSError, UnicodeError) as exc:
                self._send_json(500, {"error": f"could not persist answers: {exc}"})

        def _story_edit(self, item_id=None):
            if not self._require_current_engine():
                return
            writing = item_id is None
            if writing and not self._same_origin():
                self._send_json(403, {"error": "same-origin CSRF check failed"})
                return
            try:
                body = self._read_json_body("story edit", maximum=1200000) if writing else None
                if writing:
                    item_id = body.get("storyId")
                if not isinstance(item_id, str) or not item_id.startswith("story:"):
                    raise ValueError("A story ID is required")
                with _mutation_guard(root):
                    live_graph = _read_graph(root)
                    if live_graph is None:
                        self._send_json(409, {"error": "current work graph unavailable; refresh before editing"})
                        return
                    source, error = _resolve_item_source(root, live_graph, item_id)
                    if source is None:
                        self._send_json(404, {"error": error})
                        return
                    result = save_edit(root, item_id, source, body) if writing else read_edit(root, item_id, source)
                self._send_json(200, {**result, "csrfToken": csrf_token, "renderId": process_render_id()})
            except StoryEditConflict as exc:
                self._send_json(409, {"error": str(exc)})
            except (ValueError, QuestionAnswerError) as exc:
                self._send_json(400, {"error": str(exc)})
            except (OSError, UnicodeError) as exc:
                self._send_json(500, {"error": f"Could not access story revision: {exc}"})

        def _area_chat(self, area=None, writing=False):
            from .area_chat import catalog, read_area, append_message
            if writing and not self._same_origin():
                self._send_json(403, {"error": "same-origin CSRF check failed"})
                return
            try:
                if writing:
                    body = self._read_json_body("area chat", maximum=20000)
                    append_message(root, area, body.get("id"), body.get("text"))
                result = read_area(root, area) if area is not None else {"areas": catalog(root)}
                self._send_json(200, {**result, "csrfToken": csrf_token})
            except (ValueError, QuestionAnswerError) as exc:
                self._send_json(400, {"error": str(exc)})
            except (OSError, UnicodeError) as exc:
                self._send_json(500, {"error": "Could not access planning conversation"})

        def do_POST(self):
            if not self._loopback_host():
                self._send_json(421, {"error": "loopback Host required"})
                return
            parsed = urlsplit(self.path)
            if not parsed.query and parsed.path.startswith("/api/area-chat/"):
                self._area_chat(unquote(parsed.path[len("/api/area-chat/"):]), writing=True)
                return
            if not parsed.query and parsed.path == "/api/story-edits":
                self._story_edit()
                return
            context = self._extension_context()
            if any(extension.post(context, parsed) for extension in SERVE_EXTENSIONS):
                return
            if not parsed.query and parsed.path == "/api/discussions/queue":
                self._discussion_queue_post()
                return
            if not parsed.query and parsed.path in {
                "/api/plan/analyze", "/api/plan/apply"
            }:
                self._planning_post(parsed.path.rsplit("/", 1)[1])
                return
            if not parsed.query and parsed.path == "/api/questions/answers":
                self._question_batch_post()
                return
            question_prefix = "/api/questions/"
            question_suffix = "/answer"
            if (not parsed.query and parsed.path.startswith(question_prefix)
                    and parsed.path.endswith(question_suffix)):
                encoded = parsed.path[
                    len(question_prefix):-len(question_suffix)
                ].rstrip("/")
                question_id = unquote(encoded)
                if question_id:
                    self._question_post(question_id)
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
            # Binding to 127.0.0.1 does not by itself defeat DNS rebinding.
            # Refuse attacker-controlled Host names before serving project data.
            if not self._loopback_host():
                self._send_json(421, {"error": "loopback Host required"})
                return
            parsed = urlsplit(self.path)
            if not parsed.query and parsed.path == "/api/area-chat":
                self._area_chat()
                return
            if not parsed.query and parsed.path.startswith("/api/area-chat/"):
                self._area_chat(unquote(parsed.path[len("/api/area-chat/"):]))
                return
            if parsed.path == "/api/radar/status" and not parsed.query:
                if not cfg.get("radar.enabled", False):
                    self._send_json(404, {"error": "radar disabled"})
                    return
                from .radar import status, RadarError
                try:
                    self._send_json(200, status(root))
                except (RadarError, OSError, ValueError, KeyError) as exc:
                    self._send_json(500, {"error": str(exc)})
                return
            if not parsed.query and parsed.path.startswith("/api/story-edits/"):
                self._story_edit(unquote(parsed.path[len("/api/story-edits/"):]))
                return
            context = self._extension_context()
            if any(extension.get(context, parsed) for extension in SERVE_EXTENSIONS):
                return
            if parsed.path == "/api/discussions" and not parsed.query:
                if not self._require_current_engine():
                    return
                live_graph = _read_graph(root, allow_stale=True)
                if live_graph is None:
                    self._send_json(500, {"error": "current work graph is unavailable"})
                    return
                try:
                    queue, warnings = read_discussion_queue(cfg, root, live_graph)
                except DiscussionQueueError as exc:
                    self._send_json(500, {"error": str(exc)})
                    return
                self._send_json(200, {
                    "engineVersion": __version__, "renderId": process_render_id(), "schema": 1,
                    "csrfToken": csrf_token, "warnings": warnings,
                    "queue": queue,
                })
                return
            if parsed.path == "/api/workstreams" and not parsed.query:
                if not self._require_current_engine():
                    return
                live_graph = _read_graph(root, allow_stale=True)
                if live_graph is None:
                    self._send_json(500, {
                        "error": "current work graph is unavailable; run vizzer refresh",
                    })
                    return
                if not cfg.get("workstreams.enabled", False):
                    self._send_json(404, {"error": "workstreams are disabled"})
                    return
                warnings = load_workstream_overlay(
                    live_graph, cfg, root, include_runtime=True
                )
                self._send_json(200, {
                    "engineVersion": __version__, "renderId": process_render_id(), "schema": 1,
                    "csrfToken": csrf_token, "warnings": warnings,
                    "workstreams": live_graph.workstreams,
                })
                return
            if parsed.path == "/api/questions" and not parsed.query:
                if not self._require_current_engine():
                    return
                # GET serves authority for the exact derived snapshot the user
                # is reading.  Rebuilding every adapter here made opening a
                # question an O(repo) operation and could return a fingerprint
                # for prose different from the already-rendered card.  Writes
                # validate against this same stored snapshot (ledger overlaid,
                # see _answer_authority), so the fingerprint a page reads here
                # is the one its answer is checked against.
                live_graph = _read_graph(root, allow_stale=True)
                if live_graph is None:
                    self._send_json(500, {
                        "error": "current work graph is unavailable; run vizzer refresh",
                    })
                    return
                live_cfg = cfg
                try:
                    ledger, _ = read_answers(live_cfg, root)
                except QuestionAnswerError as exc:
                    self._send_json(500, {"error": str(exc)})
                    return
                assert ledger is not None
                # The stored graph may predate the latest answer while its
                # refresh runs; the ledger decides what is still open.
                open_questions, decisions = current_questions_and_decisions(
                    live_graph, ledger)
                # The overlay only ever closes questions, so a shorter open
                # list means the stored graph (and every view rendered from
                # it) is behind the ledger. The page says so once that lasts
                # past the normal refresh window or a refresh has failed.
                behind = len(open_questions) != len(live_graph.owner_questions)
                worker = _refresh_worker(root)
                if behind and (worker.thread is None or not worker.thread.is_alive()):
                    # Nothing is catching the views up (e.g. serve restarted
                    # after a failed refresh): start the refresh now.
                    _schedule_background_refresh(root)
                self._send_json(200, {
                    "engineVersion": __version__,
                    "renderId": process_render_id(),
                    "schema": 1,
                    "csrfToken": csrf_token,
                    "revision": ledger["revision"],
                    "questions": [
                        question_to_api(question) for question in open_questions
                    ],
                    "decisions": [
                        decision_to_api(decision) for decision in decisions
                    ],
                    # The owner's answer to an earlier wording of a question
                    # that was reworded at its source and so reopened.
                    "supersededAnswers": [
                        superseded_to_api(decision)
                        for decision in superseded_answers(open_questions, ledger)
                    ],
                    "viewsBehind": behind,
                    "viewsBehindSince": worker.views_behind_since(behind),
                    "refreshFailure": worker.failure(),
                })
                return
            if parsed.path == "/api/plan" and not parsed.query:
                if not self._require_current_engine():
                    return
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
                self._send_json(200, {
                    "engineVersion": __version__,
                    "renderId": process_render_id(),
                    "csrfToken": csrf_token,
                    "overlay": overlay,
                })
                return
            story_body_prefix = "/api/story/"
            story_body_suffix = "/body"
            if (not parsed.query and parsed.path.startswith(story_body_prefix)
                    and parsed.path.endswith(story_body_suffix)):
                if not self._require_current_engine():
                    return
                encoded = parsed.path[
                    len(story_body_prefix):-len(story_body_suffix)
                ].rstrip("/")
                item_id = unquote(encoded)
                if not item_id:
                    self._send_json(404, {"error": "not found"})
                    return
                source, error = _resolve_item_source(root, graph, item_id)
                if source is None:
                    self._send_json(404, {"error": error})
                    return
                if source.suffix.lower() != ".md":
                    self._send_json(404, {"error": "item source is not markdown"})
                    return
                try:
                    payload = source.read_text(encoding="utf-8").encode("utf-8")
                except (OSError, UnicodeError):
                    self._send_json(500, {"error": "could not read story body"})
                    return
                if len(payload) > 2 * 1024 * 1024:
                    self._send_json(413, {"error": "story body is too large"})
                    return
                self._send_bytes(200, payload, "text/markdown; charset=utf-8")
                return
            if parsed.path.startswith("/api/open/"):
                self._send_json(405, {"error": "POST required"})
                return
            # codex-sequence-2026-08-08: the human entry point is the map, not
            # a raw directory listing that looks like Vizzer failed to load.
            if parsed.path == "/":
                location = "/constellation.html"
                if parsed.query:
                    location += f"?{parsed.query}"
                self.send_response(302)
                self.send_header("Location", location)
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


def _serve(root: Path, port: int | None, open_browser: bool = False) -> int:
    graph = _read_graph(root)
    if graph is None:
        print("serve: run 'sync' and 'render' first")
        return 2
    cfg = _load_config(root, "serve")
    if cfg is None:
        return 2
    resolved_port = cfg.get("server.port", 0) if port is None else port
    if (isinstance(resolved_port, bool) or not isinstance(resolved_port, int)
            or not 0 <= resolved_port <= 65535):
        print("serve: port must be an integer from 0 through 65535")
        return 2
    views = _output_dir(cfg, root, "serve")
    if views is None or not views.is_dir():
        print("serve: run 'render' first")
        return 2
    try:
        ensure_developer_store(graph, cfg, root)
    except Exception as exc:
        # The store is a performance cache, never availability or source truth.
        # The HTTP extension will use the validated in-memory oracle instead.
        print(f"serve: warning: developer query cache unavailable: {exc}")
    try:
        server = _make_serve_server(root, graph, views, resolved_port, cfg)
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


_GRAPH_LAST_GOOD_LOCK = threading.Lock()
_GRAPH_LAST_GOOD: dict[Path, str] = {}


def _reset_graph_read_cache() -> None:
    """Clear read-only serving fallback (also used by isolated tests)."""
    with _GRAPH_LAST_GOOD_LOCK:
        _GRAPH_LAST_GOOD.clear()


def _graph_file_identity(path: Path) -> tuple | None:
    try:
        value = path.stat()
        if stat_module.S_ISREG(value.st_mode):
            return value.st_dev, value.st_ino, value.st_mtime_ns, value.st_size
    except OSError:
        pass
    return None


def _last_good_graph(path: Path, reason: str, allow_stale: bool) -> Graph | None:
    with _GRAPH_LAST_GOOD_LOCK:
        text = _GRAPH_LAST_GOOD.get(path) if allow_stale else None
    if text is None:
        print(f"graph: could not load {path}: {reason}; re-run 'sync'", flush=True)
        return None
    print(f"graph: could not load {path}: {reason}; serving the last good graph", flush=True)
    return Graph.from_dict(json.loads(text))


def _read_graph(root: Path, *, allow_stale: bool = False) -> Graph | None:
    """Strict by default; only read-only HTTP routes may survive a torn rewrite.

    Git checkouts and artifact replacement can briefly remove or truncate the
    graph. Validation, rendering and mutations must never accept cached authority.
    Every call rebuilds a fresh Graph because handlers mutate its overlays.
    """
    path = (root / GRAPH_RELPATH).resolve()
    before = _graph_file_identity(path)
    if before is None:
        return _last_good_graph(path, "missing or not a regular file", allow_stale)
    try:
        text = path.read_text(encoding="utf-8")
        graph = Graph.from_dict(json.loads(text))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        AttributeError,
        ValueError,
    ) as exc:
        return _last_good_graph(path, str(exc), allow_stale)
    if _graph_file_identity(path) != before:
        return _last_good_graph(path, "changed during read", allow_stale)
    with _GRAPH_LAST_GOOD_LOCK:
        if path not in _GRAPH_LAST_GOOD and len(_GRAPH_LAST_GOOD) >= 16:
            del _GRAPH_LAST_GOOD[next(iter(_GRAPH_LAST_GOOD))]
        _GRAPH_LAST_GOOD[path] = text
    return graph


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


class _AnswerNotRecorded(Exception):
    """Nothing was recorded: the story note or the ledger could not be written."""


def _record_answers(cfg: Config, graph: Graph, root: Path, answers: list[dict],
                    expected_revision: int) -> tuple[dict, list]:
    """Journal accepted answers in their stories, then write the ledger.

    The ledger is the commit point (review 2026-09-25): it is written last, so
    a failure before it leaves no accepted answer behind, and the only
    rollback is of the story notes. A derived-view refresh is never part of
    accepting an answer and can never roll one back.
    Validation errors (``QuestionAnswerError`` and subclasses) propagate
    before anything is written. Call under ``_mutation_guard``.
    """
    ledger, decisions = prepare_answers(
        graph, cfg, root, answers, expected_revision=expected_revision,
    )
    snapshots: dict[Path, bytes] = {}
    try:
        snapshots = story_snapshots(graph, root, decisions)
        try:
            append_evolution_events(graph, root, decisions)
        except Exception as exc:
            raise _AnswerNotRecorded(
                f"its story evolution event could not be written: {exc}") from exc
        try:
            write_answers(cfg, root, ledger)
        except Exception as exc:
            raise _AnswerNotRecorded(
                f"the answer ledger could not be written: {exc}") from exc
    except Exception as exc:
        try:
            restore_story_snapshots(snapshots)
        except OSError as restore_exc:
            raise _AnswerNotRecorded(
                f"{exc}; restoring the story also failed: {restore_exc}") from exc
        if isinstance(exc, _AnswerNotRecorded):
            raise
        raise _AnswerNotRecorded(
            f"its story evolution event could not be written: {exc}") from exc
    return ledger, decisions


def _answer_authority(root: Path) -> tuple[Config, Graph] | None:
    """Config plus the graph an owner answer is validated against.

    The stored graph is the snapshot the page rendered and the one
    ``GET /api/questions`` serves, so its fingerprints are the ones the owner
    answered. Rebuilding every adapter here held the mutation lock for 5-20 s
    before the answer was written, long enough for a browser to give up. Only
    a project with no stored graph yet pays for a fresh build.

    The stored graph can lag the ledger while its refresh runs, so the ledger
    is overlaid first: a question answered since then is no longer open, and a
    second answer to it is refused as already answered, exactly as a fresh
    build would refuse it.
    """
    cfg = _load_config(root, "questions")
    if cfg is None:
        return None
    graph = _read_graph(root)
    if graph is not None:
        ledger, _ = read_answers(cfg, root)
        assert ledger is not None
        open_questions, decisions = current_questions_and_decisions(graph, ledger)
        return cfg, dataclasses.replace(
            graph, owner_questions=open_questions, owner_decisions=decisions)
    built = _build_fresh_graph(root, "questions")
    return None if built is None else (built[0], built[1])


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


def _write_artifacts(entries: list[tuple[Path, str]], command: str,
                     failures: list[str] | None = None) -> bool:
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
        if failures is not None:
            failures.append(str(exc))
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
    if only is None or "developer_flow" in only:
        try:
            prepare_developer_store(graph, cfg, root)
        except Exception as exc:
            # A performance cache must not turn a valid static render into a
            # failed delivery. Serving will use the in-memory oracle instead.
            print(f"{command}: warning: developer query cache unavailable: {exc}")

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
def _prepare_developer_store(cfg: Config, graph: Graph, root: Path) -> None:
    try:
        prepare_developer_store(graph, cfg, root)
    except Exception as exc:
        print(f"refresh: warning: developer query cache unavailable: {exc}")


def _refresh(root: Path) -> int:
    """Synchronize then render the graph built in this invocation.

    Deliberately do not call ``_render``: it reads the last on-disk graph, so a
    failed sync could otherwise render stale state and falsely look current.
    """
    result = _build_fresh_graph(root, "refresh")
    if result is None:
        return 2
    cfg, graph, progress = result
    if _journal_superseded_answers(cfg, graph, root):
        # A story gained a note: build again so the graph includes it.
        result = _build_fresh_graph(root, "refresh")
        if result is None:
            return 2
        cfg, graph, progress = result
    prepared = _refresh_entries(root, cfg, graph, progress)
    if prepared is None:
        return 2
    entries, rendered_count = prepared
    _prepare_developer_store(cfg, graph, root)
    if not _write_artifacts(entries, "refresh"):
        return 2
    _report_sync(cfg, graph, root, "refresh")
    print(f"refresh: wrote {rendered_count} files")
    return 0


def _refresh_entries(root: Path, cfg: Config, graph: Graph,
                     progress: ProgressHistory) -> tuple[list[tuple[Path, str]], int] | None:
    """Render every artifact a refresh writes, without writing any of them.

    Returns the entries plus how many of them are rendered views.
    """
    output_dir = _output_dir(cfg, root, "refresh")
    if output_dir is None:
        return None
    try:
        # The ONLY Git read behind the committed views: record new main-line
        # merges into the committed ledger before rendering from it. `check`
        # reads the ledger alone, so the squash merge that lands this refresh
        # cannot restale what it lands.
        merge_ledger = stage_merge_ledger(graph, cfg, root)
        rendered = render_all(graph, cfg, root)
    except Exception as exc:
        print(f"refresh: {exc}")
        return None
    entries = [(root / GRAPH_RELPATH, graph.dumps())]
    if progress.path is not None and progress.content is not None:
        entries.append((progress.path, progress.content))
    if merge_ledger is not None:
        entries.append(merge_ledger)
    for filename, content in rendered.items():
        relative = Path(filename)
        if relative.is_absolute() or ".." in relative.parts:
            print(f"refresh: renderer returned unsafe output path {filename!r}")
            return None
        entries.append((output_dir / relative, content))
    return entries, len(rendered)


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
    # Normalize once: render/output helpers may return resolved paths, and a
    # documented relative `--root .` must compare in the same coordinate
    # system instead of crashing in Path.relative_to.
    root = root.resolve()
    if (root / "vizzer/engine/vizzer").is_dir():
        try:
            installed_render_id = render_id(root)
        except RenderIdError as exc:
            print(f"check: installed engine identity failed: {exc}")
            return 2
        running_render_id = process_render_id()
        if running_render_id is None:
            print(f"check: running engine identity failed: {process_render_id_reason()}")
            return 2
        if installed_render_id != running_render_id:
            print(
                f"check: running engine {running_render_id} does not match installed "
                f"engine {installed_render_id}; use the project's vendored engine"
            )
            return 2
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
    # A story note the answer ledger does not hold (an answer interrupted
    # between its two writes) would tell an agent a decision the owner never
    # recorded. Reported, never a gate.
    for warning in expected_graph.warnings:
        if warning.startswith("story note without a recorded answer"):
            print(f"check: WARNING {warning}")

    answered_blockers = answered_blocker_records(expected_graph)
    if answered_blockers:
        for work, decisions in answered_blockers:
            answers = ", ".join(
                f"{decision.question.id} at {decision.answered_at}"
                for decision in decisions
            )
            print(
                f"check: answered blocker: {work.story_id} remains blocked "
                f"after accepted decision(s) {answers}"
            )
        return 1

    grandfathered, grandfather_warnings = load_grandfathered_blockers(root)
    for warning in grandfather_warnings:
        print(f"check: {warning}")
    if grandfather_warnings:
        return 1
    unresolved = unresolved_blocker_records(
        expected_graph,
        done_statuses=cfg.done_statuses(),
        grandfathered=grandfathered,
    )
    live_blockers = [
        violation for violation in unresolved if not violation.grandfathered
    ]
    carried = len(unresolved) - len(live_blockers)
    if carried:
        print(
            f"check: {carried} grandfathered blocked-record violation(s) "
            f"remaining (see {GRANDFATHER_RELPATH})"
        )
    if live_blockers:
        for violation in live_blockers:
            print(
                f"check: unresolved blocker [{'+'.join(violation.reasons)}]: "
                f"{violation.remedy}"
            )
        return 1
    question_budget = int(cfg.get("questions.age_budget_hours", 72))
    ages = question_ages(expected_graph, cfg, root, datetime.now(timezone.utc))
    overdue = [age for age in ages if age.over_budget]
    for warning in overdue_warning_lines(ages, question_budget):
        print(warning)
    if overdue and cfg.get("questions.age_budget_hard_fail", False):
        return 1
    graph_path = root / GRAPH_RELPATH
    stale: set[str] = set()

    if cfg.get("reviews.enabled", False):
        try:
            load_review_plans(cfg, root)
        except ReviewContractError as exc:
            print(f"check: review contracts are invalid: {exc}")
            return 2
    if cfg.get("agent_ops.enabled", False):
        from .agent_lanes import AgentLaneError, read_ledger
        try:
            read_ledger(root, cfg.get("agent_ops.ledger_path"), strict=True)
        except AgentLaneError as exc:
            print(f"check: agent operations ledger is invalid: {exc}")
            return 2

    # Installed copies carry a marker beside the vendored engine. A partial
    # update can render static files while every guarded HTTP API rejects the
    # mismatch, so ``check`` must audit the installation contract too.
    marker_path = root / "vizzer" / "VERSION"
    if marker_path.exists():
        try:
            installed_version = marker_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            stale.add("vizzer/VERSION")
        else:
            if installed_version != __version__:
                stale.add("vizzer/VERSION")
    if (root / "vizzer/engine/vizzer").is_dir():
        marker = read_marker(root)
        if marker is None or marker.render_id != installed_render_id:
            stale.add("vizzer/RENDER_ID")

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
    if args.plan_action in {"apply", "undo"}:
        try:
            with _mutation_guard(root):
                return _plan_inner(root, args)
        except OSError as exc:
            print(f"plan: could not acquire mutation lock: {exc}")
            return 2
    return _plan_inner(root, args)


def _plan_inner(root: Path, args: argparse.Namespace) -> int:
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


def _journal_owner_decisions(root: Path, args: argparse.Namespace) -> int:
    """Backfill accepted answer events into their source stories."""
    with _mutation_guard(root):
        built = _build_fresh_graph(root, "decisions")
        if built is None:
            return 2
        _cfg, graph, _progress = built
        by_id = {
            decision.question.id: decision for decision in graph.owner_decisions
        }
        requested = list(args.question_id or [])
        if args.apply and (args.all or len(requested) != 1):
            print("decisions: --apply requires exactly one question id")
            return 2
        if args.all:
            if requested:
                print("decisions: use question ids or --all, not both")
                return 2
            decisions = list(by_id.values())
        else:
            if not requested:
                print("decisions: provide at least one question id or --all")
                return 2
            unknown = sorted(set(requested) - set(by_id))
            if unknown:
                print(f"decisions: unknown accepted decision {unknown[0]}")
                return 2
            decisions = [by_id[value] for value in requested]

        if args.apply and (not isinstance(args.summary, str) or not args.summary.strip()):
            print("decisions: --apply requires a nonempty --summary")
            return 2

        if not args.yes:
            action = "apply" if args.apply else "journal"
            print(
                f"decisions: would {action} {len(decisions)} accepted decision(s); "
                "rerun with --yes"
            )
            return 1

        try:
            snapshots = story_snapshots(graph, root, decisions)
            if args.apply:
                changed = append_application_event(
                    graph,
                    root,
                    decisions[0],
                    applied_at=datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ).replace("+00:00", "Z"),
                    summary=args.summary,
                    evidence=list(args.evidence or []),
                )
            else:
                changed = append_evolution_events(graph, root, decisions)
        except (OSError, UnicodeError, DecisionJournalError) as exc:
            print(f"decisions: {exc}")
            return 2
        try:
            refresh_result = _refresh(root)
        except Exception:
            refresh_result = 2
        if refresh_result != 0:
            try:
                restore_story_snapshots(snapshots)
            except (OSError, DecisionJournalError) as exc:
                print(
                    "decisions: refresh failed and story rollback also failed: "
                    f"{exc}"
                )
                return 2
            print("decisions: journaling was rolled back because views could not refresh")
            return 2
        if args.apply:
            print(
                f"decisions: recorded application in {len(changed)} story "
                f"file(s) for {decisions[0].question.id}"
            )
        else:
            print(
                f"decisions: journaled {len(changed)} story file(s) for "
                f"{len(decisions)} accepted decision(s)"
            )
        return 0


def _read_request_file(path: str, subject: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkstreamError(f"{subject} file is unreadable or malformed: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkstreamError(f"{subject} file must contain a JSON object")
    return value


def _workstreams(root: Path, args: argparse.Namespace) -> int:
    built = _build_fresh_graph(root, "workstreams")
    if built is None:
        return 2
    cfg, graph, _ = built
    if not cfg.get("workstreams.enabled", False):
        print("workstreams: disabled in vizzer.toml")
        return 2
    try:
        if args.workstream_action == "show":
            overlay, _ = read_workstreams(cfg, root, graph)
            runtime, _ = read_runtime(cfg, root, graph)
            print(json.dumps({"definitions": overlay, "runtime": runtime}, indent=2))
            return 0
        with _mutation_guard(root):
            # Rebuild under the lock so a concurrent accepted answer or source
            # edit cannot change the item/question universe between validation
            # and persistence.
            locked = _build_fresh_graph(root, "workstreams")
            if locked is None:
                return 2
            cfg, graph, _ = locked
            previous, _ = read_workstreams(cfg, root, graph)
            if args.workstream_action == "apply":
                request = _read_request_file(args.file, "workstream state")
                state = request.get("state", request)
                updated = apply_workstreams(
                    cfg, root, graph, state,
                    expected_revision=args.expected_revision,
                    actor=args.actor, rationale=args.rationale,
                )
            else:
                updated = append_discussion(
                    cfg, root, graph,
                    expected_revision=args.expected_revision,
                    workstream_id=args.workstream,
                    discussion_id=args.id,
                    author=args.author,
                    kind=args.kind,
                    scope=args.scope,
                    body=args.body,
                    reply_to=args.reply_to,
                    owner_question_id=args.owner_question,
                )
            if _refresh(root) != 0:
                restore_workstreams(cfg, root, graph, previous)
                print("workstreams: mutation rolled back because refresh failed")
                return 2
        print(json.dumps(updated, indent=2))
        return 0
    except WorkstreamConflict as exc:
        print(f"workstreams: {exc}")
        return 3
    except WorkstreamError as exc:
        print(f"workstreams: {exc}")
        return 2


def _sessions(root: Path, args: argparse.Namespace) -> int:
    built = _build_fresh_graph(root, "sessions")
    if built is None:
        return 2
    cfg, graph, _ = built
    if not cfg.get("workstreams.enabled", False):
        print("sessions: workstreams are disabled in vizzer.toml")
        return 2
    try:
        if args.session_action == "show":
            runtime, _ = read_runtime(cfg, root, graph)
            print(json.dumps(runtime, indent=2))
            return 0
        with _mutation_guard(root):
            locked = _build_fresh_graph(root, "sessions")
            if locked is None:
                return 2
            cfg, graph, _ = locked
            previous, _ = read_runtime(cfg, root, graph)
            if args.session_action == "start":
                updated = start_session(
                    cfg, root, graph,
                    session_id=args.id, actor=args.actor, model=args.model,
                    role=args.role, workstream_id=args.workstream,
                    branch=args.branch, worktree=args.worktree,
                    expected_revision=args.expected_revision,
                    lease_minutes=args.lease_minutes,
                )
            elif args.session_action == "heartbeat":
                updated = heartbeat_session(
                    cfg, root, graph, session_id=args.id,
                    expected_revision=args.expected_revision,
                    lease_minutes=args.lease_minutes,
                )
                print(json.dumps(updated, indent=2))
                return 0
            else:
                updated = stop_session(
                    cfg, root, graph, session_id=args.id,
                    expected_revision=args.expected_revision,
                )
            if _refresh(root) != 0:
                restore_runtime(cfg, root, graph, previous)
                print("sessions: mutation rolled back because refresh failed")
                return 2
        print(json.dumps(updated, indent=2))
        return 0
    except WorkstreamConflict as exc:
        print(f"sessions: {exc}")
        return 3
    except (WorkstreamError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"sessions: {exc}")
        return 2


def _reviews(root: Path, args: argparse.Namespace) -> int:
    """Inspect review authority or append an agent's independently run event."""
    cfg = _load_config(root, "review")
    if cfg is None:
        return 2
    if not cfg.get("reviews.enabled", False):
        print("review: disabled in vizzer.toml")
        return 2
    try:
        if args.review_action == "show":
            print(json.dumps(review_state(cfg, root), indent=2))
            return 0
        event = _read_request_file(args.file, "review event")
        actor = event.get("actor")
        if not isinstance(actor, dict) or actor.get("kind") != "agent":
            raise ReviewServiceError(
                "review record accepts agent runs only; owners validate through vizzer serve"
            )
        with _mutation_guard(root):
            ledger = append_review_event(
                cfg, root, args.plan, event,
                expected_revision=args.expected_revision,
                allow_owner=False,
            )
        print(json.dumps({
            "planId": args.plan,
            "revision": ledger["revision"],
            "event": ledger["events"][-1],
        }, indent=2))
        return 0
    except ReviewContractError as exc:
        print(f"review: {exc}")
        return 3 if "stale; current revision" in str(exc) else 2
    except (WorkstreamError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"review: {exc}")
        return 2


def _configure(root: Path, args: argparse.Namespace) -> int:
    from .onboarding import ConfigurationError, configure_from_answers, grill

    try:
        if args.answers:
            if not args.yes:
                print("configure: --answers requires --yes")
                return 1
            answers = _read_request_file(args.answers, "configuration answers")
            text, preview = configure_from_answers(root, answers)
        else:
            configured = grill(root)
            text = configured["config_text"]
            preview = {
                "projectName": configured["project_name"],
                "sourceAreas": configured["source_areas"],
            }
        destination = root / "vizzer" / "vizzer.toml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix=".vizzer.toml.", dir=str(destination.parent)
        )
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        if (root / "vizzer" / "engine").exists() and _refresh(root) != 0:
            print("configure: wrote config but refresh failed; fix the reported source contract")
            return 2
        print(json.dumps(preview, indent=2))
        return 0
    except (ConfigurationError, WorkstreamError, OSError) as exc:
        print(f"configure: {exc}")
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vizzer")
    subparsers = parser.add_subparsers(dest="command")

    radar = subparsers.add_parser("radar", help="compare registered local Vizzer engines without modifying them")
    radar_commands = radar.add_subparsers(dest="radar_action", required=True)
    for action in ("register", "scan", "show", "annotate", "watch"):
        command = radar_commands.add_parser(action)
        command.add_argument("--root", default=".")
        if action == "register":
            command.add_argument("--id", required=True)
            command.add_argument("--project", required=True)
            command.add_argument("--engine", default="vizzer/engine/vizzer")
            command.add_argument("--baseline", required=True,
                                 help="upstream comparison commit/ref; not assumed fork ancestry")
        elif action == "annotate":
            command.add_argument("--id", required=True, help="full content fingerprint")
            command.add_argument("--title")
            command.add_argument("--summary")
            command.add_argument("--evidence", action="append")
            command.add_argument("--brief", help="capture a repository Markdown brief with Intent, Rationale and Sources headings")
            command.add_argument("--review", help="review note bound to this exact change")
        elif action == "watch":
            command.add_argument("--interval", type=int, default=30)
        def radar_handler(args):
            from .radar import cli
            return cli(Path(args.root).resolve(), args)
        command.set_defaults(handler=radar_handler)

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
    serve.add_argument(
        "--port", type=int, default=None,
        help="loopback port; overrides [server] port (0 chooses an ephemeral port)",
    )
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

    decisions = subparsers.add_parser(
        "decisions", help="journal accepted answers into evolving source stories"
    )
    decisions.add_argument("question_id", nargs="*")
    decisions.add_argument("--all", action="store_true")
    decisions.add_argument(
        "--apply", action="store_true",
        help="record normative follow-through for one accepted decision",
    )
    decisions.add_argument(
        "--summary", help="what scope, acceptance, or dependencies changed",
    )
    decisions.add_argument(
        "--evidence", action="append", default=[],
        help="repeatable source, test, or receipt supporting application",
    )
    decisions.add_argument("--yes", action="store_true")
    decisions.add_argument("--root", default=".")
    decisions.set_defaults(
        handler=lambda args: _journal_owner_decisions(Path(args.root), args)
    )

    workstreams = subparsers.add_parser(
        "workstreams", help="inspect or atomically update collaborative workstreams"
    )
    workstream_subparsers = workstreams.add_subparsers(
        dest="workstream_action", required=True
    )
    workstream_show = workstream_subparsers.add_parser("show")
    workstream_show.add_argument("--root", default=".")
    workstream_show.set_defaults(handler=lambda args: _workstreams(Path(args.root), args))
    workstream_apply = workstream_subparsers.add_parser(
        "apply", help="replace versioned workstream intent from a JSON state file"
    )
    workstream_apply.add_argument("--root", default=".")
    workstream_apply.add_argument("--file", required=True)
    workstream_apply.add_argument("--expected-revision", type=int, required=True)
    workstream_apply.add_argument("--actor", required=True)
    workstream_apply.add_argument("--rationale", required=True)
    workstream_apply.set_defaults(handler=lambda args: _workstreams(Path(args.root), args))
    workstream_discuss = workstream_subparsers.add_parser(
        "discuss", help="append a peer discussion or owner escalation"
    )
    workstream_discuss.add_argument("--root", default=".")
    workstream_discuss.add_argument("--expected-revision", type=int, required=True)
    workstream_discuss.add_argument("--workstream", required=True)
    workstream_discuss.add_argument("--id", required=True)
    workstream_discuss.add_argument("--author", required=True)
    workstream_discuss.add_argument("--kind", choices=sorted({
        "question", "proposal", "response", "decision", "escalation",
    }), required=True)
    workstream_discuss.add_argument(
        "--scope", choices=("implementation", "product", "scope", "contract"),
        required=True,
    )
    workstream_discuss.add_argument("--body", required=True)
    workstream_discuss.add_argument("--reply-to")
    workstream_discuss.add_argument("--owner-question")
    workstream_discuss.set_defaults(handler=lambda args: _workstreams(Path(args.root), args))

    sessions = subparsers.add_parser(
        "sessions", help="manage leased Claude, Codex, human, or script sessions"
    )
    session_subparsers = sessions.add_subparsers(dest="session_action", required=True)
    session_show = session_subparsers.add_parser("show")
    session_show.add_argument("--root", default=".")
    session_show.set_defaults(handler=lambda args: _sessions(Path(args.root), args))
    session_start = session_subparsers.add_parser("start")
    session_start.add_argument("--root", default=".")
    session_start.add_argument("--id", required=True)
    session_start.add_argument("--actor", required=True)
    session_start.add_argument("--model", required=True)
    session_start.add_argument("--role", choices=("lead", "reviewer", "observer"), required=True)
    session_start.add_argument("--workstream", required=True)
    session_start.add_argument("--branch", required=True)
    session_start.add_argument("--worktree", required=True)
    session_start.add_argument("--expected-revision", type=int, required=True)
    session_start.add_argument("--lease-minutes", type=int)
    session_start.set_defaults(handler=lambda args: _sessions(Path(args.root), args))
    session_heartbeat = session_subparsers.add_parser("heartbeat")
    session_heartbeat.add_argument("--root", default=".")
    session_heartbeat.add_argument("--id", required=True)
    session_heartbeat.add_argument("--expected-revision", type=int, required=True)
    session_heartbeat.add_argument("--lease-minutes", type=int)
    session_heartbeat.set_defaults(handler=lambda args: _sessions(Path(args.root), args))
    session_stop = session_subparsers.add_parser("stop")
    session_stop.add_argument("--root", default=".")
    session_stop.add_argument("--id", required=True)
    session_stop.add_argument("--expected-revision", type=int, required=True)
    session_stop.set_defaults(handler=lambda args: _sessions(Path(args.root), args))

    review = subparsers.add_parser(
        "review", help="inspect review plans or record an agent evidence run"
    )
    review_subparsers = review.add_subparsers(dest="review_action", required=True)
    review_show = review_subparsers.add_parser(
        "show", help="print current plans and latest agent/owner runs"
    )
    review_show.add_argument("--root", default=".")
    review_show.set_defaults(handler=lambda args: _reviews(Path(args.root), args))
    review_record = review_subparsers.add_parser(
        "record", help="append an agent run from a validated JSON event file"
    )
    review_record.add_argument("--root", default=".")
    review_record.add_argument("--plan", required=True)
    review_record.add_argument("--file", required=True)
    review_record.add_argument("--expected-revision", type=int, required=True)
    review_record.set_defaults(handler=lambda args: _reviews(Path(args.root), args))

    configure = subparsers.add_parser(
        "configure", help="grill project source roles and write vizzer.toml"
    )
    configure.add_argument("path")
    configure.add_argument("--answers", help="non-interactive JSON answer file")
    configure.add_argument("--yes", action="store_true")
    configure.set_defaults(handler=lambda args: _configure(Path(args.path), args))

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("path")
    install_parser.add_argument("--claude-skill", action="store_true")
    install_parser.add_argument(
        "--harness", choices=("auto", "claude", "agents"), default="auto"
    )
    install_parser.add_argument(
        "--grill", action="store_true",
        help="interactively name source roles and paths before installation",
    )

    def install_handler(args: argparse.Namespace) -> int:
        from .install import install

        configuration = None
        if args.grill:
            from .onboarding import ConfigurationError, grill
            try:
                configuration = grill(Path(args.path))
            except ConfigurationError as exc:
                print(f"install: {exc}")
                return 2
        return install(
            Path(args.path),
            claude_skill=args.claude_skill,
            harness=args.harness,
            configuration=configuration,
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
        from .install import install
        from .onboarding import ConfigurationError, grill

        target_text = input("Project path [.]: ").strip()
        target = Path(target_text or ".")
        try:
            configuration = grill(target)
        except ConfigurationError as exc:
            print(f"install: {exc}")
            return 1
        return install(target, configuration=configuration)

    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    return args.handler(args)
