# Lifecycle truth fixes

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, lifecycle

## Origin

IllTool e8848c0bc (owner answer r416), 5a7af75bf, cbdb5c7a6 (#1449), 32730bf73 (#1354).

## Acceptance

- A shipped story stays shipped unless the configured lifecycle policy withdraws
  it. The policy (e.g. a shipped gate on failing acceptance tests) is the only
  thing that withdraws a shipped label; later edits never do.
- A promotion whose story has shipped is satisfied, not a warning.
- A status flip not yet persisted is stamped at the progress-history ledger's persisted
  `updatedAt`.


## Test plan (RC)

Startup-smoke fixes from #1354 are verified by the RC browser smoke.

## Named tests

- `tests/test_progress_history.py::test_shipped_story_with_later_non_withdrawing_edits_stays_shipped` (PR #20)
- `tests/test_progress_history.py::test_check_never_writes_the_ledger_and_stamps_an_unpersisted_flip_at_its_updated_at` (PR #20)
- `tests/test_planning.py::test_shipped_promotion_is_satisfied_not_a_warning_while_a_missing_one_still_warns` (PR #20)
