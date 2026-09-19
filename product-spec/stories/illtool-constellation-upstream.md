# IllTool constellation and flow-metrics intake

> Status: building
> Deps: []
> Tags: upstream, constellation, velocity

## Origin and comparison

Owner authorized review, abstraction, PR and merge on 2026-09-19. Upstream base
is 2ba0172. Source is rydersd/illtool-standalone, engine changes after f8c4f2b66
through b6a67bb80776ce246c9845f067c872deead975ff. Earlier capability planning,
appearance and session-history imports are already upstream and are not recopied.

Concrete missing changes: hierarchy details/foundation counts (13e8030a6),
graph reload resilience (49d5d11f7, d03af167d), velocity exports/dashboard/tab
(48f5791ce, 8dc9d2d75, 669810903), epic layout and capability regions/labels
(669810903, 59c560dd8, b6a67bb80). Engine paths map from
vizzer/engine/vizzer/ to src/vizzer/. No IllTool ledger, generated graph,
owner record or machine telemetry is imported.

## Acceptance

- Hierarchy drawers expose authored source/plans and count unfinished delivery
  members once, with optional project-owned foundation tier mapping.
- Constellation layout is deterministic across synthetic project hierarchies;
  capability hulls retain their members, names avoid glyphs/docks, background
  focus scenery does not intercept pointer actions, and undone circles remain single.
- Velocity derives counts from persisted lifecycle, merge/build/spend evidence;
  absent spend is not zero, project source roots/timezone are configurable,
  and exported/dashboard/tab values agree. No private log is bundled.
- Torn graph replacement can preserve read-only serving, but invalid current
  graph content must not authorize writes or make check/render falsely succeed.
- Portable Python 3.9–3.13 tests and distributable packaging pass; independent
  adversarial review and hosted CI precede merge. Local tests are not owner UX approval.

## Evidence

See wiki/mortems/illtool-upstream-2026-09-19/ and
thoughts/ledgers/illtool-upstream-2026-09-19.md. Integration tuple pending.
