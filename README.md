# vizzer

Turn whatever your project uses to track work — spec trees, continuity ledgers,
loose docs, TODO lists — into **one normalized work graph** and a set of
regenerable views: a dependency-ordered roadmap, a searchable feature index, a
"what do I work on today" dashboard, a completion sheet, a ledger table, a
machine-readable tracked-item manifest, and an interactive 3D constellation.

Vizzer is **LLM-first**: it installs itself *inside* your project as a
self-contained directory (no PATH, no venv, no dependencies beyond system
`python3`) and registers itself in your `CLAUDE.md`/`AGENTS.md` so any agent
session discovers the graph and keeps it fresh.

## 60-second quickstart

```bash
curl -LO https://github.com/rydersd/vizzer/releases/latest/download/vizzer.pyz
python3 vizzer.pyz          # interactive: pick your project directory
```

The installer scans the project, detects which source shapes exist, writes a
commented `vizzer/vizzer.toml`, vendors the engine, registers the agent-facing
block, and runs the first refresh. From then on, from the project root:

```bash
python3 vizzer/engine refresh   # re-read sources → graph → every view
python3 vizzer/engine sync      # graph only, for inspection or automation
python3 vizzer/engine render    # render an already-synced graph only
python3 vizzer/engine check     # exit 1 if graph/views are stale (CI-friendly)
python3 vizzer/engine serve     # loopback constellation; story links open in default app
python3 vizzer/engine open story:some-id  # validated direct source opener
python3 vizzer/engine plan analyze --promote story:some-id
python3 vizzer/engine plan apply --promote story:some-id --expected-revision 0 --rationale "why"
```

Use `refresh` whenever a task completes, an issue is found, or a story's
status or dependencies change. Update the configured source document first;
the graph and views are derived and are never a write-back surface.

Non-interactive: `python3 vizzer.pyz install <path>`. Upgrading later:
`python3 vizzer.pyz update <path>` — replaces the vendored engine and the
managed doc block, never touches your config, graph, or views.

## The views (`vizzer/views/`)

| View | What it answers |
|---|---|
| `dashboard.md` | What do I work on today? Active milestone, in-progress and regression buckets, dependency-satisfied ready queue, decision-blocked items. |
| `roadmap.md` | In what order does everything ship? Topologically sorted waves per release. |
| `feature-index.md` | Cmd-F over every behavior, grouped by your hierarchy, with status. |
| `completion-sheet.md` | Counts by status, group, and wave; verified-rate; debt tally. |
| `ledger-table.md` | One row per continuity ledger: goal, current phase, progress bar, staleness. |
| `manifest.json` | Machine-readable index of docs represented by enabled adapters (titles, statuses, git dates). It is not a whole-repository corpus manifest unless the configured adapters cover that corpus. |
| `constellation.html` | Self-contained interactive 3D map with switchable Delivery, Activity, Structure, and Progress lenses plus tokenized local search across story, hierarchy, source, and live-work text. <!-- codex-sequence-2026-08-08 --> |

## The graph contract

`vizzer/vizzer-graph.json` is **derived** — regenerate it with `refresh` (or
`sync` when you intentionally need graph-only output), never
hand-edit it. Your source files stay the truth; the graph is the merge. When
two sources disagree about an item's status, the higher-precedence source wins
**and the disagreement is recorded** in the graph's `conflicts` array and
printed by `sync`. Nothing is silently resolved.

Output is deterministic (stable sorting, no wall-clock timestamps — dates come
from git), so graph and view diffs stay small and reviewable.

## Sources

Four adapters ship in v1; enable any mix in `vizzer.toml`:

- **`spec_tree`** — nested work-item markdown (any `a/*/b/*/stories/*.md`
  shape; level names are yours). Reads status/release/deps from headers or
  YAML front-matter. An explicit empty dependency declaration remains
  authoritative over a lower-precedence import. Can also import a legacy DAG JSON during migration,
  including optional milestone phase membership.
- **`ledgers`** — `CONTINUITY_*.md` session ledgers: goals, phase checkboxes
  (`[x]` / `[→]` / `[ ]`), open questions.
- **`loose_docs`** — any markdown glob; front-matter when present, title +
  git dates otherwise. The works-on-any-repo floor.
- **`todos`** — `TODO.md`-style checkbox lists.

## Configuration (`vizzer/vizzer.toml`)

The one file you edit. Keys and defaults:

| Key | Default | Meaning |
|---|---|---|
| `project.name` | `"project"` | Used in view titles. |
| `sources.spec_tree.glob` | `""` | Story-file glob; each `*` directory is a hierarchy level. |
| `sources.spec_tree.levels` | `[]` | Names for those levels, e.g. `["capability", "epic"]`. |
| `sources.spec_tree.item_kind` | `"story"` | Id prefix for items. |
| `sources.spec_tree.dag_import` | `""` | Optional legacy DAG JSON to merge. |
| `sources.ledgers.glob` | `"thoughts/ledgers/CONTINUITY_*.md"` | Ledger locations. |
| `sources.loose_docs.globs` | `[]` | Doc globs, e.g. `["docs/**/*.md"]`. |
| `sources.todos.globs` | `["TODO.md"]` | Checkbox files. |
| `render.output_dir` | `"vizzer/views"` | Where views go. |
| `render.releases` | `["R0","R1","R2","R3"]` | Release wave names/order. |
| `render.recommended` | `[]` | Item ids highlighted as next steps in the constellation. |
| `render.title` | `""` | Constellation title override. |
| `render.obsidian_links` | `false` | Embed absolute-path `obsidian://` links (local vaults only). |
| `render.repo_url` | `""` | Base URL for source links in the constellation. |
| `reconcile.precedence` | `["spec_tree","dag_import","ledgers","todos","loose_docs"]` | Who wins disagreements. |
| `reconcile.dependency_authority` | `""` | Optional adapter whose dependency field wins during a staged authority migration, without stealing story title/status/source provenance. |
| `reconcile.mention_globs` | `[]` | Docs scanned for activity mentions. |
| `reconcile.staleness_days` | `14` | Ledger staleness threshold. |
| `archive.adapters` | `["todos"]` | Which adapters' files `archive` may move. |
| `priority.enabled` | `false` | Enable target-scoped, explainable uptake ranking. |
| `priority.target_manifest` | `""` | Strongest target tier: repo-relative schema-1 JSON with `directTargetIds`. |
| `priority.target_items` | `[]` | Explicit target ids when no manifest is configured. |
| `priority.target_milestones` | `[]` | Target authored milestones when no stronger tier is configured. |
| `priority.target_releases` | `[]` | Target releases only when no stronger tier is configured. |
| `priority.limit` | `10` | Maximum recommendations rendered. |
| `planning.enabled` | `false` | Enable accepted owner course overlays and loopback planning controls. |
| `planning.overlay_path` | `"vizzer/planning-overlay.json"` | Versioned, repo-local priority overlay; never a story write-back surface. |
| `activity.path` | `""` | Optional repo-relative schema-1 live-agent checkpoint feed. |
| `activity.stale_after_minutes` | `120` | Age after which work stays visible but stops animating. |
| `progress.history_path` | `""` | Optional generated semantic-history ledger; never hand-edit it. |
| `progress.hot_window_days` | `7` | Brightness window for recent progress trails. |
| `progress.stalled_after_days` | `14` | No-progress age before previously started work shows `?`. |
| `progress.stall_max_days` | `90` | Marker-growth cap for long stalls. |
| `progress.backfill_days` | `7` | One-time exact-header Git lookback when history is introduced. |

Three table-arrays: `[[status]]` replaces the status vocabulary (`name`,
`emoji`, `done`, optional dashboard `role`, optional `description`, and
optional `next`); `[[gates]]` marks items blocked on a decision (`item`,
`reason`); and repeatable `[[group]]` entries add a hierarchy level that the
directory tree does not encode, such as product or team. A group entry has an
`id`, an optional `title` (derived from the id when omitted), and `contains`, a
list of existing group or item ids:

```toml
[[group]]
id = "product:time"
title = "Time"
contains = ["capability:billing", "capability:first-session"]
```

The named children are re-parented in the generated graph; no source files or
cross-links need to move.

## Relations, priority, and live activity

Hard prerequisites stay in `deps`; only those edges affect readiness. Explicit
`Revises`, `Bug against`, and DAG `contractDeps.roots` become typed nonblocking
relations. Foundation roots are visible structure, not a sneaky way to make every
story depend on everything. <!-- codex-sequence-2026-08-08 -->

Priority is opt-in and target-scoped. Its target precedence is manifest, explicit
items, milestones, releases, then the first incomplete milestone/release fallback.
Each recommendation persists its direct-target flag, unique incomplete target
dependents, condensed critical-path depth, milestone membership, lifecycle-role
bias, and appetite cost. Activity and mention counts are deliberately excluded:
attention is not impact. A malformed authored target tier warns and produces no
recommendations instead of silently widening scope.

Planning is a separate owner-authored course overlay. A promotion adds a direct
target, a deferral removes that target from the effective course without changing
its story status or dependency edges, and ordering breaks uptake ties through the
ordered target's prerequisite closure. The base target manifest remains intact and
visible as `base_targets`; the composed result is `effective_targets`. `plan
analyze` is read-only and reports new prerequisite closure, ready/blocked impact,
displaced recommendations and V1 targets, milestone/release implications, and
provenance. `plan apply` requires an explicit rationale and expected revision,
writes atomically, records an audit revision, refreshes derived views, and fails a
stale browser/CLI revision instead of winning silently. `plan undo` restores the
prior accepted state as another audited revision.

The self-contained `file://` constellation only displays the accepted course.
Priority controls appear under `vizzer serve`; writes require same-origin loopback
requests plus a per-server CSRF token. The endpoint accepts graph item IDs, never
paths, and validates every ID against the current graph.

The optional activity feed records a story id, agent/task label, state, exact
`completed/total` checkpoints, timestamp, current checkpoint, and optional explicit
related story ids. Active nodes pulse; explicitly authored active links pulse;
dependency edges merely touching active work receive steady emphasis so the view
does not claim the relation itself is being edited. Stale, blocked, paused, and
complete records remain inspectable but do not pulse. `prefers-reduced-motion` is
honored. Delivery, Activity, Structure, and Progress are independently switchable
lenses.

Progress history is narrower than generic Git activity on purpose. Only forward
lifecycle transitions, removed hard dependencies, and increased explicit checkpoint
counts create a `+` trail. A one-time Git backfill compares exact historical
`Status`/`Deps` headers and ignores prose-only commits. Only work with recorded
start/eligibility evidence can become stalled; untouched idea, backlog, parked, and
unknown work never receives a `?`. The graph stores stable timestamps and anchors;
the browser derives brightness, age text, and marker size at display time so an
unchanged project does not become stale merely because a clock advanced.

Constellation file mode uses portable repo-relative Markdown links. `serve` binds
only `127.0.0.1` (an ephemeral port by default); its POST-only item-id endpoint
resolves the current graph source inside the repository, rejects traversal,
unknown/missing sources, and then delegates to the platform default application.
No checked-in view needs an absolute workstation path. The explicit Obsidian link
option remains available for local vault users. <!-- codex-sequence-2026-08-08 -->

Status `role` controls dashboard placement. Built-in roles are `active`,
`regression`, `ready`, `done`, and `hold`; project-specific role names are
allowed but are not rendered into a built-in queue. Omitting `role` preserves
the pre-role lifecycle behavior. When a configured DAG contains `milestones`,
Vizzer preserves their authored phase order and renders the first incomplete
milestone in `dashboard.md`. <!-- codex-sequence-2026-08-08 -->

`description` documents the meaning of a status. `next` is an optional list
of allowed successor status names: omitting it preserves the legacy
unconstrained lifecycle, while `next = []` declares a terminal status. Vizzer
validates duplicate names, malformed metadata, undefined successor names, and
attempts to move a `done = true` status back to unfinished work before any
derived artifact is written. A shipped story should stay shipped; capture a
regression or follow-up as separate work (or a configured flag/gate), rather
than silently downgrading the completed story. <!-- codex-sequence-2026-08-08 -->

Config is parsed by a small built-in TOML subset (sections, table-arrays,
strings/bools/ints/string-arrays) so the engine stays stdlib-only on
Python ≥ 3.9.

## Archiving (opt-in, off by default)

`python3 vizzer/engine archive --yes` moves fully-ingested source files (by
default only TODO files) into `vizzer/archive/`, which is gitignored.
**Archived files leave git tracking** — the command warns and refuses to run
without `--yes`. Widen the scope via `archive.adapters` only if you mean it.

## How agents use this

Installation appends a managed block to your `CLAUDE.md` or `AGENTS.md`
(created if neither exists) between `<!-- vizzer:begin -->` /
`<!-- vizzer:end -->` markers — it tells agent sessions to read the graph for
orientation, update source stories/issues/ledgers first, then run `refresh`
after completion, issue discovery, status changes, or dependency changes.
`update` rewrites only that block; your other instructions are never touched.

## Safety

Vizzer never executes project code. It reads files and git history, and writes
only inside `vizzer/` plus the managed doc block and one `.gitignore` line.

## License

MIT.
