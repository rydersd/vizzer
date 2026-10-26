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
- Hook policy is project configuration; the default runs hooks. A
  hook-skipping behavior is available only as an explicit setting (owner
  ruling 2026-10-17).

## Named tests

- (planned) `tests/test_served_commit.py::test_accepted_answer_commits_exactly_the_touched_files`
- (planned) `tests/test_served_commit.py::test_git_failure_leaves_write_on_disk_and_response_succeeds`

## Open contract questions

- How is "exactly the touched files" proven when the index or worktree is already dirty?
- Hook failure: does it warn and skip the commit, or fail the write?
- Behaviour with concurrent writers or repos with unrelated staged changes.
- Partial Git failure (some pathspecs staged, commit fails): cleanup or leave as is?
