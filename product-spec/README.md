# Vizzer product specification

This is Vizzer's current product contract and work register. Authored Markdown
is authoritative; the local dashboard is a derived view.

- [Current behavior](current-behavior.md): feature contracts and implementation/verification pointers.
- [Change register](changes.md): integrations and unresolved coverage.
- [Work items](stories/): concrete changes, acceptance criteria and lifecycle.
- [Wiki](../wiki/index.md): operating guides, concepts and historical context.
- [Documentation](../docs/README.md): evidence archive and historical plans.
- [Dashboard setup](../vizzer/README.md): refresh, serve and troubleshoot.

## Coverage and authority

Baseline: upstream merge `1d9e4e4c9fe5e7c12827fd8d6d62cc7f8dbe2efd`, inspected
2026-09-05. The behavior inventory records existing implementation, not a new
claim that every acceptance scenario was executed. Test pointers name checks;
dated review receipts describe what actually ran.

This is not yet an exhaustive inventory of every downstream fork.
[Cross-project intake](stories/cross-project-change-intake.md) remains open.
The dashboard's completion fraction counts authored delivery Stories, not the
percentage of the whole product implemented. Existing capabilities appear as
references rather than invented completed tasks.

## Change policy

Every behavior change updates its current contract here and adds or updates a
Story with provenance, acceptance criteria, dependencies and evidence. Record
its PR and integration commit after merge. New regressions get separate Stories
linked to shipped behavior. Historical receipts stay dated and do not override
the current contract.

Use stable Story filenames and headers (`Status`, `Deps`, `Release`, `Tags`).
Run `python3 vizzer/engine refresh` and `python3 vizzer/engine check` after source
changes. Commit authored sources and durable evidence; generated views, graph
caches and server state are regenerated locally.
