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

## Now

Reconcile the original “all reusable functionality” migration promise with the still-pending
portable families in the divergence map. G-001 must remain active until each family is either
ported, explicitly excluded as non-reusable, or moved to a named follow-up with owner agreement.

## Next

1. Audit/resolve the remaining migration-matrix rows (render identity, blocked records, decision
   replay, workstream runtime exclusion, conflicts/completion, perspectives, remaining generic
   Constellation interaction families).
2. Run final package/leakage/dirty-worktree audit and update the capability matrix.
3. Commit and push the review branch once its declared scope and residuals match reality.

## Open questions

- Whether the broad portable-fork families belong in this one publication or explicitly named
  follow-up releases remains a scope decision; silently calling the current subset “all” is not an
  option.
- Remote multi-user owner identity is not implemented. V1 authority is local loopback possession;
  remote collaboration needs an authentication adapter and a separate threat model.

## Working set

- Upstream: `/Users/ryders/Developer/GitHub/project_vizzer-developer-flow`
- Prototype: `/Users/ryders/Developer/GitHub/illtool-standalone-vizzer-reactflow`
- Claude lane: `/Users/ryders/Developer/GitHub/project_vizzer` (read-only to Codex)
