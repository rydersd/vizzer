# Constellation chrome modules

> Status: specced
> Deps: [intake-constellation-polish](intake-constellation-polish.md)
> Release: R1
> Tags: upstream, constellation, licensing

## Origin

Pre-b6a67bb IllTool modules excluded in 2026-08 and now ruled in: appearance,
area_planning, chip_layout, panel_resize, view_tables, notices, symbols.

## Acceptance

- Modules reconcile with upstream equivalents (`preferences.js`,
  `chrome_layout.js`) instead of duplicating them.
- Glyphs: the SF Symbol outlines are Apple-licensed for Apple-platform apps and
  are not redistributed. Upstream ships the same glyph slots from a permissively
  licensed set, recorded in THIRD-PARTY-NOTICES; a project may supply its own
  glyph file.
- Owner ruling 2026-10-17: Lucide (ISC) is the default set; the owner will
  customize later.

## Named tests

- (planned) `tests/test_glyphs.py::test_every_glyph_slot_resolves_and_project_override_replaces_it`
- (planned) `tests/test_glyphs.py::test_no_sf_symbol_data_in_built_distributable`
