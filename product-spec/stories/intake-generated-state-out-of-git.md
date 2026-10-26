# Generated state stays out of Git

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, storage

## Origin

IllTool 2bd3abf86 (#1436), 7469ca7ff, df53d9811.

## Acceptance

- Disposable rendered output (generated views, review packets) is regenerated
  locally by any reader and stays out of Git.
- Durable records (review plans, agent runs, owner verdicts, the answer ledger)
  stay tracked and append-only; they are never treated as generated state.
- Legacy tracked history is kept until compaction.
- Stored history size is measured and reported, not estimated.

## Named tests

- (planned) `tests/test_generated_state.py::test_fresh_clone_refresh_regenerates_views_and_check_passes`
- (planned) `tests/test_generated_state.py::test_durable_records_stay_tracked_and_legacy_history_survives_until_compaction`
