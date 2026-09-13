# Cross-project change radar

The radar compares registered local Vizzer engines with an explicit upstream
Git baseline. It discovers file-level differences, retains content-bound review
proposals, and checks which installations contain each patch. It never applies
patches, pulls repositories, commits, or launches downstream tests.

## Open the inbox

Use **Views → Change radar**, or the radar card at the top of the dashboard.
On this Mac: <http://127.0.0.1:8480/radar.html>. Search by title, source path or
project, filter by lifecycle, inspect the installation table, and download a
patch. Patches use paths relative to the engine package; reconcile them in the
appropriate checkout before applying. A clean applicability check is not approval.

## Register and scan

Run from the upstream Vizzer source checkout:

```sh
python3 vizzer/engine radar register --id example --project /path/to/project \
  --engine vizzer/engine/vizzer --baseline HEAD
python3 vizzer/engine radar scan
python3 vizzer/engine refresh
python3 vizzer/engine radar show
```

`--baseline` resolves to an immutable upstream commit and stores its engine
snapshot. It is a comparison reference, **not a claim about the fork's ancestry**.
Old behavior, project-specific changes and actual improvements all require
review. Different Git histories do not prevent matching the same content or
patch hunks. A registration cannot silently overwrite an existing baseline.

The first version reads `src/vizzer` upstream and each explicitly registered
engine directory. It includes text `.py`, `.js`, `.css`, `.html`, `.json`, `.md`,
`.txt` and `.svg` files, and skips cache/dependency directories. Binary assets,
file modes, renames and semantically different implementations need manual
review. Registration and scanning require Git and Python on macOS/Linux.

## Interpretation

| Observation | Meaning |
| --- | --- |
| Exact code present | The current file equals the proposal's after-image. |
| Matching patch present | Reverse application checks successfully in an isolated copy, despite other edits. This establishes matching hunks, not semantic equivalence. |
| Missing · baseline unchanged | The file still equals the proposal's before-image. |
| Patch applies cleanly | The file differs, but the patch passes an isolated forward check. No real file was modified. |
| Needs reconciliation | Neither exact content nor applicability establishes the change; inspect the diff and project assumptions. |
| Unavailable | The registered engine could not be read; absence is not adoption. |

A proposal is **discovered** until reviewed. Record review against its full
fingerprint with `radar annotate --id FINGERPRINT --review "findings"`.
**Integrated** additionally requires the change in the local upstream Git commit
and working engine. This does not claim remote publication. **Adopted** requires
matching code in all registered engines as well. Regression or an unavailable
installation withdraws that claim; prior states remain in history. A changed
patch gets a new fingerprint and cannot inherit a previous review.

Name a proposal and attach evidence:

```sh
python3 vizzer/engine radar annotate --id FINGERPRINT \
  --title "Explain the behavior change" --summary "Scope and assumptions" \
  --evidence product-spec/stories/example.md
```

Evidence records capture file hashes. Links to tests or receipts are not a claim
that the radar executed them. Proposals are local durable records in
`.vizzer/radar/report.json`; before/after images, origin HEAD and dirty state,
source fingerprints, review notes and observation history remain attached.
Registrations contain local absolute paths and stay in the ignored local store.
Baselines and proposals should be retained together if backing up this state.
Generated `radar.html` and `radar-patches/` live in the configured views directory.

## Automatic local discovery

```sh
python3 vizzer/engine radar watch --interval 30
```

The watcher checks engine content and each repository’s HEAD/dirty state every 30 seconds. Changed
inputs trigger a scan and view refresh; an idle graph does not produce new
proposals or history events. The open radar page checks for completed updates.
A failed scan keeps the last good report and exposes its error through live
status. Missing projects are represented explicitly. Concurrent source edits
abort a scan rather than publishing a mixed snapshot. One watcher owns the
project; other scans and annotations serialize on a separate nonblocking lock.

On this Mac the login service is `com.vizzer.project.ad84a7edba4f.radar`.
Its plist is in `~/Library/LaunchAgents/`; logs share
`~/Library/Logs/Vizzer/ad84a7edba4f/`. Restart after changing radar code:

```sh
launchctl kickstart -k gui/$(id -u)/com.vizzer.project.ad84a7edba4f.radar
```

Stop with `launchctl bootout gui/$(id -u)/com.vizzer.project.ad84a7edba4f.radar`;
use `launchctl disable` with the same service target to disable login startup.

Budgets: 12 registered projects, 1500 files / 32 MiB per engine, 4 MiB per file,
300 retained proposals, 96 MiB per state file, 10-second subprocess timeouts,
and a 45-second scan budget checked between proposals. Reaching a limit fails
visibly and preserves the prior report. The proposal count includes file-level
comparison noise and superseded candidates, not accepted product work.

## Preserve intent for future articles

Before integrating an idea, capture its source project's problem, intent and
rationale in a [wiki idea brief](../ideas/README.md). Keep source rationale
separate from Vizzer's adaptation, and label unknowns rather than inventing them.

```sh
python3 vizzer/engine radar annotate --id FINGERPRINT --brief wiki/ideas/idea.md
```

The Markdown file must contain `## Intent`, `## Rationale` and `## Sources`
sections (64 KiB maximum). Radar snapshots the text and hash, preserves captured
revisions, and offers a readable section plus Markdown download on the proposal.
Reattach after edits. A changed patch does not inherit the old brief automatically.
The authored wiki file is ready for Git; the local capture remains in radar state.
Missing briefs are visible on proposals, but do not change code-adoption truth.
