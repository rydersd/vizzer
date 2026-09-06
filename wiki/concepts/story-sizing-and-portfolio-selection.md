# AI-era story sizing and portfolio selection

> Status: design context, not a claim that every capability below is implemented.
> Updated: 2026-08-10.
> Provenance: adapted from the IllTool wiki's
> [AI-era story sizing and portfolio selection](https://github.com/rydersd/illtool-standalone/blob/main/wiki/spec-ops/ai-era-story-sizing-and-portfolio-selection.md).
> The source page contains IllTool-specific audit results and policy; this version keeps the
> portable Vizzer concepts. Projects remain authoritative for their own process.

## Decision in one page

Vizzer should not turn a project's appetite field into Fibonacci numerology, nor divide an impact
guess by an effort guess and present the result as truth. The portable model is layered:

1. Gate readiness before ranking work.
2. Describe delivery size as a coarse range, with uncertainty and reasons visible.
3. Describe impact independently: user harm or value, reach, urgency, risk reduction, and dependency
   leverage are different claims.
4. Describe agent fit and parallel safety independently from delivery complexity.
5. Forecast from comparable local cycle-time history when enough completed work exists.
6. Select feasible portfolios, not one magic queue: several high-impact small outcomes, optionally a
   larger anchor, and explicit integration capacity.

The practical modern alternative to mandatory story points is coarse rightsizing plus probabilistic
flow forecasting plus explicit impact evidence. Story points may still help a stable team expose
disagreement, but velocity is not productivity and points are not portable across teams, agents,
repositories, or validation regimes.

## Evidence and limits

The [Open Guide to Kanban](https://kanbanguides.org/open-guide-to-kanban/2025.7/pdf/open-guide-to-kanban.en-us.pdf)
defines a Service Level Expectation as elapsed time plus probability and recommends cycle time,
work-item age, work in progress, and throughput as core flow measures. It also warns that value
divided by effort is usually one educated guess divided by another.

The [Scrum Guide](https://scrumguides.org/scrum-guide.html) requires Product Backlog items to be sized
enough for selection. It does not require Fibonacci points, velocity, or t-shirt sizes. The
[SPACE framework](https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity-theres-more-to-it-than-you-think/)
likewise rejects developer productivity as a single metric.

Current AI evidence does not support a universal multiplier:

- METR's randomized early-2025 study found experienced maintainers working in their own repositories
  took [19% longer with AI tools](https://arxiv.org/abs/2507.09089), despite expecting and perceiving a
  speedup.
- METR's [February 2026 update](https://metr.org/blog/2026-02-24-uplift-update/) found its newer signal
  difficult to interpret because of participant/task selection and concurrent-agent time measurement.
- A 2025 *Management Science* paper reports a pooled
  [26.08% increase in completed tasks](https://pubsonline.informs.org/doi/10.1287/mnsc.2025.00535)
  across three field experiments involving 4,867 developers, with noisy individual experiments.
- DORA reports that AI can improve individual experience while larger batches can hurt system
  delivery; its [2026 report](https://dora.dev/ai/gen-ai-report/report/) associates increased adoption
  with lower throughput and stability in that data set.

These results can all be true in different task and repository regimes. “LLMs make work 40% smaller”
would therefore be a particularly polished lie. Agent benefit depends on task type, repository
familiarity, harness quality, model/tool regime, review burden, and actual parallelizability.

## The portable delivery profile

Preserve a project's authored `Appetite` or equivalent. Derive an assessed delivery profile rather
than overwriting authored intent or adding a competing mystery score.

```json
{
  "storyId": "story:example",
  "scopeFingerprint": "sha256(normalized-story+deps+verified-surfaces)",
  "estimate": {
    "band": "M",
    "plausibleRange": ["S", "L"],
    "uncertainty": "U1",
    "dimensions": {
      "implementation": "S",
      "verification": "M",
      "integration": "L",
      "coordination": "M"
    },
    "evidence": [],
    "unknowns": [],
    "methodVersion": "delivery-sizing-v1"
  },
  "impact": {},
  "parallelism": {},
  "actual": null
}
```

An assessor may propose this record. Vizzer should validate its shape and references, retain
provenance, and invalidate it when the scope fingerprint changes. Derived assessment must never
silently edit a source story.

### Size bands

Size describes change topology and validation burden, not lines of code or optimistic agent-hours.

| Band | Working definition |
|---|---|
| **XS** | Acceptance/ratchet or localized change with a reliable harness; no new model, persistence, owner, or external gate. |
| **S** | One coherent module or seam; named acceptance exists; limited regression surface; no migration or unresolved decision. |
| **M** | Multiple modules or one real system boundary; several acceptance surfaces; meaningful integration or coordination. |
| **L** | Persistence, history, platform, security/privacy, migration, perceptual approval, or broad cross-layer integration. |
| **XL** | Multiple unresolved boundaries or independently shippable outcomes. Split it or run discovery/shaping first. |

Record four dimensions before choosing the band:

- **implementation:** production mechanisms and system boundaries;
- **verification:** test classes, UI/device/external evidence, mutation and adversarial burden;
- **integration:** persistence, compatibility, generated projects, caches, rollout, and merge seams;
- **coordination:** owner decisions, shared files, exclusive test hosts, review, and outside services.

Until all four dimensions are established, an authored appetite may remain visible as a planning
proxy but is not an assessed delivery size and must not qualify an item for a dispatch portfolio.
Missing evidence is uncertainty, not a coupon for cheaper work.

The overall band is not an arithmetic average. One load-bearing `L` boundary can make the story `L`;
failures do not average themselves into politeness.

### Uncertainty

| Level | Meaning |
|---|---|
| **U0 — measured** | Calibrated from several completed, materially comparable stories under the same tool/model/harness regime. |
| **U1 — inferred** | Derived from verified repository facts and a settled contract. |
| **U2 — unresolved** | Depends on an owner ruling, missing harness, external gate, or unsettled architecture. Widen the range. |
| **U3 — discovery** | Not responsibly deliverable as a build story yet. Size the research/shaping time box instead. |

Every dimension carries provenance: `observed`, `authored`, `inferred`, or `unknown`. An LLM may
propose an inference with evidence and a falsifier; it may not promote its own guess to observation.

## Impact is a vector

Vizzer should preserve at least these independently inspectable claims.

### User and product impact

- **severity:** data loss/corruption, crash/hang, workflow blocker, trust/accessibility, fidelity,
  friction, or polish;
- **reach/frequency:** affected users, journeys, operations, and frequency;
- **outcome:** the observable user or product outcome expected to change;
- **urgency/cost of delay:** deadline, compounding loss, release block, or decaying opportunity;
- **confidence:** measured, observed, owner judgment, or guess.

### System and portfolio impact

- **immediate unlocks:** items that become ready if this item alone lands;
- **frontier reach:** downstream targets that remain blocked elsewhere;
- **structural reach:** all known descendants, displayed as context rather than immediate value;
- **risk reduction/opportunity enablement:** harness, foundation, compliance, or architecture leverage;
- **defect blast radius:** affected contract and surfaces, data/security exposure, recurrence, and
  confidence.

Do not give full unlock credit to every descendant in a dependency diamond. Full credit belongs to
the last incomplete blocker; otherwise foundations get paid repeatedly for hypothetical futures.
Similarly, defect lineage may establish known structural reach but cannot invent severity or
frequency.

RICE—reach × impact × confidence ÷ effort—and WSJF/cost-of-delay can be useful optional lenses. They
must remain views over the raw components, never the canonical truth. A ratio of guesses does not
become empirical because the UI gives it two decimal places.

## Agent fit and parallel safety

Agent fit is a scheduling constraint and modifier, not permission to rewrite the base story smaller.
Record:

- `maxSafeAgents`, based on independently testable packages rather than available workers;
- file, symbol, subsystem, build-host, owner-review, service, and fixture conflict keys;
- whether a distinct integration owner is required;
- whether acceptance can run independently;
- context burden and availability of a reliable local harness;
- the model/toolchain profile behind any historical comparison.

Many agents do not make a serial edit many times faster. They make a merge-conflict documentary.

## Portfolio selection

An iteration should offer two or three nondominated portfolios—such as **journey speed**, **risk
retirement**, and **balanced**—instead of declaring one opaque ordering ordained.

A reasonable uncalibrated balanced default is:

1. Two to four XS/S outcomes, prioritized by user impact and immediate unlocks.
2. Zero or one M/L anchor by default.
3. A second M/L anchor only when its conflict graph is disconnected, it has independent validation
   capacity and integration ownership, and neither anchor depends on the other's likely delta.
4. One question/research lane when resolving it unlocks valuable work.
5. Explicit slack/integration capacity, labeled as a starting policy rather than measured truth.

Do not require a large item every iteration. A U2 large item is not made healthier by putting it on a
balanced-looking slide. Do not maximize item count either: splitting one outcome into ten tickets must
not multiply its impact.

Filter before selection:

- unresolved hard dependencies or owner decisions;
- missing acceptance oracle;
- stale assessment fingerprint;
- unavailable external environment;
- collision with active ownership or exclusive resources;
- `XL/U3` work not yet decomposed.

Ownership expiry and blocker resolution are different facts. A stale `active` or `paused` record may
release a dispatch reservation, but a stale `blocked` record remains nondispatchable until a newer
record or accepted owner decision explicitly clears the blocker.

## Forecasting and calibration

When enough comparable project history exists, forecast cycle time by size band, work type,
subsystem, and agent/tool profile. Report p50/p85/p95 or a Service Level Expectation, not one
deterministic date.

Record per immutable assessment revision:

- elapsed, active, blocked, human-wait, review, and exclusive-resource time;
- work type, subsystem, model/toolchain profile, and safe-agent count;
- production boundaries and acceptance surfaces touched;
- build/test attempts, mutation cycles, rework, and post-delivery defects;
- scope changes and the final scope fingerprint;
- outcomes or targets closed, not only items completed.

Backtest range coverage and underestimation. Abandoned work is not zero effort. A new model or harness
regime is not automatically comparable to old history.

## Model-neutral boundary

Vizzer does not need an internal product-manager model. Its durable contract should stay portable:

- Vizzer owns parsing, validation, derivation, persistence, and rendering.
- Claude, Codex, Gemini, local models, and humans may propose the same records.
- Prompts and workflows belong in portable agent instructions, not inside the priority engine.
- Inferred size and impact claims include evidence, confidence, and a falsifier.
- Accepted owner overrides remain distinct from agent-authored proposals.

See [PRDs and living product-spec work structure](prds-and-living-product-specs.md) for the document
authority that feeds those assessments.

## Implementation sequence

1. **Normalize honestly.** Preserve raw appetite, map only explicit aliases, flag ambiguity, and expose
   a useful high-impact XS/S shortlist without changing existing uptake ordering.
2. **Add assessed profiles.** Store versioned, fingerprinted overlays with evidence; show size range,
   uncertainty, impact dimensions, and conflict keys in the dossier.
3. **Generate portfolios.** Build conflict graphs from ownership and declared resource collisions,
   produce multiple feasible portfolios, and explain exclusions.
4. **Forecast empirically.** Collect comparable actuals and add probabilistic forecasts only after
   sample-size and backtest gates pass.

## Adversarial acceptance

The design is not credible unless these cases fail safely:

1. Change only `Appetite: large` to `small`; corroborating scope evidence is still required.
2. Invent test names; confidence does not improve unless selectors exist and execute.
3. Add dependency diamonds or cycles; unique outcome reach does not inflate.
4. Add defect lineage; structural reach may change, severity remains unknown.
5. Split one outcome into ten items; portfolio value does not multiply.
6. Merge unrelated work into one item; uncertainty widens or decomposition is required.
7. Give two anchors the same conflict key; their concurrent portfolio is infeasible.
8. Increase available agents on serial work; parallel capacity does not change.
9. Remove the acceptance harness; readiness drops even if implementation looks easy.
10. Change the scope fingerprint; assessments and overrides become stale.
11. Mark the whole corpus `small`; anomaly detection complains instead of launching confetti.
