# Cross-project change radar: local review receipt

Date: 2026-09-06. Scope: local implementation; not a published release.

## Skeptical review

- A dirty upstream fix must not count as integrated: committed HEAD and the
  working engine must both contain the patch. Fixture exercises this distinction.
- Different Git histories cannot identify adoption: content hashes and isolated
  forward/reverse patch checks provide narrower evidence; conflicts stay unknown.
- Changed patch bytes cannot inherit a review: identity binds path and both file
  images; old reviews and observations are retained.
- Missing engines, tampered baselines, unsafe paths and files changing during a
  scan cannot produce a clean adoption claim. Failed scans retain the prior report.
- Watcher also observes downstream HEAD/dirty state, so committing unchanged
  working bytes refreshes provenance. One watcher owns each local store.

## Validation

Focused deterministic checks: **157 passed, 2 deselected**, 75.59 seconds.
Command: `.venv/bin/python -m pytest -q tests/test_radar.py tests/test_config.py
 tests/test_render_dashboard.py tests/test_cli.py tests/test_render_constellation.py
 tests/test_trail_visibility.py -k 'not physical'`. Physical-browser selectors
were excluded; the radar page was separately inspected in the local browser.
Search reduced the visible list to the named trail repair. The local status API
reported a healthy watcher after its first successful scan and view refresh.

## First real proposal

Fingerprint: `da3a75ca6f9d3b5b0bb5ab796972f502900c512a86891eafe60471c5e0949727`.
The upstream working trail repair is discovered, not integrated. Illmater,
IllTool and IllTool's live runtime all need reconciliation. Direct source
inspection independently found the offscreen-endpoint `.on` rejection and
older recency alpha in each installation. Each also adds `edgeFog(a,b)`, so
wholesale replacement would risk losing fork behavior. No downstream writes.

## Limits

File-level differences include old code and project customizations; they are
not automatically improvements. The comparison commit is not verified fork
ancestry. Matching patch hunks do not prove semantic equivalence or runtime
correctness. Binary assets, file modes and renames are outside this first scope.
Registration, annotation and review use CLI commands; the inbox is read-only.
The login service has been started and inspected; a machine reboot was not tested.
