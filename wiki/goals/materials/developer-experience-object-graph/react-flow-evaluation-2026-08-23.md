# React Flow optional-bundle evaluation

> Goal: [G-002 — Developer-experience object graph](../../developer-experience-object-graph.md)
> Captured: 2026-08-23
> State: initial verified constraint, not a final renderer design

## Verified facts

- The current package is [`@xyflow/react`](https://reactflow.dev/learn), installed into a React
  application with its stylesheet.
- React Flow is open-source under the
  [MIT License](https://github.com/xyflow/xyflow/blob/main/LICENSE). Redistribution and commercial
  use are allowed when the copyright and license notice are retained.
- The maintainers distinguish the MIT library from
  [React Flow Pro](https://reactflow.dev/pro), which sells support and Pro examples/templates rather
  than a separate required runtime.
- The library renders a small attribution by default. MIT does not make that UI attribution a legal
  condition, but the maintainers [ask non-Pro users to keep it](https://reactflow.dev/remove-attribution).

## Current direction

Bundle React Flow only as an optional, precompiled Vizzer add-on:

- no CDN fetches;
- pinned React, React DOM, React Flow, and transitive versions;
- reproducible build input and checked third-party notices;
- attribution visible unless the distributor deliberately supplies an applicable Pro entitlement;
- core install and existing generated views remain React/Node-free;
- normalized developer-graph data and dossier actions do not import React types.

This accepts the owner's permission to bundle React Flow without making a frontend framework the
authority for Vizzer's model. The latter would be an exciting way to make every adapter migration a
UI rewrite, which is not the kind of excitement this goal needs.
