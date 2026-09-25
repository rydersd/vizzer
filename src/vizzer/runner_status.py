"""Served-only GitHub Actions runner fleet status.

Owner directive 2026-08-26: "in vizzer it should show the runners connected
and i should be able to hover over and see status."  Scar tissue: the single
runner was once dead for eight hours before anyone noticed, because nothing
the owner reads showed it.

This follows ``ci_status`` exactly — the same volatility split:

* runner state changes whenever a machine sleeps or picks up a job, so it
  NEVER enters a rendered file.  Rendered views do not import this module
  (proven by a forced-throw test); ``vizzer serve`` answers ``/api/runners``
  at request time instead;
* read-only: one ``gh api .../actions/runners`` call per cache window, plus —
  only when some runner is busy — a bounded lookup of in-progress runs and
  their jobs to name the job, PR and start time;
* hard budget: the whole collection has an eight-second deadline; a slow or
  failed job lookup leaves the runner list intact with ``job`` unknown;
* stale-while-revalidate: a cached payload returns at once while one
  background refresh runs.  Unlike CI status, a FAILED refresh replaces the
  last good payload with ``available: false`` — the story forbids showing a
  last-known-green runner when GitHub cannot be reached.

Classification (pure functions, unit-tested):

* opt-in: ``[runners] enabled = true`` in vizzer.toml; disabled projects get
  a 404 and the page shows no runner chrome;
* the lane label is read from the runner's own labels, never from its name;
* a runner with no custom (routing) labels is "out of pool": offline or idle,
  it is shown neutrally, never as an alarm;
* an in-pool runner that is offline is the alarm state.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
CACHE_SECONDS = 60.0
_GH_TIMEOUT = 20
_COLLECT_TIMEOUT_SECONDS = 8.0
# Busy runners are matched to jobs by scanning the newest in-progress runs.
# A fleet of a handful of runners never has more busy jobs than this.
_MAX_RUN_LOOKUPS = 10
_JOB_WORKERS = 4

# GitHub's own default self-hosted labels.  They describe the machine
# (OS / architecture), not the lane it serves, so they are left out of the
# compact lane label when the runner has anything more specific.
GITHUB_DEFAULT_LABELS = {"self-hosted", "linux", "macos", "windows",
                         "x64", "arm", "arm64"}

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {
    "at": None,
    "attemptedAt": None,
    "payload": None,
    "refreshing": False,
}
# runner name -> ISO time this serve last saw it online.  In memory only:
# GitHub's API has no "last seen" field, so this is what this process saw.
_LAST_SEEN_ONLINE: dict[str, str] = {}


def _utc_now_iso() -> str:
    """UTC ISO-8601 with a colon offset — parseable by every browser's Date."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_OBSERVING_SINCE = _utc_now_iso()


# ---- pure classification -------------------------------------------------

def label_names(runner: dict) -> list[str]:
    """Every label name on a runner, in GitHub's order."""
    return [str(label.get("name") or "") for label in runner.get("labels") or []
            if isinstance(label, dict) and label.get("name")]


def routing_labels(runner: dict) -> list[str]:
    """Custom labels — the ones a workflow's ``runs-on`` routes by.

    GitHub marks labels it applied automatically as ``read-only``; anything
    an operator added is ``custom``.  ``self-hosted`` is never a lane.
    """
    return [str(label.get("name")) for label in runner.get("labels") or []
            if isinstance(label, dict) and label.get("type") == "custom"
            and label.get("name")
            and str(label.get("name")).lower() != "self-hosted"]


def lane_label(runner: dict) -> str:
    """Compact lane text for the indicator, built only from labels.

    Prefers the operator's specific labels (``xctest-pr · mini · heavy``);
    falls back to the custom OS/arch labels when those are all there is.
    Empty when the runner has no routing labels at all.
    """
    routing = routing_labels(runner)
    specific = [name for name in routing if name.lower() not in GITHUB_DEFAULT_LABELS]
    return " · ".join(specific or routing)


def runner_state(runner: dict) -> str:
    """'offline' | 'busy' | 'idle' | 'out-of-pool' for one runner.

    ``offline`` (the alarm) applies only to in-pool runners.  A runner with
    no routing labels reads ``out-of-pool`` whether it is idle or offline —
    unless it is actually running a job, in which case ``busy`` is the truth.
    """
    online = str(runner.get("status") or "").lower() == "online"
    busy = bool(runner.get("busy")) and online
    if busy:
        return "busy"
    if not routing_labels(runner):
        return "out-of-pool"
    return "idle" if online else "offline"


def jobs_by_runner(runs: list[dict], jobs: list[dict]) -> dict[str, dict]:
    """runner name -> its current job, joined to the run for workflow + PR."""
    runs_by_id = {run.get("id"): run for run in runs if isinstance(run, dict)}
    current: dict[str, dict] = {}
    for job in jobs:
        if not isinstance(job, dict) or job.get("status") != "in_progress":
            continue
        runner_name = str(job.get("runner_name") or "")
        if not runner_name:
            continue
        run = runs_by_id.get(job.get("run_id")) or {}
        prs = [pr for pr in run.get("pull_requests") or [] if isinstance(pr, dict)]
        pr_number = prs[0].get("number") if prs else None
        current[runner_name] = {
            "workflow": str(run.get("name") or ""),
            "name": str(job.get("name") or ""),
            "url": str(job.get("html_url") or ""),
            "branch": str(run.get("head_branch") or ""),
            "pr": pr_number if isinstance(pr_number, int) else None,
            "startedAt": str(job.get("started_at") or ""),
        }
    return current


def shape_runner(runner: dict, job: dict | None, last_seen_online: str | None,
                 job_error: str = "") -> dict:
    """The per-runner record the served page renders."""
    state = runner_state(runner)
    return {
        "id": runner.get("id"),
        "name": str(runner.get("name") or ""),
        "labels": label_names(runner),
        "lane": lane_label(runner),
        "inPool": bool(routing_labels(runner)),
        "online": str(runner.get("status") or "").lower() == "online",
        "state": state,
        "alarm": state == "offline",
        "job": job if state == "busy" else None,
        "jobError": job_error if state == "busy" and job is None else "",
        "lastSeenOnline": last_seen_online,
    }


# ---- GitHub collection ---------------------------------------------------

def _run_gh(arguments: list[str], root: Path, *, timeout: float) -> str:
    """One read-only gh call with the ambient token; raises on any failure."""
    call_timeout = min(_GH_TIMEOUT, timeout)
    if call_timeout <= 0:
        raise TimeoutError("runner status collection timed out")
    completed = subprocess.run(
        ["gh", *arguments], cwd=root, capture_output=True, text=True,
        timeout=call_timeout, check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail.splitlines()[0] if detail else
                           f"gh exited {completed.returncode}")
    return completed.stdout


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("runner status collection timed out")
    return remaining


def _collect_runners(root: Path, deadline: float) -> list[dict]:
    body = json.loads(_run_gh(
        ["api", "repos/{owner}/{repo}/actions/runners?per_page=100"],
        root, timeout=_remaining_seconds(deadline)))
    return [runner for runner in body.get("runners") or [] if isinstance(runner, dict)]


def _collect_current_jobs(root: Path, deadline: float) -> dict[str, dict]:
    """Current job per busy runner, from the newest in-progress runs."""
    body = json.loads(_run_gh(
        ["api", "repos/{owner}/{repo}/actions/runs?status=in_progress"
                f"&per_page={_MAX_RUN_LOOKUPS}"],
        root, timeout=_remaining_seconds(deadline)))
    runs = [run for run in body.get("workflow_runs") or [] if isinstance(run, dict)]
    runs = runs[:_MAX_RUN_LOOKUPS]
    if not runs:
        return {}

    def run_jobs(run: dict) -> list[dict]:
        listed = json.loads(_run_gh(
            ["api", f"repos/{{owner}}/{{repo}}/actions/runs/{run['id']}/jobs"
                    "?filter=latest&per_page=100"],
            root, timeout=_remaining_seconds(deadline)))
        return [job for job in listed.get("jobs") or [] if isinstance(job, dict)]

    executor = ThreadPoolExecutor(max_workers=min(_JOB_WORKERS, len(runs)))
    futures = [executor.submit(run_jobs, run) for run in runs]
    try:
        completed, _pending = wait(futures, timeout=max(0, deadline - time.monotonic()))
        jobs: list[dict] = []
        for future in completed:
            try:
                jobs.extend(future.result())
            except Exception:  # noqa: BLE001 - one run's jobs failing stays local
                continue
        return jobs_by_runner(runs, jobs)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _build_payload(root: Path) -> dict:
    deadline = time.monotonic() + _COLLECT_TIMEOUT_SECONDS
    runners = _collect_runners(root, deadline)
    now_iso = _utc_now_iso()
    for runner in runners:
        if str(runner.get("status") or "").lower() == "online":
            _LAST_SEEN_ONLINE[str(runner.get("name") or "")] = now_iso

    jobs: dict[str, dict] = {}
    job_error = ""
    if any(runner_state(runner) == "busy" for runner in runners):
        try:
            jobs = _collect_current_jobs(root, deadline)
        except Exception as error:  # noqa: BLE001 - the runner list still stands
            job_error = f"current job unavailable: {str(error)[:160]}"
    shaped = []
    for runner in runners:
        name = str(runner.get("name") or "")
        job = jobs.get(name)
        shaped.append(shape_runner(
            runner, job, _LAST_SEEN_ONLINE.get(name),
            job_error or ("" if job else "current job not found in the newest runs")))
    return {
        "schema": SCHEMA,
        "available": True,
        "fetchedAt": now_iso,
        "observingSince": _OBSERVING_SINCE,
        "runners": shaped,
    }


def _unavailable_payload(error: Exception | str) -> dict:
    reason = str(error).strip() or error.__class__.__name__
    return {
        "schema": SCHEMA,
        "available": False,
        "error": f"Runner status unavailable: {reason[:200]}",
        "runners": [],
    }


def _with_freshness(payload: dict, age: float | None, refreshing: bool) -> dict:
    """A response copy with cache age; never mutate the cached payload."""
    result = dict(payload)
    result["ageSeconds"] = None if age is None else max(0, int(age))
    result["stale"] = age is None or age >= CACHE_SECONDS
    result["refreshing"] = refreshing
    return result


def _refresh(root: Path, attempted_at: float) -> None:
    """Refresh outside the HTTP lock.  A failure REPLACES the cached payload."""
    try:
        fresh = _build_payload(root)
    except Exception as error:  # noqa: BLE001 - graceful degradation is the contract
        fresh = _unavailable_payload(error)
    with _CACHE_LOCK:
        _CACHE["attemptedAt"] = attempted_at
        _CACHE["refreshing"] = False
        _CACHE["at"] = attempted_at
        _CACHE["payload"] = fresh


def _start_refresh(root: Path, attempted_at: float) -> None:
    _CACHE["refreshing"] = True
    threading.Thread(
        target=_refresh, args=(root, attempted_at), daemon=True,
        name="vizzer-runner-refresh",
    ).start()


def payload(root: Path, *, now=time.monotonic) -> dict:
    """Non-blocking, stale-while-revalidate payload for ``/api/runners``.

    Never raises and never waits for GitHub.  With nothing cached yet the
    caller gets ``available: false`` ("refresh in progress").
    """
    with _CACHE_LOCK:
        moment = now()
        cached = _CACHE["payload"]
        cached_at = _CACHE["at"]
        attempted_at = _CACHE["attemptedAt"]
        age = None if cached_at is None else moment - cached_at
        needs_refresh = attempted_at is None or moment - attempted_at >= CACHE_SECONDS
        if needs_refresh and not _CACHE["refreshing"]:
            _start_refresh(root, moment)
        if cached is None:
            cached = _unavailable_payload("refresh in progress")
        return _with_freshness(cached, age, _CACHE["refreshing"])


def reset_cache() -> None:
    """Test seam: forget the cached payload and the last-seen memory."""
    with _CACHE_LOCK:
        _CACHE["at"] = None
        _CACHE["attemptedAt"] = None
        _CACHE["payload"] = None
        _CACHE["refreshing"] = False
        _LAST_SEEN_ONLINE.clear()
