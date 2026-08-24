# Responsive dossier and low-detail review — 2026-08-24

## Owner contract

- Breadcrumbs collapse instead of clipping the title bar.
- Capability and epic/cluster frames open the same right-side detail surface as leaf stories.
- Low-detail cards become Vizzer-style dots with hover and keyboard-focus summaries.
- Story icons are deterministic best-fit SF Symbols; status remains an independent channel.

## Adversarial findings resolved

1. The first selectable-frame build failed at runtime because the selected identity was not passed
   through the layout flattener. Source assertions had stayed green; live browser execution exposed
   `ReferenceError: selectedId is not defined`. The call boundary is now explicit and guarded.
2. Hiding breadcrumb text was not enough: a long saved-view status still made the 1280-pixel title
   bar scroll to 1349 pixels. The status owns a bounded ellipsis region and the measured title bar is
   now 1280/1280.
3. The first semantic classifier mapped most perspective stories to `sparkles`. That produced one
   icon with ten titles. The classifier now prioritizes the story action—grouping, grid/view,
   detection, command, prediction, provider, drawing, storage, test, and security. The focused
   ten-story epic renders six distinct verified SF Symbol outlines.
4. The old glyph LOD was a full card box with `border-radius: 50%`, producing large empty ovals.
   Glyph and overview LOD now render 24- and 12-pixel status dots. Focus on a dot exposed its title,
   kind, status, and summary and opened the same story dossier.
5. Notes originally floated over the graph while dossiers consumed a real column. Both now use one
   mutually exclusive inspector lane. Opening Notes closes the dossier; selecting a graph object
   closes Notes. At phone widths the inspector replaces the canvas in the content row instead of
   covering it.
6. Dot summaries originally always opened to the right, which failed beside the inspector and
   React Flow chrome. They now live in a viewport layer that selects right, left, below, or above,
   clamps to the canvas, and treats controls, the minimap, stats, and layout notices as obstacles.
7. Relationship labels no longer blindly use the path midpoint. Candidate positions are scored
   against card rectangles, group headers, and already placed labels before rendering.
8. The adversarial narrow-width pass found that a fixed 50-pixel title row could avoid overlap only
   by clipping or hiding controls. Below 820 pixels the bar now wraps into a growing breadcrumb row
   and a horizontally scrollable action row; the filter and content rows move down with it.
9. The old `Pan` button implied that navigation was a mutually exclusive tool. It is gone. React
   Flow now owns drag-pan, two-finger scroll-pan, pinch-zoom, and scroll suppression by default;
   Note and Sketch are the only authoring modes. Their temporary capture surface installs a
   non-passive wheel handler so trackpad navigation still targets the graph rather than the browser.
10. Notes and strokes now use a 100-step undo/redo history. New edits clear the redo branch, toolbar
    state reflects availability, and Command/Control-Z plus Shift-Command/Control-Z work whenever a
    native text editor does not own the shortcut.
11. Canvas markup can now be hidden without mutating the saved annotations. Visibility is part of
    the normalized saved-view document (legacy documents default visible). SVG export has a separate
    Markup checkbox, omits both note and stroke geometry when unchecked, and records
    `annotationsIncluded: false` plus an annotation count of zero in metadata.

## Browser receipt

Served IllTool review at 1280 pixels:

- title bar client/scroll width: `1280 / 1280`;
- collapsed breadcrumb menu: in viewport, with `Overview` and the capability ancestor;
- capability dossier: `27 objects`, status composition present;
- epic dossier: `9 objects`, kind announced as `epic group`;
- glyph LOD: `24px × 24px`, focus summary visible, story dossier open;
- semantic icon variety: `6` distinct paths across `10` cards.
- object dossier and Notes inspector are mutually exclusive and each owns the same `390px` lane;
- right-edge preview stayed within the `890px` canvas and intersected dossier, minimap, and stats by
  `0px²`;
- `10` visible relationship labels intersected `0` cards and `0` other labels.
- live note create → undo → redo changed canvas note counts `0 → 1 → 0 → 1`; the Pan control count
  is `0`, and Note returned to baseline navigation after placement.
- live hide → show changed mounted canvas-note counts `1 → 0 → 1` without changing `Notes (1)`;
  unchecked export reported `without notes & sketches`.

The older IllTool process still lacks the candidate saved-view endpoint, so its existing header API
error remains an integration-version issue rather than a responsive-layout result.

## Verification

- Focused developer graph/flow/query suite: **40 passed**.
- Focused collision/layout/navigation/history suite: **27 passed**.
- Focused visibility/export/storage/HTTP suite: **37 passed**.
- Complete upstream suite: **512 passed, 2 skipped**.
- Source and wheel/sdist package builds: **passed**.
