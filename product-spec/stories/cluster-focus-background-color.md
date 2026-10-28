# Paint faded clusters while another cluster is focused

> Status: building
> Deps: []
> Release: R1
> Tags: constellation, cluster-focus, regression

## Intent

Focusing a capability (clicking its rail row) fades every other capability
toward the canvas background. Since 2026-09-19 (#12) that fade mixed toward
`RGB.bg`, which `recolor()` never set, so the first frame containing a faded
node threw a TypeError. The page then showed the error overlay instead of the
focused cluster. Found while recording the README demo against a six-capability
project.

## Acceptance criteria

- A frame painted with one capability focused and another visible below
  `FOCUS_BACKGROUND_TIER` completes without throwing.
- Faded nodes mix toward the theme's `--bg` token, so light and dark themes
  both fade to their own background.

## Test plan

- Automated: `tests/test_constellation_focus_spread.py::test_focused_frame_paints_faded_background_clusters`
  (fails with the TypeError without the fix).
- RC pass: focus a cluster in a real browser in both themes and check that
  background clusters read as faded, not missing.
