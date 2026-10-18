# Durable served writes

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, durability, served

## Origin

Pre-b6a67bb IllTool `autocommit.py` (owner-ruled 2026-08-15 after a lost answer).

## Acceptance

- Opt-in: each accepted served write is committed locally with explicit
  pathspecs on the current branch; never pushes.
- Best-effort: a Git failure warns and leaves the write on disk.
- Hook policy is project configuration; the default runs hooks. IllTool's
  hook-skipping behavior is available only as an explicit setting (owner
  ruling 2026-10-17).

## Tests

1. Accepted answer produces one commit with exactly the touched files.
2. Git failure leaves the write on disk and the HTTP response succeeds (data-loss guard).
