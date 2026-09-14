# Cross-project change radar

> Status: building
> Deps: []
> Release: R1
> Tags: radar, provenance, self-hosting

## Contract

Register local engine copies against immutable comparison commits; discover
file-level differences without changing downstream files. Deduplicate by exact
path and before/after content, retain review and lifecycle history, and export
patches. Matching hunks establish patch presence, not semantic equivalence.
Integrated requires presence in the local upstream commit and working copy.
Adopted additionally requires presence in every registered installation.

The optional radar page and dashboard shortcut expose observations, source
commits, fingerprints, evidence, timestamps and watcher health. The local login
service polls every 30 seconds and refreshes views after input changes.

## First case

The orbiting-trail repair is present in the upstream working copy. Illmater,
IllTool and IllTool's live runtime require reconciliation; their extra depth
fog must survive a later targeted integration. No downstream patch is applied.

## Delivery

Implementation is local and uncommitted. See the [operating guide](../../wiki/guides/change-radar.md)
and [review receipt](../../docs/reviews/2026-09-06-change-radar.md).

## Intent and article material

Ideas brought upstream require an authored wiki brief capturing original intent,
rationale and sources, plus alternatives, adaptation, evidence and lessons.
The CLI captures bounded Markdown against the exact proposal; the radar displays
and exports that snapshot, retaining revisions. Missing context remains explicit.
This is article source material, not automatic publication or inferred authorship.

Brief validation (2026-09-06): 15 radar tests passed, including capture through
the CLI, HTML escaping, retained revisions after source edits, rejection of
missing context/path escapes, and no inherited brief for changed patch bytes.
