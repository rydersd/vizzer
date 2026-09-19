# Pre-mortem — downstream Vizzer intake, 2026-09-19

Written before product edits. Predictable failures: copying fork-specific roots
mislabels upstream PRs; tests depend on IllTool's live graph; replacing files
discards upstream fixes; stale fallback makes validation or mutations accept an
obsolete graph; layout fails on empty/small/degenerate projects; velocity adds
nondeterministic or expensive Git reads to every renderer.

Falsifiers: synthetic graphs and temporary Git repositories; missing/torn graph
with cached content; safe-path and malformed configuration probes; full existing
suite; package smoke test; independent review of exact candidate. Import bounded
source hunks, not generated output. Keep main and unrelated branches untouched.
