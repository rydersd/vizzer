# Constellation polish

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, constellation

## Origin

IllTool d81015726, 36e9c19d5, 91e5ff44a, db1123214 (#1394), ce5c77560.

## Acceptance

- Capability outlines draw; names fade in beside the form.
- Release `Rn` filter means accepted future work after the last configured release.
- Text boxes grow with their text (shared module, used by constellation and review sheets).
- Agent-ops notices and dossier updates; latest append-only test progress shown once.

## Test plan (RC)

Autogrow, fade timing and notices are visual; covered by the RC browser pass.

## Named tests

- (planned) `tests/test_release_filter.py::test_rn_filter_membership_against_configured_releases`
- (planned) `tests/test_constellation_canvas.py::test_one_outline_per_capability_no_duplicate`

## Open contract questions

- How is `Rn` defined relative to the configured release labels (e.g. before the first or after the last)?
- What are the measurable fade timing and notice behaviours that replace "visual" review?
