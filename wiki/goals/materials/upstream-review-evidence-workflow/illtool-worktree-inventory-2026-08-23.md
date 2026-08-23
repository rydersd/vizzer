# IllTool worktree inventory — 2026-08-23

> Goal: [G-001 — Upstream the generic review and evidence workflow](../../upstream-review-evidence-workflow.md)
> Scope: owner-named directories, read-only first pass
> IllTool `main` at scan start: `e826df2c82010676cfa923ecbd51f71eb50b2348`
> Upstream Vizzer at scan start: `6739779b9ab29942d38bc91269f7d4e5c6182edb`

This inventory prevents the upstream audit from equating one checkout with the whole week of work.
It records repository state, not feature conclusions; source and materials in relevant lanes still
need content-level comparison.

## Registered live worktrees

| Directory | Branch | HEAD | First-pass Vizzer/review finding |
|---|---|---|---|
| `illtool-standalone` | `main` | `e826df2c8` | Current fork authority. Had concurrent staged/dirty generated Vizzer views and lane data; preserve, do not normalize from another lane. |
| `illtool-standalone-align` | `codex/align-distribute` | `6f6ed1afd` | Relevant branch delta is curated-test registration plus generated Vizzer snapshots; no unique engine/review source found in first pass. |
| `illtool-standalone-fpsbug` | `codex/bezier-handle-fps` | `510c4dad5` | Relevant delta is performance acceptance registration; no unique engine/review source found in first pass. |
| `illtool-standalone-objectlock` | `codex/object-lock-hittest` | `a03cfd1ed` | Relevant delta is an acceptance selector; no unique engine/review source found in first pass. |
| `illtool-standalone-prefs` | `claude/app-preferences-window` | `6aeebfd9a` | Relevant Vizzer differences are generated snapshots around the feature lane; no unique review engine source found in first pass. |
| `illtool-standalone-strokelabels` | `claude/stroke-recovery-labels` | `0528b4db2` | Active-work/progress and generated view differences carry useful review-lifecycle examples, but not a distinct review implementation. |
| `illtool-standalone-w2b-components` | `codex/w2b-components` | `55941dd8f` | Old generated Vizzer snapshot only in first-pass relevant diff. |
| `illtool-standalone-w2b-panels` | `codex/w2b-panels` | `f9908123a` | Old generated Vizzer snapshot and blocker note only in first-pass relevant diff. |
| `illtool-standalone-w2b-spine` | `codex/w2b-spine` | `57b7fe3db` | Old generated Vizzer snapshot plus named acceptance/closeout records; no distinct review engine source found in first pass. |

## Named directories that are not live worktrees

| Directory | Observed state | Material to inspect |
|---|---|---|
| `illtool-standalone-curvebounds` | 83 MB directory with a `.git` pointer to an absent worktree-admin directory. | Historical scripts include DoD extraction and named review-artifact capture; compare with current `main` before treating anything as unique. |
| `illtool-standalone-pr810` | 134 MB directory with a `.git` pointer to an absent worktree-admin directory. | Contains an older complete review-sheet/capture engine snapshot and review fixtures; useful as historical evidence, not a branch authority. |
| `illtool-standalone-review-capture` | 16 MB stripped remnant with a broken `.git` pointer and no current `vizzer/` tree. | `task-capture-blank.md` and `test-support/ReviewWindowCaptureContracts.swift` may preserve capture-workflow intent or test evidence absent from the engine diff. |
| `illtool-standalone-selgate` | 12 KB tombstone containing only `.DS_Store`; no `.git` pointer or source files. | None. Record it so later audits do not repeatedly “discover” it. |

## First-pass conclusion

The live side worktrees do not presently expose a second unmerged Vizzer engine. Their value is in
acceptance, lifecycle, and evidence examples. The strongest review implementation remains current
IllTool `main`; the detached `pr810` and `review-capture` remnants are historical/material sources
that need targeted comparison. This conclusion is wrong if a relevant untracked file sits outside
the scanned Vizzer, spec-ops, review, capture, and test patterns; the next pass must compare the
named capture artifacts and branch histories directly rather than trusting filenames.
