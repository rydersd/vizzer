# Continuity ledger — IllTool intake 2026-10 + Hermes

## Fixed facts
- Source: illtool-standalone origin/main 93fdab962; prior intake base b6a67bb80776ce246c9845f067c872deead975ff.
  Path map vizzer/engine/vizzer/ -> src/vizzer/. Already upstream: 93051bb8c(#13), def1064ed(#14), abb082fd9(#15).
- Spec branch: upstream/illtool-2026-10-17 (stories 023c3d9, c352a2e + rulings commit).
- Owner rulings 2026-10-17: port ALL via 2026-08-23 matrix gates; extend neutral review contract, no 2nd review
  system; Lucide replaces SF Symbols; served-write autocommit runs hooks by default; slice list confirmed.
- Hermes facts: see product-spec/stories/hermes-integration.md (Origin).

## Method
- Per slice: format-patch the slice's commits relative to vizzer/engine/vizzer, seed pre-image blobs into the
  vizzer object store, `git apply -3 --directory=src/vizzer`, resolve, port 2-3 tests with neutral fixtures,
  leak-guard grep, full pytest, codex review (§4), PR per slice stacked on the spec branch.

## State
- [ ] slice 1 intake-question-navigation
- [ ] slice 2 intake-lifecycle-truth
- [ ] slice 3 intake-generated-state-out-of-git
- [ ] slices 4-11, hermes-integration
