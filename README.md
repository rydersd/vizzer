# vizzer

Turn whatever your project uses to track work — spec trees, continuity ledgers,
loose docs, TODO lists — into **one normalized work graph** and a set of
regenerable views: a dependency-ordered roadmap, a searchable feature index, a
"what do I work on today" dashboard, a completion sheet, a ledger table, a
machine-readable corpus manifest, and an interactive 3D constellation.

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
block, and runs the first sync + render. From then on, from the project root:

```bash
python3 vizzer/engine sync      # re-read sources → vizzer/vizzer-graph.json
python3 vizzer/engine render    # regenerate all views from the graph
python3 vizzer/engine check     # exit 1 if graph/views are stale (CI-friendly)
```

Non-interactive: `python3 vizzer.pyz install <path>`. Upgrading later:
`python3 vizzer.pyz update <path>` — replaces the vendored engine and the
managed doc block, never touches your config, graph, or views.

## The views (`vizzer/views/`)

| View | What it answers |
|---|---|
| `dashboard.md` | What do I work on today? In-progress, dependency-satisfied ready queue, decision-blocked items. |
| `roadmap.md` | In what order does everything ship? Topologically sorted waves per release. |
| `feature-index.md` | Cmd-F over every behavior, grouped by your hierarchy, with status. |
| `completion-sheet.md` | Counts by status, group, and wave; verified-rate; debt tally. |
| `ledger-table.md` | One row per continuity ledger: goal, current phase, progress bar, staleness. |
| `manifest.json` | Machine-readable index of every tracked doc (titles, statuses, git dates). |
| `constellation.html` | Self-contained interactive 3D map of the whole graph — open it in a browser. |

## The graph contract

`vizzer/vizzer-graph.json` is **derived** — regenerate it with `sync`, never
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
  YAML front-matter. Can also import a legacy DAG JSON during migration.
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
| `reconcile.mention_globs` | `[]` | Docs scanned for activity mentions. |
| `reconcile.staleness_days` | `14` | Ledger staleness threshold. |
| `archive.adapters` | `["todos"]` | Which adapters' files `archive` may move. |

Two table-arrays: `[[status]]` (replace the status vocabulary — `name`,
`emoji`, `done`) and `[[gates]]` (`item`, `reason` — items blocked on a
decision, surfaced on the dashboard instead of the ready queue).

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
orientation, re-run `sync && render` after merging work, and treat the graph
as derived. `update` rewrites only that block; your other instructions are
never touched.

## Suggested project conventions

Vizzer works on whatever your project already does — none of the following is
required. But the graph is only as good as the files it reads, and these five
conventions are the ones that measurably change what vizzer can tell you. Adopt
them in your own `CLAUDE.md` / `AGENTS.md` if they fit; vizzer will never write
them there for you.

**1. Separate "shipped" from "verified."** The most common way a completion
number lies is by counting merged work as finished work. Vizzer's `[[status]]`
table lets you define the vocabulary and mark which entries are `done`, and the
completion sheet reports a verified rate — so a project that distinguishes
`shipped` (merged) from `verified` (tests, logs, or user confirmation exist)
gets an honest number instead of a hopeful one. A build succeeding is not
evidence that a feature works.

**2. Link with `[display text](relative-path.md)`.** Vizzer renders links in
six of its seven views. Relative markdown links resolve in GitHub, Obsidian,
IDE previews and any future renderer; `[[wikilinks]]` only reliably work in
Obsidian, and absolute paths break for everyone but you. Make the visible text
the human-readable name and put the path inside the link, rather than showing a
raw path as the link text. Note that `render.obsidian_links` deliberately
trades this portability away for local-vault convenience — leave it off if the
views are committed anywhere others read them.

**3. Fix the source, never the derived view.** `vizzer-graph.json` and
everything in the output directory are regenerated wholesale by `sync` and
`render`; edits there are silently discarded on the next run. When two sources
disagree about an item, vizzer keeps the higher-precedence value, records the
disagreement in the graph's `conflicts` array, and prints it — it never averages
the two or quietly picks a winner. Those conflicts are a to-do list against your
source files, not noise to tune out. In practice they are the fastest way to
find a stale cached status.

**4. Give continuity ledgers a predictable shape.** The `ledgers` adapter reads
a `## Goal` section, phase checkboxes (`[x]` done, `[→]` in progress, `[ ]`
pending), and `## Open Questions`. A project that writes ledgers that way gets
the ledger table for free. One trap worth stating plainly: **a source directory
that is gitignored produces silently empty views.** If ledgers live somewhere
untracked, vizzer sees nothing in CI or in a fresh clone, and the resulting view
is empty rather than wrong — which is harder to notice.

**5. Cite the work item in the pull request.** Every item gets a stable id
(`story:<slug>`). If merged PRs carry a `Spec: <path-to-item.md>` line, those
ids become checkable against real work, and the graph stops being decorative:
you can gate on whether shipped code corresponds to a specified item, and find
items whose status was never updated after their PR merged.

## Safety

Vizzer never executes project code. It reads files and git history, and writes
only inside `vizzer/` plus the managed doc block and one `.gitignore` line.

## License

MIT.
