"""Optional deterministic agent-operations telemetry perspective."""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from statistics import median

from ..agent_lanes import AgentLaneError, read_ledger
from ..config import Config
from ..model import Graph


BURN_RE = re.compile(
    r"^> Burn: est (?P<est>[^·\s]+) .*? actual ~?(?P<actual>[^·\n]+) "
    r"· lane (?P<lane>[^\s·]+)", re.MULTILINE,
)
DURATION_RE = re.compile(r"(?:(?P<hours>\d+)h)?\s*(?:(?P<minutes>\d+)m)?")


def _time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed(start, end):
    left, right = _time(start), _time(end)
    return max(0.0, (right - left).total_seconds()) if left and right else None


def _duration(seconds) -> str:
    if seconds is None:
        return "unknown"
    minutes = int(seconds // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _number(values, percentile=None) -> str:
    values = sorted(values)
    if not values:
        return "—"
    if percentile is None:
        value = median(values)
    else:
        value = values[int((len(values) - 1) * percentile + .999999)]
    return f"{int(value):,}"


def _burns(root: Path, glob: str) -> dict[str, list[tuple[str, float]]]:
    result = {}
    if not glob:
        return result
    try:
        paths = root.glob(glob)
    except (NotImplementedError, ValueError, OSError):
        return result
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for match in BURN_RE.finditer(text):
            duration = DURATION_RE.fullmatch(match.group("actual").strip())
            if duration is None:
                continue
            seconds = float(
                int(duration.group("hours") or 0) * 3600
                + int(duration.group("minutes") or 0) * 60
            )
            observation = (match.group("est"), seconds)
            values = result.setdefault(match.group("lane"), [])
            if observation not in values:
                values.append(observation)
    return result


def _markdown(records: list[dict], burns: dict[str, list[tuple[str, float]]]) -> str:
    lanes = {
        record["lane"]: record for record in records
        if record.get("kind", "lane") == "lane"
    }
    samples = {}
    for record in records:
        if record.get("kind") == "sample":
            lane = record["lane"]
            if lane not in samples or record.get("at", "") > samples[lane].get("at", ""):
                samples[lane] = record
    terminal = [record for record in lanes.values() if record.get("outcome")]
    lines = [
        "# Agent operations telemetry", "",
        "Read-only projection of the configured append-only lane ledger and optional "
        "authored Burn stamps. Agent reports remain claims; verified outcomes stay "
        "separate.", "", "## Lanes now", "",
        "| Lane | State | Log age | Elapsed since dispatch |",
        "|---|---|---:|---:|",
    ]
    live = [record for record in lanes.values() if not record.get("outcome")]
    for record in sorted(live, key=lambda value: value["lane"]):
        sample = samples.get(record["lane"], {})
        age = sample.get("logAgeSeconds")
        lines.append(
            f"| `{record['lane']}` | `{sample.get('state', 'unobserved')}` | "
            f"{f'{age}s' if age is not None else 'no sample'} | "
            f"{_duration(_elapsed(record.get('dispatched'), sample.get('at')))} |"
        )
    if not live:
        lines.append("| — | No undischarged lanes recorded | — | — |")

    lines.extend([
        "", "## Model scoreboard", "",
        "| Model × effort | Lanes | Merged | Blocked | Rework / killed | "
        "Wanders | Median tokens | Median wall-clock |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    groups = {}
    for record in terminal:
        groups.setdefault((record["model"], record["effort"]), []).append(record)
    for (model, effort), group in sorted(groups.items()):
        outcomes = [record.get("outcome") for record in group]
        wall = [
            value for record in group
            if (value := _elapsed(record.get("dispatched"), record.get("terminal")))
            is not None
        ]
        lines.append(
            f"| `{model}` × `{effort}` | {len(group)} | {outcomes.count('merged')} | "
            f"{sum(value in {'blocked-spec', 'blocked-env'} for value in outcomes)} | "
            f"{sum(value in {'rework', 'killed'} for value in outcomes)} | "
            f"{sum(len(record.get('wander', [])) for record in group)} | "
            f"{_number([record['tokens'] for record in group])} | "
            f"{_duration(median(wall)) if wall else '—'} |"
        )
    if not groups:
        lines.append("| — | 0 | 0 | 0 | 0 | 0 | — | — |")

    by_est = {}
    for record in terminal:
        for estimate, seconds in burns.get(record["lane"], []):
            by_est.setdefault(estimate, []).append((seconds, float(record["tokens"])))
    lines.extend([
        "", "## Sizing calibration", "",
        "| Authored estimate | Count | Median actual | P90 actual | Median tokens |",
        "|---|---:|---:|---:|---:|",
    ])
    for estimate, values in sorted(by_est.items()):
        durations = [value[0] for value in values]
        tokens = [value[1] for value in values]
        lines.append(
            f"| {estimate} | {len(values)} | {_duration(median(durations))} | "
            f"{_duration(sorted(durations)[int((len(durations)-1)*.9+.999999)])} | "
            f"{_number(tokens)} |"
        )
    if not by_est:
        lines.append("| — | 0 | — | — | — |")
    lines.append("")
    return "\n".join(lines)


def _html(markdown: str) -> str:
    escaped = html.escape(markdown)
    return (
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Agent operations</title><style>body{max-width:1100px;margin:auto;"
        "padding:28px;background:#14161a;color:#e7e9ee;font:14px/1.5 system-ui}"
        "pre{white-space:pre-wrap}</style><pre>" + escaped + "</pre></html>"
    )


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    del graph
    if not cfg.get("agent_ops.enabled", False):
        return {}
    relpath = cfg.get("agent_ops.ledger_path")
    try:
        records = read_ledger(root, relpath, strict=True)
    except AgentLaneError as exc:
        markdown = f"# Agent operations telemetry\n\n**Ledger unavailable:** {exc}\n"
    else:
        markdown = _markdown(
            records, _burns(root, cfg.get("sources.spec_tree.glob", "")),
        )
    return {"agent-ops.md": markdown, "agent-ops.html": _html(markdown)}
