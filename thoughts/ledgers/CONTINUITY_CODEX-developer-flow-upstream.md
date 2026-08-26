# Continuity — upstream developer flow

## Goal

Extract the reusable IllTool developer-object graph into upstream Vizzer without
project vocabulary, while preserving the larger generic agent-to-owner review goal.

## Constraints

- Project-neutral schema, adapters, fixtures, paths, and UI copy only.
- React Flow is optional, precompiled, offline, and disabled by default.
- Do not duplicate or overwrite Claude's uncommitted G-001 review service/UI work.
- Owner explicitly authorized pushing the Vizzer project; commit/push only after the combined audit
  is green and the branch documents incomplete broader migration work honestly.
- A DOM cap is not an enterprise payload strategy; 100k-scale needs bounded queries.

## Key decisions

- The normalized developer graph is the contract; React/ELK are one renderer.
- Semantic focus is capability/group → child group → object neighborhood.
- Detail is an injected normalized payload shared with Constellation, not reparsed by
  the React renderer.
- Codex owns new G-002 modules/assets/tests plus minimal registry/config seams.
- Claude currently owns dirty review service, adapters, story sidebar, Constellation
  dossier/reviews/preferences, and review documentation/tests in the primary checkout.

## Done

- IllTool prototype proved 700 real objects, nested grouping, orthogonal routing,
  one-hop story neighborhoods, shared detail schema, and Roadmap facets.
- Adversarial pass fixed six concrete UI/algorithm defects.
- Created isolated branch/worktree `codex/developer-flow-upstream` from `d51e194`.
- Added the neutral developer graph, shared detail contract, two non-origin fixtures,
  optional offline React Flow/ELK bundle, semantic LOD/focus/filtering, Roadmap
  column/capability/dependency/modified filters, packaging, and leakage guards.
- Added a snapshot-bound bounded query index for overview, group, and one-hop object
  slices, exact omission/byte reporting, boundary objects, snapshot-bound cursors, and loopback HTTP
  transport.
- Composed the generic review service/UI, adapter declarations, owner lineage, source/evidence
  descriptor walks, project-neutral web/local fixtures, and full-width review evidence.
- Added named saves, bookmark/share URLs, SVG export, stable-origin warnings, responsive title-bar
  actions, Roadmap capability/column/order filters, and a readable shared story dossier.
- Browser receipts prove story drill-down, owner validation, 918×516 inline review evidence from a
  1280×720 source, saved/shared views, and a well-formed routed SVG.
- A 25,000-object scale fixture returns a bounded 600-of-2,500 slice within its budget. Complete
  Python 3.9 suite: 453 passed, 2 skipped.
- Ported the remaining reusable Python-core families: content-based render identity, explicit
  blocker records, durable/static workstream separation, conflict sources, completion provenance,
  legacy-safe decision replay, question aging, and opt-in project-neutral perspectives.
- Added live-measured Constellation top chrome and stable object deep links. Stored two new
  full-width 1280×720 IllTool Developer Flow receipts: capability overview and Drawing story detail.
- Adversarially exercised 100,000 objects. The bounded response stayed correct (600 rows,
  617,362 bytes), but cold normalization/indexing took 21.765 seconds and about 1.0 GB RSS.
- Final combined Python audit is 488 passed, 2 skipped in 99.08s. Frontend build/audit, wheel,
  sdist, zipapp, compile, archive-integrity, diff, and project-identity leakage gates are green.
- Replaced fixed Developer Flow frame/card geometry with content-derived dimensions after the owner
  exposed a clipped `Component Authoring & Instances` title. Added rounded orthogonal bends and
  explicit 18-unit parallel lanes/24-unit node clearance; 126 focused tests and full-size browser
  receipts cover the revised geometry.
- Final post-geometry Python audit: 488 passed, 2 skipped in 83.04 seconds.
- Fixed route-label occlusion in both the live canvas and SVG export, including wide-label export
  bounds. Final settled audit: 489 passed, 2 skipped; pushed `95ff95b`.
- Revalidated every owner-named IllTool path against its current on-disk state. No newer generic
  engine seam was found; the only new relevant commits belong to the excluded review-capture lane.
- 2026-08-25: Fixed a renderer-only stale-route defect without changing source relationships.
  Custom edges now accept cached ELK points only while their first and last points remain near the
  current React Flow handles; scope, frame, or orientation churn falls back to the current-handle
  route. Focused regression, full 540-test audit, and 1075x754 browser churn in both orientations
  cover the seam, including frame collapse/expand culling.

## Now

G-001 is complete on the pushed upstream review branch. Keep G-002's measured 100k cold-start/RSS
limit visible rather than turning a correctness ceiling into an enterprise-performance claim.

## Next

1. Repository owner decides when/how to merge `codex/developer-flow-upstream` into `main`.
2. If G-002 resumes, design persisted/incremental indexes and adapter-side aggregation against an
   explicit startup/RSS budget before making an enterprise-performance claim.

## Open questions

- What startup/RSS budget should gate a future “enterprise ready” claim at 100,000 objects. The
  current measured result is correct but expensive; the answer likely determines whether the next
  architecture is a persisted index, adapter aggregation, or both.
- Remote multi-user owner identity is not implemented. V1 authority is local loopback possession;
  remote collaboration needs an authentication adapter and a separate threat model.

## Working set

- Upstream: `/Users/ryders/Developer/GitHub/project_vizzer-developer-flow`
- Prototype: `/Users/ryders/Developer/GitHub/illtool-standalone-vizzer-reactflow`
- Claude lane: `/Users/ryders/Developer/GitHub/project_vizzer` (read-only to Codex)
