# Compound routing and icon delivery review — 2026-08-24

## Findings

The dangling dependency arrows were a real coordinate-space defect. ELK returned the edge objects
on the root graph, but section points between two objects in the same nested frame were relative to
that frame; cross-frame section points were relative to the endpoints' lowest common ancestor. The
renderer treated every section as root-relative. React Flow independently composed parent-relative
node positions, so cards were correct while routes and labels drifted away together.

The blue diamonds in the IllTool screenshot were independent evidence of stale delivery. The
current Developer Flow source and bundle rendered Vizzer's SF Symbol vector paths, while IllTool's
previously generated 6.4 MB HTML snapshot contained neither the catalog names nor their outlines.

## Remediation

- `absoluteEdgeRoutes` indexes compound parents and absolute origins, resolves each edge's endpoint
  lowest common ancestor, and shifts its section points into root flow coordinates once.
- The renderer consumes those normalized routes for both the rounded path and the opaque label.
- The built page embeds the same Vizzer SF Symbol outline catalog used by live cards and SVG export.
- The renderer injects Constellation's canonical theme tokens before Developer Flow's component
  stylesheet. Developer Flow now aliases `--bg2`, `--mut`, `--buggap`, the lifecycle colors, accent,
  and `--font-mono` instead of carrying a second blue-gray palette.
- Group projection moved out of the React entry file. A focused group now materializes each direct
  input dependency and external dependent as a root-level dashed card, while the query contract
  omits unrelated external group frames and keeps the 250-card boundary cap explicit.
- IllTool's generated Developer Flow page was refreshed from the candidate bundle. Its newer
  vendored Vizzer engine was deliberately not replaced wholesale: the candidate upstream base is
  older and an unqualified vendor update would delete newer review, symbol, and resize modules.

## Independent checks

- A real pinned-ELK compound graph verified two inner-frame edges and one cross-frame edge against
  absolute source and target bounds; a top-level edge verified that root routes are not double
  shifted.
- The focused IllTool `AI Perspective Grounding (Depth + Normals)` view rendered ten dependency
  paths, all ten terminating on both mounted endpoints.
- The same view rendered nine card icon paths and zero fallback dots. The generated HTML contains
  the document, failure, and group SF Symbol outlines and no old diamond substitute.

## Residual integration risk

IllTool's already-running Vizzer server predates the saved-view endpoint in this upstream candidate.
It can serve the regenerated graph and corrected assets, but the new saved-view client reports an
API parse error until the upstream work is reconciled additively with the newer vendored engine and
that server is restarted. Downgrading the vendor to make one screen green would trade a visible
integration error for silent feature deletion, which is not an acceptable fix.
