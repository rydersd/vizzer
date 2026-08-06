# Continuity — vizzer build

## Goal
Ship vizzer v0.1.0: public, stdlib-only tool that normalizes a project's work-tracking
sources into a checked-in graph + 7 regenerable views, installing itself into target
projects with CLAUDE.md/AGENTS.md registration. Done = all 15 plan tasks green,
cross-vendor review passed, repo ready for public GitHub push.

## Constraints
- Spec: docs/superpowers/specs/2026-08-06-vizzer-portable-spec-views-design.md (approved)
- Plan: docs/superpowers/plans/2026-08-06-vizzer-implementation.md (tasks T1-T15, test code is the contract)
- Python ≥3.10 stdlib-only runtime; deterministic outputs; no the source project/personal content (public repo, MIT)
- Delegation: codex implements marked lanes; Claude verifies artifacts + commits; cross-vendor review before done
- Test runner: .venv/bin/python -m pytest tests/ -q (venv is py3.12 via uv; system python3 is 3.9 — too old)

## Key Decisions
- Derived-graph-file model (vizzer-graph.json committed; sources stay truth; conflicts visible, never silent)
- Distribution: vizzer.pyz installer that VENDORS engine into <project>/vizzer/engine (run: python3 vizzer/engine <verb>)
- Config: bundled TOML-subset parser (tomllib is 3.11+, floor is 3.10)
- Constellation "now" = max last_touched (deterministic, no wall clock)
- archive verb: opt-in, --yes required, default scope todos only, target gitignored
- README release URL assumes public repo github.com/rydersd/vizzer — CONFIRM actual repo name at push time

## State
- Done:
  - [x] T1 model  [x] T2 config  [x] T3 gitmeta+conftest  [x] T4 spec_tree
  - [x] T5 ledgers  [x] T6 loose_docs  [x] T7 todos  [x] T8 reconciler
  - [x] T9 registry+roadmap+feature-index  [x] T10 dashboard+completion-sheet
  - [x] T11 ledger-table+manifest  [x] T12 constellation (Claude port, zero the source project refs)
  - [x] T13 CLI+mixed fixture+goldens (goldens eyeballed)  [x] T15 pyz+CI+README
- Now: [→] T14 installer — codex RETRY in flight (first attempt died with zero artifacts;
  one-retry-then-reroute rule active: if retry fails, implement inline from plan's test contract)
- Next: full suite re-run (T14 touches cli.py → re-verify pyz test), commit T14,
  then `codex review` cross-vendor pass over whole repo, fix findings, done-report.

## Open Questions
- UNCONFIRMED: public repo name/remote (README says github.com/rydersd/vizzer)
- Cosmetic backlog: dashboard shows 0/0 bars for ledger/todo groups (noted at T13 eyeball, deferred)

## Working Set
- Branch: main (13 commits, all tasks committed individually, no attribution)
- 33 tests green pre-T14; plan checkboxes NOT ticked in plan file (state tracked here + git log)
- Codex lane pattern note: 3 lanes (T8/T10/T13) reported "killed" AFTER completing —
  always verify artifacts, not exit codes. T14 attempt 1 was a true empty death.
