# Session history upstream integration

> Status: shipped
> Depends on: progress-pathing-upstream-integration
> Release: R1

## Problem

The constellation shows the project's current delivery graph, but not how agent
sessions moved through it. Project owners cannot distinguish a repeated trail
from double rendering, isolate one session, or inspect the public work record
behind a Story touch without leaving the map.

## Acceptance criteria

- The constellation may opt into a rolling 72-hour Claude and Codex overlay.
- Trails use explicit Story references only, fade with age, distinguish models,
  and never draw an ordered hop from one message that names multiple Stories.
- The owner can filter provider/session/time, double-click a trail to isolate it,
  dismiss isolation from a visible banner, and open the corresponding event or
  filtered work log in the existing sidebar.
- Work-log filters remain visible while scrolling and include exact exec-family
  invocations without retaining command arguments or output.
- Recorded public progress is rendered as attributed Markdown with separate
  challenges, rationale, evidence, and improvement opportunities; UI-derived
  suggestions are labeled rather than promoted to agent findings.
- Existing answer drafts and saved answers survive history navigation.
- Transcript admission uses Git repository identity or explicit configured
  checkout paths, never a colliding directory-name prefix.
- Public excerpts and archives stay in a machine-local cache outside the project
  checkout; hidden reasoning, tool arguments, tool output, and injected ambient
  context are excluded.

## Definition of done

- Parser, privacy, incremental recovery, de-duplication, pagination, and filter
  tests pass.
- A real loopback server serves summary, event, and log endpoints when enabled
  and returns 404 when disabled.
- An assembled physical-browser smoke proves canvas rendering, event opening,
  double-click isolation/dismissal, sticky filters, and a 760 px layout.
- Mutations removing the canvas draw hook or double-click integration make the
  browser smoke fail.
- The complete upstream test suite and generated golden output pass.
