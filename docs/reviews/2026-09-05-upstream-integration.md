# Upstream integration adversarial review — 2026-09-05

Scope: `codex/progress-pathing-editors`, composed on upstream source commit
`29d54a040e52f503325bab354ac23d796a79d338`. Includes formatted owner answers,
pending Story revisions, progress-pathing recording/playback, tag identity colors,
and opt-in macOS login-service configuration. Other open branches are excluded.

## Findings and repairs

1. **High: archive installation failed.** New playback/editor assets were read
   through filesystem `Path(__file__)`, which does not represent files inside a
   `.pyz`. The existing published-installer test reproduced `NotADirectoryError`
   before the repair. `render_all` now uses package resources, matching the
   existing Constellation renderer. The identical installer test then passed.
2. **Medium: playback ignored the configured output directory.** The recorder
   always selected `vizzer/views`, unlike refresh/serve. It now loads the project
   config and rejects an output directory outside the project. A deterministic
   custom-directory and escape-path check covers this boundary.
3. **Medium: full-suite expectations were stale.** The original targeted test
   receipt omitted the exact output-list/status assertions and generated fixture.
   Both now expect the five added assets; the Constellation golden was regenerated
   from the unchanged fixed-date fixture. Assertions were retained.
4. **Medium: newly refreshed Stories could not be edited.** The new HTTP route
   used the server's startup graph. A same-server regression reproduced a 404
   after a new Story appeared in the refreshed graph. The route now reads the
   current graph inside the mutation guard and fails closed if it is unavailable.
   The regression also checks saved proposal content, unchanged source bytes,
   removal after refresh and unavailable-graph handling.

The review also checked the graph-ID-only source lookup, project containment,
CSRF/CAS handling, source-preserving proposal writes, offline archive seam,
early CSP, sandbox without same-origin privileges, and bundled license notices.

## Evidence boundaries

The independent pre-execution packet retains test-design findings, repaired
supervision, source fingerprints, exact recipes and actual outcomes separately.
The compatibility suite is not proof of every UI operation. Browser editor checks
and real HTTP revision persistence checks cover separate boundaries; they do not
constitute an upstream browser-to-HTTP-to-reload Story submission test.

No live login services were installed by this review. LaunchAgent tests mock
system operations. Archive checks inspect generated restrictions; this review
does not claim a new hostile-browser CSP penetration test. Markdown preservation
is demonstrated for the tested metadata/list/fence fixture, not arbitrary syntax.
The checked-in Markdown bundle was exercised but not independently rebuilt here.

Pending revisions remain review candidates; Save does not apply source edits or
launch a model. Recorder history has no automatic retention policy. These are
documented limits, not reasons to delay unrelated product building.

## Validation outcome

The complete local compatibility suite passed **560 tests in 78.06 seconds**
before the final current-graph lookup repair. No tests were skipped. The bounded
supervisor recorded a 1.47 GB peak aggregate resident set and no run snag.
An earlier run aborted on a disappearing temporary directory in the supervisor;
that incomplete run is retained as infrastructure evidence, not a test result.

The exact installer regression failed before repair and passed afterward. The
new-Story HTTP regression failed at the intended new-Story GET (404 instead of
200) before repair. Final focused results and current-head CI follow below.

Final focused validation passed **12 tests in 10.11 seconds**: Story revision
HTTP (including the new refresh regression), Story proposal persistence/guards,
packaging, and the CLI fixed-fixture render/check/archive contract. No skips.
The new regression passed on the repaired production route; its original failing
404 remains the negative control. `git diff --check` passed.

No unresolved blocking findings remain in this reviewed scope. Current-head CI
is the final merge gate; its status is retained on the pull request.
