# Continuity ledger — IllTool intake 2026-10 + Hermes

## Fixed facts
- Source: illtool-standalone origin/main 93fdab962; prior intake base b6a67bb80776ce246c9845f067c872deead975ff.
  Path map vizzer/engine/vizzer/ -> src/vizzer/. Already upstream: 93051bb8c(#13), def1064ed(#14), abb082fd9(#15).
- Spec branch: upstream/illtool-2026-10-17 (stories 023c3d9, c352a2e + rulings commit).
- Owner rulings 2026-10-17: port ALL via 2026-08-23 matrix gates; extend neutral review contract, no 2nd review
  system; Lucide replaces SF Symbols; served-write autocommit runs hooks by default; slice list confirmed.
- Hermes facts: see product-spec/stories/hermes-integration.md (Origin).

## Later source commits (2026-10-26, illtool origin/main 1dd48fa8f)
Engine commits after 93fdab962, mapped to existing slices (no new capability beyond the 2026-10-17 port-all ruling):
- 24bf253a4 progress-history merge unions events -> intake-generated-state-out-of-git
- 2eca5a943, fc10bed7c, dba9110bd serve-branch guard / autocommit names revision -> intake-served-write-durability
- 1146552d1 overflow chips show lifecycle symbols -> intake-constellation-chrome
- 98dde8d08 serve listen backlog 128 -> intake-served-write-durability (serve robustness)
- e2dbcb992 (#2003) issue trails -> intake-bug-pulse
- 052540589 (#2021) rail reveals capability/epic -> intake-constellation-polish
- 3bf75a077 (#2062) focused cluster spread -> upstream PR #18 (already ported)
- upstream PR #17 (question prev/next) is the navigation half of intake-question-navigation

## Method
- Per slice: format-patch the slice's commits relative to vizzer/engine/vizzer, seed pre-image blobs into the
  vizzer object store, `git apply -3 --directory=src/vizzer`, resolve, port 2-3 tests with neutral fixtures,
  leak-guard grep, full pytest, codex review (§4), PR per slice stacked on the spec branch.

## State
- [ ] slice 1 intake-question-navigation
- [ ] slice 2 intake-lifecycle-truth
- [ ] slice 3 intake-generated-state-out-of-git
- [ ] slices 4-11, hermes-integration
