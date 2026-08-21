# Vizzer Wiki Index

> Auto-maintained knowledge base for `project_vizzer`. Last updated: 2026-08-21. Articles: 1.
>
> This is the routing table — each entry carries enough context to decide whether to open the full
> article without reading it first. Read this before researching anything; if a prior session already
> filed it, read that article instead of re-deriving it.
>
> Longer-lived product context lives alongside in [`docs/context/`](../docs/context/); this wiki holds
> concepts, investigations, and decisions.

## Recent

- 2026-08-21: [Vizzer divergence map: project_vizzer ↔ illtool fork](concepts/illtool-fork-divergence-map-2026-08-21.md) — Read-only reconnaissance ahead of porting the illtool fork's 139-commit week back upstream project-agnostically, with the review/capture harness as an optional install. Key findings: **B is a strict file-level superset** (21 identical, 27 diverged, 23 only-in-B, **zero only-in-A**) so this is a one-directional port, not a merge; **zero A→B backports needed** — all eight of A's newest fixes verified already present in the fork; A's shipped package is **already illtool-free** (`grep -rn "illtool" src/` returns nothing) and the status ladder is upstream's default, not a fork divergence, so the bias is narrower than expected. The bias that does exist is nine concerns with no config key, two of them blockers: the story-path shape re-derived by hand in three places, and a `launchctl kickstart gui/501/com.ryders.vizzer-serve` restart command hardcoded in three copies, encoding launchd + one uid + one person's domain. Riskiest port item is the content-hashed `renderId`: `package_root()` counts parent directories, so under `src/` layout or a pip install it either raises on every render or — worse — silently disables its own staleness gate. Includes an eight-workstream port plan partitioned so no two parallel agents write the same file, the observed `.sheet.json` schema, the harness↔host interface as a capability table, and an unresolved licensing question about 15 SF Symbol outlines embedded in an MIT package. Tags: vizzer, port, divergence, review-harness, project-agnostic, reconnaissance

## Concepts

- [Vizzer divergence map: project_vizzer ↔ illtool fork](concepts/illtool-fork-divergence-map-2026-08-21.md) — Structural map, feature-by-feature divergence, the illtool-bias audit, the review/capture harness inventory and its core↔extra seam, an eight-workstream port plan, and the open licensing question. Tags: vizzer, port, divergence, review-harness, project-agnostic
