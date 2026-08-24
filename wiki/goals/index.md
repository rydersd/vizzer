# Vizzer goal backlog

> Updated: 2026-08-23

This directory is Vizzer's durable goal backlog. It holds more ideas than the Codex runtime can
execute at once, without pretending that a wiki checkbox is a running agent.

## Execution model

- A goal brief is project planning truth: objective, boundaries, success conditions, unresolved
  questions, and links to its materials.
- Codex runtime goal state is separate and intentionally single-active. Promoting a wiki goal into
  `/goal` is an explicit act; pausing, clearing, or completing the runtime goal does not silently
  rewrite this wiki.
- Goal status changes are authored here with evidence. A generated view may summarize them later,
  but must not become the write-back authority.
- Expanding an idea means appending or refining its brief and adding linked material. Do not stuff a
  second objective into an active goal merely because the runtime has only one slot. That is a queue
  wearing a trench coat.

## Backlog

| ID | Status | Ambition | Goal | Next promotion gate |
|---|---|---:|---|---|
| `G-001` | complete | large | [Upstream the generic review and evidence workflow](upstream-review-evidence-workflow.md) | Completion audit passed on the pushed upstream review branch; merge remains a repository-owner integration decision. |
| `G-002` | in progress | ambitious | [Developer-experience object graph](developer-experience-object-graph.md) | Extract the proven IllTool schema, semantic focus, shared-detail, ELK, and optional-bundle seams upstream without fixture vocabulary or monolithic enterprise payloads. |

## Storage convention

Each goal owns:

```text
wiki/goals/<goal-slug>.md
wiki/goals/materials/<goal-slug>/...
```

The brief stays readable and decision-oriented. Related material may include research, source
inventories, diagrams, schema sketches, benchmark output, small scrubbed screenshots, and test
receipts. Prefer links to an existing authoritative artifact over copies.

Do not store secrets, access tokens, private user data, machine-specific credentials, or giant raw
recordings here. Binary evidence needs provenance, capture time, source goal, media type, digest,
and a privacy review; large artifacts belong in a configured artifact store or Git LFS rather than
quietly turning the wiki into a landfill.

## Lifecycle vocabulary

- `draft` — thought is being captured; success is not yet testable.
- `queued` — coherent enough to promote, but not the active execution objective.
- `in progress` — implementation or evidence work is active somewhere.
- `paused` — deliberately stopped with a named resumption condition.
- `complete` — every stated success condition has current evidence.
- `superseded` — replaced by a linked goal; history remains readable.

Only completion evidence can move a goal to `complete`. Optimism remains, regrettably, not a test
runner.
