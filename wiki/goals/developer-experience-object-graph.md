# G-002 — Developer-experience object graph

> Status: implementation complete on review branch; publication pending
> Ambition: ambitious
> Created: 2026-08-23
> Updated: 2026-08-23

## Owner thought

> “seems like there could be a react flow developer view which comprised of cards showing objects
> and relationships. With grouping based on functionlality. The cards show the core details and
> then are clickable and show the sidebar on the right. but a more detailed view of the
> constellation laid out in a 2d space.”

> “and it's ok to bundle react flow, can be an optional add on.”

> “we need to support levels of detail. we should show capabilities at hte highest level, and then
> drill in to show the drawing capability and dependencies when you go lower, when you drill into a
> specific story, it shows the related stories which make the story functional.”

> “as well as the status of the sub components.”

> “each object has the detail view that it shares with the constellation view.”

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
- Semantic drill-down has authored meaning: capabilities → immediate functional clusters/epics →
  stories → the focused story's prerequisites, consumers, and typed related-story neighborhood.
- Aggregate frames report blocked/failed, active, ready, and shipped descendant counts; one rolled-up
  color may not hide a failed subcomponent.
- Object selection consumes the same normalized detail payload as Constellation, including review
  steps, acceptance criteria, definition of done, provenance, failure, and relationships.

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

## Resolved v1 choices

1. Object classes are adapter-declared; the core accepts safe arbitrary kinds instead of pretending
   that one language's type system is universal.
2. Relations carry kind, direction, confidence, and provenance. V1 renders adapter-supplied truth;
   future inference belongs in an adapter and must disclose its confidence.
3. Groups carry authored/derived provenance and support nested capability/cluster frames.
4. Pinned ELK Layered supplies compound, orthogonal, deterministic routing; React Flow renders it.
   Parallel routes reserve equal 18-unit lanes and the renderer rounds orthogonal corners without
   changing ELK's obstacle-avoiding topology.
5. The add-on is disabled by default. Core retains Constellation and Markdown; the normalized graph
   and current routed scope can be exported as real SVG.
6. Overview queries aggregate groups. Group and object-neighborhood queries return bounded slices,
   cross-scope boundary objects, exact omission counts, snapshot-bound cursors, and a 4 MiB response
   ceiling. The UI does not pretend that rendering 40,000 rich cards is a feature.

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
- [IllTool prototype findings and browser receipts](materials/developer-experience-object-graph/illtool-prototype-findings-2026-08-23.md)
- [Upstream project-neutral verification](materials/developer-experience-object-graph/upstream-verification-2026-08-23.md)
- [Readable story-neighborhood screenshot](materials/developer-experience-object-graph/upstream-neutral-story-neighborhood.png)
- [Full-width IllTool capability overview](materials/developer-experience-object-graph/illtool-capability-overview-full-width-2026-08-23.png)
- [Full-width Drawing story and shared detail](materials/developer-experience-object-graph/illtool-drawing-story-detail-full-width-2026-08-23.png)
- [Unclipped capability frame at review scale](materials/developer-experience-object-graph/illtool-capability-frame-unclipped-2026-08-23.png)
- [Rounded, equally spaced dependency routes](materials/developer-experience-object-graph/illtool-rounded-equidistant-routes-2026-08-23.png)
- [Exported routed SVG](materials/developer-experience-object-graph/upstream-neutral-commerce-component.svg)
