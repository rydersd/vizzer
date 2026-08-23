# G-001 — Upstream the generic review and evidence workflow

> Status: in progress
> Ambition: large
> Created: 2026-08-23
> Updated: 2026-08-23
> Runtime goal thread: `01a02f0a-b3c3-77e2-b974-3856f1de7aa2` (execution state is external and may change)

## Objective

Review the evolved Vizzer implementation and product thinking in
`/Users/ryders/Developer/GitHub/illtool-standalone` and compare it with
`/Users/ryders/Developer/GitHub/project_vizzer`; then update upstream `project_vizzer` and its
project-agnostic contracts with every reusable capability developed in the fork, without importing
IllTool-specific concepts, paths, schemas, fixtures, or product assumptions.

Expand the review mechanism for web and local development projects into a generic agent-to-owner
acceptance loop:

1. An agent derives concrete, repeatable test steps from the applicable Definition of Done.
2. The agent executes the steps and records structured results.
3. The agent captures screenshots and other evidence showing what it believes is done.
4. Vizzer presents the same steps and machine evidence to the owner.
5. The owner repeats the checks, records independent validation or rejection, and preserves the
   outcome without overwriting the machine claim.

## Success conditions

- The upstream/fork comparison covers current `main`, every named IllTool worktree, and the recent
  product/spec evolution—not only one convenient checkout.
- Reusable fork functionality is incorporated upstream with explicit migration boundaries.
- Review schema distinguishes source contract, derived steps, execution result, machine evidence,
  human verification, verdict, and archival/application state.
- Web and local-project adapters exercise real launch/test/evidence paths without assuming Xcode,
  `.illtool` files, Application Support, launchd, or one repository layout.
- Security and privacy contracts cover path containment, symlinks, media validation, capture limits,
  untrusted commands, secrets, and user data.
- Non-IllTool fixtures plus negative vocabulary/path checks prove project agnosticism.
- Upstream tests, rendered views, served interaction, packaging, and offline behavior are verified
  independently before completion.

## Boundaries

- The optional review capability may integrate with host launchers and artifact stores only through
  declared adapters/capabilities.
- A screenshot is evidence of an observation, not proof that the Definition of Done is satisfied.
- Accepted review and lifecycle completion remain separate facts.
- The queued 2D developer graph is tracked as [G-002](developer-experience-object-graph.md), not
  silently folded into this delivery.
- Claude's IllTool burn ledger is a collision blacklist, not an upstream work queue. This goal does
  **not** implement or amend the ledger's claimed IllTool work: review-sheet captures;
  `under-cursor-reach`; PRs #908/#909/#910; harvest-golden or close-target XCUITest; regularize,
  token-governance, or smart-align ruling work; group-transform planning; or the locked-row picking
  decision. Reusable mechanisms may be studied read-only and re-expressed behind generic upstream
  contracts, but no IllTool story, evidence row, verdict, or lifecycle state is changed here.

## Materials

- [Fork divergence map](../concepts/illtool-fork-divergence-map-2026-08-21.md)
- [Named IllTool worktree inventory, 2026-08-23](materials/upstream-review-evidence-workflow/illtool-worktree-inventory-2026-08-23.md)
- [Capability migration matrix, 2026-08-23](materials/upstream-review-evidence-workflow/capability-migration-matrix-2026-08-23.md)
- [Adversarial review of the first upstream slice, 2026-08-23](materials/upstream-review-evidence-workflow/adversarial-review-2026-08-23.md)
- [Project-agnostic review workflow contract](../../docs/review-workflows.md)

## Progress log

- 2026-08-23 — Started fresh comparison against the current upstream branch and IllTool `main`.
- 2026-08-23 — Expanded the source audit to all thirteen owner-named IllTool directories; nine are
  live registered worktrees and four are detached remnants/tombstones that still require material
  inspection rather than being dismissed as branches.
- 2026-08-23 — Recorded the live Claude ledger's claimed work as an exclusion set. The upstream
  port can learn from those mechanisms, but it will not duplicate or execute those IllTool items.
- 2026-08-23 — Landed the first upstream review core: normalized DoD-derived plans, named adapter
  operations, required done-state screenshots for visual rows, separate append-only agent/owner
  runs, CAS writes, image byte validation/dimensions, containment and symlink checks. Focused tests
  passed 12/12 and the complete existing suite passed 374/374 before the final two integrity attacks
  were added; those focused attacks also pass.
- 2026-08-23 — Formal adversarial review found and fixed three high-severity gaps (metadata-only
  evidence, invented DoD under a valid source fingerprint, and cross-format image decode budgets)
  plus unbounded ledger growth. The expanded focused suite passes 15/15; stale-lock recovery remains
  explicitly deferred to the service layer because time-based lock theft would be unsafe. The full
  upstream suite passes 379/379 after these fixes.
