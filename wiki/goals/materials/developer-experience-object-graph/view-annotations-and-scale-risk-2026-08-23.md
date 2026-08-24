# Saved views, annotations, and scale-risk follow-up — 2026-08-23

> Goal: [G-002 — Developer-experience object graph](../../developer-experience-object-graph.md)

## Implemented contract

- Served named views persist semantic scope/filter state, view notes, canvas/object note cards, and
  freehand vector strokes in a bounded schema-1 project-relative document.
- Writes use same-origin/CSRF guards and compare-and-swap revisions. Static-file mode keeps a
  browser-local fallback but will not pretend that local annotations are shareable.
- Notes and strokes live in graph coordinates, survive saved-link reloads and zoom, and export as
  SVG text/paths. They decorate the view and cannot write project dependency truth.

## Real browser attack

A neutral nine-object fixture was served at a fixed loopback port. The test added and edited a note,
drew a pink six-point stroke, saved the named view, copied its URL, navigated to that URL, and zoomed
the graph. The first attempt exposed a URL-normalization bug that removed `saved=<id>` before the
store loaded; the implementation was corrected and the complete sequence repeated.

Observed after the corrected reload:

- URL retained `saved=view-fc5fee66b9964dbeac4df1f7c1b4477e`.
- The note and stroke both restored (`Notes (2)`), with the saved view active.
- Zoom changed the React Flow viewport from scale `0.257519` to `0.309023`; the note moved with the
  viewport and the stroke remained present.
- Browser error/warning log was empty.

## 100k cold-path measurement

The attack creates 100,000 neutral objects, 199,899 relations, and 100 groups, then normalizes and
indexes the complete graph. `/usr/bin/time -l` measured the same command before and after removing a
duplicate whole-graph validation pass and replacing one enterprise-sized canonical byte allocation
with bounded canonical record hashing.

| Build | Wall time | Maximum RSS | Snapshot prefix |
|---|---:|---:|---|
| branch baseline | 8.09 s | 747,257,856 bytes | `75a6fd6f6956` |
| risk-remediated | 6.28 s | 535,363,584 bytes | `75a6fd6f6956` |

The identical fingerprint independently checks that the lower-allocation hash preserves canonical
snapshot identity for this corpus. The browser still receives a bounded slice, never the complete
enterprise graph.

## Residual and falsifier

This is a substantial cold-path reduction, not a persisted/incremental index. Roughly 535 MB RSS is
still too high to claim comfortable Salesforce-scale startup. G-002 remains open until a persisted
index proves lower cold-start time and memory across process restarts. A corpus whose old and new
canonical fingerprints differ, a malformed adapter graph accepted through the default constructor,
or a served response exceeding its existing byte/card caps would falsify this result.

## 2026-08-24 lazy-detail follow-up

Fresh measurement on `codex/view-annotations-risk-remediation`, based on upstream
`83c66ffe4019b91eeedecfbb9c43ae9f34abfb7a` with the lazy-detail candidate dirty, separated the
cost instead of attributing the whole process to “the index”:

| Stage | Wall time | Maximum RSS |
|---|---:|---:|
| Source `Graph` only | 2.247 s | 251,543,552 bytes |
| Eager complete projection | 20.485 s | 721,453,056 bytes |
| Eager projection + in-memory index | 28.264 s | 728,612,864 bytes |
| Identity-bound lazy-detail index + overview + 600-card group query | 12.270 s | 528,154,624 bytes |

The candidate removes about 200 MB of peak memory and 56% of the measured startup/query time by
retaining compact card/search records and materializing full shared dossiers only for the bounded
page returned to the client. It also binds dossier identity to the requested object and retains an
8 MiB / 5,000-entry LRU detail cache. The compact snapshot includes every lazy dossier's semantic
identity, so authored detail changes still invalidate old cursors. This is meaningful progress, not
completion: the normalized source
`Graph` remains a 251 MB floor and the compact projection is still rebuilt after every process
restart. A persisted, fingerprint-bound query store remains the next scale boundary.
