# Vizzer Wiki Index

> Auto-maintained knowledge base for `project_vizzer`. Last updated: 2026-08-23. Articles: 9.
>
> This is the routing table — each entry carries enough context to decide whether to open the full
> article without reading it first. Read this before researching anything; if a prior session already
> filed it, read that article instead of re-deriving it.
>
> Longer-lived product context lives alongside in [`docs/context/`](../docs/context/); this wiki holds
> concepts, investigations, and decisions.

## Recent

- 2026-08-23: [Goal backlog](goals/index.md) — Durable project goals and their related research,
  evidence, and design materials. Wiki goals are planning records; only one may be promoted into a
  Codex runtime goal at a time.
- 2026-08-23: [Developer-experience object graph](goals/developer-experience-object-graph.md) —
  Active ambitious goal for a functionality-grouped 2D code-object graph with capability→cluster→
  story-neighborhood drill-down, descendant status composition, and the shared Constellation
  dossier contract. React Flow remains an optional renderer over project-neutral graph data.
- 2026-08-23: [IllTool React Flow prototype findings](goals/materials/developer-experience-object-graph/illtool-prototype-findings-2026-08-23.md) — Browser and scale receipts from the 700-object IllTool prototype: semantic levels, nested frames, routed dependencies, provenance-backed failure, `vizzer-story-detail/v1`, a 10k/19k corpus, Roadmap capability/column/recency filters, and the remaining chunked-query requirement before enterprise-scale claims. Tags: vizzer, react-flow, elk, developer-experience, roadmap, scale, evidence
- 2026-08-23: [Upstream the generic review and evidence workflow](goals/upstream-review-evidence-workflow.md)
  — Active project goal to reconcile the evolved IllTool fork into upstream Vizzer without leaking
  host-specific paths, schemas, fixtures, or assumptions.
- 2026-08-21: [Vizzer divergence map: project_vizzer ↔ illtool fork](concepts/illtool-fork-divergence-map-2026-08-21.md) — Read-only reconnaissance ahead of porting the illtool fork's 139-commit week back upstream project-agnostically, with the review/capture harness as an optional install. Key findings: **B is a strict file-level superset** (21 identical, 27 diverged, 23 only-in-B, **zero only-in-A**) so this is a one-directional port, not a merge; **zero A→B backports needed** — all eight of A's newest fixes verified already present in the fork; A's shipped package is **already illtool-free** (`grep -rn "illtool" src/` returns nothing) and the status ladder is upstream's default, not a fork divergence, so the bias is narrower than expected. The bias that does exist is nine concerns with no config key, two of them blockers: the story-path shape re-derived by hand in three places, and a `launchctl kickstart gui/501/com.ryders.vizzer-serve` restart command hardcoded in three copies, encoding launchd + one uid + one person's domain. Riskiest port item is the content-hashed `renderId`: `package_root()` counts parent directories, so under `src/` layout or a pip install it either raises on every render or — worse — silently disables its own staleness gate. Includes an eight-workstream port plan partitioned so no two parallel agents write the same file, the observed `.sheet.json` schema, the harness↔host interface as a capability table, and an unresolved licensing question about 15 SF Symbol outlines embedded in an MIT package. Tags: vizzer, port, divergence, review-harness, project-agnostic, reconnaissance

## Goals

- [Goal backlog and storage contract](goals/index.md)
- [G-001 — Upstream the generic review and evidence workflow](goals/upstream-review-evidence-workflow.md)
- [G-002 — Developer-experience object graph](goals/developer-experience-object-graph.md)

## Concepts

- [Vizzer divergence map: project_vizzer ↔ illtool fork](concepts/illtool-fork-divergence-map-2026-08-21.md) — Structural map, feature-by-feature divergence, the illtool-bias audit, the review/capture harness inventory and its core↔extra seam, an eight-workstream port plan, and the open licensing question. Tags: vizzer, port, divergence, review-harness, project-agnostic
