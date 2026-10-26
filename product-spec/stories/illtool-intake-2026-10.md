# IllTool engine intake, October 2026

> Status: specced
> Deps: [illtool-constellation-upstream](illtool-constellation-upstream.md)
> Release: R1
> Tags: upstream, intake

## Origin and ruling

Source: rydersd/illtool-standalone `origin/main` 93fdab962 (2026-10-17),
`vizzer/engine/vizzer/` mapped to `src/vizzer/`. The prior intake stopped at
b6a67bb; 43 engine commits follow it (three already upstream as #13, #14, #15).

Owner ruling 2026-10-17: every IllTool engine capability is relevant to other
projects, including those the 2026-08-23 migration matrix excluded (CI overlay,
notices, restart channel, autocommit, review launcher/preverify, glyphs, review
sheets/archive). They come in **through the matrix's port gates**: generalized,
opt-in, adapter-driven, no host literals. Where upstream already has a neutral
contract that superseded the IllTool mechanism (review contract/service/adapters),
IllTool's behaviors extend that contract; no second review system is imported.

Owner confirmed the slice list below on 2026-10-17.

## Slices

Each slice is its own story, one user-visible behavior, merged separately.

| Story | Capability |
|---|---|
| intake-question-navigation | Test plans as checklists; Previous / N of M / Next across open questions |
| intake-lifecycle-truth | Shipped stays shipped; shipped promotion satisfied; unpersisted status-flip stamp |
| intake-generated-state-out-of-git | Generated views, workstream history and review packets regenerate locally |
| intake-bug-pulse | Bug pulse view; app bugs vs tooling bugs chips |
| intake-constellation-polish | Capability outlines, release Rn, autogrowing text boxes, agent-ops notices |
| intake-constellation-chrome | Appearance, area planning, chip layout, panel resize, view tables, notices, licensed glyph set |
| intake-testing-hub | Opt-in hub strip with a provider-neutral capacity probe |
| intake-ci-overlay | Provider-neutral CI overlay; GitHub as one adapter |
| intake-served-write-durability | Opt-in local commit of accepted served writes, hooks honored |
| intake-review-gate | Review holds, consolidated review sheet, archive, on the neutral contract |
| intake-review-launch | Launch the project's app for review via declared adapter operations, incl. preverify |
| hermes-integration | Hermes Agent discovers, refreshes and answers through Vizzer (see story) |

## Gates (all slices)

From the 2026-08-23 matrix: no `illtool`, `.illtool`, personal identity,
Application Support, LaunchServices, launchd, Xcode or fork-path literals in
shipped source or generic fixtures; disabled features render and serve nothing;
agent results and owner validation stay distinct events; side effects run only
as trusted adapter operations from configuration.

## Test plan (RC pass)

- Install the built `vizzer.pyz` into the neutral fixture project
  (`tests/fixtures/mixed_proj`); confirm each opt-in feature is invisible when
  off and works when on. A run against an IllTool copy is non-gating migration
  evidence only.
- Diff IllTool's served behavior against upstream on the same graph for every
  ported view.
