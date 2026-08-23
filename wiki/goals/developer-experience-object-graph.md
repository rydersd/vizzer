# G-002 — Developer-experience object graph

> Status: queued
> Ambition: ambitious
> Created: 2026-08-23
> Updated: 2026-08-23

## Owner thought

> “seems like there could be a react flow developer view which comprised of cards showing objects
> and relationships. With grouping based on functionlality. The cards show the core details and
> then are clickable and show the sidebar on the right. but a more detailed view of the
> constellation laid out in a 2d space.”

> “and it's ok to bundle react flow, can be an optional add on.”

## Objective

Add an optional developer-experience view that presents project objects and typed relationships in
a navigable 2D space. Functionality groups provide the primary visual regions; compact cards expose
the core identity and status; selecting a card opens a detailed right-side dossier. The result is
more explicit and inspectable than the 3D constellation while sharing its selection, provenance,
filtering, and detail concepts.

## Product shape

- 2D pan/zoom graph with readable cards rather than point symbols.
- Typed, directional relationships with filters and a visible legend.
- Nested or spatial groups based on functionality, with source provenance for the grouping.
- Cards show a small stable summary; the dossier owns depth and avoids card bloat.
- Direct navigation from an object to its source, tests, owning work, review evidence, and related
  objects when those capabilities exist.
- Layout is deterministic enough to compare, preserve orientation, and produce review evidence.

## Architecture constraints

- The normalized developer graph—not React Flow—is the product contract. Renderers consume stable
  object, edge, group, provenance, and detail schemas.
- React Flow may ship as an optional precompiled add-on. Core Vizzer must still install, render, and
  serve without Node, React, a CDN, or the add-on.
- Bundled third-party code is pinned, reproducible, offline-capable, and accompanied by license and
  attribution notices.
- Project adapters decide what an “object” means. The core must not hardcode Python, Swift, React,
  Xcode, IllTool, or one source-tree convention.
- Read-only understanding comes first. Any future graph editing or refactoring controls require a
  separate authority and safety contract.

## Questions to resolve when promoted

1. Which object classes form the portable floor: files/modules, types, functions, endpoints,
   components, data entities, tests, runtime services, or an adapter-declared subset?
2. Which relationships are source-observed versus inferred, and how is confidence displayed?
3. Is functional grouping authored, directory-derived, graph-clustered, or composed from all three?
4. Which layout engine provides deterministic grouped placement at useful scale?
5. What is the minimum non-React fallback: generated SVG/HTML, existing canvas, or no developer view?
6. How do very large codebases aggregate without producing a beautiful hairball with 40,000 nodes?

## Candidate completion evidence

- Two unrelated language/framework fixtures generate the same normalized schema and render through
  the optional view.
- Cards, typed edges, grouping, keyboard navigation, selection, and dossier routing are exercised in
  a real browser.
- A cold offline install proves the optional bundle has no CDN dependency.
- A no-extra install proves core Vizzer has no React/Node runtime dependency.
- Vocabulary and path guards reject leaked fixture/project identity.
- Layout and interaction remain usable at a documented scale threshold.

## Materials

- [React Flow optional-bundle evaluation](materials/developer-experience-object-graph/react-flow-evaluation-2026-08-23.md)
