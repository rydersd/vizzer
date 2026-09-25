"""Velocity view: what shipped, what merged, what it cost — per day and per host.

Portable persisted flow metrics only
(throughput, WIP, lead time); host comparisons are descriptive, not causal.
"""
from __future__ import annotations

import json
import html
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

from ..config import Config
from ..model import Graph
from ..velocity import (
    DayRow, HostSummary, anchor_day, build_stamps, day_rows, host_cuts,
    host_summaries, lead_times, lifecycle_transitions, median_lead_time,
    Merge, merge_ledger_text, merged_pull_requests, parse_spend_log,
    ratio_text, read_jsonl, read_merge_ledger, rolling_average, sparkline,
    tokens_text, union_merges, work_in_progress,
)

DEFAULT_LOG_PATH = "vizzer/velocity-log.jsonl"
DEFAULT_BUILDS_PATH = "vizzer/owner-builds.jsonl"
DEFAULT_MERGES_PATH = "vizzer/velocity-merges.json"
# Set by `stage_merge_ledger` on the graph a refresh is about to render.
_STAGED_MERGES_ATTR = "_velocity_staged_merges"
DEFAULT_WINDOW_DAYS = 28
DEFAULT_ROLLING_DAYS = 7


def _zone(cfg: Config) -> tzinfo:
    name = cfg.get("velocity.timezone", "UTC")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(str(name))
    except (ImportError, KeyError, ValueError) as exc:
        raise ValueError(f"unknown or unavailable velocity timezone: {name}") from exc


def _history(graph: Graph, cfg: Config, root: Path) -> dict:
    """The ledger this build staged, else the committed file (render-only path)."""
    if graph.progress_history:
        return graph.progress_history
    relpath = str(cfg.get("progress.history_path", "") or "")
    if not relpath:
        return {}
    if not (root / relpath).resolve().is_relative_to(root.resolve()):
        raise ValueError("progress history path escapes repository")
    try:
        return json.loads((root / relpath).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _fmt_lead(value: tuple[float | None, int]) -> str:
    """Median days with its sample size, so `—` reads as "nothing measurable" not "zero"."""
    days, samples = value
    return f"{days:.1f} d (n={samples})" if days is not None else f"— (n={samples})"


def _fmt_rate(value: float) -> str:
    return f"{value:.2f}"


def _cell(value: object) -> str:
    return html.escape(str(value)).replace("|", "&#124;").replace("`", "&#96;").replace("\n", " ").replace("\r", " ")


def _day_line(row: DayRow) -> str:
    bugs = f"{row.bug_opened}/{row.bug_closed}"
    prs = f"{row.prs} ({row.prs_visible}/{row.prs_infra})"
    return (
        f"| {row.day.isoformat()} | {_cell(row.host or '—')} | {row.shipped} | {row.started} | "
        f"{bugs} | {prs} | {row.builds} | {tokens_text(row.tokens_m)} | "
        f"{ratio_text(row.shipped, row.tokens_m)} | {ratio_text(row.prs, row.tokens_m)} |"
    )


def _host_line(summary: HostSummary) -> str:
    return (
        f"| {_cell(summary.host)} | {summary.days} | {summary.shipped} | "
        f"{_fmt_rate(summary.shipped_per_day)} | {summary.prs} | "
        f"{_fmt_rate(summary.prs_per_day)} | "
        f"{_fmt_lead((summary.lead_median, summary.lead_samples))} | "
        f"{tokens_text(summary.tokens_m)} | "
        f"{ratio_text(summary.shipped, summary.tokens_m)} |"
    )


def _visible_roots(cfg: Config) -> tuple[str, ...]:
    visible_roots = cfg.get("velocity.visible_roots", ["src/"])
    if not isinstance(visible_roots, (list, tuple)) or any(
        not isinstance(value, str) or not value or value.startswith("/")
        or ".." in value.split("/") for value in visible_roots
    ):
        raise ValueError("velocity.visible_roots must be repository-relative directory names")
    return tuple(value.rstrip("/") + "/" for value in visible_roots)


def _merges_relpath(cfg: Config) -> str:
    return str(cfg.get("velocity.merges_path", DEFAULT_MERGES_PATH))


def _merges_path(cfg: Config, root: Path) -> Path:
    path = root / _merges_relpath(cfg)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("velocity merge ledger path escapes repository")
    return path


def stage_merge_ledger(graph: Graph, cfg: Config, root: Path,
                       now: datetime | None = None) -> tuple[Path, str] | None:
    """WRITE path only (`refresh`): record new main-line PR merges.

    Reads Git once, unions what it saw into the committed ledger, stages the
    result on ``graph`` for this refresh's renderers, and returns the file to
    write. `check`, `render` and every renderer read the committed ledger and
    never Git, so the squash merge that lands a refreshed view cannot restale
    it: that merge is recorded by the NEXT refresh.
    """
    path = _merges_path(cfg, root)
    recorded, recorded_ref, _ = read_merge_ledger(path)
    window_days = int(cfg.get("velocity.window_days", DEFAULT_WINDOW_DAYS))
    moment = now or datetime.now(timezone.utc)
    since = moment - timedelta(days=window_days + 2)
    observed, ref = merged_pull_requests(root, since, _visible_roots(cfg))
    if ref is None and not recorded:
        return None
    merges = union_merges(recorded, observed, keep_days=window_days + 2)
    ledger_ref = ref or recorded_ref
    setattr(graph, _STAGED_MERGES_ATTR, (merges, ledger_ref))
    return path, merge_ledger_text(merges, ledger_ref)


def _merges(graph: Graph, cfg: Config, root: Path) -> tuple[list[Merge], str | None, list[str]]:
    """The merges this refresh staged, else the committed ledger. Never Git."""
    staged = getattr(graph, _STAGED_MERGES_ATTR, None)
    if staged is not None:
        return staged[0], staged[1], []
    path = _merges_path(cfg, root)
    return read_merge_ledger(path)


# One refresh renders dashboard.md, velocity.md, and the constellation from the
# same graph object; the summary is memoised on it so all three read ONE
# computation (one ledger read, one clock) rather than three that could disagree.
_MEMO_ATTR = "_velocity_summary_memo"


def velocity_summary(graph: Graph, cfg: Config, root: Path) -> dict:
    """Everything the velocity page, dashboard panel, and constellation need.

    Computed once per (graph, root, config) and memoised on the graph instance.
    """
    key = (str(Path(root).resolve()), id(cfg))
    memo = getattr(graph, _MEMO_ATTR, None)
    if memo is not None and memo[0] == key:
        return memo[1]
    summary = _compute_velocity_summary(graph, cfg, root)
    setattr(graph, _MEMO_ATTR, (key, summary))
    return summary


def _compute_velocity_summary(graph: Graph, cfg: Config, root: Path) -> dict:
    zone = _zone(cfg)
    window_days = int(cfg.get("velocity.window_days", DEFAULT_WINDOW_DAYS))
    rolling_days = int(cfg.get("velocity.rolling_days", DEFAULT_ROLLING_DAYS))
    if not 1 <= rolling_days <= window_days <= 366:
        raise ValueError("velocity requires 1 <= rolling_days <= window_days <= 366")
    visible_roots = _visible_roots(cfg)
    log_relpath = str(cfg.get("velocity.log_path", DEFAULT_LOG_PATH))
    builds_relpath = str(cfg.get("velocity.owner_builds_path", DEFAULT_BUILDS_PATH))
    for relpath in (log_relpath, builds_relpath):
        if not (root / relpath).resolve().is_relative_to(root.resolve()):
            raise ValueError("velocity input path escapes repository")

    history = _history(graph, cfg, root)
    transitions = lifecycle_transitions(history)
    leads = lead_times(transitions)
    wip = work_in_progress(history)

    spend_rows, spend_warnings = read_jsonl(root / log_relpath)
    spend = parse_spend_log(spend_rows)
    spend_warnings.extend(
        f"{entry.day}: multiple declared hosts; host and spend attribution withheld"
        for entry in spend if entry.note == "ambiguous hosts"
    )
    build_rows, build_warnings = read_jsonl(root / builds_relpath)
    builds = build_stamps(build_rows, zone)

    # Persisted merges only (see stage_merge_ledger): a renderer that read Git
    # would count the very merge that commits its output.
    merges, merge_ref, merge_warnings = _merges(graph, cfg, root)
    anchor = anchor_day(transitions, merges, spend, builds, zone)

    rows = day_rows(window_days, anchor, transitions, merges, spend, builds, zone) \
        if anchor else []
    cuts = host_cuts(rows)
    shipped_series = rolling_average([float(row.shipped) for row in rows], rolling_days)
    pr_series = rolling_average([float(row.prs) for row in rows], rolling_days)

    recent = rows[-rolling_days:]
    recent_days = {row.day for row in recent}
    recent_leads = {
        item_id: (shipped_at, days)
        for item_id, (shipped_at, days) in leads.items()
        if shipped_at.astimezone(zone).date() in recent_days
    }
    return {
        "zone": zone,
        "window_days": window_days,
        "rolling_days": rolling_days,
        "anchor": anchor,
        "updated_at": history.get("updatedAt") if isinstance(history, dict) else None,
        "current_host": next((row.host for row in reversed(rows) if row.host), None),
        "rows": rows,
        "cuts": cuts,
        "shipped_series": shipped_series,
        "pr_series": pr_series,
        "recent_shipped": sum(row.shipped for row in recent),
        "recent_prs": sum(row.prs for row in recent),
        "recent_days": len(recent),
        "recent_lead_median": median_lead_time(recent_leads),
        "window_lead_median": median_lead_time(
            leads,
            since=datetime.combine(rows[0].day, datetime.min.time(), tzinfo=zone)
            if rows else None,
        ),
        "wip": wip,
        "hosts": host_summaries(rows, leads, zone),
        "merge_ref": merge_ref,
        "log_relpath": log_relpath,
        "merges_relpath": _merges_relpath(cfg),
        "builds_relpath": builds_relpath,
        "visible_roots": visible_roots,
        "warnings": spend_warnings + build_warnings + merge_warnings,
    }


def _day_payload(row: DayRow) -> dict:
    return {
        "day": row.day.isoformat(),
        "host": row.host,
        "shipped": row.shipped,
        "started": row.started,
        "bugOpened": row.bug_opened,
        "bugClosed": row.bug_closed,
        "prs": row.prs,
        "prsVisible": row.prs_visible,
        "prsInfra": row.prs_infra,
        "builds": row.builds,
        "tokensM": row.tokens_m,
    }


def _host_payload(summary: HostSummary) -> dict:
    return {
        "host": summary.host,
        "days": summary.days,
        "shipped": summary.shipped,
        "shippedPerDay": summary.shipped_per_day,
        "prs": summary.prs,
        "prsPerDay": summary.prs_per_day,
        "leadMedianDays": summary.lead_median,
        "leadSamples": summary.lead_samples,
        "tokensM": summary.tokens_m,
    }


def _rate_block(rows: list[DayRow], lead: tuple[float | None, int]) -> dict:
    """Totals and per-day rates over ``rows``; rates are 0 when there are no days."""
    days = len(rows)
    shipped = sum(row.shipped for row in rows)
    prs = sum(row.prs for row in rows)
    builds = sum(row.builds for row in rows)
    lead_days, lead_samples = lead
    return {
        "days": days,
        "shipped": shipped,
        "shippedPerDay": shipped / days if days else 0.0,
        "prs": prs,
        "prsPerDay": prs / days if days else 0.0,
        "builds": builds,
        "buildsPerDay": builds / days if days else 0.0,
        "leadMedianDays": lead_days,
        "leadSamples": lead_samples,
    }


def velocity_payload(summary: dict) -> dict:
    """JSON-safe slice of the summary for ``DATA.velocity`` in the constellation.

    Same numbers the markdown views print, so the served dashboard and the
    exported files can never disagree on a rate.
    """
    rows: list[DayRow] = summary["rows"]
    anchor = summary["anchor"]
    return {
        "windowDays": summary["window_days"],
        "rollingDays": summary["rolling_days"],
        "anchor": anchor.isoformat() if anchor else None,
        "updatedAt": summary["updated_at"],
        "currentHost": summary["current_host"],
        # Window headline (the full 28-day default) and the trailing rolling span.
        "window": _rate_block(rows, summary["window_lead_median"]),
        "recent": _rate_block(rows[-summary["rolling_days"]:], summary["recent_lead_median"]),
        "wip": list(summary["wip"]),
        "days": [_day_payload(row) for row in reversed(rows)],
        "hosts": [_host_payload(host) for host in summary["hosts"]],
        "mergeRef": summary["merge_ref"],
        "logPath": summary["log_relpath"],
        "warnings": list(summary["warnings"]),
    }


def dashboard_panel(summary: dict) -> list[str]:
    """Compact velocity panel for the top of dashboard.md."""
    days = summary["recent_days"]
    if not days:
        return [
            "## Velocity",
            "",
            "No persisted lifecycle, merge, build, or spend evidence yet. "
            "See [velocity](velocity.md).",
            "",
        ]
    shipped = summary["recent_shipped"]
    prs = summary["recent_prs"]
    wip = summary["wip"]
    host = _cell(summary["current_host"] or "unrecorded")
    return [
        "## Velocity",
        "",
        f"Last {days} days ending {summary['anchor'].isoformat()} on `{host}`: "
        f"**{shipped} shipped** ({shipped / days:.2f}/day), **{prs} PRs merged** "
        f"({prs / days:.2f}/day), median lead time "
        f"{_fmt_lead(summary['recent_lead_median'])}, **{len(wip)} in "
        f"flight** (not evidence of completion). Full table, per-token ratios, and "
        "the host comparison: [velocity](velocity.md).",
        "",
    ]


def _velocity_view(summary: dict) -> str:
    rows: list[DayRow] = summary["rows"]
    window_days = summary["window_days"]
    rolling_days = summary["rolling_days"]
    updated = summary["updated_at"] or "unknown"
    host = _cell(summary["current_host"] or "unrecorded")
    anchor = summary["anchor"]

    lines = [
        "# Velocity",
        "",
        "Generated read-only view. Lineage: lifecycle events in the progress-history "
        "ledger (never status inferred from Git), pull-request merges on the main "
        f"line (`--first-parent`, subject `(#N)` or `Merge pull request #N`, read from `{summary['merge_ref'] or 'no git'}` "
        f"by the last `engine refresh` and persisted in `{summary['merges_relpath']}`), "
        "owner review-build stamps, and the declared token spend "
        f"log `{summary['log_relpath']}`.",
        "",
        f"**Window:** last {window_days} days ending {anchor.isoformat() if anchor else '—'} "
        f"(newest persisted evidence) · **ledger updatedAt:** `{updated}` · "
        f"**current host:** `{host}`",
        "",
    ]
    if not rows:
        lines.extend(["_No persisted lifecycle, merge, build, or spend evidence yet._", ""])
        return "\n".join(lines)

    lines.extend([
        "## Per day (newest first)",
        "",
        "Lifecycle columns are dated by the `engine refresh` that recorded the transition, "
        "not by the merge. Only transitions retained by the project's configured "
        "progress vocabulary can be counted; absent events are not proof of no regressions.",
        "",
        "| Day | Host | Shipped | →In flight | Bug-gaps open/closed | PRs (visible/infra) | "
        "Builds | Tokens (M) | Shipped/M | PRs/M |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    lines.extend(_day_line(row) for row in reversed(rows))

    days = summary["recent_days"]
    shipped = summary["recent_shipped"]
    prs = summary["recent_prs"]
    wip: list[str] = summary["wip"]
    lines.extend([
        "",
        f"**Rolling {rolling_days}-day:** shipped/day {shipped / days:.2f} · PRs/day "
        f"{prs / days:.2f} · median lead time (in-flight→shipped) "
        f"{_fmt_lead(summary['recent_lead_median'])} "
        f"(window median {_fmt_lead(summary['window_lead_median'])}) · "
        f"WIP {len(wip)} item(s) currently in-flight/building — not necessarily finished.",
        "",
    ])
    if wip:
        lines.append("WIP ids: " + ", ".join(f"`{_cell(item_id)}`" for item_id in wip))
        lines.append("")

    cuts = summary["cuts"]
    lines.extend([
        f"## Rolling {rolling_days}-day trend (oldest → newest; `|` marks a host change)",
        "",
        "```",
        f"shipped/day  {sparkline(summary['shipped_series'], cuts)}  "
        f"max {max(summary['shipped_series']):.2f}",
        f"PRs/day      {sparkline(summary['pr_series'], cuts)}  "
        f"max {max(summary['pr_series']):.2f}",
        "```",
        "",
        "## By host",
        "",
        "| Host | Days | Shipped | Shipped/day | PRs | PRs/day | Lead median | "
        "Tokens (M) | Shipped/M |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    lines.extend(_host_line(host_summary) for host_summary in summary["hosts"])
    lines.extend([
        "",
        "## Columns",
        "",
        "- **Shipped** — lifecycle events whose target is `shipped`.",
        "- **→In flight** — ledger events entering `in-flight` or `building`. The ledger "
        "only records transitions allowed by the project's vocabulary; omitted starts "
        "reduce measured counts and lead-time sample size.",
        "- **Bug-gaps open/closed** — events entering `bug-gap` / `bug-gap → shipped`. The "
        "ledger records configured forward transitions only; regression counts can be "
        "incomplete and are not a defect census.",
        "- **Lead time** — first `in-flight`/`building` event to `shipped`, per item; items "
        "that jumped straight to `shipped` have no measurable lead time and are not counted "
        "(that is what `n=` reports).",
        "- **PRs (visible/infra)** — main-line merges with `(#N)` or `Merge pull request #N` "
        "subjects; visible when any "
        f"touched file is under configured product roots `{', '.join(summary['visible_roots'])}` "
        "(tests excluded). This is path classification, not proof of visible UX delivery.",
        f"- **Builds** — declared review-build timestamps in `{summary['builds_relpath']}`.",
        "- **Tokens (M)** — declared spend from the log; `—` when not recorded. Host "
        "totals/ratios require every included day to have declared spend.",
        "- **Host** — carried forward from the last log line; a change is the cut line for the "
        "before/after comparison.",
        "",
        "_Lifecycle events land in the ledger only when `engine refresh` runs, so a day's "
        "shipped count can be credited late; the ledger `updatedAt` above bounds that lag. "
        "Merge counts are read from this checkout's main line, so a checkout whose main line "
        "differs re-renders different counts; run `engine refresh` after each merge._",
    ])
    for warning in summary["warnings"]:
        lines.append(f"- warning: {warning}")
    lines.append("")
    return "\n".join(lines)


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    return {"velocity.md": _velocity_view(velocity_summary(graph, cfg, root))}
