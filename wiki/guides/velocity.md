# Velocity: evidence, not a productivity score

The Dashboard summary, Velocity tab and `velocity.md` export share one computed
summary per render. Lifecycle counts come only from persisted progress history;
merge counts are separate Git first-parent observations. A merge is recognized
from GitHub's PR subject convention, not authenticated against GitHub's API.
WIP means the recorded status is building/in-flight, not that work is finished.

Optional `vizzer/vizzer.toml` configuration:

```toml
[velocity]
timezone = "UTC"
window_days = 28
rolling_days = 7
visible_roots = ["src/"]
log_path = "vizzer/velocity-log.jsonl"
owner_builds_path = "vizzer/owner-builds.jsonl"
```

The window must be 1–366 days; the rolling period must fit inside it. Product
roots are repository-relative directories; test directories do not count as
product source. “Visible” is only this path classification, not proof of UX.
Use project-specific roots for another layout. Input files must stay inside the
repository. Missing inputs produce explicit unknown/empty values, not inferred
token usage or lifecycle events. No logs are created by the renderer.

Spend records are JSON lines such as
`{"date":"2026-09-19","host":"build-a","tokens_m":2.5}`. The last record
for a day wins if its host agrees; conflicting hosts withhold attribution and
show a warning. The host label carries forward until replaced, while spend does
not. Build records require nonempty build and source identifiers:
`{"at":"2026-09-19T12:00:00Z","build":"42","sha":"..."}`.
These are declared inputs, not independently verified machine telemetry. Host
ratios require complete spend coverage for every included day. A comparison
between host periods does not establish the machine caused a throughput change.

The newest persisted evidence anchors the window. Only lifecycle events retained
by the project's configured progress vocabulary can be measured. Omitted starts
reduce lead-time sample size; omitted regressions cannot be counted. Git refs
and declared inputs can change output: refresh after updating them.

## Hierarchy foundations

`render.foundation_tiers_path` optionally names an in-repository JSON object
mapping tier names to epic IDs, e.g. `{"base":["epic:parser"]}`. Underscore-prefixed
metadata keys are ignored. Existing authored foundation tags remain supported;
the tier file is an additional explicit membership source, not inferred authority.

## Graph reload behavior

Read-only discussion/workstream/question HTTP requests may use the last parsed
graph during an incomplete replacement; the server logs that fallback. The cache
is per process and bounded to 16 paths. Each request gets its own mutable object.
Validation, render commands and editing use strict current reads. Restart clears
the fallback; permanently removed graphs require resync rather than reliance on
an old read-only view.
