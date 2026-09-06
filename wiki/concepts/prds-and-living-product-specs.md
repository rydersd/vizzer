# PRDs and living product-spec work structure

> Status: design context, not a mandatory project template.
> Updated: 2026-08-10.
> Provenance: adapted from the IllTool wiki's
> [PRDs and living product-spec work structure](https://github.com/rydersd/illtool-standalone/blob/main/wiki/spec-ops/prd-and-living-product-spec-work-structure.md).
> The source page defines IllTool-specific authority boundaries; this version describes a portable
> artifact model for repositories using Vizzer.

## Short answer

PRDs are not obsolete. The large frozen PRD handed from product to design to engineering is the
archaic part. Teams still need durable answers to: whose problem is this, why now, what outcome
matters, what is in or out, what constraints are real, who decided, and what proves success.

Modern practice distributes those answers across a small set of linked artifacts instead of asking
one document to be strategy memo, product contract, technical design, project plan, and
archaeological site. That separation matters more when several LLMs or humans may implement the same
work: durable intent, constraints, decisions, and acceptance must live outside one transient chat.

The danger is not having a PRD. It is stale prose outranking current evidence, or one giant document
becoming a second implementation that nobody can compile.

## Names are less important than jobs

| Decision/job | Common artifact | What it must answer |
|---|---|---|
| Is this problem worth pursuing? | PRD, PRFAQ, opportunity canvas/tree, Shape Up pitch | User/problem, evidence, outcome, appetite, no-gos, strategic fit |
| What behavior are we promising? | Product spec, feature spec, story contract | User-visible behavior, rules, states, nonfunctional constraints, exclusions, acceptance |
| How should a substantial technical change work? | RFC or design document | Architecture, alternatives, drawbacks, compatibility, rollout |
| Why did we choose this direction? | ADR | Context, decision, consequences, status/supersession |
| How will this increment ship? | Plan, tasks, test plan, rollout checklist | Sequencing, ownership, validation, migration, release, rollback |
| Did it work? | Telemetry/experiment report, support evidence, postmortem | Outcome, reliability, adoption, harms, follow-up decisions |

Calling all six things “the PRD” does not make the process lean. It makes the document obese.

## What current practice looks like

### Outcome narrative before implementation

AWS describes the
[Working Backwards PRFAQ](https://docs.aws.amazon.com/wellarchitected/latest/devops-guidance/oa.ti.6-prioritize-customer-needs-to-deliver-optimal-business-outcomes.html)
as a future customer-facing press release plus FAQs, adoption expectations, value, mock-ups, and use
cases. Its job is customer/outcome alignment before technical execution, not a line-by-line build
spec.

Basecamp's [Shape Up](https://basecamp.com/shapeup/1.1-chapter-02) similarly produces a pitch with the
problem, appetite, rough solution, rabbit holes, and limitations. Its useful portable lesson is
bounded appetite and explicit no-gos, not that every team should cosplay six-week cycles.

### A maintained source of truth

GitLab's
[Product Development Flow](https://handbook.gitlab.com/handbook/product-development/how-we-work/product-development-flow/)
uses issue and epic descriptions as a maintained source of truth through problem validation,
solution validation, planning, delivery, verification, and launch readiness. This is not a frozen
handoff PRD; it is a living evidence trail.

### Formality proportional to risk

Rust's official [RFC process](https://rust-lang.github.io/rfcs/) reserves full design and consensus
review for substantial changes. Minor fixes use normal pull requests. RFCs cover motivation, impact,
drawbacks, and alternatives; substantial later changes generally use a new RFC rather than silently
rewriting accepted history.

### Agent-oriented specification

GitHub's current [Spec Kit](https://github.github.com/spec-kit/) formalizes `Spec → Plan → Tasks →
Implement` and supports multiple agents, including Codex, Claude, Gemini, and generic integrations.
Its [spec-of-specs guidance](https://github.github.com/spec-kit/concepts/spec-of-specs.html) recommends
decomposing large features into independently testable slices with stable IDs, scope boundaries,
dependencies, and separate specs.

That is evidence of current tooling practice, not proof that a particular template improves product
outcomes. The defensible lesson is narrower: agents need durable intent and constraints outside an
ad-hoc prompt, and large scopes need explicit decomposition.

## Portable artifact authority

Projects may use different names and directories. Vizzer should model the jobs, relationships, and
declared precedence instead of imposing one taxonomy.

| Artifact class | Authority |
|---|---|
| Research and concepts | Exploratory evidence, alternatives, and historical context. Non-normative until adopted. |
| PRD / opportunity / pitch | Why an outcome is worth pursuing, for whom, how success is observed, appetite, and strategic boundaries. |
| Product spec / story | Normative behavior contract and independently buildable acceptance boundary. |
| RFC / design doc | Cross-cutting technical proposal when architecture or compatibility deserves review before code. |
| ADR | Durable technical decision and consequences; reversal supersedes rather than erases it. |
| Execution plan and tasks | Sequencing, work packages, temporary deferral, ownership, rollout, and validation commands. |
| Named tests and receipts | Executable acceptance and current evidence. A method name without a runnable route is not evidence. |
| Vizzer graph and views | Derived selection, impact, activity, question, and portfolio views; never a competing source of truth. |
| Devlogs, reviews, postmortems | Historical implementation record and learning, not the current product contract. |

Repositories should configure precedence when sources disagree. Vizzer may expose the disagreement;
it must not silently choose whichever artifact makes a story easiest to call complete.

## Recommended lifecycle

### 1. Discover

Use research, customer evidence, dogfood observations, PRFAQ/pitch material, prototypes, and open
questions. State confidence. Minimum output before shaping:

- user/problem and affected context;
- evidence and confidence;
- desired outcome and how it will be observed;
- why now or cost of delay;
- constraints, harms, and non-goals;
- alternatives worth preserving.

### 2. Shape and decide

Set an appetite, identify rabbit holes, expose owner questions, and split the outcome into coherent,
independently testable stories. A decision record should include:

- chosen option and rationale;
- rejected alternatives and trade-offs;
- falsifier or condition that reopens the decision;
- owner and date;
- downstream contracts affected.

### 3. Specify

A story becomes a build contract only when it covers:

- user-visible behavior and states;
- model, persistence, rendering, and interaction rules where relevant;
- dependencies and frozen contracts;
- accessibility, performance, privacy/security, migration, and failure behavior where relevant;
- explicit non-goals;
- named acceptance and readiness criteria.

Freeze behavioral and compatibility seams. Do not freeze implementation trivia merely because an
early author guessed a filename.

### 4. Design technically when warranted

Use an RFC/design document for architecture with broad compatibility or system effects. Use an ADR
for a decision that must survive the meeting. Small local changes do not need a costume change into
RFCs.

### 5. Plan and build

Plans own sequencing, work packages, temporary deferral, ownership, validation commands, and rollout.
They may adapt without silently narrowing the product contract. Independent packages can go to
multiple agents; shared integration seams retain one owner.

### 6. Verify and learn

Named acceptance must run through the real production route. Record outcome, stability, review, and
rework evidence. Product learning may amend future direction; it does not retroactively make an old
estimate clairvoyant.

## The Story is a longitudinal work record

A Story is not only the current instruction set and not merely a ticket to close. It is the durable
record of how the task was created, questioned, changed, implemented, and verified. Preserve two
views at once:

- **effective-current truth:** the behavior and named acceptance an implementer must satisfy now;
- **evolution history:** source ideas, assumptions, alternatives, decisions, deviations, material
  checkpoints, application evidence, and lifecycle/revision transitions.

Use typed append-only events for material changes. A decision event records the question, options,
recommendation, rationale, falsifier, owner answer, and any deviation. A later application event
records how that answer changed the contract, tests, dependencies, or follow-up work. High-frequency
progress remains in the activity feed; only milestones that change understanding or explain a later
revision belong in the Story itself.

This separation matters. Rewriting the current prose destroys rationale; copying every agent update
into the Story buries rationale. Both are bad records wearing opposite hats.

The structured history should support process retrospection: when owner questions surfaced, which
assumptions failed, how assessed and observed size differed, where acceptance changed after build
started, what rework recurred, and which rejected alternatives later became viable. Use that to
improve shaping, templates, and assessment calibration—not to rank individual humans or models.

## Living does not mean ahistorical

A useful living-spec system preserves both effective-current truth and decision history:

- discovery documents may evolve before commitment;
- accepted stories retain their historical baseline;
- material product changes use an owner-approved amendment or successor;
- defects against shipped behavior use explicit lineage;
- enhancements use revision or supersession lineage;
- technical discoveries go to plans/ADRs unless they change the product promise;
- deferral belongs in planning, not by deleting inconvenient acceptance.

Append-only history still needs an effective-current projection. If a reader must reconcile six
contradictory amendments manually, the repository has preserved history and misplaced the contract.
Vizzer should show the active requirement, superseded text and decision, unresolved conflicts, and
current named acceptance.

Agents are excellent at confidently selecting the wrong fossil. Do not hand them a sedimentary cliff
and call it context engineering.

## How much document is enough

Scale artifact weight to decision risk:

| Change | Minimum useful structure |
|---|---|
| Tiny objective bug fix | Defect lineage, reproduction, expected behavior, regression test, blast assessment |
| Small user-visible feature | Problem/outcome, bounded story contract, states/non-goals, named acceptance |
| Cross-layer feature | PRD/pitch context, stories, technical plan; RFC if architecture is unsettled |
| Persistent/public/security-sensitive change | Full behavior contract, migration/rollback, privacy/security, compatibility, operations, acceptance |
| Novel/uncertain capability | Time-boxed research/spike with falsifier; implementation story after findings |
| Multi-release/system change | Shallow roadmap/spec-of-specs, independent stories, explicit dependencies |

The test is not page count. It is whether a competent human or different LLM can make the same
material decisions without silently inventing missing product policy.

## A useful PRD or pitch

A short product-outcome document usually needs:

1. Problem and affected user/journey.
2. Evidence and confidence.
3. Desired outcome and measures.
4. Why now or opportunity cost.
5. Appetite and strategic boundaries.
6. Candidate experience or solution outline.
7. Rabbit holes, risks, and trust concerns.
8. No-gos and non-goals.
9. Open owner questions.
10. Proposed story decomposition and dependencies.

It should link to the story, RFC, ADR, or plan that owns detail instead of duplicating them.

## A useful story/spec

For agentic delivery, a story should carry:

- intent and user-visible behavior;
- acceptance criteria and rules;
- dependency and frozen-contract references;
- likely areas as guidance, not unearned architecture law;
- non-goals;
- exact named acceptance and readiness criteria;
- source ideas and decision lineage;
- stable requirement/scenario IDs where amendments or tests need precise references;
- size and impact evidence described in
  [AI-era story sizing and portfolio selection](story-sizing-and-portfolio-selection.md).

## Failure modes

- **The handoff PRD:** written once, thrown over a wall, never reconciled with evidence.
- **The everything document:** strategy, UX, schema, code plan, task list, and launch checklist merged
  into one brittle novel.
- **The no-document rebellion:** chat or prompt history becomes the accidental authority.
- **Spec-as-implementation:** early file/class guesses are frozen while user behavior stays vague.
- **Acceptance cosplay:** test names exist, but no current production route or executable environment.
- **Living-spec amnesia:** history is overwritten, so later teams cannot explain constraints.
- **Append-only archaeology:** every ruling is preserved but no current contract is generated.
- **AI prompt as product policy:** one model's transient context decides behavior no other client can
  reproduce.

## Implications for Vizzer

Vizzer should stay model-neutral. It does not need an internal product-manager prompt. It needs
validated portable records that any agent or human can produce:

- open questions with options, recommendation, evidence, and falsifier;
- owner answers in a separate append-only decision ledger;
- normalized size/uncertainty and explicit impact evidence;
- dependency, relation, readiness, and conflict data;
- effective-current contract and named acceptance;
- derived portfolios and explanations, never hidden source edits.

Agent instructions can guide Claude, Codex, Gemini, or local models to research and propose those
records. Persisted schema and validation—not a proprietary prompt—are the interoperability contract.

## Source quality and limits

| Source | What it establishes | Limit |
|---|---|---|
| [AWS Working Backwards guidance](https://docs.aws.amazon.com/wellarchitected/latest/devops-guidance/oa.ti.6-prioritize-customer-needs-to-deliver-optimal-business-outcomes.html) | Narrative customer-outcome artifacts remain active practice | Amazon mechanism, not a universal template |
| [Basecamp Shape Up](https://basecamp.com/shapeup/1.1-chapter-02) | Appetite, shaping, risks, pitch, separate betting/building | One company's process; complementary discovery may be needed |
| [GitLab Product Development Flow](https://handbook.gitlab.com/handbook/product-development/how-we-work/product-development-flow/) | Maintained issue/epic source of truth through validation and delivery | Heavier than every small change needs |
| [Rust RFC process](https://rust-lang.github.io/rfcs/) | Formality proportional to change; motivation, alternatives, consensus | Technical/open-source governance, not product discovery |
| [GitHub Spec Kit](https://github.github.com/spec-kit/) | Current agent-neutral spec-to-implementation practice | Young tooling; not causal delivery evidence |
