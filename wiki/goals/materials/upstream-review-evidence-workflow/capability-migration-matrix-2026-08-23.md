# Capability migration matrix — IllTool fork to upstream Vizzer

> Date: 2026-08-23
> Purpose: execution inventory, not a claim that the port is complete.

The fork is a file-level superset, but a merge would import host policy and stale assumptions. Port
capabilities by contract, with upstream source as authority and IllTool read-only as evidence.

| Capability family | Upstream disposition | State |
|---|---|---|
| Image byte validation and dimensions | Core utility; no review or host dependency | Implemented and tested |
| DoD-derived procedure + agent/owner run separation | New generic core contract superseding prose-only receipts | Implemented and tested |
| Evidence containment, symlink, size, hash, media checks | Core validation; store/capture remain adapters | Implemented and tested |
| Append-only response/run ledger with revision CAS | Core review contract; owner identity reserved for served owner surface | Implemented and tested |
| Story sidebar (steps, AC, DoD) | Core `vizzer-object-detail/v1` capability shared by Constellation and Developer Flow | Implemented and tested |
| Neutral story-path identity | The new review contract uses source item id + repo-relative path rather than inferring identity from one directory grammar; CI extraction still needs a neutral seam | Review need superseded; CI follow-up pending |
| Review console and screenshot viewer | Optional served review surface, off by default; opaque evidence URLs | Implemented and tested |
| Acceptance bundle archival and rollback | Fork behavior moves host-owned fixtures; upstream preserves review plans, append-only runs, and content-addressed evidence without taking fixture ownership | Excluded from core; a future artifact-store adapter may add archival |
| Browser/local execution | Named adapter operations validated against a trusted declaration; host harness performs execution | Registry plus real neutral web/local host fixtures exercised |
| Fixture launch/staging/liveness/annotation | Host adapter interfaces only | Generic trusted-operation registry implemented; IllTool executors intentionally excluded |
| Screenshot capture quality and blank-frame falsifiers | Capture adapter responsibility; core verifies contained bytes, digest, media structure, dimensions, and decode budgets but cannot infer whether project-specific pixels prove a scenario | Historical IllTool contracts inspected; host geometry/accessibility/content thresholds and the active review-capture ledger lane deliberately excluded |
| Renderer/config/HTTP extension seams | Renderer registry plus served-extension registry; review and developer-flow config are opt-in | Implemented and tested |
| `renderId` content identity | Core, rebased on logical package paths shared by source and installed layouts | Implemented, mutation-tested, and installed-engine guarded |
| Graph blocked records, conflicts, completion provenance | Core project-agnostic semantics | Implemented and tested against configured lifecycle roles |
| Decision-journal replay/dedup migration | Core one-way migration with legacy reader | Implemented; torn events and non-equivalent same-fingerprint history attacked |
| CI overlay, notices, restart, autocommit | Fork code binds GitHub CLI, launchd, a fixed service label, and hook-bypassing commit policy | Excluded; provider-neutral CI/restart/autocommit need separate opt-in adapters and threat models |
| Analytics, lanes, awaiting-owner perspectives | Optional renderers, off by default; remove personal/name/path heuristics | Implemented and tested as project-neutral optional perspectives |
| Shared reading controls and left-rail resizing | Title-bar 14/18/22 control, fixed chips, shared dossier/rail type, persisted rail geometry | Implemented and tested |
| Constellation interaction/features | Shared typography/rail geometry, measured top chrome, Roadmap filters, and stable object deep links are core; Developer Flow owns dense 2D grouping/focus | Implemented core subset; Apple-exported symbols and IllTool answer/CI chrome excluded |
| Optional 2D developer graph | Neutral graph/detail/query contracts plus precompiled React Flow/ELK renderer | Implemented and tested at 25,000 objects |
| Fork test corpus | Re-home by capability with non-IllTool fixtures and leak guards | Selected portable families re-homed; project-policy tests excluded with their features |

## Collision exclusions

Claude's live IllTool ledger claims the following work. This upstream goal does not execute or amend
it: review-sheet captures; `under-cursor-reach`; PRs #908/#909/#910; harvest-golden; close-target
XCUITest; regularize, token-governance, and smart-align rulings; group-transform planning; and the
locked-row picking decision. Generic contracts may be informed by their existing mechanisms, but
the IllTool work items, fixtures, screenshots, verdicts, and lifecycle states remain untouched.

## Port gates

1. No `illtool`, `.illtool`, Ryder/Claude identity, Application Support, LaunchServices, launchd,
   Xcode, or fork directory literals in shipped upstream source or generic fixtures.
2. Optional features render and serve nothing when disabled.
3. Agent results and owner validation remain distinct events under the same plan fingerprint.
4. A visual agent pass requires structurally valid screenshot evidence; a screenshot remains an
   observation, never proof by itself.
5. Every side effect is an adapter operation from trusted configuration, not executable text from a
   review artifact.

## Scale falsifier

The bounded-query architecture survives a 100,000-object synthetic corpus and returns 600 of 1,000
matching objects in a 617,362-byte response. The cold normalization/index build took 21.765 seconds
and peaked near 1.0 GB RSS on the test Mac. That is a supported safety ceiling, not evidence of a
pleasant Salesforce-scale startup. Persisted/incremental indexing is a named follow-up before the
UI may claim enterprise-scale operational performance.
