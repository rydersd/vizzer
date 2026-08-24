# Adversarial review — final reusable-fork migration

> Date: 2026-08-23
> Scope: content identity, blocked work, conflicts/completion, decision replay, optional
> perspectives, Constellation chrome/deep links, and Developer Flow scale.

## Findings fixed

### High — version text could still bless replaced runtime bytes

The old check trusted `vizzer/VERSION`. The port now hashes classified runtime resources under one
logical package namespace, produces the same identity in `src/vizzer` and a vendored install,
stamps `vizzer/RENDER_ID`, and refuses an installed engine whose marker, disk bytes, and running
process identity disagree. Tests mutate installed bytes after process capture and require HTTP 409.

### High — answered blockers remained undispatchable

The first blocked-record port recognized explicit question links but delivery assessment still
treated every `blocked` activity record as live. Dispatch now asks the shared blocker authority;
answered questions clear the gate while unlinked and expired records fail `vizzer check`.

### High — decision replay could erase legitimate history

Fingerprint-only markers prevent duplicate replay, but a naïve cleanup would collapse two
non-equivalent decisions for the same question snapshot. The replay comparison ignores only the
marker revision and ledger revision line, preserves materially different events, accepts legacy
revision markers, and ignores torn/incomplete events.

### Medium — optional perspectives silently became default product surface

Analytics, awaiting-owner, lanes, and agent-operations views initially rendered in a default
install. That changed Vizzer's output set and imported policy simply by updating the engine. All
perspectives now require explicit configuration; agent operations also requires a declared ledger
grammar and path.

### Medium — fixed top offsets reintroduced rail/search overlap

The title bar now holds the 14/18/22 reading control and can wrap at narrow widths. Fixed search and
rail offsets therefore became invalid. A ResizeObserver measures the real title/search chrome and
publishes semantic `--search-top` and `--rail-top` values consumed by search, rail, and its resize
handle.

### Medium — screenshots were technically present and practically useless

Earlier evidence reduced 1280×720 captures to ornamental thumbnails. The review UI now renders
evidence at full content width with an actual-size link. Final Developer Flow evidence is stored at
1280×720 for the capability overview and the Drawing story/shared-detail drill-down.

### High — authored titles escaped fixed frame geometry

Collapsed frames were hard-coded to `280×132` with a `43px` header. A legitimate three-line
capability title therefore rendered above its own border at review zoom. Frame and card dimensions
now derive from wrapped content, visible summaries and failures no longer use silent clamps, and
detail overflow remains scrollable. The exact failing title has a geometry regression and a
full-size browser receipt.

### Medium — orthogonal routing was readable but mechanically sharp

The first renderer drew ELK bend points as square polylines and relied on default edge spacing.
Routes now preserve ELK's obstacle-avoiding points while rounding corners with a 10-unit quadratic
bend. Root and nested layouts reserve an explicit 18-unit edge-to-edge lane gap and 24-unit
edge-to-node gap; a real four-edge fan-out test verifies adjacent vertical lanes exactly 18 units
apart.

## Unresolved high-severity scale finding

A fresh 100,000-object/100-group synthetic corpus returned the correct bounded 600-of-1,000 slice
in 617,362 bytes, but cold normalization plus indexing took 21.765 seconds and peaked near 1.0 GB
RSS on the test Mac. This falsifies any claim that the current implementation is already
enterprise-performance-ready. The 4 MiB response boundary and 100,000-object safety ceiling remain
valid; persisted/incremental indexes and adapter-side aggregation are required before claiming a
pleasant Salesforce-scale startup.

## Deliberate exclusions

- Apple-exported symbol paths were not copied; their licensing is unresolved.
- IllTool review capture, fixture staging, launchd restart, GitHub-CLI status, and hook-bypassing
  autocommit remain host policy, not upstream defaults.
- Claude-led IllTool work items and their evidence/lifecycle records were not changed.

No unresolved correctness or data-integrity issue is known in the shipped local review loop. The
remaining high finding is performance at the declared upper safety ceiling, not unbounded response
materialization or a false UI count.
