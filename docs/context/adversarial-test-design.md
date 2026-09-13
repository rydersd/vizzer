# Adversarial test design

Vizzer treats consequential tests as reviewable work, not invisible terminal
activity. Every test must have one precise, falsifiable goal and finite limits.

## Risk classes

- **Risk A — routine:** isolated, deterministic, cheap, non-destructive checks
  against an established seam. Independent review is optional, but time,
  attempts, abort conditions, cleanup, and non-claims remain explicit.
- **Risk B — reviewed:** integration, UI, performance, mutation, profiling,
  shared-runner, or new acceptance/causal claims. A separate testing agent must
  return PASS for the exact design packet before execution.
- **Risk C — high impact:** broad or expensive end-to-end runs, scarce shared
  infrastructure, or substantial CPU/GPU/disk/interference radius. It uses the
  same independent gate and receives stronger visual emphasis in Vizzer.

Restricted actions still require their own authority. A Risk C label does not
authorize destructive changes, external writes, private data access, permission
changes, or work outside the owning scope.

## Testing-agent contract

Name the author, independent reviewer, and executor. The reviewer must be
different from author and executor. The reviewer starts with every Story
acceptance criterion and Definition of Done clause, maps each to its production
route and observable oracle, and attacks the proposed evidence for blind spots.
Relevant competitor behavior may suggest questions when backed by attributable
evidence; it never silently becomes product authority. Ask the owner when
intended user-visible semantics remain ambiguous.

## Bounded packet and execution record

Record the stable proposal ID, Story, Test Risk, one goal, non-claims, exact
selectors, fixtures, source/build/environment boundary, clocks and thresholds,
negative controls, falsifiers, finite resources, attempts, wall time, abort
conditions, cleanup, defect linkage, current phase, elapsed time, outcome,
snags, evidence, challenges, and opportunities to improve.

States are `preparing`, `under-review`, `ready`, `running`, `finished`,
`snagged`, or `invalidated`. Outcomes are separately recorded as `pending`,
`pass`, `expected-red`, `unexpected-fail`, `partial`, `inconclusive`,
`infrastructure-failure`, `cancelled`, or `invalidated`.

The author writes a `TEST REVIEW PACKET`. The independent reviewer replies with
a separate `TEST REVIEW VERDICT` naming Proposal ID, Story, the exact packet
fingerprint, reviewer session, and PASS, REPAIR, or RESTRICTED. Self-attested
PASS text inside the proposal grants nothing. Changing a fingerprinted design
field invalidates the prior verdict. Risk B/C execution waits for independent
PASS, but routine tests do not become owner-gated.

Vizzer shows packet risk, state, outcome, evidence, challenges, opportunities,
reviewer identity, and snags on the owning Story. An In-review Story without a
packet can queue a durable bounded-test request. Passing design review proves
only that the named test is credible enough to execute; it does not authorize
product edits, lifecycle promotion, or broader conclusions.
