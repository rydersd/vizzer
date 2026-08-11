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

Question answering is model-neutral by design. Claude, Codex, Gemini, a local
model, or a human-facing client all read the same open-question packet and write
the same validated, repo-local answer overlay. The provider is not part of the
decision identity or authority; the durable repo-local answer record is.

## 60-second quickstart

```bash
curl -LO https://github.com/rydersd/vizzer/releases/latest/download/vizzer.pyz
python3 vizzer.pyz          # interactive: pick a project, then grill its source map
```

The installer proposes what it detects, then asks what the folders actually
mean. A directory can be called `product-spec`, `experience-spec`, `prd`, or
something delightfully unhelpful; Vizzer stores its semantic role instead of
promoting the spelling to architecture. It writes a commented
`vizzer/vizzer.toml`, vendors the engine, registers the agent-facing block, and
runs the first refresh. From then on, from the project root:

```bash
python3 vizzer/engine refresh   # re-read sources → graph → every view
python3 vizzer/engine sync      # graph only, for inspection or automation
python3 vizzer/engine render    # render an already-synced graph only
python3 vizzer/engine check     # exit 1 if graph/views are stale (CI-friendly)
python3 vizzer/engine serve     # loopback constellation; story links open in default app
python3 vizzer/engine open story:some-id  # validated direct source opener
python3 vizzer/engine plan analyze --promote story:some-id
python3 vizzer/engine plan apply --promote story:some-id --expected-revision 0 --rationale "why"
python3 vizzer/engine workstreams show
python3 vizzer/engine sessions show
```

Use `refresh` whenever a task completes, an issue is found, or a story's
status or dependencies change. Update the configured source document first;
the graph and views are derived and are never a write-back surface.

Re-run the source interview with `python3 vizzer.pyz configure <path>`, or use
`install <path> --grill` on first installation. Automation can provide a JSON
answer file with `configure <path> --answers answers.json --yes`; validation
rejects paths outside the repository and structured globs that match nothing.

Non-interactive detection without the grill remains available as
`python3 vizzer.pyz install <path>`. Upgrading later:
`python3 vizzer.pyz update <path>` — replaces the vendored engine and the
managed doc block, never touches your config, graph, or views.

## The views (`vizzer/views/`)

Open `constellation.html` and use its visible **Views** menu. Dashboard,
Roadmap, Hierarchy, Features, Completion, Ledgers, Workstreams, and Constellation are interactive
routes over one embedded graph and one shared filter state. Delivery, Activity,
Structure, and Progress are composable graph lenses, not separate pages.

The **Export** menu downloads the Markdown reports below. They are portable
snapshots for review, archives, and model context—not a second user interface.

| View | What it answers |
|---|---|
| `constellation.html#dashboard` / `dashboard.md` | What do I work on today? Interactive delivery lanes plus a Markdown export of the same graph. |
| `constellation.html#roadmap` / `roadmap.md` | In what order does everything ship? Interactive release lanes plus the topological Markdown export. |
| `constellation.html#structure` | Where is work structurally owned? A filter-aware nested view over the complete authored group tree. |
| `constellation.html#features` / `feature-index.md` | Search and filter every behavior by capability; export the portable index separately. |
| `constellation.html#completion` / `completion-sheet.md` | Explore lifecycle, regression, and question counts; export the completion snapshot separately. |
| `constellation.html#ledgers` / `ledger-table.md` | Inspect ownership, progress, checkpoints, and staleness; export the ledger table separately. |
| `constellation.html#workstreams` | Inspect durable workstream intent, current Claude/Codex/human sessions, checkpoints, path scopes, collisions, and peer discussions. |
| `decision-journal.md` | LLM-readable export of open questions and accepted decisions, including recommendation deviations and whether the source story contains the evolution event. |
| `manifest.json` | Machine-readable index of docs represented by enabled adapters (titles, statuses, git dates). It is not a whole-repository corpus manifest unless the configured adapters cover that corpus. |
| `constellation.html#constellation` | Interactive 3D dependency map using the same search, filters, dossier, and owner-decision queue as every other route. <!-- codex-sequence-2026-08-08 --> |

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

Four adapters ship in v1; enable any mix in `vizzer.toml`. The configuration
grill describes them through semantic `[[source_area]]` entries so humans and
agents can distinguish delivery truth, knowledge, planning, evidence, and
operations without relying on folder names:

- **`spec_tree`** — nested work-item markdown (any `a/*/b/*/stories/*.md`
  shape; level names are yours). Reads status/release/deps from headers or
  YAML front-matter. An explicit empty dependency declaration remains
  authoritative over a lower-precedence import. Can also import a legacy DAG JSON during migration,
  including optional milestone phase membership. Story `Tags` remain searchable
  labels, while `Product capabilities` become many-to-many product and capability
  facets rather than being forced into one hierarchy branch.
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
| `sources.spec_tree.product_tags` | `[]` | Tags also treated as product-facet membership; keeps ordinary tags distinct. |
| `sources.ledgers.glob` | `"thoughts/ledgers/CONTINUITY_*.md"` | Ledger locations. |
| `sources.loose_docs.globs` | `[]` | Doc globs, e.g. `["docs/**/*.md"]`. |
| `sources.loose_docs.item_role` | `"reference"` | Typed role for loose documents: `delivery`, `coverage`, `evidence`, `decision`, or `reference`. |
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
| `assessment.enabled` | `false` (`true` for new installs) | Derive model-neutral size, impact, uncertainty, parallel-safety, and portfolio guidance. |
| `assessment.signals_path` | `"vizzer/assessment-signals.json"` | Optional schema-1, repo-local researched evidence overlay keyed by item id. |
| `assessment.small_limit` | `4` | Maximum high structural-leverage XS/S stories in the assessed portfolio. |
| `assessment.anchor_limit` | `2` | Maximum M/L anchors; a second requires explicit independent-execution evidence. |
| `assessment.question_limit` | `1` | Maximum owner-decision/research lane in the portfolio. |
| `assessment.verification_globs` | `["tests/**/*","test/**/*","tests-ui/**/*"]` | Candidate verification sources; text presence is not execution evidence. |
| `planning.enabled` | `false` | Enable accepted owner course overlays and loopback planning controls. |
| `planning.overlay_path` | `"vizzer/planning-overlay.json"` | Versioned, repo-local priority overlay; never a story write-back surface. |
| `activity.path` | `""` | Optional repo-relative schema-1 live-agent checkpoint feed. |
| `activity.stale_after_minutes` | `120` | Age after which work stays visible but stops animating. |
| `questions.answers_path` | `"vizzer/question-answers.json"` | Repo-local, model-neutral authority for accepted owner answers. |
| `progress.history_path` | `""` | Optional generated semantic-history ledger; never hand-edit it. |
| `progress.hot_window_days` | `7` | Brightness window for recent progress trails. |
| `progress.stalled_after_days` | `14` | No-progress age before previously started work shows `?`. |
| `progress.stall_max_days` | `90` | Marker-growth cap for long stalls. |
| `progress.backfill_days` | `7` | One-time exact-header Git lookback when history is introduced. |
| `workstreams.enabled` | `false` | Enable versioned workstream intent plus machine-local leased sessions. |
| `workstreams.definitions_path` | `"vizzer/workstreams.json"` | Repo-local, reviewed workstream definitions, path scopes, discussions, and audit revisions. |
| `workstreams.runtime_path` | `".vizzer/runtime/sessions.json"` | Machine-local live session leases; generated views never expose absolute worktree paths. |
| `workstreams.lease_minutes` | `30` | Time without heartbeat before a session becomes stale and stops claiming work. |

Four table-arrays: `[[source_area]]` gives an arbitrary folder an `id`, `title`,
semantic `role`, and adapter; `[[status]]` replaces the status vocabulary (`name`,
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

Complex repositories can also define segmented navigation over any typed
facet. Items may belong to several values at once:

```toml
[[area]]
id = "products"
title = "Products"
facet = "product"
values = ["desktop", "mobile"]

[[area]]
id = "platform"
title = "Platform"
facet = "product"
values = ["core", "ecosystem"]
```

For example, this project calls delivery truth an Experience Spec and keeps a
Handbook beside it without turning every handbook page into a roadmap item:

```toml
[[source_area]]
id = "experience-spec"
title = "Experience Spec"
role = "delivery"
path = "experience-spec"
adapter = "spec_tree"

[[source_area]]
id = "handbook"
title = "Handbook"
role = "knowledge"
path = "handbook"
adapter = "none"
```

The grill asks separately whether Markdown in a knowledge area should become
reference items. Saying yes enables `loose_docs`; saying no still preserves the
area in the source map. This explicit choice prevents a documentation folder from
quietly adding hundreds of nodes to delivery completion.

Area selection changes the visible slice. Delivery completion remains scoped
to `role = "delivery"`, so supporting coverage, evidence, decisions, and
references cannot quietly alter the denominator.

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

Bug-gap burn-down is ranked separately from feature uptake. A defect with an
explicit `Bug against` relation inherits that shipped contract's hard-dependency
reach; an unlinked gap is ranked only from its own story node and is labeled a
story-only estimate. The dashboard sorts first by current target impact, then
incomplete and total downstream reach. This is known structural blast radius,
not guessed severity: Vizzer cannot infer user harm from graph shape, however
seductive that fake precision might look.

Delivery assessment is also separate from uptake priority. When enabled, Vizzer
preserves the authored appetite, derives an XS–XL burden profile across
implementation, verification, integration, and coordination, records U0–U3
uncertainty and evidence provenance, and computes structural impact from the
dependency graph. It does not divide impact by effort, infer integration work from
an empty dependency list, or apply a universal “AI multiplier.” That sort of number
looks scientific right up until someone asks what it measured.

The provisional portfolio selects structural-leverage-ranked small work, at most two independently
executable M/L anchors, a separate defect lane, and a bounded owner-question lane.
Without explicit target scope, delivery lanes are withheld rather than falling back
to alphabetical roadmap theater. The complete result is stored at
`graph.assessment`; assessment never rewrites lifecycle, dependencies, source
appetite, priority, or owner course.

Teams can add researched evidence at `assessment.signals_path`. Each schema-1
entry is keyed by item id, binds to the current pre-evidence `scopeFingerprint`,
and contains a `signals` object. Source changes reopen the estimate instead of
silently reusing stale evidence. The repo overlay may add authored dimensions,
surfaces, boundaries, coordination and uncertainty evidence; it cannot self-certify
observed sizes or executed tests. Those require a trusted runtime/evidence producer.

Workflow: refresh once without the entry (or after Vizzer reports it stale), copy
the item's current `scope_fingerprint`, author the bounded `signals`, then refresh
again. Allowed proposal fields include `authored_dimensions`, `planned_surfaces`,
`acceptance_checks`, `integration_points`, `coordination_parties`, `write_surfaces`,
`serial_surfaces`, `parallel_evidence`, `scope_tokens`, `evidence`, and `unknowns`.
The overlay rejects `observed_*`, `verification_harnesses`, `harnessed_checks`, and
`verified_checks`; a model does not become a test runner by typing confidently.

```json
{
  "schema": 1,
  "items": {
    "story:example": {
      "scopeFingerprint": "<copy from graph.assessment.items[story:example]>",
      "signals": {
        "authored_dimensions": {"integration": "L"},
        "planned_surfaces": ["core", "bridge", "UI"],
        "write_surfaces": ["src/shared-model.swift"],
        "evidence": ["repository audit 2026-08-10"],
        "unknowns": ["migration volume unmeasured"]
      }
    }
  }
}
```

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

Accepted owner overrides use a theme-aware magenta planning channel: a solid halo
marks promoted or explicitly ordered work, a dashed halo and slash mark a punt, and
quieter dotted halos mark stories downstream of a punt. The connecting magenta paths traverse only
authored hard-dependency edges and brighten on inspection; the dossier names the
owner course and lists the affected downstream stories. Planning therefore remains
visually distinct from lifecycle, release, activity, and recommendation evidence.

The optional activity feed records a story id, agent/task label, state, exact
`completed/total` checkpoints, timestamp, current checkpoint, and optional explicit
related story ids. Its separate optional `questions` array records only researched
owner decisions: a stable id, story and owner, 2–3 options with tradeoffs, one
recommended option and rationale, a falsifier, and evidence. A blocked work record
does not become a question by implication. Open questions remain in `questions`;
accepted answers move into the configured answer overlay with the exact question
snapshot and fingerprint, answer kind/value, author, timestamp, and monotonic
revision. The served Answer transaction also appends a structured evolution event
to the source story: prompt, options, recommendation, owner answer, deviation,
falsifier, and evidence. This makes the repository record authoritative across LLM
vendors and detects an answer to a stale, changed question instead of silently
accepting it.
Active nodes pulse; explicitly authored active links pulse;
dependency edges merely touching active work receive steady emphasis so the view
does not claim the relation itself is being edited. Stale, blocked, paused, and
complete records remain inspectable but do not pulse. `prefers-reduced-motion` is
honored. Delivery, Activity, Structure, and Progress are independently switchable
lenses.

Question discovery is a repository-review responsibility, not a keyword heuristic:
scan specs, plans, active work, and implementation evidence; read the surrounding
contracts; distinguish decisions from operational blockers; research options before
adding a question record. Any model may author the same answer schema after applying
the same validation rules; accepted answers are retained as auditable owner decisions
and are no longer counted as open questions.

## Concurrent workstreams

Workstreams make a Claude session, a Codex session, a local model, and a human
planner coordinate through one provider-neutral contract. Durable intent lives in
versioned `vizzer/workstreams.json`: objective, story scope, allowed and shared
paths, lead/reviewer, checkpoint, dependencies, discussion, rationale, and audit
revision. Live process identity lives separately in ignored
`.vizzer/runtime/sessions.json` with a renewable lease. A crashed client therefore
goes stale instead of retaining ownership by folklore.

```bash
python3 vizzer/engine workstreams apply --file split.json \
  --expected-revision 0 --actor Ryder --rationale "separate token and canvas risk"
python3 vizzer/engine sessions start --id codex-tokens --actor Codex --model Spark \
  --role lead --workstream tokens --branch codex/tokens --worktree ../tokens \
  --expected-revision 0
python3 vizzer/engine sessions heartbeat --id codex-tokens --expected-revision 1
python3 vizzer/engine sessions stop --id codex-tokens --expected-revision 2
```

All mutations are compare-and-swap and run under a repository mutation lock. The
Workstreams view exposes overlapping stories, shared/exclusive path collisions,
stale leases, checkpoints, and peer discussion. Peers may record reversible
implementation decisions. Product, scope, or contract disagreements must link an
open owner question and escalate; two models agreeing does not manufacture product
authority. That would be efficient, certainly, but also nonsense.

Served mode exposes a read-only `/api/workstreams` snapshot so a long-running view
can update without regenerating HTML. Agents mutate through the atomic CLI; owner
priority and question decisions keep their separate guarded loopback controls.

The answer ledger is append-only and provider-free. Each entry carries a contiguous
ledger revision and the fingerprint returned for the current question:

```json
{
  "schema": 1,
  "revision": 1,
  "answers": [{
    "revision": 1,
    "questionId": "question:render-authority",
    "fingerprint": "<64 lowercase hex characters from the current question>",
    "answeredAt": "2026-08-10T18:30:00Z",
    "answeredBy": "Ryder",
    "kind": "option",
    "optionId": "shared",
    "text": null
  }]
}
```

A freeform answer uses `"kind": "freeform"`, a non-empty `text`, and a null
`optionId`. Prefer the served endpoint because it performs compare-and-swap and
atomic persistence. An agent writing the file directly must preserve the same
schema, current fingerprint, contiguous revisions, option membership, and audit
fields; merely remembering an answer in Claude, Codex, or Gemini does precisely
nothing to project authority. Direct ledger authors must then run
`python3 vizzer/engine decisions --all --yes`; `refresh` emits a warning for any
accepted answer missing from its story. The command is idempotent and appends only
an evolution event—it does not claim the story's normative scope or acceptance has
already been reconciled.

When implementation or specification follow-through actually lands, record that
separate state instead of leaving the accepted answer permanently labeled pending:

```bash
python3 vizzer/engine decisions question:render-authority --apply \
  --summary "Routed staged export through the shared evaluator and strengthened its named gate." \
  --evidence src/export.py --evidence tests/test_export.py --yes
```

This appends a fingerprint-bound application event to the same source story. It
does not mark delivery or lifecycle complete; those still require the Story's
named acceptance and normal lifecycle evidence.

The generated `vizzer/views/decision-journal.md` is the model-friendly index for
future shaping. It keeps accepted and open decisions together, calls out departures
from the recorded recommendation, links every event to its story, and labels
normative application as pending or applied from the matching story event. Agents
should use that history to explain why a story changed and to avoid reintroducing
options already rejected by evidence.

Progress history is narrower than generic Git activity on purpose. Only forward
lifecycle transitions, removed hard dependencies, and increased explicit checkpoint
counts create a circle-check trail. A one-time Git backfill compares exact historical
`Status`/`Deps` headers and ignores prose-only commits. Only work with recorded
start/eligibility evidence can become stalled; untouched idea, backlog, parked, and
unknown work never receives a `?`. The graph stores stable timestamps and anchors;
the browser derives brightness, age text, and marker size at display time so an
unchanged project does not become stale merely because a clock advanced.

The constellation keeps progress and version visually independent: lifecycle progress
controls circle fill opacity, while release horizon controls a separate outer-ring
opacity. Both span 50–100% before temporary filtering dim. The newest check and any
question marker overlap their story circle as badges; older checks trail outward.
Pointer proximity adds a subtle continuous glow, exact containment adds a hit ring,
and clicked selection remains visibly distinct.

For repositories with more than one product or a deep specification tree, the
**Hierarchy** view preserves the normalized group ancestry instead of flattening it
into capability labels. It nests the current filtered slice under the repository's
authored groups, reports delivery completion at each branch, and leaves ungrouped
records explicit. Structural ownership is intentionally distinct from many-to-many
facets: a Core-affecting Notes story remains owned by its authored Notes epic while
still appearing when the Core facet is selected.

Constellation `file://` mode is explicitly read-only: it renders open questions and
accepted decisions, but it does not offer a placebo Answer button that cannot save.
Run `python3 vizzer/engine serve` for the write-capable question cards. That
loopback UI reads `GET /api/questions` and submits validated answers to
`POST /api/questions/<encoded-id>/answer`; the repository overlay, not browser state
or a particular LLM session, remains authoritative.

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

## Design context

Two portable research notes explain the assumptions behind the assessor and the
work-source model:

- [Story sizing and portfolio selection](docs/context/story-sizing-and-portfolio-selection.md)
- [PRDs and living product specs](docs/context/prds-and-living-product-specs.md)

They are guidance, not runtime contracts. Projects remain free to use stories,
issues, RFCs, PRDs, or another source form; Vizzer cares about explicit authority,
evidence, and graph semantics, not which acronym won the meeting.

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
