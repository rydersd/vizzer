"""Flow-metric inputs for the velocity view: lifecycle events, merges, builds, spend.

Everything here is deterministic over persisted inputs. Lifecycle counts come
from the progress-history ledger only (never inferred from Git, per the
project's model-neutral rule). Git is consulted for exactly one thing, the
list of pull-request merges on the main line, and the view says so.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from statistics import median


ACTIVE_STATUSES = {"in-flight", "building"}
SHIPPED = "shipped"
BUG_GAP = "bug-gap"

# Configurable product-source classification, not a claim of user-visible UX.
VISIBLE_ROOTS = ("src/",)
# A directory segment naming tests (`tests`, `tests-ui`, `WidgetTests`).
TEST_SEGMENT = re.compile(r"(?i:(^|[-_])tests?($|[-_]))|Tests$")

# GitHub writes two merge-commit subjects: squash/rebase merges end in "(#N)",
# true merge commits start "Merge pull request #N from ...". Both are one PR.
PR_SUBJECT = re.compile(r"(?:\(#(\d+)\)\s*$|^Merge pull request #(\d+)\b)")
SPARK_BARS = "▁▂▃▄▅▆▇█"


def parse_stamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def local_day(moment: datetime, zone: tzinfo) -> date:
    return moment.astimezone(zone).date()


# ---------------------------------------------------------------- lifecycle


@dataclass(frozen=True)
class Transition:
    item_id: str
    at: datetime
    source: str
    target: str

    @property
    def shipped(self) -> bool:
        return self.target == SHIPPED

    @property
    def started(self) -> bool:
        return self.target in ACTIVE_STATUSES

    @property
    def bug_opened(self) -> bool:
        return self.target == BUG_GAP

    @property
    def bug_closed(self) -> bool:
        return self.source == BUG_GAP and self.target == SHIPPED


def lifecycle_transitions(history: dict) -> list[Transition]:
    """Every `lifecycle` event in the ledger, oldest first, malformed ones skipped."""
    items = history.get("items") if isinstance(history, dict) else None
    if not isinstance(items, dict):
        return []
    found: list[Transition] = []
    for item_id, record in items.items():
        events = record.get("events") if isinstance(record, dict) else None
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict) or event.get("kind") != "lifecycle":
                continue
            at = parse_stamp(event.get("at"))
            detail = event.get("detail")
            if at is None or not isinstance(detail, str) or "→" not in detail:
                continue
            source, target = (part.strip() for part in detail.rsplit("→", 1))
            found.append(Transition(str(item_id), at, source, target))
    found.sort(key=lambda t: (t.at, t.item_id, t.source, t.target))
    return found


def lead_times(transitions: list[Transition]) -> dict[str, tuple[datetime, float]]:
    """Per item: (shipped-at, days from first in-flight/building to shipped).

    Only items whose ledger shows both a start and a later ship qualify; an item
    that went straight to `shipped` has no measurable lead time and is left out
    rather than counted as zero.
    """
    started: dict[str, datetime] = {}
    result: dict[str, tuple[datetime, float]] = {}
    for transition in transitions:
        if transition.started and transition.item_id not in started:
            started[transition.item_id] = transition.at
        elif transition.shipped and transition.item_id in started \
                and transition.item_id not in result:
            begun = started[transition.item_id]
            days = (transition.at - begun).total_seconds() / 86400
            result[transition.item_id] = (transition.at, days)
    return result


def median_lead_time(leads: dict[str, tuple[datetime, float]],
                     since: datetime | None = None,
                     until: datetime | None = None) -> tuple[float | None, int]:
    """(median days, sample size) over items shipped inside [since, until)."""
    values = [
        days for shipped_at, days in leads.values()
        if (since is None or shipped_at >= since)
        and (until is None or shipped_at < until)
    ]
    return (median(values) if values else None), len(values)


def work_in_progress(history: dict) -> list[str]:
    """Ids whose persisted status is in-flight/building, not evidence of completion."""
    items = history.get("items") if isinstance(history, dict) else None
    if not isinstance(items, dict):
        return []
    return sorted(
        item_id for item_id, record in items.items()
        if isinstance(record, dict) and record.get("status") in ACTIVE_STATUSES
    )


# ------------------------------------------------------------------ merges


@dataclass(frozen=True)
class Merge:
    number: int
    at: datetime
    visible: bool


def classify_paths(paths: list[str], visible_roots: tuple[str, ...] = VISIBLE_ROOTS) -> str:
    """`visible` when any touched file is product source; otherwise `infra`."""
    for path in paths:
        parts = path.split("/")
        if not path.startswith(visible_roots):
            continue
        if any(TEST_SEGMENT.search(part) for part in parts[:-1]):
            continue
        return "visible"
    return "infra"


def parse_merge_log(text: str, visible_roots: tuple[str, ...] = VISIBLE_ROOTS) -> list[Merge]:
    """Parse `git log --format=M<TAB>%ct<TAB>%s --name-only` output into PR merges."""
    merges: list[Merge] = []
    current: tuple[int, datetime] | None = None
    paths: list[str] = []

    def flush() -> None:
        if current is not None:
            merges.append(Merge(current[0], current[1], classify_paths(paths, visible_roots) == "visible"))

    for line in text.splitlines():
        if line.startswith("M\t"):
            flush()
            current, paths = None, []
            fields = line.split("\t", 2)
            if len(fields) != 3:
                continue
            _, raw_epoch, subject = fields
            match = PR_SUBJECT.search(subject)
            if match and raw_epoch.isdigit():
                try:
                    current = (int(match.group(1) or match.group(2)),
                               datetime.fromtimestamp(int(raw_epoch), tz=timezone.utc))
                except (ValueError, OverflowError, OSError):
                    continue
        elif line.strip() and current is not None:
            paths.append(line.strip())
    flush()
    merges.sort(key=lambda m: (m.at, m.number))
    return merges


def main_line_ref(root: Path) -> str | None:
    """The main line to count merges on: origin/main, then main, then HEAD."""
    for ref in ("origin/main", "main", "origin/HEAD", "master", "HEAD"):
        try:
            probe = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", ref],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if probe.returncode == 0:
            return ref
    return None


def merged_pull_requests(root: Path, since: datetime,
                         visible_roots: tuple[str, ...] = VISIBLE_ROOTS) -> tuple[list[Merge], str | None]:
    """PR merges on the main line since `since`, plus the ref they were read from."""
    ref = main_line_ref(root)
    if ref is None:
        return [], None
    try:
        result = subprocess.run(
            [
                "git", "-C", str(root), "-c", "core.quotePath=false",
                "-c", "log.showSignature=false", "log", "--first-parent", "--diff-merges=first-parent", ref,
                f"--since={since.isoformat()}", "--format=M%x09%ct%x09%s", "--name-only",
            ],
            check=True, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return [], ref
    return parse_merge_log(result.stdout, visible_roots), ref


# ------------------------------------------------------ append-only ledgers


def read_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    """Objects from an append-only jsonl file; malformed lines are reported, not fatal."""
    if not path.exists():
        return [], []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [], [f"{path.name}: unreadable ({exc})"]
    rows: list[dict] = []
    warnings: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"{path.name}: line {number} is not JSON")
            continue
        if isinstance(value, dict):
            rows.append(value)
        else:
            warnings.append(f"{path.name}: line {number} is not an object")
    return rows, warnings


@dataclass
class SpendEntry:
    day: date
    host: str
    tokens_m: float | None
    note: str


def parse_spend_log(rows: list[dict]) -> list[SpendEntry]:
    """Last declaration per day, withholding ambiguous multi-host attribution."""
    by_day: dict[date, SpendEntry] = {}
    for row in rows:
        try:
            day = date.fromisoformat(str(row.get("date", "")))
        except ValueError:
            continue
        tokens = row.get("tokens_m")
        tokens_m = float(tokens) if isinstance(tokens, (int, float)) \
            and not isinstance(tokens, bool) else None
        if tokens_m is not None and (not math.isfinite(tokens_m) or tokens_m < 0):
            tokens_m = None
        host = row.get("host")
        prior = by_day.get(day)
        entry = SpendEntry(
            day=day,
            host=host.strip() if isinstance(host, str) and host.strip() else "unrecorded",
            tokens_m=tokens_m,
            note=str(row.get("note", "") or ""),
        )
        if prior is not None and (prior.host != entry.host or prior.note == "ambiguous hosts"):
            entry = SpendEntry(day, "unrecorded", None, "ambiguous hosts")
        by_day[day] = entry
    return [by_day[day] for day in sorted(by_day)]


def build_stamps(rows: list[dict], zone: tzinfo) -> dict[date, int]:
    """Owner review builds stamped per local day, from `{"at","build","sha"}` lines."""
    counts: dict[date, int] = {}
    for row in rows:
        build, sha = row.get("build"), row.get("sha")
        if (not isinstance(build, (str, int)) or isinstance(build, bool)
                or not str(build).strip() or not isinstance(sha, str) or not sha.strip()):
            continue
        at = parse_stamp(row.get("at"))
        if at is None:
            continue
        day = local_day(at, zone)
        counts[day] = counts.get(day, 0) + 1
    return counts


# ------------------------------------------------------------------- table


@dataclass
class DayRow:
    day: date
    host: str | None = None
    shipped: int = 0
    started: int = 0
    bug_opened: int = 0
    bug_closed: int = 0
    prs_visible: int = 0
    prs_infra: int = 0
    builds: int = 0
    tokens_m: float | None = None
    note: str = ""
    shipped_ids: list[str] = field(default_factory=list)

    @property
    def prs(self) -> int:
        return self.prs_visible + self.prs_infra


def _ratio(count: int, tokens_m: float | None) -> float | None:
    if tokens_m is None or tokens_m <= 0:
        return None
    return count / tokens_m


def ratio_text(count: int, tokens_m: float | None) -> str:
    value = _ratio(count, tokens_m)
    return "—" if value is None else f"{value:.2f}"


def tokens_text(tokens_m: float | None) -> str:
    return "—" if tokens_m is None else f"{tokens_m:g}"


def anchor_day(transitions: list[Transition], merges: list[Merge],
               spend: list[SpendEntry], builds: dict[date, int],
               zone: tzinfo) -> date | None:
    """Newest persisted evidence day. Refresh time is never the anchor."""
    candidates: list[date] = []
    if transitions:
        candidates.append(local_day(max(t.at for t in transitions), zone))
    if merges:
        candidates.append(local_day(max(m.at for m in merges), zone))
    if spend:
        candidates.append(max(entry.day for entry in spend))
    if builds:
        candidates.append(max(builds))
    return max(candidates) if candidates else None


def day_rows(window_days: int, anchor: date, transitions: list[Transition],
             merges: list[Merge], spend: list[SpendEntry],
             builds: dict[date, int], zone: tzinfo) -> list[DayRow]:
    """One row per day in the window, oldest first; hosts carry forward."""
    first = anchor - timedelta(days=window_days - 1)
    rows = {first + timedelta(days=offset): DayRow(first + timedelta(days=offset))
            for offset in range(window_days)}

    for transition in transitions:
        row = rows.get(local_day(transition.at, zone))
        if row is None:
            continue
        if transition.shipped:
            row.shipped += 1
            row.shipped_ids.append(transition.item_id)
        if transition.started:
            row.started += 1
        if transition.bug_opened:
            row.bug_opened += 1
        if transition.bug_closed:
            row.bug_closed += 1
    for merge in merges:
        row = rows.get(local_day(merge.at, zone))
        if row is None:
            continue
        if merge.visible:
            row.prs_visible += 1
        else:
            row.prs_infra += 1
    for day, count in builds.items():
        if day in rows:
            rows[day].builds = count

    # A host line is a cut, not a daily heartbeat: it stays in force until the
    # next line names a different host. Tokens are per-day declarations only.
    entries = {entry.day: entry for entry in spend}
    current_host: str | None = None
    for entry in spend:
        if entry.day < first:
            current_host = entry.host
    for day in sorted(rows):
        entry = entries.get(day)
        if entry is not None:
            current_host = entry.host
            rows[day].tokens_m = entry.tokens_m
            rows[day].note = entry.note
        rows[day].host = current_host
    return [rows[day] for day in sorted(rows)]


def rolling_average(values: list[float], span: int) -> list[float]:
    """Trailing mean over `span` entries; the first entries average what exists."""
    out: list[float] = []
    for index in range(len(values)):
        window = values[max(0, index - span + 1): index + 1]
        out.append(sum(window) / len(window) if window else 0.0)
    return out


def sparkline(values: list[float], cuts: set[int] | None = None) -> str:
    """Eight-level bar glyphs; `cuts` are indexes preceded by a `|` host-change marker."""
    if not values:
        return ""
    top = max(values)
    glyphs: list[str] = []
    for index, value in enumerate(values):
        if cuts and index in cuts:
            glyphs.append("|")
        level = 0 if top <= 0 else round((value / top) * (len(SPARK_BARS) - 1))
        glyphs.append(SPARK_BARS[max(0, min(level, len(SPARK_BARS) - 1))])
    return "".join(glyphs)


def host_cuts(rows: list[DayRow]) -> set[int]:
    """Row indexes where the host differs from the previous known host."""
    cuts: set[int] = set()
    previous: str | None = None
    for index, row in enumerate(rows):
        if row.host is not None and previous is not None and row.host != previous:
            cuts.add(index)
        if row.host is not None:
            previous = row.host
    return cuts


@dataclass
class HostSummary:
    host: str
    days: int
    shipped: int
    prs: int
    tokens_m: float | None
    lead_median: float | None
    lead_samples: int

    @property
    def shipped_per_day(self) -> float:
        return self.shipped / self.days if self.days else 0.0

    @property
    def prs_per_day(self) -> float:
        return self.prs / self.days if self.days else 0.0


def host_summaries(rows: list[DayRow],
                   leads: dict[str, tuple[datetime, float]],
                   zone: tzinfo) -> list[HostSummary]:
    """Before/after comparison: every distinct host value, in first-seen order."""
    order: list[str] = []
    buckets: dict[str, list[DayRow]] = {}
    for row in rows:
        host = row.host or "unrecorded"
        if host not in buckets:
            order.append(host)
            buckets[host] = []
        buckets[host].append(row)
    summaries: list[HostSummary] = []
    for host in order:
        host_rows = buckets[host]
        days = {row.day for row in host_rows}
        tokens = [row.tokens_m for row in host_rows if row.tokens_m is not None]
        lead_values = [
            days_taken for shipped_at, days_taken in leads.values()
            if local_day(shipped_at, zone) in days
        ]
        summaries.append(HostSummary(
            host=host,
            days=len(host_rows),
            shipped=sum(row.shipped for row in host_rows),
            prs=sum(row.prs for row in host_rows),
            tokens_m=sum(tokens) if len(tokens) == len(host_rows) else None,
            lead_median=median(lead_values) if lead_values else None,
            lead_samples=len(lead_values),
        ))
    return summaries
