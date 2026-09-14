# Preserve crossing trails while orbiting and clarify chronological fade

> Status: building
> Deps: []
> Release: R1
> Tags: constellation, progress-pathing, regression

## Intent

The owner supplied two screenshots showing trail segments disappearing while
orbiting. The renderer incorrectly required both endpoints to remain inside
clickable canvas bounds. Offscreen geometry is not an authored filter.

## Acceptance criteria

- Retain a crossing trail when one or both endpoints move outside canvas bounds.
- Let the canvas clip painted geometry beneath chrome and outside the viewport.
- Respect explicit node filters without connecting across a filtered checkpoint.
- Make chronological fade perceptible, with a continuous 12–88% opacity gradient
  and matching arrowheads; retain search dimming.

## Evidence — 2026-09-06

A deterministic Node harness executes the production trail pass with endpoints
inside, one outside, both outside, and a filtered middle checkpoint. It checks
segment counts and old/new gradient stops. This verifies drawing decisions,
not a completed visual orbit walkthrough in the screenshot's source project.
That project has been requested from the owner before updating its installation.

Focused validation: 59 passed, 1 physical-browser selector deselected.
