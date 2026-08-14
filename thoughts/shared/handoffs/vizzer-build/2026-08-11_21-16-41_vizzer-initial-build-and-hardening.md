---
date: 2026-08-11T21:16:41-0700
session_name: vizzer-build
researcher: rydersd
git_commit: 250d0fb5e0aa7681b4f3d55b5edeec5958cf8237
branch: agent/vizzer-0.8.31-interaction-reliability
repository: project_vizzer
topic: "vizzer initial build, hardening, and config-declared grouping"
tags: [implementation, strategy, vizzer, adapters, renderers, security, packaging, grouping]
status: complete
last_updated: 2026-08-11
last_updated_by: rydersd
type: implementation_strategy
root_span_id:
turn_span_id:
---

# Handoff: vizzer built, hardened over four review rounds, released v0.1.0

## ⚠️ Read this first — the repo has moved past this session

This handoff documents commits **1–37** (root `6b1cd3a` → `bc7ab06`), which built vizzer
from nothing to the released **v0.1.0**. The repo is now at **v0.8.31**, 50 commits, on
branch `agent/vizzer-0.8.31-interaction-reliability`, with **339 tests passing**. Thirteen
commits by later sessions added surfaces this session never touched:

- `src/vizzer/render/decision_journal.py`, `src/vizzer/render/discussion_queue.py`
- config: `[[area]]`, `[activity]`, `[assessment]`, status `role`/`next` transitions,
  `reconcile.dependency_authority`, `sources.loose_docs.item_role`
- a live browser test harness (`tests/browser_live_*.js`)

**Do not treat the architecture notes below as current for those areas.** The core
pipeline (adapters → graph → renderers) and everything in "Learnings" is still accurate —
that is the load-bearing part worth carrying forward.

## Task(s)

1. **Design + plan vizzer** — COMPLETE. Abstract a private single-project set of spec-view
   generators into a public, project-agnostic tool. Spec and plan approved by owner.
2. **Build all 15 planned tasks** — COMPLETE. Model, config, git metadata, four adapters,
   reconciler, seven renderers, engine CLI, installer, packaging, CI.
3. **Harden against four rounds of scrutiny** — COMPLETE. Sixteen defects found and fixed.
4. **Release v0.1.0** — COMPLETE, cut twice (re-cut after later fixes).
5. **Config-declared parent groups** — COMPLETE (`bc7ab06`), driven by a real deployment
   need: one install spanning a shared core plus two apps.

## Critical References

- `docs/superpowers/specs/2026-08-06-vizzer-portable-spec-views-design.md` — approved design
- `docs/superpowers/plans/2026-08-06-vizzer-implementation.md` — the 15-task TDD plan
- `docs/field-report-2026-08-07.md` — **the most valuable document here**: all sixteen
  defects, why a green suite missed them, and the judgment calls

## Recent changes

Session range `6b1cd3a..bc7ab06` (37 commits). Load-bearing ones:

- `src/vizzer/model.py` — normalized graph, deterministic serialization, validation
  (rejects group cycles, malformed ids, non-numeric activity)
- `src/vizzer/config.py` — bundled TOML-subset parser (stdlib-only; `tomllib` is 3.11+ and
  the floor is 3.9), status vocabulary with per-status `done`
- `src/vizzer/adapters/` — `spec_tree` (+ shape-tolerant DAG import), `ledgers`,
  `loose_docs`, `todos`; common `ScanResult` contract
- `src/vizzer/reconcile.py` — precedence merge, file claims, visible conflicts,
  dangling-dep pruning, dependency-cycle reporting, config-declared parent groups
- `src/vizzer/render/` — roadmap, feature index, dashboard, completion sheet, ledger table,
  manifest, constellation (ported template)
- `src/vizzer/install.py` — source detection, engine vendoring (zipapp-aware), managed
  CLAUDE.md/AGENTS.md block, `update` verb
- `scripts/build_pyz.py` — byte-reproducible zipapp (fixed timestamps, sorted staging)

## Learnings

**Synthetic fixtures cannot disagree with their author.** Sixteen defects survived a green
suite. They were found by changing *who or what* was looking, never by writing more tests
in the same style:

1. Dogfooding on a large real repo → 4 defects (including a completely broken `.pyz`
   install path and every dependency edge silently dropped)
2. An independent trial on a differently-shaped project → 5 defects
3. An adversarial review aimed at the fixes → 6 defects, including one **created by a fix**
4. Final end-to-end verification → 1 (silent dependency cycles)

**Specific traps worth remembering:**

- **Sequential `str.replace` on templates is an injection vector.** Escaping `__TITLE__`
  then replacing `__DATA__` let the first substitution's output be re-scanned, so a title
  containing the literal `__DATA__` smuggled the JSON payload into the HTML body. Fixed with
  a single `re.sub` pass (`src/vizzer/render/constellation.py`).
- **Zipapp breaks filesystem assumptions.** `shutil.copytree` and `Path(__file__).parent`
  both fail inside a `.pyz`. Use `zipimport` loader `.archive` and `importlib.resources`.
  Unit tests never caught it because they ran in-process from source.
- **Real DAGs key collections by slug (dicts), not lists.** Assuming lists skipped all 43
  stories in a real project. Detect by *records* (`slug` + one of
  `deps`/`status`/`release`/`wave`), not by one key path.
- **A fix that trades a false positive for a false negative has not solved the problem.**
  Overrode a proposed "≥3 slug records" DAG threshold — the work-item signal alone
  discriminates, and counting would reject legitimate small DAGs.
- **A check that cries wolf is worse than no check.** The duplicate-id warning fired 524
  times on a real repo because `dag_import` restates every story id by design. Cross-adapter
  same-id is the merge path; only same-adapter collisions are duplicates.
- **Docs are corpus, not work items.** `loose_docs` auto-enabled alongside a real spec tree
  became 738/1498 items on one repo and 111/154 on another. It is now a fallback only.
- **The declared Python floor was wrong.** All tests pass on 3.9.6, which is what macOS
  ships — and vizzer's pitch is "no dependencies beyond system python3". Floor is `>=3.9`.

**Test bugs masquerading as code bugs — four this session.** Each would have sent someone
editing correct code:
- two edited a config key the fixture did not contain (silent no-op `str.replace`)
- one asserted a threshold its own fixture was too small to reach
- one forbade a string anywhere in the document when the real invariant was "not outside the
  script block"

**Read why a test is red before believing it. A red test is a claim, not a verdict.**

**Codex lane operations:** a `<task-notification>` reporting killed/failed usually killed
only the *Bash wrapper* — codex kept running and often finished. Verify artifacts (`ls` +
run the suite), never the exit status. Check liveness with
`ps -eo pid,etime,command | grep "[c]odex exec"`. Hangs correlated with mega-prompts: the
only lane that truly died was the one told to read two large documents. Rewriting it as a
compact self-contained `task.md` in the scratchpad succeeded immediately. Saved as memory
`codex-lane-kill-notifications`.

## Post-Mortem

### What Worked

- **Dogfooding on real repositories before trusting the suite.** Highest-yield practice by
  a wide margin — found four defects the tests structurally could not see.
- **Test-first codex handoff via compact scratchpad task files.** Claude writes the failing
  tests as the contract; codex implements blind; Claude verifies artifacts and commits.
  Roughly a dozen lanes, nearly all clean on first try.
- **Cross-vendor review after changes, not just once.** The second review found a
  high-severity hole introduced by the first review's fix.
- **Verifying claims by independent reproduction.** The graph reported 0 status conflicts
  across 524 stories, which looked broken; checking the DAG against story files
  independently proved it correct. Also proved `commit-revenue-target` in the ready queue
  was a *data gap in the consuming project*, not a vizzer bug — acting on the surface
  reading would have meant changing correct code.
- **Chasing single anomalies.** 38 of 39 dependency pairs ordered correctly; chasing the one
  violation found an unreported dependency cycle.

### What Failed

- Tried: `timeout` command on macOS → not available; use the Bash tool's `timeout` param.
- Tried: mega-prompt codex lanes (read plan + spec, then implement) → hung 48 min with zero
  output → fixed by compact self-contained task files.
- Error: suite appeared to hang for 2 min → was CPU contention with a running codex process,
  not a code defect. Isolating test-by-test proved it.
- Tried: a reproducibility test comparing two builds → passed against broken code (ZIP
  timestamps have 2-second granularity). Rewritten to assert one fixed timestamp per entry.

### Key Decisions

- **Derived graph file committed to the repo** (`vizzer-graph.json`), sources stay
  authoritative. Alternatives: read-only lens; active restructurer. Reason: other tools and
  agents can consume a stable normalized index; conflicts stay visible rather than silent.
- **Vendored engine, not a dependency.** Alternatives: pip install; copy-in template.
  Reason: zero setup for cloners, CI, and agent sandboxes; `update` re-vendors.
- **Config-declared `[[group]]` over a per-story `Product:` field.** Alternatives: per-story
  field (43 file edits); three separate installs (loses the shared core and the one
  cross-product edge); directory restructure (43 moves + link fixups + tooling updates).
  Reason: the consuming project's capabilities partition cleanly by product, so nine lines
  of config express the truth with zero file moves — and the tool should never force a
  filesystem migration to express a grouping.
- **Provenance scrubbed from git history, not just the working tree.** Reason: the first
  commit message and original doc text would otherwise have gone public on push.

## Artifacts

- `docs/superpowers/specs/2026-08-06-vizzer-portable-spec-views-design.md`
- `docs/superpowers/plans/2026-08-06-vizzer-implementation.md`
- `docs/field-report-2026-08-07.md`
- `thoughts/ledgers/CONTINUITY_CLAUDE-vizzer-build.md` — **STALE**, see next steps
- Public repo: https://github.com/rydersd/vizzer · release `v0.1.0`
- Memory: `~/.claude/projects/-Users-ryders-Developer-GitHub/memory/codex-lane-kill-notifications.md`

## Action Items & Next Steps

1. **The continuity ledger is badly stale.** Its `Now:` still reads "T14 installer — codex
   RETRY in flight", which completed on 2026-08-06. Everything through v0.8.31 is missing.
   Rewrite or retire it — `thoughts/ledgers/CONTINUITY_CLAUDE-vizzer-build.md`.
2. **Five untracked files on the current branch** — `docs/fix 1.md` (note the space in the
   filename), `docs/fix-1-evidence.md`, `tests/browser_live_constellation_matrix.js`,
   `tests/browser_live_illtool_smoke.js`, `uv.lock`. Decide: commit or remove.
3. **`.venv` had no pytest** when this handoff was written (`uv pip install -p .venv/bin/python
   pytest` fixed it). If CI-equivalent local runs matter, pin dev deps.
4. **The release is far behind HEAD.** `v0.1.0` predates 13 commits and v0.8.31; the README
   `curl` quickstart still resolves to the old artifact. Re-cut when the branch lands.
5. **Owner decision still open** for the consuming monorepo: whether to also do the
   `spec/<product>/…` restructure. It is no longer a prerequisite for product rollups —
   `[[group]]` delivers those with no file moves.
6. **Consuming-project data gaps to report back** (not vizzer bugs): `commit-revenue-target`
   has no dependencies recorded in the DAG though the delivery log treats it as blocked; and
   Notes declares zero dependencies on Core despite 25 prose mentions of SpuriousCore.

## Other Notes

- **Test runners:** `.venv` (3.12) and `.venv39` (3.9) both exist. Two tests are
  version-guarded — they assert the 3.11+ integer digit limit and skip below it.
- **The engine runs from the vendored copy** as `python3 vizzer/engine <verb>` — no PATH, no
  venv. That is the contract that makes it work in CI and agent sandboxes.
- **Determinism is a hard requirement**: stable sort orders, dates from git, no wall-clock.
  The constellation's `now` is `max(last_touched)`, never `time.time()`. Golden-file tests
  depend on fixture commits using fixed `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`
  (`tests/conftest.py`).
- **`check --structural`** intentionally skips `manifest.json` and `constellation.html`
  because both embed activity data; an unrelated commit would otherwise fail it.
- Verified deployments: a 1,656-item repo and a 43-story monorepo, both installed and
  rendered using macOS **system** Python 3.9.
