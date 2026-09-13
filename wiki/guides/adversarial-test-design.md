# Adversarial test design

Vizzer treats consequential tests as reviewable work, not invisible terminal
activity. Every test has a precise, bounded goal. Complex, end-to-end,
performance, mutation, profiling, shared-runner, or otherwise high-impact runs
must be represented by a durable test-review packet before execution.

The executable Codex skill is `~/.codex/skills/adversarial-test-design/`. This
page is the portable project contract for any testing agent, including agents
that do not have that local skill installed.

## Risk classes

- **Risk A — routine:** isolated, deterministic, cheap, non-destructive checks
  against an established seam. Independent review is optional, but the goal,
  time limit, attempt limit, abort conditions, and cleanup remain explicit.
- **Risk B — reviewed:** integration, UI, performance, mutation, profiling,
  shared-runner, or new acceptance/causal claims. A separate testing agent must
  return PASS for the exact packet before execution.
- **Risk C — high impact:** broad or expensive end-to-end runs, scarce shared
  infrastructure, or substantial CPU/GPU/disk/interference radius. These use
  the same independent gate and receive stronger visual emphasis in Vizzer.

Restricted actions—destructive changes, external writes, private data,
permissions, or work outside the owning scope—require their own explicit
authority. Calling them Risk C does not magically authorize them. Nice try.

## Testing-agent contract

Author, reviewer, and executor are named roles. The independent reviewer must
be distinct from both author and executor; author and executor may be the same
lane unless execution is delegated. The author proposes; the testing agent
attacks the design read-only; the executor follows the reviewed recipe exactly.
The reviewer starts from every Story acceptance
criterion and Definition of Done clause, then maps each to a production route,
observable oracle, selector, and residual non-claim.

The review also attacks the contract itself for missing states, inputs,
recovery, accessibility, persistence, scale, concurrency, and platform
boundaries. Relevant competitor behavior may expose blind spots when backed by
current attributable evidence. It is evidence for a question, not automatic
product authority. Ambiguous user-visible semantics become explicit owner
questions with a recommendation, alternatives, and consequences.

## Bounded packet

Every packet declares:

- stable proposal ID, Story, author, executor, and Test Risk;
- one falsifiable goal and explicit non-claims;
- exact selectors, fixtures, source/build/process/environment boundaries;
- decisive observations, clocks, counters, samples, aggregation, thresholds;
- negative controls, mutations, hostile cases, and falsifiers;
- finite wall time, attempts, workload, resources, abort conditions, cleanup;
- defect linkage and expected RED/repaired GREEN when fixing a bug;
- current phase, elapsed time, outcome, snags, evidence, and opportunities.

State and outcome are separate. States are `preparing`, `under-review`,
`ready`, `running`, `finished`, `snagged`, or `invalidated`. Outcomes are
`pending`, `pass`, `expected-red`, `unexpected-fail`, `partial`,
`inconclusive`, `infrastructure-failure`, `cancelled`, or `invalidated`.

## Append-only review protocol

The author records a `TEST REVIEW PACKET` discussion. The independent reviewer
replies with a separate `TEST REVIEW VERDICT` discussion containing the exact
Proposal ID, Story, Packet fingerprint, Reviewer session, and a verdict of
PASS, REPAIR, or RESTRICTED. A PASS typed into the proposal is self-attestation
and grants nothing.

Vizzer recomputes SHA-256 over compact key-sorted JSON of these immutable
fields: Proposal ID, Story, Test Risk, Goal, Selectors, Bounds, Evidence,
Defect, Challenge, Opportunity, Source boundary, Falsifiers, Environment, and
Executor. Changing any field invalidates the prior verdict. Runtime State,
Outcome, Phase, and Elapsed remain visible but are excluded so honest progress
updates do not revoke a sound design review.

## Vizzer presentation

Test packets appear on their Story and in search. Preparing, under-review,
running, snagged, and finished states are visibly distinct; Risk C is louder;
finished tests stop pulsing and keep their outcome badge. Reduced-motion mode
uses static labels. The dossier shows the full formatted packet, challenges,
opportunities, reviewer identity/session, source boundary, falsifiers,
execution state, elapsed time, and evidence.

An In-review Story without a packet offers **Create bounded test**. That action
writes a durable provider request before attempting the clipboard. Provider
reassignment preserves superseded requests as audit history, and retention
never evicts a live request.

PASS only establishes that the described test is credible and bounded. It
does not authorize product edits, lifecycle promotion, external effects, or a
broader conclusion than the packet names.
