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

## 2026-08-24 persisted-store follow-up

The next candidate builds an atomic standard-library SQLite projection during large-graph
`render`/`refresh`, opens it immutable and read-only while serving, and falls back to the validated
in-memory oracle when its canonical graph hash, projection configuration, or renderer identity does
not match. Full dossiers
are compressed inert JSON; typed columns and precomputed unfiltered group rollups support bounded
queries without rehydrating the complete projection. Returned object, detail, group, boundary, and
relation identities are checked against their rows, and corrupt caches fail rather than becoming
source truth.

Same-machine 100,000-object measurements after the streaming-builder and compression changes:

| Stage | Wall time | Maximum RSS | Derived bytes |
|---|---:|---:|---:|
| Canonical graph load + atomic store build | 31.175 s idle; 70.329 s contended | 464,584,704–626,507,776 | 159,141,888 |
| Warm graph load + store open + overview + 600-card group query | 2.614–3.277 s | 293,355,520–355,713,024 | unchanged |

The normalized graph artifact was 37,260,684 bytes. Compared with the prior lazy in-memory
12.270-second / 528,154,624-byte path, warm serving is 73–79% faster and uses 33–44% less peak
memory in these runs. This is not a 43 MB server claim: a store-only probe is smaller, but the real Vizzer server
still loads the normalized `Graph` for source opening and its other APIs. Cache construction is also
not free—it moves cost to refresh and uses roughly 4.3× the graph's disk size. A warm served query
that rebuilds the compact projector, a cursor that survives an authored-detail cache rebuild, a
tampered row that is returned without identity validation, or a failed replacement that destroys
the previous store would falsify the result.

### Adversarial release review

The skeptical pass found four release-relevant holes and closed them before publication:

- Cache identity originally omitted projection configuration. It now binds canonical graph bytes,
  the complete normalized configuration, and renderer identity; mutation coverage proves changed
  configuration rejects the cache.
- Filtered group queries originally omitted an immediate child frame when it had no matching
  objects. Persisted queries now preserve the oracle's frame structure, including empty children.
- The first store reader reused a private in-memory request parser. Both backends now use one public
  normalization function, preventing query grammar drift.
- A cache build failure originally failed `render`/`refresh`, contradicting the claim that the cache
  is disposable. It now emits a warning and preserves the authoritative render; serving falls back
  to the validated in-memory implementation.

The builder also rejects programmatically-created group cycles rather than looping, cleanup and
atomic replacement are mutation-tested, and returned object/detail, group/detail, boundary, and
relation identities are revalidated. The remaining trust boundary is local derived SQL metadata:
the ignored cache is mode `0600`, opened immutable/read-only, and never treated as an adversarially
authenticated database. A local actor able to rewrite that file can influence selection metadata;
that is not represented as a security guarantee. The cache remains disposable and rebuilding it
from the authoritative graph is the recovery path.
