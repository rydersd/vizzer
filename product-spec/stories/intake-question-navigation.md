# Question checklists and navigation

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, questions, constellation

## Origin

IllTool 29884954e (#1340), b62d13726 (#1400), 332006f9d.

## Acceptance

- A review testing plan renders as a checklist; checked state is an answer
  recorded through the existing answer ledger, not page-local state.
- Open owner questions show `Previous | N of M | Next`; arriving at another
  story's questions starts at its first one.

## Tests

1. Checklist answer persists through reload via the answer ledger.
2. Navigation order and N-of-M across two stories, arrival lands on question 1.

## Test plan (RC)

Keyboard navigation and a question edited mid-navigation are not automated.
