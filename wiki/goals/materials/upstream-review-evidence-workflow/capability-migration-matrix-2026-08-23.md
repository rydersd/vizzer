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
| Story sidebar (steps, AC, DoD) | Core dossier capability, derived from configured source shape | Pending port |
| Neutral story-path identity | Core utility shared by review and CI; derive from adapter/config | Pending port |
| Review console and screenshot viewer | Optional review surface, off by default | Pending decontaminated port |
| Acceptance bundle archival and rollback | Optional review service; retain copy/hash/restore safety | Pending port and attack tests |
| Browser/local execution | Named adapter operations; no agent-authored raw commands | Contract landed; adapters pending |
| Fixture launch/staging/liveness/annotation | Host adapter interfaces only | Pending; IllTool implementations excluded |
| Renderer/config/HTTP/check extension registries | Core seams required before optional review UI | Pending refactor |
| `renderId` content identity | Core, but rebase on installed package layout rather than parent counts | Pending high-risk isolated port |
| Graph blocked records, conflicts, completion provenance | Core project-agnostic semantics | Pending port |
| Decision-journal replay/dedup migration | Core one-way migration with legacy reader | Pending isolated port |
| CI overlay, notices, restart, autocommit | Optional served features; neutral providers, restart command unset, autocommit false | Pending decontamination |
| Analytics, lanes, awaiting-owner perspectives | Optional renderers, off by default; remove personal/name/path heuristics | Pending port |
| Constellation interaction/features | Port generic depth/chrome/tables/deep-links/sidebar/focus/drafts/filters/alerts fixes | Pending; symbols licensing unresolved |
| Fork test corpus | Re-home by capability with non-IllTool fixtures and leak guards | In progress |

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
