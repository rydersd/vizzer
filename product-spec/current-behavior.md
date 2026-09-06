# Current product behavior

## Purpose and users

Vizzer gives project owners and collaborating coding agents one navigable view
of delivery work, dependencies, decisions, evidence and supporting knowledge.
It installs into downstream repositories or runs directly from this checkout.
Views derive from repository sources and explicit overlays.

## Implemented upstream baseline

Baseline: merge `1d9e4e4`, inspected 2026-09-05. Links below identify code and
verification harnesses; they are not fresh test results. Configuration examples
live in the [main guide](../README.md).

| Capability | Current contract | Implementation | Verification pointer |
| --- | --- | --- | --- |
| Portable installation | Downstream installs receive a self-contained Python engine and assets; this checkout uses its source engine directly. | [Installer](../src/vizzer/install.py) | [Tests](../tests/test_install.py) |
| Source selection | Explicit adapters ingest spec trees, ledgers, docs, TODOs and conflicts. Roles distinguish delivery from references. | [Configuration](../src/vizzer/config.py) | [Tests](../tests/test_config.py) |
| Normalized graph | Stable items, groups and typed relations compose into one graph, with source precedence for competing fields. | [Model](../src/vizzer/model.py), [reconciliation](../src/vizzer/reconcile.py) | [Tests](../tests/test_model.py) |
| Living specifications | Story headers carry lifecycle/dependencies; revision and bug relations retain lineage. | [Adapter](../src/vizzer/adapters/spec_tree.py) | [Tests](../tests/test_spec_tree.py) |
| Work navigation | Constellation, roadmap, structure and searchable details share graph data and filters. Dossiers expose source. | [Views](../src/vizzer/render/constellation/views.js) | [Tests](../tests/test_render_constellation.py) |
| Dashboard | Assessment portfolio lanes or configured recommendations populate the dashboard under active filters. An unranked, unrecommended backlog alone does not. | [View](../src/vizzer/render/constellation/views.js) | [Tests](../tests/test_render_dashboard.py) |
| Priority | Opt-in target-scoped recommendations use dependencies and eligibility; scores do not change lifecycle. | [Priority](../src/vizzer/priority.py) | [Configuration tests](../tests/test_config.py) |
| Assessment | Size, uncertainty, impact and coordination evidence remain distinct; named checks do not prove execution. | [Assessment](../src/vizzer/assessment.py) | [Tests](../tests/test_assessment.py) |
| Planning | Accepted overlays adjust target authority without rewriting Story status or dependency edges. | [Planning](../src/vizzer/planning.py) | [Tests](../tests/test_planning_http.py) |
| Owner decisions | Model-neutral answer records retain decision identity, validation and inspectable history. | [Answers](../src/vizzer/question_answers.py), [journal](../src/vizzer/decision_journal.py) | [Tests](../tests/test_question_answers.py) |
| Discussions | Repo-local queues record requests and provider lanes; providers are not decision authority. | [Queue](../src/vizzer/discussion_queue.py) | [Tests](../tests/test_discussion_queue.py) |
| Concurrent work | Workstreams and activity expose ownership and freshness, not independent proof of completion. | [Workstreams](../src/vizzer/workstreams.py), [activity](../src/vizzer/activity.py) | [Tests](../tests/test_workstreams.py) |
| Reviews | Generic review contracts/adapters expose scoped review states and evidence. | [Service](../src/vizzer/review_service.py) | [Tests](../tests/test_review_service.py), [guide](../wiki/guides/review-workflows.md) |
| Developer graph | Optional 2D graph supports query-backed materialization, lazy detail and persisted views. | [Store](../src/vizzer/developer_store.py), [queries](../src/vizzer/developer_query.py) | [Store tests](../tests/test_developer_store.py), [query tests](../tests/test_developer_query.py) |
| Route integrity | Developer-flow routes remain attached across layout changes; malformed composed coordinates are rejected. | [Render sources](../src/vizzer/render) | [Tests](../tests/test_developer_flow.py) |
| Owner Markdown edits | Source-preserving Story edits use revision conflicts; newly refreshed Stories use current graph lookup. | [Edits](../src/vizzer/story_edits.py) | [HTTP tests](../tests/test_story_edits_http.py), [review](../docs/reviews/2026-09-05-upstream-integration.md) |
| Progress playback | Recordings use configured output paths. Playback, editor assets, tag colors and optional login-service operation have a dedicated guide. | [Evolution](../src/vizzer/evolution.py) | [Tests](../tests/test_evolution.py), [guide](../wiki/guides/progress-pathing.md) |
| Exports | Markdown views and machine-readable manifests regenerate from the graph rather than becoming independent authority. | [Renderers](../src/vizzer/render) | [Tests](../tests/test_render_ledger_manifest.py) |
| Local serving | Loopback serving supports configured ports and identity checks; restart after code/config changes. | [CLI](../src/vizzer/cli.py), [startup](../src/vizzer/startup.py) | [Tests](../tests/test_startup.py), [identity tests](../tests/test_render_identity.py) |
| Archiving | Archiving is opt-in and adapter-scoped. | [Guide](../README.md#archiving-opt-in-off-by-default) | [CLI tests](../tests/test_cli.py) |

## Self-hosting acceptance contract

- A clone can run documented refresh/check/serve commands without a second engine.
- Specs, wiki and docs appear as references; only current Stories count as delivery.
- Default dashboard offers a concrete next action.
- Source changes appear after refresh/reload; code/config changes require restart.
- Fixtures, generated output and historical ledger tasks do not inflate counts.
- Git contains authored sources/setup; generated views and runtime state stay ignored.

## Self-host usability repair — 2026-09-05

Filter groups now wrap without shrinking away, and routed content starts below
the measured header/search area. This makes References usable in the narrow
Codex panel. The source-map and this repair are captured in the
[setup Story](stories/self-host-documentation.md).

## Local availability — 2026-09-05

This Mac runs the source checkout at `http://127.0.0.1:8480/constellation.html#dashboard`
using a login LaunchAgent with refresh-before-serve and restart-on-exit. See the
[startup Story](stories/stable-local-startup.md) and [operating instructions](../vizzer/README.md).
This is local availability after login; it is not a public deployment.

## Project landing page

Configured `render.project_documents` references appear as persistent dashboard
shortcuts, alongside a filtered work register. Reference dossiers open the full
Markdown document. [Landing-page Story](stories/project-landing-page.md).

## Knowledge organization

The wiki owns maintained guides, design concepts and dated learning records.
Docs retains raw evidence and historical execution plans. Compatibility
forwarding pages are excluded from the graph. See the
[documentation map](../wiki/documentation-map.md).

## Limits and open work

Self-hosting does not automatically pull projects, watch repositories or prove
fork parity. [Intake](stories/cross-project-change-intake.md) must compare exact
origin commits with upstream. Historical wiki goals predate some integrations.
[Empty-state guidance](stories/dashboard-empty-state-guidance.md) is a proposed
product improvement; configuring recommendations fixes this installation's
empty dashboard but does not change the generic UI behavior.
