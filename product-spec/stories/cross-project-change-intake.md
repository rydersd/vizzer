# Cross-project change intake

> Status: ready
> Deps: []
> Tags: upstream, dogfood

## Intent

Track reusable Vizzer changes developed in other projects before bringing them
into this upstream repository. This is the intake lane, not a claim that any
particular fork change is missing or has already been ported.

## Workflow

Create one sibling Story per concrete change with a stable filename and these
fields in its body:

- Origin project and repository-relative engine paths.
- Exact source commit or patch fingerprint; distinguish uncommitted source.
- Intended generic behavior and project-specific assumptions to remove.
- Upstream comparison: absent, partially present, already present, or unconfirmed.
- Dependencies, acceptance criteria, and bounded verification evidence.
- Integration commit/PR when available; a local change is not a published release.

Use the Story header for current lifecycle (`backlog`, `ready`, `building`,
`shipped`, or `parked`) and `> Deps: []` or comma-separated Story slugs for
dependencies. Keep completed imports visible as shipped Stories. Record new
regressions separately rather than reopening shipped work without explanation.

## Acceptance criteria

- Every proposed import has a concrete source and comparison against upstream.
- Imported behavior is project-neutral and has evidence linked from its Story.
- Source Story changes are followed by `python3 vizzer/engine refresh`.
- No import is marked shipped solely because another project's copy works.

## Initial state — 2026-09-05

No individual cross-project changes have been inventoried by this setup task.
Existing goals and the historical divergence map remain reference material;
they are not evidence of current fork parity.
