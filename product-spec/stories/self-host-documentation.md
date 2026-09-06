# Make Vizzer's own product and documentation visible

> Status: shipped
> Deps: []
> Release: R1
> Tags: dogfood, documentation
> Appetite: small

## Intent

Replace the two-card bootstrap with a living product contract, discoverable
wiki/docs and useful dashboard recommendations.

## Acceptance criteria

- Product contracts link implementation/checks with baseline and coverage limits explicit.
- Current Stories are delivery; product references and all wiki/docs Markdown are references.
- Default dashboard shows work; fixtures and historical tasks do not become delivery.
- Refresh/check succeed, configured files and authored links resolve.
- Authored setup/specs/wiki/docs are in Git; generated/runtime files stay ignored.

## Verification

2026-09-05: refresh/check produced 46 items (4 delivery, 42 references), zero
conflicts/warnings. All wiki/docs Markdown appears in the graph, no fixture
items leak in, and all newly authored Markdown links resolve. Live Codex panel
inspection reproduced an empty dashboard and clipped References controls.
Configured recommendations now appear; wrapping intact filter groups and
positioning content below measured chrome makes reference selection/search
work at the observed 646-pixel panel width. Wiki search was verified in Features.

This task does not claim exhaustive downstream inventory or new full-suite
verification. Authored sources and the layout fix are published together.

Focused renderer validation: 75 passed using `.venv/bin/python -m pytest
 tests/test_render_constellation.py tests/test_render_dashboard.py -q`.
Three old CSS-shape assertions initially failed because they required a fixed
28px filter row, nowrap controls and only two measured-position consumers;
these assertions now reflect wrapping controls and the routed content offset.
The live panel check independently verified the previously inaccessible control.
