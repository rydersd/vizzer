# Vizzer — Portable Work-Graph Views — Design

> Status: approved (owner, 2026-08-06)
> Origin: generalization of a private, single-project set of spec-view generator
> scripts (roadmap, dashboard, completion sheet, constellation, manifest) into a
> public, project-agnostic tool.

## Purpose

Vizzer turns whatever a project uses to track work — spec trees, continuity
ledgers, loose docs, TODO lists — into one normalized, checked-in work graph
and a set of regenerable views: roadmap, feature index, daily dashboard,
completion sheet, ledger table, corpus manifest, and an interactive 3D
constellation. It is LLM-first: it installs itself *inside* the target project
as a self-contained directory and registers itself in the project's agent
instructions (CLAUDE.md / AGENTS.md) so any future agent session discovers and
maintains it.

Success criteria:

1. `install → refresh` works on a repo vizzer has never seen, with zero
   dependencies beyond system `python3` (≥3.10).
2. The generated views on a real project are as useful as the single-project
   originals this design generalizes, with no project-specific content in code.
3. An agent session opening a vizzer-enabled project knows the tool exists,
   where the graph is, and when to refresh it — from the managed
   CLAUDE.md/AGENTS.md block alone.

## Decisions (settled during brainstorming, owner-approved)

| Decision | Choice |
|---|---|
| Organizing role | Vizzer maintains a **derived, checked-in graph file** (`vizzer-graph.json`) reconciled from sources. Sources stay authoritative; the graph is regenerable. |
| Distribution | Public repo shipping a single-file `vizzer.pyz` (stdlib zipapp; also `uvx`/`pipx` installable). Running it **vendors a self-contained engine into the target project** — no PATH/venv/install for cloners, CI, or agent sandboxes. |
| v1 adapters | spec-tree markdown, continuity ledgers, loose docs + front-matter, TODO/checkbox files. |
| Write-back | Opt-in only: `archive` moves fully-ingested source files into a gitignored subdirectory. Requires `--yes`; warns that archived files leave git tracking. Never a default, never a delete. |
| Architecture | Adapter → normalized graph → renderer pipeline — one parser, one vocabulary, one refresh cadence by construction (see "Defects fixed" for everything this structure eliminates). |
| Repo visibility | Public. MIT license. Synthetic test fixtures only — no private-project or personal content in code, fixtures, or default output. |
| In-project directory name | `vizzer/` at project root (visible, not hidden). |

## In-project footprint

```
<project>/vizzer/
├── engine/              # vendored stdlib-only package; never hand-edited
├── VERSION              # engine version stamp, read by `update`
├── vizzer.toml          # generated at install from source detection; the ONE file users edit
├── vizzer-graph.json    # derived graph (committed; deterministic, stable-sorted, timestamp-free)
├── views/               # roadmap.md, feature-index.md, dashboard.md, completion-sheet.md,
│                        # ledger-table.md, spec-manifest.json, constellation.html
└── archive/             # gitignored; exists only if the user opts into archiving
```

Invocation from project root: `python3 vizzer/engine <verb>`.

## CLI verbs

Downloadable tool (`vizzer.pyz` / `uvx vizzer`):

- **(no args)** — interactive install: pick or paste target directory → scan →
  show detected sources → confirm → vendor `engine/`, write `vizzer.toml`,
  append `.gitignore` entry, register the harness block, first `refresh`.
- **`install <path>`** — same, non-interactive.
- **`update <path>`** — re-vendor `engine/` and rewrite the managed
  CLAUDE.md/AGENTS.md block; never touches `vizzer.toml`, graph, or views.

Vendored engine (`python3 vizzer/engine …`):

- **`sync`** — run adapters, reconcile, write `vizzer-graph.json`; print
  warning + conflict summary.
- **`render [--only view,…]`** — regenerate views from the graph only (never
  re-parses sources).
- **`refresh`** — sync then regenerate every view from the graph built in that
  same invocation. A failed sync never renders the prior graph as if it were
  current. This is the normal task-completion and issue-discovery command.
- **`check`** — exit 1 if graph or views are stale vs sources. Two modes, following the
  prior art: full, and `--structural` (ignores git-date fields;
  pre-commit-safe).
- **`archive --yes`** — move fully-ingested originals to `vizzer/archive/`.

## Harness registration

Install detects `CLAUDE.md` / `AGENTS.md` (offers to create `AGENTS.md` if
neither exists) and appends an idempotent managed block:

```markdown
<!-- vizzer:begin (managed — do not hand-edit; `update` rewrites this block) -->
## Vizzer — project work-graph views
- `vizzer/vizzer-graph.json` is the normalized index of this project's work items
  (from specs/ledgers/docs). Read it for orientation; NEVER hand-edit — it's derived.
- Update authoritative source stories/issues/ledgers first. After a task completes,
  an issue is discovered, or story status/dependencies change: run
  `python3 vizzer/engine refresh`. A shipped story stays shipped; follow-up issues
  become separate work or flags rather than a status downgrade.
- `python3 vizzer/engine check` gates staleness (CI/pre-commit friendly).
- Views live in `vizzer/views/` — dashboard.md answers "what next";
  constellation.html is the 3D map.
<!-- vizzer:end -->
```

Optional (yes/no prompt at install): drop `.claude/skills/vizzer/SKILL.md` for
Claude Code projects.

## Graph schema (`vizzer-graph.json`, `"schema": 1`)

```json
{
  "schema": 1,
  "groups": [{"id": "cap:canvas", "kind": "capability|epic|ledger|folder",
              "title": "…", "parent": null}],
  "items": [{"id": "story:snap-to-grid", "title": "…", "one_liner": "…",
             "status": "specced", "release": "R0", "wave": null,
             "group": "epic:drawing-tools", "deps": ["story:canvas-core"],
             "relations": [{"kind": "foundation_root",
                             "target": "foundation:geometry-kernel"}],
             "appetite": "medium", "flags": ["debt"],
             "source": {"adapter": "spec_tree", "path": "wiki/…/snap-to-grid.md"},
             "activity": {"commits": 4, "mentions": 2, "last_touched": 1754400000}}],
  "milestones": [{"id": "M1", "title": "Usable slice", "goal": "…",
                  "phases": [{"name": "Floor", "items": ["story:snap-to-grid"]}]}],
  "conflicts": [{"item": "story:x", "field": "status",
                 "kept": {"adapter": "spec_tree", "value": "building"},
                 "dropped": {"adapter": "dag_import", "value": "specced"}}],
  "warnings": ["dangling dep story:y → story:missing (edge dropped)"],
  "vocab": {"statuses": [{"name": "specced", "emoji": "📝", "done": false,
                            "role": "ready"}, "…"]}
}
```

- Item IDs are `<kind>:<slug>`, derived from file paths, stable across runs.
- Every item carries provenance (adapter + path) — views link back, and
  `archive` knows which files are fully ingested.
- Status vocabulary lives in config; each status declares `done: true/false`,
  so dependency satisfaction is data, not code.
- A status may declare a dashboard `role`; this keeps active implementation,
  regression queues, ready work, done work, and held work as project data.
- A status may document itself with `description` and constrain source-editor
  integrations with `next`. Omitted `next` remains unconstrained for existing
  vocabularies; explicit successors must exist, and done statuses may not lead
  back to unfinished work. Vizzer validates this config before writing output.
- A DAG import may carry ordered milestones and phases. They are derived
  planning metadata and never become a write-back authority.
- Typed relations are explicit, nonblocking edges; only `deps` changes readiness.
  A DAG's explicit `contractDeps.roots` may materialize foundation group targets,
  but prose resemblance is never promoted to graph truth.
- Optional priority metadata is derived from an explicit target scope and persists
  every score component. Optional live-agent activity persists named checkpoint
  counts and timestamps as a switchable overlay; neither may rewrite lifecycle or
  dependencies. <!-- codex-sequence-2026-08-08 -->
- Optional planning composes a revisioned owner course over the target scope without
  rewriting source contracts. Optional progress history records only semantic header
  and checkpoint advances; elapsed age remains browser-derived presentation so a
  no-op `check` stays deterministic. <!-- codex-sequence-2026-08-08 -->
- Output is stable-sorted and timestamp-free (git supplies dates) → small,
  reviewable diffs.

<!-- codex-sequence-2026-08-08: implementation extension required for shadow parity. -->

## Adapters

Common contract: `scan(config, repo) → (groups, items, milestones, warnings)`. Adapters
only read and emit; the reconciler owns merging, conflicts, and writes. New
adapters (GitHub issues, Linear, …) touch nothing else.

1. **`spec_tree`** — nested work-item trees. Directory shape is config
   (default mirrors `capabilities/*/epics/*/stories/*.md`; depth and level
   names declared in `vizzer.toml`). Parses title (`# Story:` or plain H1 or
   front-matter), `> Status:`, `Release:`, `Wave:`, `Appetite:`, `> Debt:`,
   `## Intent` one-liner. Deps come from a `> Deps:` line or front-matter
   `deps:` list in the item file. A config key may point at an existing
   external DAG JSON to import deps/status (migration path for projects whose deps already live in a DAG file).
   Optional DAG milestones preserve ordered phase membership for the dashboard.
   Explicit empty story dependency declarations beat a lower-precedence DAG;
   absence and an authored empty set are not conflated.
2. **`ledgers`** — `CONTINUITY_*.md`. Ledger → group (carries Goal); each
   phase checkbox → item (`[x]` → done-status, `[→]` → in-progress, `[ ]` →
   pending); open-questions count as metadata.
3. **`loose_docs`** — configured `.md` globs. Front-matter fields used when
   present; otherwise title + git dates + synopsis only. The
   works-on-any-repo floor; feeds the manifest as a general corpus index.
4. **`todos`** — `TODO.md` / checkbox inventories → flat backlog items,
   checked → done.

## Reconciliation

- Same item described by multiple sources → precedence is explicit config
  (default: story file beats imported DAG — the human-edited doc is truth).
  Every disagreement lands in the graph's `conflicts` array AND in `sync`
  output. Visible, never silent.
- During a staged migration, optional `reconcile.dependency_authority` selects
  only the dependency field's winning adapter; story provenance and lifecycle
  continue to follow normal precedence. <!-- codex-sequence-2026-08-08 -->
- Dangling deps → warning, edge dropped, never a crash.
- Git metadata in one pass: a single cached `git log --name-only` walk yields
  created/modified dates, per-item commit counts, last-touched epochs;
  mention counts scan configurable corpora globs (defaults: docs dirs,
  ledgers).

## Renderers

Pure functions over the graph; they cannot disagree with each other.

1. **roadmap.md** — dependency-ordered (topo-sorted) waves per release;
   release names/labels from config; cycle-tolerant (falls through with the
   remainder appended, following the prior art).
2. **feature-index.md** — Cmd-F behavior table grouped by top two group
   levels.
3. **dashboard.md** — first incomplete milestone, role-classified in-progress
   and regression queues, dependency-satisfied ready queue,
   blocked items with the blocking gate named. Decision gates are a
   `[gates]` table in `vizzer.toml` (the originals hardcoded them in source).
4. **completion-sheet.md** — status counts overall / by group / by wave, debt
   tally, verified-rate; vocabulary + done-semantics from config.
5. **ledger-table.md** *(new)* — one row per ledger: goal, current `[→]`
   phase, done/total with progress bar, open-questions count, last-touched,
   staleness flag (configurable threshold).
6. **manifest.json** — index of documents represented by enabled adapters
   (title, status, synopsis, git dates, kind) with kind classification from
   adapter provenance, not path regexes. It is not a complete repository
   corpus inventory unless adapter coverage is complete; projects with a
   broader canonical corpus manifest must retain it during migration.
7. **constellation.html** — ported 3D template (self-contained, no external
   deps, light/dark) with: title/legend/status colors injected from config;
   recommended-next highlight read from an optional `recommended` list in
   `vizzer.toml` (replaces next-steps.json); independent Delivery, Activity,
   Structure, and Progress lenses; local search; loopback source opening; guarded
   planning controls; and `obsidian://` absolute-path links opt-in and off by
   default (no absolute paths in default output).

## Error handling

Malformed source files never crash a run — the item enters the graph with
`status: "unknown"` plus a warning. `sync` ends with a warning/conflict
summary; `refresh` has one failure contract and never renders a stale graph if
sync fails; `check` exits nonzero on staleness; hard errors are reserved for
unreadable/invalid config or unwritable output. Vizzer never executes project
code — it reads files and git history only. <!-- codex-sequence-2026-08-08 -->

## Testing

- `tests/fixtures/`: 3–4 tiny synthetic project repos (one per adapter shape
  + one mixed). Invented content only.
- Golden-file tests: `sync` + `render` per fixture, diffed against committed
  expected output (determinism makes this cheap and total).
- Unit tests for sharp edges: topo sort with cycles, conflict precedence,
  checkbox parsing, front-matter vs header precedence, staleness logic.
- CI (GitHub Actions): Python 3.10–3.13 matrix; an end-to-end job
  (`install → refresh → check` into a fixture repo); `.pyz` release
  build.

## Defects fixed relative to the originals

1. Four independent parsers with divergent conventions → one loader.
2. Status vocabulary inconsistencies (emoji maps missing statuses; dashboard
   treating only `shipped` as dependency-satisfying so `verified` stopped
   satisfying dependents) → single config vocabulary with per-status `done`.
3. Split refresh cadence (manifest on a different ritual than the other
   views) → one `render`, one `check`.
4. Product decisions hardcoded in generator source (`DECISION_GATED`) →
   config data.
5. Absolute repo path baked into constellation output → opt-in config.
6. Silent status disagreement between DAG JSON and story files → explicit
   precedence + visible conflict reporting.

## Out of scope for v1 (recorded, not lost)

- Watch mode / live server / SQLite index (Approach C; revisit if static
  regeneration proves insufficient).
- Active restructuring of user docs (stamping headers, scaffolding spines)
  beyond opt-in archiving.
- Non-filesystem adapters (GitHub issues, Linear) — the adapter contract is
  the extension point.
- The originating project migrating onto vizzer — that is a story to propose in
  that project's own spec, never a silent swap.

## Relationship to source material

The topo sort, ready-queue logic, completion aggregation, manifest
check-modes, and the constellation template are ports from
the author's own prior single-project scripts, rewritten against the
normalized graph. No content from that project (paths, statuses, decision
tables, fixtures) ships in this repo.
