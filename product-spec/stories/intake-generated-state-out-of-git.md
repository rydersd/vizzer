# Generated state stays out of Git

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, storage

## Origin

IllTool 2bd3abf86 (#1436), 7469ca7ff, df53d9811.

## Acceptance

- Generated views, workstream history and review packets are not tracked; any
  reader regenerates them locally. Legacy tracked history is kept until compaction.
- Stored history size is measured and reported, not estimated.

## Tests

1. Refresh in a fresh clone regenerates views; `check` passes without tracked views.
2. Legacy history survives until compaction (data-loss guard).
