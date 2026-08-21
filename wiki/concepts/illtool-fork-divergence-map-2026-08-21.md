# Vizzer divergence map: `project_vizzer` (A) ↔ `illtool-standalone/vizzer/` (B)

> Brief: Read-only reconnaissance of the two diverged vizzer copies, ahead of porting the fork's
> changes back upstream project-agnostically and shipping the review/capture harness as an optional
> install. B is a strict file-level superset — 21 files identical, 27 diverged, 23 only-in-B, zero
> only-in-A — so this is a one-directional port with a short exclusion list, not a two-way merge.
> Tags: vizzer, port, divergence, review-harness, project-agnostic, reconnaissance
> Created: 2026-08-21
> Updated: 2026-08-21

## Motivation

Owner directive, 2026-08-21: update this repo "with all the functional changes we've made this week",
**without the bias toward this project (project agnostic)**, and include the review/capture harness as
something users can **optionally install**.

Two copies of vizzer have diverged. This repo (**A**) went `0.8.0 → 0.8.36` over 54 commits. The
`illtool-standalone` fork (**B**) vendored A at `951536f64` and then took **188 commits touching
`vizzer/`, 139 of them since 2026-08-14**. Before any port could be planned, someone had to establish
what each side actually has — and, critically, whether the fork's work is portable or welded to one
project's directory layout.

Reconnaissance was read-only: nothing was changed or committed in either repo, and **nothing was
executed** — every claim below is source-verified, not execution-verified. Standing up A's existing
suite as a green baseline is the first thing the port should do.

## Method

Byte-level `cmp`/`diff -u` across the union of both package trees (71 files), plus four parallel
read-only deep-dives (review harness, illtool-bias audit, constellation frontend, Python core). Every
load-bearing claim was re-verified against source; two subagent claims did not survive that check and
are corrected inline below.

**A** = `/Users/ryders/Developer/GitHub/project_vizzer`, package root `src/vizzer/`, HEAD `8ae6462`,
branch `agent/vizzer-0.8.31-interaction-reliability` **exactly even with `origin/main`** (0 ahead, 0
behind), version `0.8.36`.
**B** = `/Users/ryders/Developer/GitHub/illtool-standalone`, vendored engine at
`vizzer/engine/vizzer/`, main at `28c9b1367`, `VERSION_SERIES = "0.12"`.

---

## 1. Structural map

### Headline

**Zero files exist only in A.** B is a strict file-level superset: 21 identical, 27 diverged, 23
only-in-B. One-directional port, short exclusion list, exactly four known A-test breakages.

### CLI verb surface

Both register the same verbs — `sync`, `render`, `refresh`, `open`, `serve`, `check`, `archive`,
`plan {analyze,apply,undo}`, `decisions`, `workstreams {show,apply,discuss}`,
`sessions {show,start,heartbeat,stop}`, `configure`, `install`, `update` — at `A/src/vizzer/cli.py:1669-1887`
and `B/vizzer/engine/vizzer/cli.py:2568-2831`.

**The surface diverges by exactly one verb:** B adds `reviews {show,record,bundle}` at
`B/cli.py:2667-2710`. Everything else in B's +944 `cli.py` lines is interior — routes, gates, helpers
(§2.7).

### Correspondence table

`A/` = `project_vizzer/src/vizzer/`, `B/` = `illtool-standalone/vizzer/engine/vizzer/`.

| Path (relative to package root) | A lines | B lines | Status |
|---|---|---|---|
| `__init__.py` | 1 | 504 | **diverged** — A is a version literal; B is the whole renderId subsystem |
| `__main__.py` | 3 | 3 | same |
| `activity.py` | 248 | 456 | diverged |
| `adapters/__init__.py` | 34 | 34 | same |
| `adapters/conflicts.py` | — | 122 | only-in-B |
| `adapters/ledgers.py` | 208 | 208 | same |
| `adapters/loose_docs.py` | 105 | 105 | same |
| `adapters/spec_tree.py` | 783 | 926 | diverged |
| `adapters/todos.py` | 51 | 51 | same |
| `assessment.py` | 1144 | 1146 | diverged (2 lines) |
| `autocommit.py` | — | 128 | only-in-B |
| `ci_status.py` | — | 374 | only-in-B |
| `cli.py` | 1909 | 2853 | diverged |
| `config.py` | 516 | 570 | diverged |
| `decision_journal.py` | 327 | 420 | diverged — **on-disk grammar change** |
| `discussion_queue.py` | 272 | 272 | same |
| `gitmeta.py` | 99 | 99 | same |
| `install.py` | 683 | 757 | diverged |
| `model.py` | 616 | 633 | diverged |
| `onboarding.py` | 269 | 269 | same |
| `planning.py` | 368 | 368 | same |
| `priority.py` | 529 | 529 | same |
| `progress_history.py` | 341 | 341 | same |
| `question_answers.py` | 449 | 449 | same |
| `reconcile.py` | 409 | 409 | same |
| `render/__init__.py` | 46 | 51 | diverged (5 renderer registrations) |
| `render/analytics.py` | — | 225 | only-in-B |
| `render/awaiting_owner.py` | — | 181 | only-in-B |
| `render/common.py` | 76 | 76 | same |
| `render/completion_sheet.py` | 95 | 95 | same |
| `render/constellation.py` | 646 | 726 | diverged |
| `render/constellation/boot.js` | 17 | 29 | diverged |
| `render/constellation/bootstrap.js` | 36 | 107 | diverged |
| `render/constellation/canvas.js` | 530 | 739 | diverged |
| `render/constellation/chip_layout.js` | — | 123 | only-in-B |
| `render/constellation/ci.js` | — | 115 | only-in-B |
| `render/constellation/dossier.js` | 174 | 318 | diverged |
| `render/constellation/filters.js` | 302 | 1008 | diverged — largest |
| `render/constellation/layout.css` | 142 | 305 | diverged |
| `render/constellation/notices.css` | — | 6 | only-in-B |
| `render/constellation/notices.js` | — | 102 | only-in-B |
| `render/constellation/planning.js` | 76 | 76 | **same** |
| `render/constellation/questions.js` | 249 | 383 | diverged |
| `render/constellation/shell.html` | 72 | 93 | diverged |
| `render/constellation/state.js` | 218 | 639 | diverged — 2nd largest |
| `render/constellation/symbols.js` | — | 209 | only-in-B |
| `render/constellation/tokens.css` | 29 | 40 | diverged |
| `render/constellation/view_tables.js` | — | 113 | only-in-B |
| `render/constellation/views.css` | 61 | 140 | diverged |
| `render/constellation/views.js` | 209 | 289 | diverged |
| `render/constellation/work_navigation.js` | 47 | 50 | diverged (1 hunk) |
| `render/dashboard.py` | 556 | 577 | diverged |
| `render/decision_journal.py` | 135 | 135 | same |
| `render/discussion_queue.py` | 53 | 53 | same |
| `render/feature_index.py` | 73 | 73 | same |
| `render/lanes.py` | — | 134 | only-in-B |
| `render/ledger_table.py` | 77 | 77 | same |
| `render/manifest.py` | 39 | 44 | diverged — **A behaviour narrowed** |
| `render/perspective_common.py` | — | 133 | only-in-B |
| `render/review_archive.py` | — | 338 | only-in-B (harness) |
| `render/review_sheets.py` | — | 208 | only-in-B (harness) |
| `render/review_sheets/review.css` | — | 106 | only-in-B (harness) |
| `render/review_sheets/review.js` | — | 428 | only-in-B (harness) |
| `render/review_sheets/shell.html` | — | 27 | only-in-B (harness) |
| `render/roadmap.py` | 74 | 74 | same |
| `review_images.py` | — | 232 | only-in-B (harness, but generic) |
| `review_launch.py` | — | 335 | only-in-B (harness) |
| `review_links.py` | — | 111 | only-in-B (harness) |
| `reviews.py` | — | 2161 | only-in-B (harness) |
| `story_sidebar.py` | — | 58 | only-in-B (generic) |
| `workstreams.py` | 640 | 654 | diverged — **A behaviour narrowed** |

### Packaging: the structural mismatch

| | A | B |
|---|---|---|
| Layout | `src/vizzer/`, pip package | `vizzer/engine/vizzer/`, vendored tree |
| Manifest | `pyproject.toml`, setuptools | **none** |
| Console script | `vizzer = "vizzer.cli:main"` | none — invoked `python3 vizzer/engine` |
| `__main__` import | `from .cli import main` (relative) | `from vizzer.cli import main` (absolute; `vizzer/engine` on `sys.path`) |
| Version | hand-edited literal, duplicated at `pyproject.toml:7` and `__init__.py:1` | `VERSION_SERIES` + commit count over `vizzer/engine` |
| Staleness marker | `vizzer/VERSION` (text = `__version__`) | `vizzer/RENDER_ID` (content hash) |
| Zipapp builder | `scripts/build_pyz.py` (74 lines, in-repo) | `scripts/dev/build_vizzer_pyz.py` (74 lines, **outside** the vendored tree) |
| Optional extras | **none declared** — no `[project.optional-dependencies]` | n/a |

### Tests — the asset the file diff misses

**B's vizzer tests live outside the vendored tree**, at
`illtool-standalone/scripts/dev/tests/test_vizzer_*.py`: **30 files, 11,738 lines**. No vendoring or
file comparison sees them. A's entire suite is 41 files / 8,952 lines of Python + 5 browser harnesses
/ 1,193 lines of JS.

They bind to the illtool layout by path: `ROOT = Path(__file__).resolve().parents[3]` then
`sys.path.insert(0, str(ROOT / "vizzer/engine"))` (`test_vizzer_ci_status.py:33-34`,
`test_vizzer_reviews.py:30`). There is **no conftest.py** anywhere under `scripts/`. Porting them
needs a path shim, nothing deeper.

Largest, in porting-value order: `test_vizzer_review_ingest_signoff.py` (1681),
`test_vizzer_constellation_focus_and_symbols.py` (1212), `test_vizzer_reviews.py` (980),
`test_vizzer_constellation_chip_layout.py` (701), `test_vizzer_render_id_authority.py` (582).

---

## 2. What B gained that A lacks

Functional additions only. "Portable" lifts with no host assumption; "entangled" needs a config hook
or carries illtool identity.

### 2.1 Content-hashed `renderId` — `B/__init__.py` (504 lines), `B/cli.py`, `B/install.py`

A's staleness gate compares the text of `vizzer/VERSION` against `__version__` (`A/cli.py:59-74`,
audit at `A/cli.py:1076-1087`). Because A's version is a hand-edited literal, that gate only fires
when someone forgets to bump it.

B separates two concepts A conflates:

- **`engineVersion`** — live human diagnostic. `VERSION_SERIES = "0.12"` (`B/__init__.py:55`) plus an
  automated revision = `git rev-list --count HEAD -- vizzer/engine` (`_engine_revision`, `:127`).
- **`renderId`** — deterministic 16-hex content hash over engine source bytes (`render_id`, `:366`),
  stamped into every artifact (`render_stamp`, `:459`), captured once per process at import
  (`process_render_id`, `:418`; `B/cli.py:98 _CAPTURED_AT_IMPORT`).

The motivating defect is documented in `test_vizzer_render_id.py`'s docstring and is real: a commit
count moves on *every* commit, so a C++-only PR re-stales seven vizzer views it never touched. It
red-lit merges for a full day and pushed two lanes to `--no-verify`.

Three deliberate honesty rules, each with a test file: identity is never a value when it is not an
identity (empty tree raises `RenderIdError` at `:76` rather than returning a hash of nothing); the
suffix allowlist **fails closed** (`RENDER_SOURCE_SUFFIXES` at `:298` — an unclassified engine file is
an error, because a runtime resource outside the identity means `check` stays green while behaviour
changes); and a process reports the code it is running, not what is on disk.

**Portable in concept, entangled in mechanism** — see §7. This is the riskiest item in the port.

**Shadow/parity checking is not in the engine.** It is
`illtool-standalone/scripts/dev/check-vizzer-shadow.py` (52 KB), which hardcodes
`wiki/product-spec/capabilities/*/epics/*/stories/*.md` and legacy `wiki/spec-ops/views/`. Not
portable, out of scope. The engine-side half it consumes is `render/manifest.py`.

### 2.2 Review-sheet + capture harness — 3,973 lines across 9 modules and 3 frontend assets

The single largest fork-only capability. Full inventory in §5.

### 2.3 The blocked-record gate — `B/activity.py:79/136/191`, enforced `B/cli.py:1888-1930`

`unresolved_blocker_records` (`:79`) fails a `check` on two arms: a `blocked` record with no linked
question or tracked dependency (`unlinked`), and a blocker whose lease has expired
(`expired-lease`/`unknown-lease`). Backed by `ActiveWork.blocked_by` (`B/model.py:64`), a grandfather
file (`GRANDFATHER_RELPATH`, `:26`), and `blocker_is_cleared` (`:171`). Contract:
`vizzer/docs/blocked-record-gate.md`.

**Absent from A entirely.** Portable — the rationale generalizes exactly ("a record no surface reads
is the same as no record"). One coupling: `assessment.py`'s only delta is importing
`blocker_is_cleared` and adding `and not blocker_is_cleared(graph, work.story_id)` at
`B/assessment.py:886`.

### 2.4 Questions / decisions / journal

`question_answers.py` is **byte-identical**. The delta is in `decision_journal.py` (+93), and it is a
**grammar change, not an addition**:

- A writes `<!-- vizzer:evolution-answer:{fingerprint}:r{revision}:begin -->` (`A/decision_journal.py:22-29`).
- B drops the revision: `<!-- vizzer:evolution-answer:{fingerprint}:begin -->`
  (`B/decision_journal.py:23-29`), making the marker an immutable accepted-question snapshot rather
  than a per-revision event.

B reads both forms (`_EVOLUTION_BEGIN` at `:32` has an optional `:r<n>` group) but writes only the
new one. It adds `_replay_comparison_key` (`:67`) and `_remove_replayed_events` (`:82`) to
de-duplicate byte-equivalent replays — the fix for the 55 duplicated decision records.

**Portable, but a one-way door.** Porting B into A means A-written markers stop matching A's
string-equality `decision_is_journaled`. Migration required; isolate this workstream.

### 2.5 Workstreams / sessions — `B/workstreams.py:598-647`

`load_workstream_overlay` gains `include_runtime: bool = False`. When false it skips `read_runtime`
entirely and excludes `heartbeatAt`/`stoppedAt` from the `as_of` computation. Only `/api/workstreams`
opts in (`B/cli.py:1168-1170`).

Effect: checked-in graphs stop changing because another checkout wrote its gitignored heartbeat.
**This supersedes A's `172a20a`**, which stabilised the `asOf` timestamp but left the hole open.
Portable; note it changes a public function's default contract, so A's callers need auditing.

### 2.6 Delivery assessment + scope fingerprints

Already in A. `assessment.py` diverges by **exactly two lines** (§2.3). Scope fingerprints,
`burden_established`, the four-dimension portfolio gate — all identical, all originally A's `30bbd5d`.

### 2.7 `cli.py` interior — where the +944 lines go

Region breakdown verified against both files. Roughly **two-thirds is the review harness**:

| Region | B lines | Net | What |
|---|---|---|---|
| Imports + restart consts | 6–98 | +79/−13 | renderId imports, `autocommit`, `ci_status`, `review_launch`, `reviews` (24 names), `review_images`, activity gate; `_RESTART_SERVICE_ARGV` at `:85-88` |
| renderId serve gate | 101–139 | +47/−9 | VERSION→renderId rewrite |
| Origin split, restart POST, 409, body cap | 255–324 | +39/−6 | `_same_loopback_origin`:258, `_same_origin`:267, `_read_json_body(max_bytes=)`:306 |
| Autocommit call sites | 514–643 | +17 | two `autocommit.commit_paths` blocks in question POSTs |
| **Review handler methods** | 654–1016 | **+378** | harness |
| New routes (`do_POST`/`do_GET`) | 1019–1119 | +58 | restart, health, 6 review routes |
| `/api/ci` | 1138–1152 | +16 | the only non-review new GET route |
| renderId in 4 envelopes, `include_runtime=True` | 1130–1236 | +11/−4 | |
| **`_reviews*` CLI handlers** | 1310–1513 | **+204** | harness |
| `_refresh` writes marker | 1792–1802 | +8 | |
| `_engine_audit_precondition` | 1821–1844 | +33 | new |
| `_check` body | 1874–1989 | +104/−9 | precondition, blocked gate, review sign-off gate, marker audit |
| **`reviews` subparser** | 2665–2709 | **+45** | harness |
| Rest of `_parser()`/`main()` | 2564–2853 | 0 | byte-identical |

**A has no HTTP route B lacks.** B adds 11: `/api/server/restart` (POST + GET-405),
`/api/server/health`, `/api/ci`, and six `/api/reviews/*`.

### 2.8 New graph sources and perspectives

| Feature | Module | Portability |
|---|---|---|
| **Conflicts adapter** | `B/adapters/conflicts.py` (122) | **Portable — highest port-readiness of anything fork-only.** Path from `sources.conflicts.path`; no hardcoded paths at all. `A/config.py:18` just needs `"conflicts"` in `SOURCE_AREA_ADAPTERS`. Note `:27-29`: group ids must be colon-namespaced or the constellation renderer `IndexError`s. |
| **Recorded completion dates** | `B/adapters/spec_tree.py:144, 768, 795, 911-919` | Two provenances (`authored` from `> Ship evidence (date)` / `**This Story shipped (date).**`, and `git` from a `Status: shipped` transition pickaxe). Portable with a smell: it shells to `git` from an adapter (`:774`) and defaults the pathspec to `wiki/product-spec/**/stories/*.md` when the config glob is empty (`:769`). |
| **CI status overlay** | `B/ci_status.py` (374) + `B/render/constellation/ci.js` (115) | Entangled twice over — `gh` CLI (`:242`, `:208-213`), and `from .review_links import story_path_key` at `:40`, so **CI currently drags in the review harness**. The severity policy (`classify_check`:68, `pr_severity`:84) and the 60 s stale-while-revalidate cache are genuinely provider-neutral and good. Served-only; never enters a rendered file. |
| **Autocommit** | `B/autocommit.py` (128) | Portable in mechanism, workflow-hack in policy. Commits the answers ledger after a served owner write with `--no-verify -c core.hooksPath=/dev/null` (`:87`), never pushes, never gates. The hook bypass deliberately skips the project's own pre-commit staleness gate. Port with default **false**. `server.autocommit` is read at `:59` but never declared in DEFAULTS. |
| **Perspective helpers** | `B/render/perspective_common.py` (133) | Portable except `PATH_TOKEN` at `:13`, which whitelists `` `.codex-results\|wiki\|vizzer/…` ``, and `explicit_receipt_paths` special-casing `.codex-results/` at `:130`. `snapshot_time`:28 anchors age to persisted evidence rather than wall clock — a good determinism property. |
| **Analytics views** | `B/render/analytics.py` (225) → `risk-heat.md`, `capability-rollup.md`, `decision-aging.md` | Portable; inherits the two path assumptions above. Column headers at `:149` and status literals at `:155-156` need routing through `cfg.status_role()`. |
| **Awaiting-owner rollup** | `B/render/awaiting_owner.py` (181) → `awaiting-owner.md` | **Illtool-flavoured.** `AMENDMENT_MARKER` at `:17-24` hardcodes four owner-name variants; `:56-60` hardcodes one specific historical sentence to suppress a false positive. |
| **Lanes view** | `B/render/lanes.py` (134) → `lanes.md` | Nearly portable — `REGISTER_PATH = "wiki/dev/active-work.md"` at `:13` is the only coupling. `_branch_freshness`:25 deliberately returns "not reproducible from this checkout", preserving determinism. Feeds the dashboard's new Coordination-lanes block (`B/render/dashboard.py:276-296`). |

### 2.9 Constellation frontend

B is not behind A anywhere in the frontend. Full per-file deltas:

| Feature | B location | A has it? |
|---|---|---|
| **Depth ramp / fog** | `canvas.js:103-116` (`p.fog=1-.76*t*t`), edges `:142-146`, floor `OWNER_FOG_FLOOR=.44` at `:23` | No. A shipped a `ctx.filter='blur(.7px)'` bucket in `0ff3edd`, then **deleted it** in `f47d5c0` for perf, leaving only opacity/scale. B's ramp is free and achieves what the blur wanted. **Do not reintroduce any `ctx.filter`.** |
| **Agent trail arrows** | `canvas.js:46-69`, `:133-146` | Yes — identical |
| **SF Symbol glyph system** | `symbols.js` (209): 15 vector outlines + `drawSymbol`, `bugSeverity`, `nodeStatusMarkers`, `questionBadgeStyle`, ring geometry | No. **Load-bearing prerequisite** for the chip legend, eyeglasses badge, parked-answer ring, and B's question hit refinement. See §9 for a licensing question. |
| **Chip legend** (chips became the legend, per-chip counts, per-chip data tables, primary/overflow split, responsive demotion) | `filters.js:201-240` (`legendChipPlan`), `:241-337` | No |
| **Chip layout / measured chrome** | `chip_layout.js` (123) — `syncChromeMetrics` publishes measured `--search-top`/`--rail-top`; `mountOverlay` on `body` | No, **and A has the bug this cures**: `A/layout.css` hardcodes `#search{top:112px}` / `#rail{top:154px}` against an auto-height `#top` grid, so any chip-row growth slides the chip row under the search field. B replaces both with measured custom properties (`B/layout.css:26,190,211`). |
| **`--z-*` stacking scale** | `layout.css:28` | No. The insight is non-obvious: `#top` is `position:fixed` *with* a z-index, so no descendant can beat `#dossier` — hence overlays mount on `body`. |
| **View tables** (per-chip sort/filter) | `view_tables.js` (113), `views.js:165-199`, `filters.js:541-630` | No |
| **Deep links** (`#story/<id>`) | `state.js:223-245`, `views.js:271-289`, `dossier.js:34-42, 268-283` | No |
| **Story sidebar** (Review steps / AC / DoD accordions) | `dossier.js:71-96`, backed by `story_sidebar.py` + `constellation.py:367-374, 400-402` | No |
| **Notices / served-error surface** | `notices.js` (102) + `notices.css` | No. Contaminated at `notices.js:4`. |
| **Stale-tab detection** | `bootstrap.js:1-52` — HEAD `Last-Modified`/`Content-Length` poll, banner, never auto-reloads | No |
| **`boot.js` resource-error fix** | `boot.js:12-19` — a 404 no longer masquerades as "Vizzer could not start"; `:5-8` once ready, the overlay can't reopen | No |
| **Color lenses** (lifecycle/activity/criticality/capability) | `state.js:41, 597-628`, dropdown `filters.js:740-752` | No |
| **Cluster focus / fly-to / node-focus camera** | `state.js:265-288`, `filters.js:830-922` | No |
| **Answer mode dim + neighbour emphasis** | `state.js:446-478`, `canvas.js:130-140` | No |
| **Parked answer drafts + sessionStorage** | `state.js:96-160`, `questions.js:282-306` | No |
| **Unsaved-draft navigation guard** | `questions.js:307-348`, `dossier.js:153-165, 176-181` | No |
| **Field filters** `cap:`/`epic:`/`status:` | `state.js:251-256`, `shell.html:44` | No |
| **Authority alert banner** | `questions.js:30-45` | No |
| **Done hidden by default** | `state.js:83`; meter re-admits shipped at `filters.js:47-49` | No — opinionated; port as config, not hardcode |
| **Reachability exemptions** | `state.js:333` (unanswered question), `:344-345` (review chip), `:367` (conflict role) | No — generic correctness fixes |
| **Work-nav centering** | `work_navigation.js:31-34` — the only hunk; `openNode(target,{center:true})` | Partially — the file is otherwise identical. The one-liner is a **no-op without** `enterNodeFocus` (`filters.js:900-914`). |
| **Interaction hardening** (`publishHitDebug`, `advertisedTarget` press-latch, `orbitThreshold=6`, `{passive:false}` wheel) | `canvas.js:541-739` | **Yes** — already aligned |
| **Question glyph hit ownership** | `canvas.js:587-645` | **Yes**, verbatim — plus B scopes it: `if(ownerQuestions(i).length && questionBadgeStyle(...)==='dot')` at `:608` |
| **Eyeglasses review badge** | `canvas.js:386-407`, `dossier.js:243`, `filters.js:219` | No — harness surface |
| `planning.js` | byte-identical | Yes. B's planning divergence is entirely renderId plumbing and fragment ordering, not planning logic. |

**Correction to a subagent finding.** It reported `toast` is "never defined anywhere in the
constellation bundle." Not quite: `toast` **is** defined, at `B/render/review_sheets/review.js:34` —
but that is a *different page bundle*. The constellation's two call sites (`dossier.js:275` "Deep link
copied", `views.js:278` "No story matches…") are `typeof toast==='function'`-guarded and therefore
**silent no-ops on the constellation page**. The comment at `views.js:276-277` ("A link that resolves
to nothing says so") is currently false. Fix while porting.

---

## 3. What A gained that B lacks — the regression list

Every one of A's newest Python-side commits was verified against B's actual code rather than assumed.

| A commit | Present in B? | Evidence |
|---|---|---|
| `94c3949` preserve priority / assessed portfolio authority split | **Yes** | `render/common.py` is **byte-identical** A↔B; `priority_items` at `:39-45` has no portfolio filter — the post-fix form |
| `30bbd5d` structural work navigation + persistent serve ports | **Yes, all parts** | `activity._reject_duplicate_object_keys` at `B:214`; `cli._serve` byte-identical, `B/cli.py:1277` `resolved_port = cfg.get("server.port", 0) if port is None else port`; `config` `"server": {"port": 0}` at `B:44` = `A:44`; `install` `[server]` block at `B/install.py:379-382` |
| `172a20a` deterministic workstream graph refresh | **Yes, and superseded** | `B/workstreams.py:641` `as_of = max(...)`; B goes further with `include_runtime` |
| `e06d69c` prefer specific nested source areas | **Yes, verbatim** | `B/config.py:539-560` identical body including docstring |
| `8ae6462` constrain question glyph center ownership | **Yes** | `B/canvas.js:611-628` — `centerCore`, `sameCenter`/`samePaint`/`sameDepth` cascade |
| `289bbb4` align overlapping question glyph hit ownership | **Yes** | `B/canvas.js:629-644` |
| `f47d5c0` restore constellation interaction performance | **Yes** | no `ctx.filter` anywhere in B |
| `8509a75` harden constellation interactions + discussion flow | **Yes** | `publishHitDebug`, `advertisedTarget`, `orbitThreshold`, `{passive:false}` all at `B/canvas.js:541-739` |

**Verdict: zero feature regressions. There is nothing to backport A→B.** But there are seven places
where B *removed or changed* A behaviour, and the port must handle each deliberately:

1. **`vizzer/VERSION`** — `A/install.py:567` `_write_version`, consumed at `A/cli.py:61` and
   `:1079-1087`. Superseded by `RENDER_ID`, not lost. **But**: B looks for `RENDER_ID`, not `VERSION`,
   so any A-installed project's existing `VERSION` file becomes silent litter while B's `_check`
   stales on the missing marker (`B/cli.py:1984-1986`). **Migration step required.**
2. **In-process initial refresh** — `A/install.py:659-662` (`from .cli import main`). B re-execs
   out-of-process through the just-vendored engine (`B/install.py:719-740`, `timeout=900`). Superseded.
3. **Revision-bearing journal markers** — `A/decision_journal.py:22-35`. **The one real one-way door.**
4. **Unconditional runtime in `load_workstream_overlay`** — `A/workstreams.py:604-607, 633`. Anything
   reading `runtimeRevision` from a *rendered* artifact starts seeing `null`.
5. **Manifest includes every path-bearing item** — `A/render/manifest.py:14`. B excludes
   `adapter == "conflicts"` (`B:19-20`). No-op for A today (no conflicts adapter), but don't port the
   exclusion blind.
6. **`_same_origin` as one method** — `A/cli.py:192`. B splits it (`B:258`, `:267`) so
   `/api/server/restart` can skip CSRF (`B:271-281`). Loopback + same-origin are still required, but
   this is a **deliberate security relaxation on one route**. Flag it in review.
7. **Four A tests break on the renderId port**, verified by grep:
   - `A/tests/test_cli.py:246,250` — asserts `vizzer/VERSION` and `"stale: vizzer/VERSION"`
   - `A/tests/test_install.py:21` — asserts `VERSION` content `== vizzer.__version__`
   - `A/tests/test_question_http.py:249` — writes `vizzer/VERSION` to force a version mismatch
   - `A/tests/test_render_constellation.py:336` — asserts `"if(body.engineVersion!==ENGINE_VERSION)"`
     in the emitted HTML

   `A/tests/test_decision_journal.py` has **no** `evolution-answer` marker assertions (grep returned
   nothing), so the journal migration is safer than feared — but re-check its golden fixtures under
   `tests/golden/`.

---

## 4. The illtool bias — how far config reaches, and where it stops

### 4.1 The surprising part: A's package is already clean, and the vocabulary is already upstream

`grep -rn "illtool" A/src/` → **zero hits**. All 29 illtool references in A are in
`tests/browser_live_illtool_smoke.js`, `docs/`, and `thoughts/`. A's shipped package is genuinely
project-agnostic today. **The port must preserve that property** — it is the single most valuable
thing A has.

And the status ladder is **not** a fork divergence. `DEFAULT_STATUSES`
(`idea/backlog/specced/ready/building/in-flight/bug-gap/shipped/verified/parked/unknown`) is
byte-identical at `A/config.py:25-38` and `B/config.py:25-38`. Illtool's vocabulary is upstream's
built-in default, overridable via `[[status]]`, validated by `_validate_statuses` (`:138-194`).

### 4.2 `config.py` diff, A vs B — the entire delta is four things

1. `"conflicts"` added to `SOURCE_AREA_ADAPTERS` (`B:18`)
2. `sources.conflicts = {enabled, path}` (`B:55`)
3. `"conflicts"` in `reconcile.precedence` (`B:60`)
4. The whole `reviews` block (`B:99-113`) + its validation (`B:322-355`)

Everything else — `source_area`, `area`, `progress`, `workstreams`, `assessment`, `priority`,
`planning`, `questions`, `discussions`, `activity` — is identical.

### 4.3 Where the abstraction stops — nine concerns with no config key

`[[source_area]]` reaches sources, semantics, and overlays. It does **not** reach:

| # | Concern | Location | Severity |
|---|---|---|---|
| 1 | **Story-path shape** `capabilities/*/epics/*/stories/*.md`, re-derived by hand in **three** places instead of from `sources.spec_tree.glob` + `levels` | `B/reviews.py:317` (`required_prefix = ("wiki","product-spec","capabilities")`), `B/review_links.py:32`, `B/ci_status.py:63-65` | **BLOCKER** |
| 2 | **Review screenshot archive** `wiki/reviews/archive` — hardcoded twice, ignoring the `reviews.archive_dir` key that exists | `B/render/review_archive.py:34`, `B/render/constellation.py:169` | LEAK + live defect |
| 3 | **Active-work register** `wiki/dev/active-work.md` | `B/render/lanes.py:13` | LEAK |
| 4 | **Codex results dir** `.codex-results/` in a receipt-path regex | `B/render/perspective_common.py:13, 130` | LEAK |
| 5 | **Owner identity** — "Ryder" in four regex alternates; `claude`/`ryder` as the two shot authors, incl. CSS classes | `B/render/awaiting_owner.py:20-21, 57-58`; `B/render/review_archive.py:265-266, 299, 315`; `B/render/constellation/views.css:125` | LEAK |
| 6 | **Serve-restart mechanism** `launchctl kickstart -k gui/501/com.ryders.vizzer-serve` — **three copies**, encoding launchd + **uid 501** + one person's reverse-DNS label | `B/cli.py:85-88` (verified), `B/render/constellation/notices.js:4` | **BLOCKER** |
| 7 | **Agent provider vocabulary** `PROVIDERS = ("codex","claude")`, validated as a closed set | `B/discussion_queue.py:18, 102, 131` | LEAK |
| 8 | **App name in the UI** — `'Open in illtool'`, `'Opened in illtool'`. The Python side is configurable via `app_process_names`; the JS never receives it | `B/render/constellation/dossier.js:54`, `B/state.js:577` | LEAK |
| 9 | **Status literals in renderers** — `[[status]]` lets you rename statuses, but ~45 sites compare against literal `"shipped"`/`"specced"`/`"bug-gap"`/`"in-flight"`. `cfg.status_role()` is the correct seam and mostly bypassed | `B/progress_history.py:23`, `B/render/ledger_table.py:11`, `B/assessment.py:565,588`, `B/render/analytics.py:47,149,155`, `B/state.js:592-593` (the whole ladder duplicated in JS), `filters.js` ×18, `canvas.js` ×6 | LEAK (**inherited from A**, not fork-introduced) |

### 4.4 Categories that came back clean

Worth stating, because they were the expected landmines and are not there:

- **Xcode / xcodebuild / XCTest / XCUITest: zero findings.** No test-selector parsing, no
  `-only-testing:`, no scheme names, no DerivedData. Test discovery is glob-based via
  `assessment.verification_globs`. (One prose mention at `B/reviews.py:200`.)
- **Swift / ObjC / C++ symbol parsing: zero findings.** No `func test`, no `XCTAssert`, no extension
  matching. `story_sidebar.py` parses Markdown headings only.
- **Hardcoded artifact URLs / external hosts: zero.** Port comes from `server.port` (default `0` =
  ephemeral); the fork pins `8477` in its own `vizzer.toml`, which is the intended use.
- **illtool `scripts/dev/*` names**: none of `sync-xcode-project.sh`, `spec-refresh.sh`,
  `gen-completion-sheet.py`, `owner-edit-digest.py`, `monolith-ratchet.sh`,
  `preflight-worktree-check.sh` appear in the engine. Only `review-shot.sh`, and only in rendered
  empty states (§5).
- **GitHub**: no hardcoded repo slug, workflow name, or branch-prefix matching. Branch handling is
  data-driven from `workstreams.json`.

### 4.5 The `configure` verb's blind spot

`B/install.py:_config_text` (`:370-508`) generates a fresh `vizzer.toml` and emits **no `[reviews]`
section at all** — so a newly-configured non-illtool project silently inherits `B/config.py:101-112`,
including `app_process_names = ["IllStandalone"]`. It also emits no `[sources.conflicts]` despite the
adapter existing.

Worse: the vendored agent instructions at `B/install.py:78-82` and `:128-132` tell every future agent
in *any* installed project to author `wiki/reviews/sheets/<id>.sheet.json` as a literal path.

And `B/render/__init__.py` registers `lanes`, `analytics`, `awaiting_owner`, `review_archive` to run
on **every** refresh, ungated. `render/review_archive.py:294` `render()` has **no** `enabled(cfg)`
check, in direct contrast to `render/review_sheets.py:187` which does. So upstream would ship a stray
`review-archive.html` and three illtool-flavoured markdown views to every consumer on first render.
They degrade to empty tables rather than crashing — hence LEAK, not BLOCKER, but it is exactly the
"bias toward this project" the owner asked to remove.

### 4.6 Undeclared config keys

Read at runtime but never in `DEFAULTS` and never validated, so a typo silently takes the default:
`reviews.brief_path` (`B/review_launch.py:62,92`), `reviews.app_bundle_id` (`:67`),
`reviews.launch_staging_dir` (`:113`), `server.autocommit` (`B/autocommit.py:59`), `ci.enabled`
(`B/cli.py:1141`).

---

## 5. The review / capture harness

### 5.1 Inventory

| File | Lines | Role |
|---|---|---|
| `B/reviews.py` | 2161 | Sheet parse/validate, response ledger CAS-append, verification captures, acceptance-bundle archival + rollback |
| `B/review_launch.py` | 335 | Stage a temp fixture copy + write a JSON brief, then `open -a` the app |
| `B/review_images.py` | 232 | Pure-stdlib structural validator for PNG/JPEG/WebP bytes |
| `B/review_links.py` | 111 | Map graph items → sheet rows that `reopens` them |
| `B/story_sidebar.py` | 58 | Pull Review steps / AC / DoD blocks out of story Markdown |
| `B/render/review_sheets.py` | 208 | Renders `review-sheets.html` (served console) + `.md` |
| `B/render/review_archive.py` | 338 | Renders `review-archive.html`, a zoom/pan screenshot viewer |
| `B/render/review_sheets/{review.js,review.css,shell.html}` | 561 | The served console client |
| `illtool/vizzer/docs/review-sheets.md` | 357 | The contract |
| `illtool/scripts/dev/review-shot.sh` | 277 | `capture`/`add`/`annotate`/`index` |
| `illtool/scripts/dev/gen-review-archive-index.py` | 118 | Regenerates the archive index |
| `illtool/scripts/dev/illtool-window-id.py` | 53 | Frontmost window CGWindowID via Quartz |
| `illtool/scripts/dev/extract-markup-layer.py` | — | Diff original vs Preview-annotated PNG → transparent overlay (Pillow) |
| `illtool/wiki/reviews/sheets/*.sheet.json` | 3 files | 2× schema 1, 1× schema 2 |
| `illtool/wiki/reviews/review-responses.json` | 12,455 B | `{schema:1, revision:19, events:[19]}` |

### 5.2 The `.sheet.json` schema (observed, not documented-from)

```
SHEET   schema ∈{1,2} · id ^[a-z0-9][a-z0-9._-]{0,79}$ · title ≤200 · date YYYY-MM-DD
        subtitle? ≤500 · chunks 1..60 (unique ids)
CHUNK   id · title ≤200 · minutes 1..120 (default 5) · note? ≤2000
        fixtures[≤16] · rows 1..100 (unique ids)
ROW kind="test"
        id · title ≤200 · tag? ≤120 · note? ≤2000
        do ≤4000        (required unless steps/testInstructions present)
        expect ≤4000    (always required)
        reopens? ≤300   ("capability/epic/story" or full story path)
        receipts[≤24 × ≤500]   ← the pre-verification receipts
        fixtures[≤16] · screenshots[≤12]
      schema 1: steps/acceptance/dod  [str]≤24, optional
      schema 2: story, testInstructions, acceptanceCriteria, definitionOfDone
                — ALL REQUIRED NON-EMPTY
ROW kind="decision"
        id · title · tag? · note? · questionId (must contain ":")
FIXTURE   origin ∈{repo,library} · repo→path (rel, no "..") · library→name (bare)
          note? ≤500 · page? ≤200
SCREENSHOT  path (rel, .png/.jpg/.jpeg/.webp) · caption? ≤300 · highlight[≤8]
HIGHLIGHT   x,y,width,height : float 0..1, w>0, h>0, x+w≤1, y+h≤1 · label? ≤120
```

Schema 2 additionally enforces that every `acceptanceCriteria`/`definitionOfDone` entry occurs
**verbatim** in the referenced story file (`_validate_story_contracts`, `B/reviews.py:714-773`).

### 5.3 Concept-by-concept

**Pre-verification receipts** are *free text*, not a structured object: `row["receipts"] =
_string_list(...)` at `B/reviews.py:513` — ≤24 strings of ≤500 chars, hand-authored into the sheet.
Live example: *"RED commit 6acd55ef7 — 4/4 new reviewable-row tests failed before implementation."*
Consumed at `render/review_sheets.py:159-160`, `review.js:88-90`, `review_launch.py:213`, and the
bundle README. **No validator enforces the "if it was NOT executed, say so" rule** — that is
prose-only in `review-sheets.md:177-179`.

**Sign-off ledger.** `review-responses.json` is append-only with CAS on `expectedRevision`
(`:1248-1252`), per-target fingerprint compare (`:1294-1298`), atomic whole-file replace with `fsync`
+ `os.replace` + dir-fsync (`_atomic_write`, `:108-129`), cap 20,000 events. Row verdicts
`pass|fail|skip`; chunk verdicts `approve|reject|carried`. `recordedBy: "owner"` is accepted **only**
from the served UI (`B/cli.py:938-942`) and refused by the CLI (`:1420-1426`). Live state: 13 row + 6
chunk events, verdicts `skip×6, carried×6, fail×4, pass×3`. **Zero `approve` events exist**, so the
fixture-move path has never fired in that repo.

**Launch-into-app.** Owner clicks → `POST /api/reviews/launch` → `primary_fixture` picks exactly one
fixture (row, then chunk, then siblings) → `stage_fixture` copies it into
`$TMPDIR/illtool-review-launch` (the library original is never opened, because illtool autosaves in
place) → `build_brief` writes `{schema:1, sheetId, chunkId, minutes, rows:[...]}` to **two** macOS
Application Support paths, one of them the App Sandbox container sibling → `["open","-a",app_name,
staged_doc]`.

**Screenshot capture and highlights are two unrelated mechanisms.** Authored `screenshots[]` are
committed repo-relative files produced *outside* the harness by XCUITest
(`scripts/dev/named-scenario-review-artifacts.sh`); the harness only validates and serves them.
Highlights are **data, not paint** — normalized 0..1 rects drawn client-side as absolute-%
`<i class="mark">` with a `box-shadow: 0 0 0 9999px rgba(0,0,0,.42)` dim (`review.css:54-55`).
Separately, owner-pasted verifications arrive via a DOM `paste` handler (`review.js:299-315`), are
byte-validated by `image_media_type`, capped (4 MiB/file, 24 files, 32 MiB total), and written
create-exclusive. They are **read back from the filesystem, never an index** — "the image IS the
record" (`:1092-1124`).

**Two things are called "archive."** (a) *Acceptance bundles* at
`wiki/reviews/<date>/<sheet>__<chunk>/`, built in a temp sibling then `os.replace`d in, containing
`sheet-chunk.json`, `responses.json`, `fixtures/` + `fixtures.json`, `screenshots/`, `verifications/`,
`README.md`. (b) The *screenshot archive* at `wiki/reviews/archive/<date>/NNN-slug.{png,json}` with a
generated `index.md` and an HTML viewer.

**The fixture MOVE is copy-verify-then-delete, never a rename.** On chunk `approve`: refuse unless the
latest chunk event is `approve` (`:1950`); if any library fixtures exist, `pgrep -x` the app and
**abort if it is running** — and abort too if `pgrep` itself is unavailable, so the gate never
silently disables (`:1376-1380`); write derived JSON *before* touching any fixture; copy each library
fixture into the bundle and re-hash at the destination; `os.replace` the whole bundle atomically; only
then re-fingerprint each library source and delete it **only if it still matches** `(sha256, bytes)` —
a concurrent edit is kept as a duplicate rather than deleted (`:1767-1768`). On any exception,
`discard_staged_bundle` reconstructs every vacated source using create-exclusive claims
(`os.mkdir`+`os.rename`, `os.link`, `os.symlink` — explicitly never `os.replace`), and if restoration
is impossible the bundle is **retained and disclosed**.

This is careful, well-reasoned code. It deserves to be ported rather than reinvented.

### 5.4 Dependency classification

**PORTABLE (no changes):** `review_images.py` · `story_sidebar.py` · `render/review_sheets.py` ·
`review_sheets/{review.js,review.css,shell.html}`. Notably the entire served console is already free
of illtool strings.

**CONFIG-HOOK:** `reviews.py` (11 keys already declared; needs the story-path prefix at `:317` derived
from `sources.spec_tree.glob`, and `app_process_names` defaulting to `[]` with the pgrep gate skipped
when empty) · `review_links.py` (`:32` regex) · `render/review_archive.py` (`:34` `ARCHIVE_REL`;
`:299,315,265-266` author identities; `:304` renders `scripts/dev/review-shot.sh` into the empty
state) · `gen-review-archive-index.py`.

**HOST-SPECIFIC:** `review_launch.py` **entirely** —
`~/Library/Application Support/illtool-standalone/Review/current-brief.json` (`:44-46`),
`com.illtool.standalone` (`:67,69`), the App Sandbox container path (`:96-99`), `open -a` (`:283`),
the `thumbnail.png`/`preview.png` in-package convention (`:328`). Plus `reviews.py:1374` (`pgrep -x`),
`review-shot.sh` (`screencapture -x -o -l`, `open -W -a Preview`, `/usr/bin/sips`),
`illtool-window-id.py` (pyobjc Quartz, `OWNER = "illtool"`), `extract-markup-layer.py` (Pillow — the
only third-party dependency anywhere in the harness).

### 5.5 The seam

**Stays in core, despite the filename:**

- `review_images.py` → rename to `images.py`. A general image-bytes validator with zero review
  knowledge. It already decodes width/height at `:70-71` without exposing them — **exposing that is
  the cheapest de-macOS-ing available**, since it replaces the `/usr/bin/sips` call outright.
- `story_sidebar.py` → it reads *story* Markdown, not review data. Its only consumer is
  `constellation.py:372`. If it moves behind the extra, the dossier loses its AC/DoD panel for every
  non-harness user.
- `story_path_key` → currently in `review_links.py:32`, imported by `ci_status.py:40`. **The sneakiest
  coupling in the codebase**: the CI feature silently depends on the review harness. Move it to a
  neutral module; that one extraction also fixes two of the three duplicated story-path regexes.

**Moves behind the extra:** `reviews.py`, `review_launch.py`, `review_links.py`,
`render/review_sheets.py` + assets, `render/review_archive.py`, the four shell/python capture scripts,
and `docs/review-sheets.md`.

**Four extension points core must grow.** None exist today; every one is currently a hardcoded list:

1. **Renderer registry** — `B/render/__init__.py:14-30` is a literal dict; `render_all` raises
   `ValueError` on an unknown name (`:41-44`). Needs
   `importlib.metadata.entry_points(group="vizzer.renderers")` or an explicit `register_renderer()`,
   plus graceful degradation for `--only`.
2. **HTTP route table** — `B/cli.py:1019-1033` (`do_POST`) and `:1077-1130` (`do_GET`) are flat
   `if parsed.path == …` ladders with **eleven** hardcoded branches. The biggest single refactor the
   port needs. Handlers need `cfg`, `root`, `csrf_token`, `_send_json`, `_same_origin`,
   `_require_current_engine`, `_read_json_body(max_bytes=)`, `_mutation_guard`. Note
   `_read_json_body`'s `max_bytes` parameter exists only because of the review paste path — that
   generalization is done and is core-safe.
3. **`check` gate providers** — `B/cli.py:1931-1965` hardcodes
   `if reviews_enabled(cfg): … unsigned_ingested_chunks(...)`. Needs a list the extra appends to. (The
   blocked-record gate at `:1888-1930` is core and stays inline.)
4. **Constellation node decorator** — `B/render/constellation.py:350-351, 372, 400-402, 439-448`
   injects `rv`/`rs`/`acx`/`dod`/`shots` and **mutates `node["q"]`, the search haystack**. The search
   corpus itself becomes review-aware. Needs a node-augmentation callback.

**The JS needs no seam work.** `reviewRows()` returns `[]`, `refreshReviewState()` swallows a 404
(`state.js:544-548`), `ci.js:106` renders no chrome on 404. It already degrades. One caution:
`state.js:344-345` reaches into `markFilters.review` **inside `passesSharedFilters`**, the core
visibility predicate — so with the module absent, `awaitingReview` must still be a *defined* function
returning `false`, not undefined. Declare null-object stubs unconditionally rather than branching on
`typeof`.

**Also a config-schema registry** — `B/config.py:99-113` (defaults) and `:322-355` (validation) both
run unconditionally today.

### 5.6 What the harness needs from a host project, as an interface

| Capability | Contract | illtool supplies | Generic host supplies |
|---|---|---|---|
| **Launch-with-document** | `launch(app, document?)` — start when down, **focus when up**, 0 or 1 document | `open -a <name> <doc>` | `reviews.launch_argv` template. **A real capability gap**, not a path substitution: LaunchServices gives launch-or-focus in one call; `xdg-open`/`start`/`Popen` do not. |
| **Brief handoff** | A well-known path where atomically-dropped JSON is picked up by the app | Two macOS Application Support paths + `ILLTOOL_REVIEW_BRIEF_PATH` | One configured path + `reviews.brief_mirror_paths: []`. The sandbox-container duplication is macOS-only and belongs in illtool's config, not the ported code. |
| **Fixture format** | A file *or directory package* that is self-contained, survives `copy2`/`copytree`, and is hashable as ordered relative contents | `.illtool` packages | Any format meeting those three. Single files already work. |
| **Fixture thumbnail** | fixture path → PNG bytes | `thumbnail.png`/`preview.png` inside the package | Same convention or a `thumbnail_command`. Optional — `None` degrades to no image. |
| **App-liveness probe** | `is_running() -> name \| None`, **fail closed** if the probe is unavailable | `pgrep -x` | Configured probe command. The fail-closed semantic must be preserved. |
| **Document library** | One directory outside the repo, addressed by bare filename | `~/Library/Application Support/illtool-standalone/Documents` | Any directory. **Already fully abstract and opt-out** (`""` disables). |
| **Window capture** | `capture(window_token, out_path) -> PNG` | `screencapture -x -o -l <CGWindowID>` + Quartz lookup | A capture command taking a window token. **The window-identity indirection is essential** — `illtool-window-id.py:3-8` records that plain region capture archived a picture of the terminal. |
| **Image dimensions** | `(w,h)`, degradable | `/usr/bin/sips` | Use `review_images.py`'s own IHDR parse. |
| **Annotation round-trip** | Open in an annotator, block until save, diff to recover an overlay | `open -W -a Preview` + Pillow diff | `annotate_command`. Preview's flatten-on-save is the *reason* the diff exists; a host with a real annotation format wants neither. |
| **Authored screenshots** | Something writes committed PNGs the sheet references | XCUITest via `xcodebuild` | **Nothing to abstract** — already fully decoupled. |
| **Story tree** | Story docs at a known path shape with AC/DoD headings | `wiki/product-spec/capabilities/…` | Configurable pattern + heading vocabulary. |

**One property must become explicit rather than inferred.** The entire temp-copy rail exists because
illtool autosaves in place (`review_launch.py:17-21`). A host whose app opens read-only doesn't need
the staging directory at all — but a host that *does* autosave and where the harness doesn't know it
would **silently mutate the owner's document library**. Make it
`reviews.launch_mutates_document: bool`, required when launch is enabled.

---

## 6. Port plan — eight workstreams, partitioned by file ownership

Design constraint: no two parallel workstreams write the same file. `cli.py`, `config.py`, and
`render/__init__.py` are the contention points, all three resolved by landing WS-0 first.

### WS-0 — Extension seams (**must land first; everything else depends on it**)
**Owns:** `A/src/vizzer/render/__init__.py`, `A/src/vizzer/cli.py` (route-table + gate-provider
refactor only, **no new features**), `A/src/vizzer/config.py` (section registry only).
**Does:** convert `RENDERERS` to a registry; convert the `do_POST`/`do_GET` ladders to a route table
with a documented handler contract; add a `check`-gate provider list; add a config-section registry.
Pure refactor — A's behaviour and tests unchanged.
**Verify:** A's existing 41-file suite passes untouched.

### WS-1 — Identity and packaging (**riskiest — see §7**)
**Owns:** `__init__.py`, `install.py`, `pyproject.toml`, `scripts/build_pyz.py`, `cli.py`
identity-gate region, and the four breaking tests.
**Does:** port `render_id`/`engine_version`/`Marker`; make `package_root()` and `ENGINE_RELPATH`
layout-derived (§7); write the `VERSION` → `RENDER_ID` migration; add
`[project.optional-dependencies]`.

### WS-2 — Frontend chrome and interaction (largest, cleanest)
**Owns:** every file under `render/constellation/` **except** review-coupled hunks, plus
`render/constellation.py` non-review regions.
**Does:** depth ramp/fog · `symbols.js` · `chip_layout.js` + measured chrome + `--z-*` scale · chip
legend · `view_tables.js` · deep links (**and define `toast`** — §2.9) · color lenses · cluster focus ·
node-focus camera + work-nav centering · answer mode · parked drafts · draft guard · field filters ·
authority alert · `boot.js` resource-error fix · stale-tab banner.
**Constraint:** the question-glyph shape and its distance function move **together** — A draws an X
with stroke-distance, B a filled disc with disc-distance plus a `'dot'` gate. Porting one without the
other silently breaks hit ownership. Highest regression risk in WS-2.

### WS-3 — Graph semantics
**Owns:** `activity.py`, `model.py`, `adapters/spec_tree.py`, `adapters/conflicts.py`,
`assessment.py`, `render/manifest.py`, `config.py` source-area + conflicts entries (via WS-0's
registry).
**Does:** blocked-record gate · `ActiveWork.blocked_by` · `Item.completion` + the two-provenance
completion dates · conflicts adapter · the 2-line assessment change.

### WS-4 — New perspectives
**Owns:** `render/perspective_common.py`, `render/analytics.py`, `render/awaiting_owner.py`,
`render/lanes.py`, `render/dashboard.py`.
**Does:** port all four, **gated off by default**, registered via WS-0's registry. Strip the "Ryder"
regexes and the hardcoded suppression sentence (do not port them, do not make them configurable —
drop them; the other five alternates in that regex are already generic). Route status literals through
`cfg.status_role()`. Make `REGISTER_PATH` a config key defaulting to `""` with the section omitted
when unset.

### WS-5 — Decision-journal migration (**isolate — one-way door**)
**Owns:** `decision_journal.py`, `tests/test_decision_journal.py`, `tests/golden/`.
**Does:** port the revision-free marker + replay dedup, keep the legacy reader, and write a forward
migration for existing A-format journals. `test_decision_journal.py` has no marker assertions, but
re-check the golden fixtures.

### WS-6 — Serve-loop features
**Owns:** `ci_status.py`, `autocommit.py`, `render/constellation/{ci.js,notices.js,notices.css}`,
`cli.py` route registrations (plugged into WS-0's table).
**Does:** CI overlay behind `[ci] provider = "gh"|"none"` · autocommit defaulting **false** ·
notices/served-error surface with the launchd command replaced by a `server.restart_command` config
value, **no default**, button hidden when unset. Declare `ci.enabled` and `server.autocommit` in
DEFAULTS with validation. Flag the CSRF-exempt restart route for review.

### WS-7 — Review harness extra
**Owns:** `reviews.py`, `review_launch.py`, `review_links.py`, `render/review_sheets*`,
`render/review_archive.py`, the four capture scripts, `docs/review-sheets.md`, and the
`[project.optional-dependencies] review` entry.
**Does:** port behind an extra per §5.5. Extract `story_path_key` and `images.py` to core first (blocks
WS-6, which imports the former). Gate `review_archive.render()` on `enabled(cfg)` — it currently is
not. Make the three story-path regexes one `Config.story_path_re()`. Neutral defaults throughout
(`app_process_names: []`, no `[reviews]` in generated config unless requested).

### WS-8 — Test corpus
**Owns:** `A/tests/` new files + a `conftest.py` path shim.
**Does:** port the 30 files / 11,738 lines from `illtool-standalone/scripts/dev/tests/test_vizzer_*.py`,
replacing `ROOT = parents[3]` + `sys.path.insert(ROOT/"vizzer/engine")` with A's
`pythonpath = ["src"]`. Runs continuously alongside every other workstream; each WS lands with its own
tests.

**Sequencing.** WS-0 alone → then WS-1, WS-2, WS-3, WS-4, WS-5 fully parallel → WS-6 after WS-7's
`story_path_key` extraction → WS-7 after WS-0. WS-8 throughout.

---

## 7. The riskiest part of the port

**WS-1, the `renderId` identity port.** Three reasons, in order:

**It is structurally welded to the vendored layout, and it fails hard rather than degrading.**

- `package_root()` at `B/__init__.py:109` is `Path(__file__).resolve().parents[3]` — correct for
  `<root>/vizzer/engine/vizzer/__init__.py`, wrong by one level for A's `src/vizzer/`, and in a pip
  install lands three directories above `site-packages` at an arbitrary path. **Fatal.**
- `render_id()` at `:369` computes `engine_root = base / ENGINE_RELPATH` where
  `ENGINE_RELPATH = "vizzer/engine"` (`:58`). A pip install has no such directory, so
  `_engine_source_files` returns `[]` and `render_id` **raises** at `:372`. Because `render_stamp`
  (`:459`) raises when `process_render_id()` is `None` (`:480`), **every render fails** — it does not
  limp, it stops.
- `_engine_revision()` at `:132` runs `git rev-list --count HEAD -- "vizzer/engine"`; A's correct
  pathspec is `src/vizzer`. Cosmetic (`compose_version` handles `None` deliberately) but wrong.
- Every consumer guards on `(root / ENGINE_RELPATH).is_dir()` (`B/cli.py:121, 1801, 1830, 1974`;
  `B/__init__.py:484`). In a pip install that is always false, so the gate **silently turns itself
  off** and degrades to A's current no-op. The worst outcome of the four, because it is invisible.

**Minimum fix:** resolve the engine root as `Path(__file__).resolve().parent` (the package dir itself)
and locate the project root by walking up for `vizzer.toml`/`pyproject.toml` rather than counting
parents. `MARKER_RELPATH` is already project-relative and is fine.

**Its blast radius is total.** `renderId` is stamped into every artifact and compared by the frontend
on every boot (`bootstrap.js:66,74,82,90`). Get it wrong and every view is either permanently stale or
permanently green — and the permanently-green failure is exactly the one the subsystem was built to
prevent.

**It breaks four existing A tests** and orphans the `vizzer/VERSION` file in every already-installed
project.

**Runner-up: WS-5, the decision-journal marker.** Lower blast radius but genuinely irreversible — the
markers live in committed story files across every downstream project, and B writes a form A cannot
match by string equality. Land it alone, with a migration, behind its own review.

**The quiet third:** `ci_status.py:40` importing `story_path_key` from `review_links.py`. A naive port
ships a "core" CI feature that ImportErrors whenever the optional review extra is not installed. One
function move to fix, one CI run to discover the hard way.

---

## 8. Direction calls

### B → A, clean lift

Depth ramp/fog · `symbols.js` (with §9 caveat) · chip layout + measured chrome + `--z-*` scale · chip
legend · view tables · deep links (+ `toast`) · story sidebar · node-focus camera + work-nav centering ·
color lenses · cluster focus · answer mode · parked drafts · draft guard · field filters · authority
alert · `boot.js` fix · stale-tab banner · reachability exemptions · blocked-record gate · conflicts
adapter · completion dates · `include_runtime` opt-in · decision-journal replay dedup (with migration) ·
`renderId` (with §7 fix) · `review_images` → `images` · `story_sidebar` · `story_path_key`.

### B → A after decontamination

Notices (strip the launchd string → `server.restart_command`, no default) · CI overlay (break the
`review_links` import; `[ci] provider`) · analytics (status literals → `status_role()`) · lanes
(`REGISTER_PATH` → config, default `""`) · autocommit (default **false**) · the review harness as an
extra · `perspective_common` (`.codex-results` → config).

### A → B

**Nothing.** All eight of A's newest fixes verified present in B (§3).

### Do not port at all — illtool-local

1. **`launchctl kickstart -k gui/501/com.ryders.vizzer-serve`**, all three copies (`B/cli.py:85-88`,
   `notices.js:4`). The *idea* — a restart button when the engine goes stale — is a real feature. The
   mechanism encodes one launchd service, one uid, and one person's domain. Don't config it either;
   make it a `server.restart_command` with no default, button hidden when unset.
2. **`B/render/awaiting_owner.py:57-62`** — suppressing one specific illtool story by matching a
   verbatim sentence. A data problem solved in code.
3. **The four "Ryder" regex alternates** at `awaiting_owner.py:20-21`. The other five in that regex
   are already generic; drop the name-bearing ones rather than making them configurable.
4. **`claude`/`ryder` shot-author colouring** (`review_archive.py:265-266, 299, 315`,
   `views.css:125`). Port as "group by whatever `by` values are present."
5. **`scripts/dev/review-shot.sh` rendered into empty states** (`review_archive.py:304`,
   `dossier.js:18`). Upstream has no such script; printing it is worse than printing nothing.
6. **`illtool-window-id.py` and `extract-markup-layer.py`** as shipped code. Ship the *interface*
   (§5.6 rows 7 and 9) and keep these as illtool's implementation. `extract-markup-layer.py` is also
   the only Pillow dependency in the whole harness.
7. **`app_process_names = ["IllStandalone"]`** as a DEFAULT (`config.py:112`). Default `[]`, skip the
   pgrep gate when empty.
8. **`'Open in illtool'` / `'Opened in illtool'`** string literals (`dossier.js:54`, `state.js:577`).
   The JS never receives `app_process_names`; plumb it or use a neutral label.

---

## 9. Open questions and what could not be settled

**One decision needs the owner, not an agent.** `B/render/constellation/symbols.js` embeds **15 SF
Symbol vector outlines** traced from Apple's symbol set (regeneration script named at `:4-9`). This
repo is **MIT licensed** and distributed as a public pip/pyz artifact. Apple's SF Symbols license
restricts use to Apple platforms and prohibits redistribution of derivative symbol artwork. Shipping
traced outlines inside an MIT package is a genuine legal conflict, and `symbols.js` is a
**load-bearing prerequisite** for WS-2's chip legend, the eyeglasses badge, the parked-answer ring,
and the question hit refinement — so this blocks a large slice of the frontend port. Options:
substitute an openly-licensed icon set, draw originals, or keep symbols illtool-local and ship A with
its existing hand-drawn glyphs.

**Five factual gaps, each with the check that closes it:**

1. **Does `_archive_shots` actually ignore `reviews.archive_dir`?** The hardcode at
   `render/constellation.py:169` and the config default `"wiki/reviews"` at `config.py:103` are both
   verified — so today they coincide by accident. Not run. **Check:** set `reviews.archive_dir` to
   something else and confirm the shots vanish.
2. **Are `render/review_sheets/*.{js,css,html}` in the built `.pyz`?** A's `build_pyz.py:60-61` stages
   `src/vizzer` + `docs/context`; A's `pyproject.toml` `package-data` lists only `constellation/*`.
   **Check:** `python3 scripts/build_pyz.py && unzip -l out.pyz | grep review_sheets` after the port.
3. **Does the fixture-move path have real test coverage,** given zero `approve` events exist in the
   live ledger? **Check:**
   `grep -n "approve\|library_dir\|movedFrom" illtool-standalone/scripts/dev/tests/test_vizzer_reviews.py`.
4. **Which of B's `include_runtime` callers pass `True`?** `/api/workstreams` does
   (`cli.py:1168-1170`). **Check:** `grep -rn "load_workstream_overlay" B/` to be sure no rendered
   artifact path opts in.
5. **`views.css` rule-body changes.** The comparison was of selector *sets*, not full rule bodies,
   because both files are heavily minified single-liners; some colour/weight changes may be
   behavioural. **Check:** `diff -u --ignore-all-space` on the `.viewtable`/`#viewpanel` rules
   specifically.

**Deliberately not done:** neither tool was executed. Every claim is source-verified, not
execution-verified. The first thing WS-0 should do is stand up A's existing suite as a green baseline
before anything moves.

## See Also

- [PRDs and living product specs](../../docs/context/prds-and-living-product-specs.md)
- [Story sizing and portfolio selection](../../docs/context/story-sizing-and-portfolio-selection.md)
