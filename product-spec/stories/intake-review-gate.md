# Review gate and sheets on the neutral contract

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, review

## Origin

IllTool `reviews.py`, `review_gate.py` (00b92c9de, e2ffc075a), `review_links`,
`review_plans`, `review_images`, `review_captures`, `render/review_sheets`,
`render/review_archive`, `story_reviews.js`, eee2af14f (#1337), 514e917a5.

## Acceptance

- Review rows are held while scope is deferred, questions are open or the build is
  unverified; chunk approval of a held row is refused; reopen paths are listed.
- One consolidated current-state review sheet, newest first, built from the
  neutral review contract's plans and runs.
- Archived reviews stay readable; archival never takes ownership of host fixtures.

## Named tests

- (planned) `tests/test_review_gate.py::test_held_row_refuses_chunk_approval_and_states_why`
- (planned) `tests/test_review_gate.py::test_consolidated_sheet_shows_latest_run_per_plan_newest_first`
- (planned) `tests/test_review_gate.py::test_owner_verdict_and_agent_run_stay_distinct_under_one_fingerprint`

## Open contract questions

- Source of truth for hold state (deferred, open questions, unverified build).
- State transitions for deferred, hold, reopen and chunk approval.
- Which events list reopen paths, and who may reopen?
