/goal Make IllTool’s vendored Vizzer a reliable, responsive, bidirectional decision console, fixing the interaction architecture rather than individual screenshots.

Currently when looking at the sidebar, and then selecting an answer the sidebar blanks out, all I can do is close it. Also, when looking at the constellation view, and filtering to stories with questions... or trying to just click a story with questions... I can’t open the story, the cursor ignores the node. If I click in the unfiltered view, it selects another node in close proximity, seems like there is also an offset happening to the mouse click, when hovering over a node it seems like a nearby node does the hover animation.

  Required outcomes:

  1. Story selection is geometrically correct in every Constellation mode, viewport size, zoom level, and filter state. Clicking a visible question/story node must select that exact node—never a hidden or nearby node. Hovering selectable nodes uses a pointer cursor; orbit/pan begins only
  after an intentional drag threshold. Pulses and decorative effects live on non-interactive background layers.

  2. Dashboard/card views are fully interactive and scrollable. Cards open the same persistent story dossier used by Constellation. No toolbar or invisible layer may intercept card, wheel, or pointer input. Responsive layouts must not clip the header or require accidental horizontal
  scrolling.

  3. Question answering is durable and unsurprising. Selecting an option must preserve the drawer, draft, scroll position, active filters, camera, and selected story. For multiple questions, show per-question answered state and one “Provide answers” CTA after the queue. Do not close or
  reset the view until the user explicitly closes it. Freeform alternatives remain supported.

  4. Accepted answers must be persisted in the append-only decision ledger, linked to the exact question fingerprint and Story, and surfaced as LLM-findable Story evolution/rationale. Clearly distinguish “answered” from “applied to the Story”; never imply the normative Story changed until
  the application event succeeds.

  5. Failed submissions must preserve all UI state and show the actual refresh/write error with a recoverable retry path. Stale server/engine versions must be prominently detected before submission. Show the running Vizzer version in persistent header chrome.

  6. Make the responsive header intentional: navigation on the first row; shipment, bug-gap, and answer-required counts on the second. Filtered counts must reflect the visible version/status slice. Status/version chips share consistent exclusive-filter behavior, including press-and-hold
  isolation. Improve status differentiation: Done beige with a distinct completed glyph, Blocked with an X, and Active/Ready with clearly different colors.

  7. Keep the implementation modular. Fix authoritative upstream project_vizzer sources first, add focused modules when responsibilities are mixed, run its full tests, vendor the exact engine into IllTool, prove upstream/vendor parity, refresh IllTool’s generated views, and run full `vizzer
  check`. Do not hand-patch generated HTML.

  Acceptance evidence:

  - Executable rendered-JavaScript tests for exact hit selection, filtered/hidden-node exclusion, drag threshold, pointer cursor, drawer persistence, option/freeform drafts, multi-question submission, failed-submit recovery, and responsive scrolling.
  - Browser smoke against the real `vizzer serve` URL at wide and contracted widths, including Dashboard and Constellation.
  - Upstream full suite green.
  - Vendored engine byte-parity verified.
  - IllTool refresh/check green.
  - Record before/after evidence and the strongest mutation or counterexample for each repaired interaction.

  Do not close the goal merely because source tests pass. Close only after the real served IllTool view demonstrates the interactions above.

  That gives the session an outcome, architectural boundaries, and kill conditions—not merely a shopping list of symptoms.