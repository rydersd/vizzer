# Upstream intake — execution record

This records pre-publication verification; CI and merge remain separate gates.

## Attacks and repairs

- Incremental comparison avoided overwriting earlier upstream planning,
  appearance, and editing behavior with the divergent downstream fork.
- Backend adversarial review found malformed merge-record crashes, incomplete
  build records, ambiguous multi-host spend, silent timezone fallback, and wrong
  main-ref precedence. All were repaired; independent backend recheck passed.
- Stale graph recovery is opt-in for three read-only GET routes. Mutations use
  fresh source under their existing guard. Cached JSON is reconstructed per read.
- The first circle test accidentally blessed the extra ring. Replaced it with
  an executed canvas-call oracle: exactly one centered circle for ordinary ready
  nodes, no outer version circle. Version uses stroke width to preserve the
  upstream contrast contract; noncircular lifecycle glyphs retain their ring.
- Hierarchy navigation now preserves an open question editor and invalidates
  pending planning-area responses before opening read-only details.
- The initial complete suite ran 659 passing, 3 failing, 2 skipped. Two failures
  came from putting temporary non-repository fixtures underneath the clone:
  Git discovered the parent repository. Temporary fixtures now live in a separate
  external-drive directory. The third caught source-project names in comments;
  provenance remains in this intake's documentation, not generic runtime source.
- Browser verification caught a no-epic layout collapse and misleading WIP
  wording in the interactive Velocity tab. The renderer no longer invents an
  epic for root capabilities, and epic-less nodes retain their original scatter.
  The tab now describes recorded in-progress work, not presumed completion.
  Executable tests cover both boundaries; a repaired browser preview visibly
  spreads the flat project. Nonempty tab tests bind displayed WIP and window data.

## Review provenance

Claude Sonnet review attempted in read-only plan mode, session
3925dbe8-bd27-4bf7-bf8d-721530d02780: HTTP 429 weekly limit, zero tokens,
NO VERDICT. Independent Codex backend review passed after repairs. Independent
Codex frontend review requested the WIP wording/parity repair. These are Codex
reviews, not Claude reciprocal review.

## Boundaries

All source changes, environments, packages and test fixtures are on the external
drive. Existing upstream and IllTool checkouts and their running services were
not modified. A temporary loopback preview serves this candidate only.
Package build and packaged `check` passed; the CLI has no `--version` flag.
Browser verification is developer evidence, not owner UX approval.
Final local full suite: **664 passed, 2 skipped**, Python 3.9 / Node 25,
107.67 seconds. The existing optional integration skips are unchanged. Hosted
Python 3.9–3.13 and distributable CI, PR review and merge remain pending.
