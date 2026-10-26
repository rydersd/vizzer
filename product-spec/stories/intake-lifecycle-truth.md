# Lifecycle truth fixes

> Status: shipped
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, lifecycle

## Origin

IllTool e8848c0bc (owner answer r416), 5a7af75bf, cbdb5c7a6 (#1449), 32730bf73 (#1354).

## Acceptance

- A shipped story stays shipped unless the configured lifecycle policy withdraws it.
- A promotion whose story has shipped is satisfied, not a warning.
- A status flip not yet persisted is stamped at the ledger's `updatedAt`.

## Tests

1. Shipped story with later non-withdrawing edits remains shipped.
2. Shipped-promotion produces no warning; an unshipped one still does.

## Test plan (RC)

Startup-smoke fixes from #1354 are verified by the RC browser smoke.
