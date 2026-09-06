# Integrate progress pathing and owner editing upstream

> Status: shipped
> Deps: []
> Tags: upstream, review

## Intent

Review and merge the reusable Illmater-origin editor, Story revision,
progress-pathing playback, tag-color and optional login-service changes from
`codex/progress-pathing-editors` into Vizzer upstream.

## Review and verification

Candidate is composed on `29d54a040e52f503325bab354ac23d796a79d338`.
Independent test-design review precedes the bounded integration suite.
The test-design packet was retained locally in the candidate worktree; it is not a published repository document.
Code review: `docs/reviews/2026-09-05-upstream-integration.md` on the candidate.

Verify Markdown preservation, source/revision conflicts, archive isolation,
portable installer assets and the existing compatibility suite before merge.
Retain failures and limitations; local test success is not publication.

## Historical test-design gate — 2026-09-05

Independent reviewer: `integration_test_review`. Tier B PASS fingerprint
`f385bac689d898f91a872bb499acc1b64fd5f98729d2d68d536f3d9b62edb472`.
At this checkpoint the compatibility suite was running; its final result is below. One process-tree
supervised attempt, 300 seconds, 4 GiB aggregate RSS, 2 GiB temporary disk.
No live login-service installation or user-window input. The earlier attempt
stopped on a temporary-directory monitor race; it is an infrastructure snag,
not a completed test result.

Installer regression: original candidate fails with archive-path
`NotADirectoryError`; package-resource repair passes the identical selector.
New Story edit lookup after refresh is separately under regression review.

## Completion — 2026-09-05

Merged [Vizzer PR #4](https://github.com/rydersd/vizzer/pull/4) as
`1d9e4e4c9fe5e7c12827fd8d6d62cc7f8dbe2efd`. Final reviewed head
`f1249904d8a402098a743947595dadffbf907d9f`.

Local compatibility: 560 passed before the final current-graph route repair;
final focused suite: 12 passed including the new-Story refresh regression.
Final-head hosted CI: Python 3.9, 3.10, 3.11, 3.12, 3.13 and pyz all passed
([run](https://github.com/rydersd/vizzer/actions/runs/33990180873)).

Test run state: finished; outcome: pass. Fixed packaged resource lookup,
configured playback paths, and newly refreshed Story editing. Detailed review
is now available at `docs/reviews/2026-09-05-upstream-integration.md`.
Illmater implementation resumed in its existing task; no wholesale downstream
engine replacement was performed.
