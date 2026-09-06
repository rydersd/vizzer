# Documentation migration inventory

Reviewed 2026-09-05. Nine substantive pages moved from docs into the wiki.
Original dates, citations, contracts and historical evidence were retained.
Old paths forward here for compatibility; only the maintained wiki copies
enter the self-host graph.

| Former path | Maintained wiki page | Purpose |
| --- | --- | --- |
| `docs/progress-pathing.md` | [progress-pathing](guides/progress-pathing.md) | Operating guide / behavior reference |
| `docs/review-workflows.md` | [review-workflows](guides/review-workflows.md) | Operating guide / behavior reference |
| `docs/context/prds-and-living-product-specs.md` | [prds-and-living-product-specs](concepts/prds-and-living-product-specs.md) | Design concept |
| `docs/context/story-sizing-and-portfolio-selection.md` | [story-sizing-and-portfolio-selection](concepts/story-sizing-and-portfolio-selection.md) | Design concept |
| `docs/superpowers/specs/2026-08-12-active-recent-keyboard-navigation.md` | [active-recent-keyboard-navigation](guides/active-recent-keyboard-navigation.md) | Operating guide / behavior reference |
| `docs/superpowers/specs/2026-08-12-configured-serve-port.md` | [configured-serve-port](guides/configured-serve-port.md) | Operating guide / behavior reference |
| `docs/superpowers/specs/2026-08-06-vizzer-portable-spec-views-design.md` | [2026-08-06-portable-work-graph-design](history/2026-08-06-portable-work-graph-design.md) | Historical record |
| `docs/superpowers/specs/codex-sequence-2026-08-08-change-manifest.md` | [2026-08-08-change-manifest](history/2026-08-08-change-manifest.md) | Historical record |
| `docs/field-report-2026-08-07.md` | [2026-08-07-deployment-lessons](history/2026-08-07-deployment-lessons.md) | Historical record |

## Material deliberately retained in docs

| File | Reason |
| --- | --- |
| [Integration review](../docs/reviews/2026-09-05-upstream-integration.md) | Dated code-review findings and exact validation receipts |
| [Fix 1 evidence](../docs/fix-1-evidence.md) | Raw acceptance observations, not a maintained operating guide |
| [Fix 1 request](../docs/fix%201.md) | Original owner brief; preserve its wording and historical scope |
| [Implementation plan](../docs/superpowers/plans/2026-08-06-vizzer-implementation.md) | Old build checklist and code sketches; copying it into current guides would misrepresent today's architecture |
| [Docs index](../docs/README.md) | Entry point to evidence and forwarding destinations |

Product contracts and current Stories stay in `product-spec/`; their lifecycle
is independent of wiki references. `README.md` remains the installation and
configuration entry point, linked from the wiki rather than duplicated.
