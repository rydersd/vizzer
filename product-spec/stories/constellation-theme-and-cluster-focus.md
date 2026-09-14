# Constellation theme and cluster focus

> Status: building
> Deps: []
> Release: R1
> Tags: constellation, accessibility, appearance

## Owner intent

Cluster navigation should emphasize its members and subdue surrounding clusters.
Improve readability against an indigo-dominant gradient ending in a narrow magenta
edge. Light mode uses pale indigo/cyan, blue-gray and a narrow pink edge. Provide
sun, moon and computer controls for light, dark and system appearance.

## Contract

- Explicit lifecycle, role, release and area filters retain their meaning.
- Hierarchy focus recenters the camera; other eligible nodes remain subdued context.
- Theme preference persists locally; system mode responds to OS appearance changes.
- Essential canvas glyph outlines meet at least 3:1 against the gradient; normal
  and focused glyphs target 4.5:1 and 7:1. Dimming reduces fills/halos while
  retaining readable outlines. Labels and enabled controls target AA text contrast.
- Shape and pressed/focus state supplement color.

This is a contrast improvement, not a claim of complete WCAG conformance before
keyboard, assistive technology and all interactive states are audited.

## Validation — 2026-09-13

62 focused renderer, appearance and trail tests passed; two physical-browser
selectors were excluded. The CLI golden/render check passed separately. Tests
sample text palettes across both gradients, check control borders, exercise
low-contrast tag correction, theme persistence and hierarchy-focus context.
Manual local-browser checks exercised light/dark switching and reload persistence.
Vizzer's own dashboard at port 8480 runs this local candidate; IllTool's separate
installation has not been updated. Full application AA conformance remains
unverified; these checks establish the documented contrast scope only.

## Owner appearance refinements — 2026-09-13

Use 20px accordion chevrons rotating about a fixed center, and thicker 2.5px
essential node outlines (3px for focused cluster members). Sidebar text uses
12/14/16 CSS pixels; the prior point units made even the smallest choice too large.
Light-mode progress uses bright orange on a dark-blue track, independently of
semantic text colors so orange does not weaken text contrast.

### Accordion follow-up — 2026-09-13

Owner found the earlier arrows still too small. Chevron geometry now fills a 28px
box (about 20px wide and 25px tall), with a fixed rotation center. Child rows use
34px inset; nested structure groups gain 24px additional indentation. An F chip
after names identifies explicit foundation groups/ancestry or groups containing
authored foundation/foundational-tagged work; dependency alone is not classification.

### Final owner sizing — 2026-09-13

The 28px treatment was too large. Accordion chevrons now have a 16px visible
bounding box in both orientations, retaining fixed-center rotation and the
separate, larger clickable summary row. This supersedes the prior geometry.

### Toolbar sizing — 2026-09-13

Text-size and theme controls share the Views control’s 24px outer height. Theme
glyphs use a 14px box; text-size previews remain compact without changing the
selected reading size.

### Owner correction — 2026-09-13, chevron weight

Replace the heavy filled accordion arrows with a shared 16px chevron using a
2px rounded stroke. Keep the existing centered quarter-turn on expand across
capability, hierarchy/plans and story accordions. This supersedes the filled
polygon treatment, while preserving the requested 16px visual size.
