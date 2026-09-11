# Product change register

This summarizes the integration baseline. Git retains the complete commit
history; downstream changes enter here only after comparison.

| Integrated change | Commit or PR | Contract / evidence |
| --- | --- | --- |
| Generic reviews and developer-flow workspace | `40e98e5`, `83c66ff` | [Review guide](../wiki/guides/review-workflows.md) |
| Reusable fork semantics and perspectives | `5df6826` | [Current behavior](current-behavior.md) |
| Lazy detail and persisted developer queries | `091a2fc`, `736815f` | [Current behavior](current-behavior.md) |
| Route integrity and hosted startup repairs | [PR #3](https://github.com/rydersd/vizzer/pull/3), `46d4bde` | [Current behavior](current-behavior.md) |
| Contextual developer-flow edge labels | `29d54a0` | [Current behavior](current-behavior.md) |
| Progress pathing, owner Markdown editing and portability repairs | [PR #4](https://github.com/rydersd/vizzer/pull/4), `1d9e4e4` | [Completed Story](stories/progress-pathing-upstream-integration.md), [review](../docs/reviews/2026-09-05-upstream-integration.md) |
| Self-host product contract, documentation map, recommendations and narrow-panel filter repair | This documentation/setup change | [Setup Story](stories/self-host-documentation.md) |

| Stable local address and login startup | Local LaunchAgent plus tracked source launcher | [Startup Story](stories/stable-local-startup.md) |

| Discoverable project landing page and document reader | This repair | [Story](stories/project-landing-page.md) |

| Wiki consolidation: nine guides, concepts and historical records | Documentation migration | [Story](stories/wiki-documentation-migration.md) |
| Bounded adversarial test-review packets, durable review requests and constellation test-state presentation | This change | [Guide](../wiki/guides/adversarial-test-design.md) |
| Rolling three-day Claude/Codex constellation trails and filterable public work logs | This change | [Completed Story](stories/session-history-upstream-integration.md) |

## Next work

1. [Inventory concrete downstream changes](stories/cross-project-change-intake.md) against this baseline using exact origin commits.
2. [Improve the empty dashboard explanation](stories/dashboard-empty-state-guidance.md) so existing work does not look like a broken install.

For each import record origin repository/commit, upstream comparison, generic
behavior, acceptance evidence and integration PR. Update the current behavior
contract in the same change. A historical proposal or passing fork test alone
is not an upstream integration receipt.
