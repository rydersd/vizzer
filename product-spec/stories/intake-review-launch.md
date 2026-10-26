# Launch the project's app for review

> Status: specced
> Deps: [intake-review-gate](intake-review-gate.md)
> Release: R1
> Tags: upstream, review, adapters

## Origin

IllTool `review_launch.py` (85b0e46f8, 56862024c, 73b0e9d5f, 94e6f7250,
9f5f370b1, 9da0524b2, 28a181a3e, a2184d1f4, e2ffc075a), `preverify.py`, `channel.py`.

## Acceptance

- One click opens the project's app on a staged copy of the review fixture with
  the brief, through adapter operations declared in project configuration
  (launch, stage, liveness, automation request/response). Originals are never opened.
- Build provenance policy (e.g. owner builds from the main branch only, lane
  builds need a reason) is configuration.
- Staged copies are named and pruned only when no holder remains; only
  self-launched processes are terminated.
- Failed verdict says not saved; a recorded verdict leaves a receipt.

## Test plan (RC)

The gating RC test runs end to end against a neutral fixture project
(`tests/fixtures/mixed_proj`) with a fixture adapter. A run against IllTool is
non-gating migration evidence only.

## Named tests

- (planned) `tests/test_review_launch.py::test_launch_stages_a_copy_and_original_bytes_unchanged`
- (planned) `tests/test_review_launch.py::test_undeclared_operation_is_refused`
- (planned) `tests/test_review_launch.py::test_prune_skips_a_copy_with_a_live_holder`

## Open contract questions

- Which host-side executor runs adapter operations, and under what trust?
- Staging containment: where copies may live and how escapes are refused.
- Holder ownership: how a holder is identified and who may release it.
- Never-launched oracle: how a test proves the original was not opened.
