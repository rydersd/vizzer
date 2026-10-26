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

## Named tests

- (planned) `tests/test_ci_overlay.py::test_fixture_adapter_output_maps_by_neutral_story_identity`
- (planned) `tests/test_ci_overlay.py::test_missing_or_failing_provider_shows_unknown_never_passing`

## Open contract questions

- Adapter declaration and result schema for a CI provider.
- Timeout and cache policy for provider calls.
- How are malformed, stale, unauthorized and unavailable results told apart?
