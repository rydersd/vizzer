# G-002 — Developer-experience object graph

> Status: implemented and merged to upstream `main`; performance follow-up retained
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

> “can i save views, also add annotations, sketche on flow, save notes?”

> “export doesn't respect wrapping. and the iconograpy”

> “should use the same icons that vizzer is using from sf symbols until we revise them with illtool.”

> “the tokens need to be shared. update the react flow to use the tokens in vizzer.”

> “it should show the input and the external dependencies as outside cards yes? answer is yes.”

> “the interface elements need to be responsive. e.g. the breadcrumb needs to collapse. we should
> have epic an capability stories as well because any object i click on should have a sidebar with
> details about it.”

> “this degredation (lod) isn't very helpful. might as well go to vizzer type dots at this point.
> Showing details on hover. We should also have story specific icons, just take some best guesses
> from sf symbol.”

> “ui elements should never overlap”

> “undo is necessary for the annotations and drawings.”

> “i don't think there should be a mode for navigating the view. I think the modes are adding
> annotations and sketches.”

> “the notes and sketches should be hideable. and in export they should be an option.”

## Objective

Add an optional developer-experience view that presents project objects and typed relationships in
a navigable 2D space. Functionality groups provide the primary visual regions; compact cards expose
the core identity and status; selecting a card opens a detailed right-side dossier. The result is
more explicit and inspectable than the 3D constellation while sharing its selection, provenance,
filtering, and detail concepts.

## Product shape

- 2D pan/zoom graph with readable cards rather than point symbols.
- A single reserved inspector lane hosts object dossiers or saved-view notes; transient previews and
  relationship labels use collision-aware placement instead of covering other Vizzer controls.
- Navigation is the canvas baseline: drag pans, two-finger scroll pans, and pinch zooms React Flow
  without a separate Pan tool or browser-viewport zoom. Note and Sketch are the authoring modes.
- Canvas notes and sketches share a bounded undo/redo history with toolbar controls and standard
  Command/Control-Z shortcuts; typing fields retain their native text undo.
- Notes and sketches can be hidden without deleting them, and saved views retain that visibility.
  SVG export exposes an independent include/exclude-markup option and records the choice in export
  metadata.
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
- A named view can persist its semantic scope and filters, view-level notes, object/canvas note
  cards, and freehand vector strokes; a served saved-view link restores the same review context.
- Annotations use flow coordinates, remain attached while panning or zooming, appear in the shared
  dossier when linked to an object, and are included in SVG export.
- SVG export uses the same card-presentation contract as the interactive graph: kind iconography,
  level of detail, status and failure treatment, and explicit wrapping for group titles, object
  titles, summaries, annotations, and expanded details. Export must remain readable without HTML
  overflow or scroll behavior.
- Developer Flow live cards and SVG exports consume Vizzer's existing verified SF Symbol outline
  catalog for lifecycle and group marks. Object kind remains a separate text label; temporary
  Unicode or hand-drawn substitutes must not become a competing icon system. IllTool may revise the
  shared catalog later without changing the graph schema.
- Developer Flow consumes Constellation's canonical theme-token stylesheet at render time. Its own
  stylesheet may define component-level semantic aliases and layout values, but may not fork the
  Vizzer background, surface, text, line, lifecycle, accent, or mono-type palette.
- When a capability or functional cluster is focused, direct incoming dependencies and outgoing
  external dependents render as bounded root-level object cards outside the focused frame. They
  retain the actual object identity and relationship direction, disclose omitted boundary counts,
  and do not masquerade as an aggregate external group.
- Compound dependency routes are normalized from ELK's endpoint lowest-common-ancestor coordinate
  space into root flow coordinates before React Flow renders paths or labels. Connections within a
  nested frame and connections crossing frame boundaries must terminate on both rendered object or
  group handles; an edge object being returned on the root graph is not proof its section points are
  root-relative.
- The title bar and breadcrumb respond to available width without clipping or forcing the graph
  sideways. Intermediate crumbs collapse behind an accessible path menu while the current location
  remains visible. Capability and epic/cluster frames are selectable entities and open the same
  right-side dossier contract as leaf stories.
- Low-detail rendering uses compact Vizzer-style dots rather than distorted card silhouettes. Dots
  preserve status, selection, connectivity, keyboard focus, and a hover/focus summary. Story cards
  use deterministic best-fit SF Symbols from the shared verified outline catalog based on portable
  kind/title vocabulary; lifecycle remains a separate status channel.

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
- Saved views are bounded, versioned documents with compare-and-swap persistence. They decorate a
  graph snapshot and never become a write-back path into authoritative stories or dependencies.
- Projection/materialization and compound-layout normalization are modules independent of the React
  shell. The entry component may orchestrate interaction state, but portable graph semantics,
  boundary selection, ELK construction, SVG export, view documents, icon contracts, and layout
  geometry may not collapse into one view file.

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
7. Served named views live in one project-relative JSON store and use loopback same-origin/CSRF
   mutation guards plus revision conflicts. Static files keep a local-only fallback; sharing notes
   or sketches requires the served store rather than stuffing prose into a query string.

## Candidate completion evidence

- Two unrelated language/framework fixtures generate the same normalized schema and render through
  the optional view.
- Cards, typed edges, grouping, keyboard navigation, selection, and dossier routing are exercised in
  a real browser.
- A cold offline install proves the optional bundle has no CDN dependency.
- A no-extra install proves core Vizzer has no React/Node runtime dependency.
- Vocabulary and path guards reject leaked fixture/project identity.
- Layout and interaction remain usable at a documented scale threshold.
- A real compound-layout fixture and a served browser pass verify nested and cross-frame route
  endpoints against absolute card or frame boundaries, with top-level edges retained as a negative
  control.

## Materials

- [React Flow optional-bundle evaluation](materials/developer-experience-object-graph/react-flow-evaluation-2026-08-23.md)
- [IllTool prototype findings and browser receipts](materials/developer-experience-object-graph/illtool-prototype-findings-2026-08-23.md)
- [Upstream project-neutral verification](materials/developer-experience-object-graph/upstream-verification-2026-08-23.md)
- [Saved views, annotations, and scale-risk follow-up](materials/developer-experience-object-graph/view-annotations-and-scale-risk-2026-08-23.md)
- [Adversarial review of saved views and residual risks](materials/developer-experience-object-graph/adversarial-saved-view-review-2026-08-23.md)
- [SVG export presentation parity review](materials/developer-experience-object-graph/svg-export-parity-review-2026-08-24.md)
- [Compound routing and icon delivery review](materials/developer-experience-object-graph/compound-routing-icon-delivery-review-2026-08-24.md)
- [Responsive dossier and low-detail review](materials/developer-experience-object-graph/responsive-dossier-and-lod-review-2026-08-24.md)
- [Readable story-neighborhood screenshot](materials/developer-experience-object-graph/upstream-neutral-story-neighborhood.jpg)
- [Full-width IllTool capability overview](materials/developer-experience-object-graph/illtool-capability-overview-full-width-2026-08-23.jpg)
- [Full-width Drawing story and shared detail](materials/developer-experience-object-graph/illtool-drawing-story-detail-full-width-2026-08-23.jpg)
- [Unclipped capability frame at review scale](materials/developer-experience-object-graph/illtool-capability-frame-unclipped-2026-08-23.jpg)
- [Rounded, equally spaced dependency routes](materials/developer-experience-object-graph/illtool-rounded-equidistant-routes-2026-08-23.jpg)
- [Exported routed SVG](materials/developer-experience-object-graph/upstream-neutral-commerce-component.svg)
