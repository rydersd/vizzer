# Orbiting trails: visibility versus interaction bounds

Draft article material captured 2026-09-06. This example documents an upstream
repair awaiting downstream reconciliation; it is not an imported fork innovation.

## Origin and attribution

Ryder reported trails disappearing while orbiting and requested a more perceptible
fade. The repair is in Vizzer's uncommitted upstream working copy. Proposal:
`da3a75ca6f9d3b5b0bb5ab796972f502900c512a86891eafe60471c5e0949727`.
Original authorship and rationale of the forks' depth-fog addition: **Not yet captured**.

## Intent

Keep crossing trail segments visible while the camera orbits, and make temporal
ordering easier to perceive through the fade. Preserve explicitly filtered gaps.

## Rationale

The repair separates authored visibility from endpoint hit-test eligibility.
An endpoint outside clickable bounds can still define a segment crossing the
viewport. Let canvas clipping handle offscreen geometry instead of rejecting
the entire segment. A continuous 12–88% opacity gradient expresses chronology;
its perceptual benefit still needs owner visual confirmation.

## Alternatives and tradeoffs

Keeping the endpoint `.on` gate drops crossing segments. Ignoring all visibility
filters would connect across intentionally hidden checkpoints. Wholesale copying
of upstream canvas.js into a fork could discard that fork's depth-fog behavior.

## Vizzer adaptation

The three registered downstream engines need targeted reconciliation. Each has
additional `edgeFog(a,b)` logic near the old endpoint and alpha code. Preserve
that behavior while evaluating how it interacts with the stronger gradient.
No downstream installation was changed by the radar.

## Evidence and outcomes

The production draw harness covers inside, one-outside, both-outside and filtered
checkpoint cases. It verifies drawing decisions and gradient stops. It does not
establish perceptual improvement or successful integration in the three forks.
The radar's patch checks report needs-reconciliation in all three installations.

## Lessons

Rendering visibility and interaction eligibility serve different purposes.
Reusing one flag for both can erase visible geometry. Patch conflicts can expose
valuable local behavior that a bulk upstream replacement would lose.

## Article angle

“How an invisible endpoint erased a visible line.” Explain the orbiting failure
with a segment crossing the viewport while both endpoints lie outside, then show
how separating filtering, hit testing and clipping fixes the decision. Include
before/after visual evidence once captured; do not invent it.

## Sources

- Ryder's trail report in this task, 2026-09-06 (source statement of intent).
- `product-spec/stories/trail-orbit-visibility.md` (repair contract and test scope).
- `tests/test_trail_visibility.py` (production draw harness).
- `docs/reviews/2026-09-06-change-radar.md` (review receipt and fork observations).
- `src/vizzer/render/constellation/canvas.js` (uncommitted implementation).
- Downstream depth-fog author statement: **Not yet captured**; obtain its original
  PR or design note before attributing a rationale in an article.
