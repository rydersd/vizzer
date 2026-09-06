# Architecture and documentation ownership

Vizzer reads configured sources through adapters, normalizes items/groups and
relations, reconciles authority, applies enabled overlays/assessments and
renders views. Source Markdown and durable overlays own state; generated graph
and HTML are projections.

| Location | Responsibility |
| --- | --- |
| `src/vizzer/` | Authoritative Python engine and bundled rendering assets |
| `product-spec/` | Current contract, change register and delivery Stories |
| `wiki/` | Operating guides, concepts, design history, historical goals and supporting material |
| `docs/` | Raw review evidence, historical execution plans and compatibility forwarding links |
| `tests/` | Verification harnesses; fixtures are not this project's backlog |
| `vizzer/vizzer.toml` | Explicit source map and stable local port |
| `vizzer/engine/__main__.py` | Source launcher, not a second engine |
| `vizzer/views/`, `.vizzer/` | Ignored generated views, caches and runtime state |

## Upstream workflow

Capture origin commit and expected generic behavior in a product Story. Compare
with upstream, record missing/present/partial status, review the diff and retain
verification evidence. After integration, link PR/commit from the Story/change
register and update the current product contract. Refresh the graph; restart
when engine or configuration changes.

Historical goals are context, not a second progress counter. The
[intake Story](../product-spec/stories/cross-project-change-intake.md) defines
provenance for future imports.
