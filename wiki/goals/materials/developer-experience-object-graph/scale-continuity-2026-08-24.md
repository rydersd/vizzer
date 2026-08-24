# Developer Flow scale continuity — 2026-08-24

## Goal

Make Developer Flow useful for very large project constellations—Salesforce-scale implementations
included—without sacrificing semantic drill-down, bounded responses, shared object detail, or the
project-agnostic adapter contract.

## Constraints

- The normalized graph, not React Flow or a database layout, remains the product contract.
- Large served views may materialize only bounded pages; no 100,000-card DOM victory laps.
- A persisted index is derived and fingerprint-bound. It cannot become story/dependency authority.
- Core install and static rendering remain dependency-free; persistence must use the Python standard
  library unless a later explicit optional-adapter decision says otherwise.
- Do not use pickle or deserialize executable object graphs. Cache records remain validated JSON or
  typed SQLite columns, contained below the project, and replace atomically.
- Claude's IllTool ledger exclusions in G-001 remain a collision blacklist, not this goal's backlog.

## Key Decisions

- Keep eager complete projection for small embedded graphs because it is simple and preserves fully
  offline detail.
- For large served graphs, store compact card/search records and resolve the shared dossier only for
  returned primary objects. Boundary cards intentionally remain detail-free.
- A custom lazy-detail adapter must supply a matching semantic identity function. Vizzer validates
  the digest shape and later binds the hydrated dossier to the requested object, but adapter truth
  remains an explicit contract; the built-in Markdown adapter is covered by mutation tests.
- Bound retained hydrated detail with an 8 MiB / 5,000-entry LRU. Request byte limits remain the
  stronger per-response boundary.
- Persist large projections in ignored `.vizzer/cache/` using standard-library SQLite. Build through
  a shared streaming projector, replace atomically, bind metadata to canonical graph bytes,
  projection configuration, and renderer identity, open read-only, and fall back to the in-memory
  oracle on any mismatch.
- Store full dossier JSON as compressed inert data plus typed search/routing columns. Revalidate
  object/detail identity and row identity on every returned record; never deserialize executable
  Python objects.

## Done

- G-001 generic web/local review workflow is merged and independently audited.
- G-002 interaction, grouping, routing, detail, LOD, responsive chrome, saved views, annotations,
  undo/redo, visibility, and SVG behavior are merged to upstream `main` at `83c66ff`; lazy detail
  materialization followed at `091a2fc`.
- All thirteen owner-named IllTool paths were re-resolved on 2026-08-24. The primary checkout and
  three Wave-2b worktrees are live; five paths are gone; four are historical remnants/tombstones.
  No new generic Vizzer engine was found outside the already-audited upstream work.
- Lazy-detail projection is implemented with identity validation; the complete upstream suite passed
  with 519 tests and two environment-dependent skips, and both distribution artifacts built.
- Same-machine 100,000-object measurement improved from 728.6 MB / 28.3 s to 528.2 MB / 12.3 s
  while retaining cursor invalidation for lazy dossier changes.
- A standard-library SQLite store now covers aggregate overview, nested group filters, object
  neighborhoods, external boundaries, typed relations, byte-bounded pagination, omission counts,
  shared dossier detail, and snapshot-bound cursors. Oracle-parity, read-only, mutation, corrupt
  cache, atomic-failure, render integration, and HTTP no-reprojection tests are implemented.
- The streaming builder avoids retaining the compact 100,000-object projection. Its measured local
  cache is 159,141,888 bytes for a 37,260,684-byte normalized graph.

## Now

The persisted-store release candidate passed the complete Python suite, byte-clean frontend rebuild,
wheel/sdist build, HTTP no-reprojection proof, and 100,000-object replay. Publish the exact reviewed
commit. The in-memory implementation remains the correctness oracle.

## Next

1. Decide after the release benchmark whether loading the complete normalized `Graph` at server
   startup is still an unacceptable memory floor for multi-million-object installations.
2. If it is, introduce a separate bounded source-locator/owner-operation index for non-Developer
   Flow endpoints; do not contort the normalized graph contract or silently disable other APIs.

## Open Questions

- None requiring owner authority yet. SQLite versus another standard-library representation is a
  reversible implementation choice; SQLite is currently recommended because it supports indexed
  filtering and crash-safe replacement without adding a runtime dependency.

## Adversarial Review

- No release blocker remains in the lazy-detail slice: complete-contract validation still requires
  every dossier, compact indexes are separately fail-closed, hydrated dossier IDs are bound to the
  requested object, response/card byte caps remain intact, and semantic detail changes invalidate
  cursors.
- The persisted store removes compact-projection reconstruction from warm serving, but Vizzer still
  loads the normalized `Graph` because source opening, questions, planning, reviews, and other APIs
  use it. Claiming a 43 MB server from the SQLite-only probe would therefore be marketing nonsense;
  the full warm-server measurement is the release claim.
- Building the cache adds work and disk: the 100,000-object build used 28.9 seconds of CPU and took
  31.2 seconds on an idle run or 70.3 seconds during a deliberately contended rerun; measured peak
  RSS ranged from 465–627 MB including canonical graph loading, and it writes a 159 MB local file.
  That is an explicit refresh-time trade for faster, lower-memory restarts.
- Low residual risk: Vizzer cannot prove that a third-party adapter's detail identity function tells
  the truth. The interface makes that trust explicit; built-in Markdown mutation tests provide an
  independent check for the bundled adapter.
- A byte-budgeted query can hydrate one candidate beyond the returned page to determine that it does
  not fit. The response and retained cache remain bounded; this is deliberate bounded lookahead, not
  eager graph materialization.

## Working Set

- `src/vizzer/developer_graph.py`
- `src/vizzer/developer_query.py`
- `src/vizzer/developer_store.py`
- `src/vizzer/object_detail.py`
- `src/vizzer/render/developer_flow.py`
- `src/vizzer/serve_extensions.py`
- `src/vizzer/story_sidebar.py`
- `tests/test_developer_graph.py`
- `tests/test_developer_query.py`
- `tests/test_developer_store.py`
- `tests/test_developer_flow_scale.py`
- `wiki/goals/developer-experience-object-graph.md`
