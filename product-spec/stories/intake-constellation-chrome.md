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

## Tests

1. Every glyph slot resolves in the default set; a project override replaces it.
2. Leak guard: no SF Symbol data in the built distributable.
