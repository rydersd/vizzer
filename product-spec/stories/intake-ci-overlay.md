# Provider-neutral CI overlay

> Status: specced
> Deps: [intake-testing-hub](intake-testing-hub.md)
> Release: R1
> Tags: upstream, ci

## Origin

Pre-b6a67bb IllTool `ci_status.py`, `ci.js`; excluded in 2026-08 for binding the GitHub CLI.

## Acceptance

- Story nodes show CI state from a configured provider adapter; GitHub (via `gh`)
  is one adapter, invoked only from trusted configuration.
- Story-to-CI mapping uses the neutral story identity, not a directory grammar.

## Tests

1. Fixture adapter output maps to the right story by neutral identity.
2. Missing or failing provider shows "unknown", never "passing".
