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

## Tests

1. Launch stages a copy; the original's bytes are unchanged (data-loss guard).
2. Undeclared operation is refused.
3. Prune skips a copy with a live holder.

## Test plan (RC)

IllTool configured as the first adapter on the RC, end to end, by the owner.
