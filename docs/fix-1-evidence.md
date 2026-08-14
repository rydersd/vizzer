# Fix 1 acceptance evidence

Date: 2026-08-11
Upstream engine: 0.8.30
IllTool target: `/Users/ryders/Developer/GitHub/illtool-standalone`

This report records executable evidence for `docs/fix 1.md`, including physical
browser input against the real served IllTool artifact rather than source-only
or synthetic-function evidence.

## Modularization audit

The concrete pre-extraction baseline is commit `fcdba77`; extraction commit
`6c0d99f` deleted the 679-line template and created the responsibility-based
modules. The extraction was not behavior-neutral: it also introduced decision,
assessment, routed-view, and question-interaction work (2,259 insertions and 690
deletions). Direct review found the composed script order sound, but found the
verified regression bundled into that change: the header expanded to three
interactive rows while canvas projection still treated the full viewport as
clickable. The source split was the crime scene, not the mechanism.

## Interaction counterexamples and repairs

| Interaction | Strongest before/mutation counterexample | After evidence |
| --- | --- | --- |
| Exact Constellation selection | Two visible centers were placed nine pixels apart. Clicking either glyph center had to select that exact Story. At the supported 0.45 minimum graph zoom, Story 42's centered X and Story 38's X arm were only 0.11 paint pixels apart; the old quarter-pixel “tie” chose front-depth Story 38 even at Story 42's exact center. A deliberately ambiguous animated ring also crossed a different Story's paint. The owner's 12:28 screenshots exposed a separate contract failure: the tooltip advertised `TextItem.sourceOnly…`, but a five-pixel press shift re-ranked the dense scene and opened a neighboring Story. | `test_constellation_exact_target_cards_and_lifecycle_hold_execute` proves centered question X, crossing-X center ownership, ordinary Story paint, hidden exclusion, decorative-ring pass-through, and advertised-tooltip authority through normal press jitter. The new counterexample fails against the old handler by selecting Story A after advertising B, then passes after the repair. Question glyphs rank materially closest stroke, then nearest owning center, then depth. The real-server matrix physically clicked 1,298 exact centers, 108 ring-over-Story counterexamples, and 17 real hover/press re-ranking pairs across 22 camera/filter/viewport/DPR/page-scale poses with zero failures. Animated rings are not input. |
| Atomic viewport geometry | After switching the live browser from 360×320 to 1280×800, `innerWidth` was current but the projection still used stale `W=360`. The target shifted by exactly `(1280−360)/2 = 460` horizontal pixels and `(800−320)/2 = 240` vertical pixels between coordinate capture and hover. | `project()` synchronizes canvas metrics when `W/H` diverge from the browser viewport. The executable resize mutation forces stale 360×320 metrics under a 913×577 viewport and proves both canvas layers plus projection update atomically. The real-URL smoke then hovers and selects the exact target after a contracted-to-wide transition. |
| Retina paint/hit parity | The DPR matrix originally changed emulated DPR after page load but did not rerun `size()`, so its claimed DPR-2 surface still had a DPR-1 backing store. Once corrected, the served 0.8.24 page exposed the owner's actual offset: at DPR 2 the canvas CSS rectangle and backing store were both 2560×1600 over a 1280×800 viewport; at DPR 1.5 they were 1920×1200 over 1280×800. Canvas paint therefore appeared at `DPR × P`, while hit testing still used `P`. | Canvas CSS now explicitly owns `100vw × 100vh`; only its backing store scales with DPR. The corrected 0.8.25 matrix proves DPR 2 has a 1280×800 CSS rectangle and 2560×1600 backing, while DPR 1.5 has a 1280×800 rectangle and 1920×1200 backing. The owner's actual Chrome at 125% zoom reports DPR 1.25, viewport 1537×903, backing 1921×1128, and fixed CSS rectangle 1536.8×903.2. The matrix now fails any canvas/viewport rectangle mismatch. |
| HTML-chrome occlusion | On the real question-only IllTool view, 13 of 52 painted question-story centers were beneath the header, chips, search/rail, or hint. `updatePointerState` identified the right Story, but `elementFromPoint` returned a chip or other HTML element, so the canvas never received `pointerdown`. | Projection and painting now share an explicit interaction viewport that excludes header, rail/search, and an open dossier; the hint is pointer-transparent. A real-server physical Chrome sweep clicks all 63 remaining advertised question centers with zero occlusions and zero selection failures. |
| Hidden-node exclusion and pointer affordance | A hidden node was projected at the same coordinates as a visible question node. This is the strongest collision case: any hit loop that ignores filter state selects an invisible target. | The executable DOM shim selects and hovers only the visible node and applies `hover-target`; hidden/filter/chrome-clipped projections are excluded by `p.on`. |
| Actionable question pulse | The screenshots `Screenshot 2026-08-11 at 8.16.21 AM.png` and `.30 AM.png` showed a magenta question treatment producing a neighboring Story tooltip. An attempted repair made the entire animated ring own input; that contradicted the acceptance rule that pulses are decorative and stole nearby Stories. | Rings/glow render on pointer-transparent `#bgcv`; the centered static X and Story glyph render on interactive `#cv`. The live smoke sampled 1,007 X-stroke points and physically clicked a ring directly over another Story, which correctly selected the painted Story. Pulse eligibility remains open question plus recommended-next, or open question plus blocked work on the same Story; the blocked branch is explicitly a heuristic because active-work records lack a causal question ID. |
| Drag threshold | A five-pixel pointer jitter is below the six-pixel orbit threshold, while a twenty-pixel gesture exceeds it. | The generated-JavaScript state test proves the five-pixel gesture opens the selected Story without moving the camera, the twenty-pixel gesture orbits without opening a dossier, and pointer cancel clears capture/drag state. |
| Decorative effects | Before this repair, edges, trails, pulses, nodes, and hit input shared `#cv`; non-interactivity depended on hit-test convention rather than ownership. A later semantic-ring target briefly reintroduced the same mistake in hit-test code. | `#bgcv` owns edges, trails, glows, echoes, and animated pulses with `pointer-events:none`; `#cv` owns selectable nodes and input. No ring hit geometry exists. The 108 physical ring-over-Story cases prove decoration passes through to actual Story paint. Both layers hide on routed views. |
| Rotation and post-answer hover | After answering two Stories, rotating could leave the pointer class and tooltip describing the pre-rotation target. Empty canvas could still show a pointer because the question-only filter globally applied `cursor:pointer`. | `updatePointerAt` now couples hit recomputation with tooltip/class presentation on every animation frame, wheel update, pointer move, and orbit release. The real smoke reconciles two answered Stories, checks 31 remaining question targets, then sends physical two-finger orbit, Command-pan, pinch-zoom, and drag-orbit input. Pan moves exactly −36/−24, pinch moves zoom 1.25→1.325, and every route retains active input with consistent hover/class/cursor; empty space truthfully shows `grab`. |
| Dashboard/card input and responsive scrolling | Contracted mutations use 360×320, 320×260, and 280×240 viewports, where Dashboard cards exceed the available panel height. A non-scrolling panel, canvas event shield, or max-content header overflow fails immediately. | The physical Chrome test wheels every real routed panel, proves document/header/title/menu containment at all three widths, verifies navigation/count/chip row ordering, proves both canvases are hidden, and physically clicks a wide Dashboard card to open the shared dossier. |
| Responsive header and filter semantics | The 360×320 mutation forces the header, meter, and filter chips to compete for height and width. Lifecycle and release holds are counterexamples to implementations that visually solo a chip but leave the filter map or ARIA state inconsistent. | Rendered JavaScript and the real served Chrome smoke physically hold Active and R1 for 760 ms; each leaves only its target enabled and synchronizes both sampled `aria-pressed` values. Filtered-count tests execute lifecycle/version slices across every interactive route. The real smoke proves navigation occupies row one, shipment/bug-gap/question counts row two, chips follow, and neither header nor page exceeds the viewport width. Done uses the shipped beige triangle, Blocked the explicit X, and Active/Ready retain distinct configured colors. |
| Drawer stays visible while selecting answers | On the owner's exact Chrome 125% tab, selecting `question-75-option-0` left 16,690 bytes of dossier DOM intact but made the panel appear blank. Direct inspection found `dossier.scrollTop=1079.2`; the drawer header and body were physically laid out near y=-957 and y=-840. `overflow:hidden` clips visually but still creates a programmatically scrollable ancestor, so radio focus scrolled the entire fixed drawer instead of only `#dbody`. The strengthened 0.8.10 smoke reproduced `outerScroll=1021`, `identityTop=-899` while all earlier “drawer open / DOM length” assertions passed. | The outer fixed shell now uses `overflow:clip`; `#dbody` remains the only scroll owner. The same real-server sequence selects five options plus a freeform alternative with `dossier.scrollTop=0`, drawer top 106, identity top 122, and body top 239.7 after every focus. Applying `overflow:clip` to the owner's already-broken live tab immediately restored the still-present drawer content, independently confirming the mechanism. |
| Drawer dismissal and metadata rhythm | The dossier could only be dismissed with its close button, and its two-column metadata grid used a three-pixel row gap that visually collapsed adjacent key/value pairs, especially when values wrapped. | Escape now calls the same `dismissDossier()` cleanup as the close button, while the search Escape handler defers when a dossier is open so one keypress does not also erase search. The real served smoke opens a Story, dispatches physical Escape, and proves the drawer closes, `aria-hidden` returns to `true`, and selection clears. Metadata uses a seven-pixel row gap and 1.35 line height. |
| Responsive, resizable Story drawer | The drawer was fixed at 320 px on desktop, abruptly switched to 100% at one breakpoint, and allowed long metadata tokens to force clipped content. A width adjustment implemented only in CSS would also leave canvas hit exclusion and routed-view layout using stale geometry. | One `--dossier-width` authority now drives the drawer and routed panel; canvas interaction bounds read the drawer's live rectangle. A visible separator supports physical pointer drag, Arrow keys, Shift+Arrow coarse steps, Home reset, and ARIA value reporting. The chosen desktop width persists for the browser session and survives a compact-width round trip. At 760 px and below the drawer is exactly viewport-wide and the handle disappears. Physical Chrome proves 461→557 px resizing on the real server, restored width 557, panel/drawer edge parity, 360 px full-width layout, and no horizontal body or page overflow. |
| Pinned drawer actions | The action footer was `sticky` inside the Story scroll body. A physical rectangle measurement found it 75.92 px above the drawer bottom, while its desktop flex row pushed readiness left and CTAs right like an unrelated toolbar. | The footer now has a dedicated non-scrolling flex slot outside `#dbody`: the rule and readiness/provider text come first, then Answer and Chat controls form a left-aligned row beneath. The real 0.8.30 browser reports footer `[724,706.8,1280,800]` and drawer `[723,106,1280,800]`, proving an exact bottom edge, actions below status, and matching left edges while Story content remains the sole scroll owner. |
| Failed answer visibility | The first browser failure returned `refresh exploded`. An early catch briefly wrote it, then queue synchronization overwrote it. A later real-server race was subtler: planning bootstrap rebuilt the dossier at 3533.9 ms while answer preflight was pending; the POST failed 20 ms later and wrote the error into the now-detached old footer, while the visible replacement showed `6 selected`. | Submission failure is durable frontend state. A rebuild binds the current footer to it; if an async catch discovers its queue was detached, it refreshes the current dossier before focusing retry. The physical fixture deliberately calls `refreshDossier()` after failure and still sees `refresh exploded`. The real smoke exercises the planning/submission race and retains the actual error, enabled retry, drawer, selection, exact submission-time scroll, route, filters, camera, option/freeform drafts, and two authority preflights. |
| Atomic multi-question submission and retry | One option plus one freeform answer are queued. The first POST is forced to fail, exercising the recovery path rather than a cosmetic disabled-button check. | One CTA submits one revision-zero payload with both question IDs and answer kinds. A physical retry sends the second request, reconciles two accepted decisions without reload, keeps the drawer/selection/scroll/filter/search/camera/drafts, removes the open questions, and shows two answered cards. |
| Successful Story reload | Replacing long question forms with compact accepted-answer cards while preserving the old scroll extent left the refreshed metadata above the viewport behind an inert spacer. The Story had been rebuilt, but the UI made it look absent. | Draft edits and failed submissions still preserve exact scroll and retry state. An accepted batch now rebuilds the complete open dossier from its top without the stale-height spacer. The latest real served smoke begins the successful retry at scroll 558, then observes scroll 0, visible `.kv` metadata, no spacer, and unchanged route/filter/camera/selection immediately and after 16, 32, 64, 128, and 256 ms. |
| Provider discussion queue | Targeting an existing Claude/Codex conversation would require provider session IDs Vizzer does not own, and would make a button imply delivery it could not prove. Restricting discussion to Stories with owner questions would also make ordinary Story review arbitrarily impossible. | Every Story dossier now has a `Chat` split action. The primary action chooses the latest relevant Codex/Claude activity or workstream session, with Codex as the explicit fallback; the overflow chooses either provider. A guarded CAS endpoint moves the Story to the top of exactly one provider lane, validates the current open-question set, refreshes atomically, and rolls back on failure. `vizzer/views/discussion-queue.md` gives both future harnesses a top-first LLM-readable handoff; both existing `AGENTS.md` and `CLAUDE.md` receive the managed startup instruction. Physical Chrome proves a no-question Story queues to its latest-touch Claude lane, while the real served IllTool smoke queues a six-question Story to Codex without writing production state and retains drawer, selection, filters, and camera. Queued remains distinct from discussed, answered, and applied. |
| Batch durability and rollback | The refresh-failure mutation forces `_refresh` to return 2 after a two-answer batch. | `test_question_batch_rolls_back_every_answer_when_refresh_fails` proves revision remains zero and no ledger survives. The success test proves one batch acceptance and two Story evolution events. |
| Answered versus applied | Treating answer acceptance as normative application would collapse two different events. | Decision-journal tests prove the owner-decision event and application event are explicit, separate, idempotent records. Rendered journal copy distinguishes recorded answers from applied Story changes. |
| Stale engine guard | The real IllTool server was deliberately left on 0.8.6 after installing 0.8.7. `/api/questions` returned HTTP 409 with `runningEngineVersion: 0.8.6` before any mutation. A later audit found that an already-open page could retain old JavaScript and an expired CSRF token after the server restarted; initial-load checks alone did not satisfy “before submission.” On 2026-08-11, the frontmost Chrome tab was independently found on cache-busted 0.8.14 while the server was already 0.8.22. | The managed service now returns engine 0.8.30. Every answer batch performs a read-only `/api/questions` preflight before its POST, compares page/server versions and exact question fingerprints, and refreshes revision plus CSRF authority on a same-version restart. Discussion queue writes independently preflight engine, question, fingerprint, CSRF, and queue revision authority. The executable stale-page mutation proves zero answer mutation POSTs and retains drawer, drafts, scroll, selection, and retry. Persistent header chrome remains visible. |

## Verification receipts

- Upstream full suite: `338 passed in 18.95s`.
- Current focused drawer visibility, geometry, CLI golden, and packaging battery:
  `8 passed in 2.99s`; HTTP batch/rollback/stale-guard and decision-journal tests
  are also included in the 338-test full-suite receipt.
- Source/vendor comparison, excluding only interpreter and Finder debris:
  exact at 0.8.30; `canvas.js` SHA-256 is
  `2af20bd040bf46c6101eea7311f2b742ac83a9033cf1249a88de09cd456d1128`
  in both trees; `questions.js` is
  `cc54a97f9ab807956fff0ef205f36deb903aea15addf2d6681384cc3d4f815cd`
  in both trees.
- `discussion_queue.py` is also byte-identical at SHA-256
  `2afdc6a26a3b6095bee83a56296bb42025fcc0187bb9c2c7ee6ab32f93446124`.
- `dossier.js` is byte-identical at SHA-256
  `20c81ad57ddaf30fe88cfc1d6988b57bfc396e534ce68c45878b6240735a7aaf`.
- IllTool refresh: 539 items, 97 groups, 0 conflicts, 0 warnings; nine views written.
- IllTool `vizzer check`: `check: up to date`.
- IllTool's real revisions 22 and 23 are append-only entries for
  `question:token-table-empty-mode-behavior` and
  `question:token-table-lock-authority`, each with its exact full SHA-256
  fingerprint. Their source Story contains separate evolution markers and says
  `accepted; normative story/test integration pending`; the generated decision
  journal links the Story and independently says normative application is
  pending. This proves the latest owner interactions are LLM-findable without
  pretending acceptance changed normative scope.
- Live IllTool endpoint: `http://127.0.0.1:8765/`, engine 0.8.30,
  ledger revision 34, 78 open questions, and 34 accepted decisions.
- Live served HTML contains `#bgcv`, `nodePaintRadius`,
  `questionGlyphPaintDistance`, `questionRingRadii`, `canvasInteractionBounds`,
  `updatePointerAt`, `data-scroll-preserver`, atomic viewport synchronization,
  `overflow:clip` drawer ownership, durable submission-error state,
  answer-authority preflight, explicit successful-update return-to-top, pinned provider split action, responsive resize separator, and persistent `v0.8.30`
  header chrome.
- The live response is byte-identical to IllTool's checked artifact; both have
  SHA-256 `ff32eb6617e8dc8027cc1aa68ff0f88b27579bd54507b9be3e27d8e19981e741`.
- The reproducible distributable is SHA-256
  `f42e5b2dda916f936e5270defc6e7b85d533495844e640c7accec6168debcd1a`.
- The repository has 47 readable implementation/resource files under
  `src/vizzer`; the local `dist/vizzer.pyz` contains every one with no missing
  source entry. CI now emits it under `dist/` rather than the source root. The
  remote latest Release is still stale v0.1.0 and must not be represented as
  0.8.30 until an explicit commit/push/release is authorized.

## Real served-IllTool browser smoke

The non-mutating Chrome smoke ran against the real
`http://127.0.0.1:8765/constellation.html?v=0.8.30-footer#dashboard` server on 0.8.30:

- Wide Dashboard card 346 opened the matching persistent dossier.
- The desktop drawer physically resized from 461 to 557 px, reported and
  persisted 557 through ARIA/session state, aligned the routed panel to the same
  edge, and restored 557 after the compact-width mutations.
- Contracted 360×320, 320×260, and 280×240 Dashboards remained page-width-safe,
  kept title and menus in the first header row without overlap, physically
  scrolled, and left both canvas layers absent from hit testing.
- The 360×320 Story drawer occupied exactly x=0…360, hid its desktop resize
  separator, and produced neither drawer-body nor document horizontal overflow.
- A 22-pose matrix physically clicked 1,306 exact Story centers across five
  viewport shapes, multiple camera rotations and zooms, time/delivery sizing,
  release/status/question/role/area/capability filters and combinations,
  graph zoom 0.45–3.4, DPR 1/1.5/2, and page scale 80%/100%/125%.
  Every click opened the exact Story.
- The same matrix found 17 real points where a five-pixel press shift changed
  the geometric winner after hover. Every press opened the Story named by the
  already-visible tooltip, rather than silently switching to the new winner.
- The same matrix physically clicked 108 animated-ring pixels that crossed a
  different Story's paint. Every click selected the actual painted Story,
  proving attention rings are pointer-transparent rather than giant ambiguous
  targets.
- The focused smoke sampled 1,007 points on centered question X strokes with
  zero ownership failures.
- The strongest old-halo counterexample was physically clicked on the real
  server: Story 14 opened its exact dossier while the 0.8.9 algorithm would
  have opened Story 134 (`DocumentPage.frame staleness`).
- Constellation story 42, with six open questions, was selected by physically
  clicking its centered glyph, followed by a three-pixel sub-threshold jitter.
- Five option selections and one freeform selection each retained the drawer,
  Story 42, all six forms, and roughly 17 KB of drawer DOM. Each also proved
  outer drawer scroll zero and both pinned identity/body physically onscreen.
- A forced failed POST retained the actual error, retry, drawer, selected Story,
  filters, camera, drafts, and exact pre-submit scroll position.
- A non-persisting fake success reconciled all six answers in place and retained
  drawer/camera/filter/draft state. A second three-question Story was then
  reconciled; all 31 remaining visible question targets still advertised and
  selected correctly. Two-finger orbit, Command-pan, pinch-zoom, and drag-orbit
  all recomputed hover presentation and returned `cursor:grab` on empty space.
  Only an explicit close cleared
  selection.

The smoke intercepts answer POSTs, so it exercises the real served IllTool UI
without writing owner choices into the production ledger. Actual HTTP batch
durability and rollback are covered separately against disposable real servers.

The user's actual Chrome tab was observed on v0.8.5 while the managed server was
already newer, then explicitly reloaded first to v0.8.8 and v0.8.9. After the
screenshot-shaped pulse-overlap regression was repaired, Chrome was opened to the
cache-busted v0.8.10 artifact. The blank drawer was then diagnosed in that
exact 125%-zoom tab, and Chrome was opened to v0.8.11 with the visible header
observed at v0.8.11. Rotation/post-answer hover presentation and truthful cursor
ownership landed in 0.8.16. Answer batches gained immediate pre-mutation
authority revalidation in 0.8.17. Minimum-zoom crossing-X ownership landed in
0.8.18; durable failure reconciliation across concurrent dossier rebuilds landed
in 0.8.21; transaction-local scroll restoration replaced the harmful deferred
callback in 0.8.22. The owner's contrary 12:28 repro correctly reopened the
interaction: the page advertised one Story and pointer-down re-ranked to another.
Tooltip authority through click jitter landed in 0.8.23, but the owner correctly
reported that the physical target was still offset. Query-gated receipts in
0.8.24 exposed the real CSS/backing mismatch; viewport-sized CSS canvases landed
in 0.8.25 and were opened in the owner's 125%-zoom tab. Escape dismissal and
metadata spacing landed in 0.8.26. Automated evidence is
green. Successful Story updates restore the complete dossier from its top in
0.8.27 while failures retain the exact draft and scroll position. Provider Story
discussion lanes and their Markdown session handoff landed in 0.8.28. The responsive,
session-persistent drawer and live-width canvas boundary landed in 0.8.29. The pinned,
vertically composed action footer landed in 0.8.30. Owner confirmation
in the real front tab remains the closure condition.

## 2026-08-14 overlapping question-X ownership follow-up (0.8.35)

The real IllTool graph exposed a counterexample that the synthetic center-click
coverage did not: a visible endpoint of Story 302's question X was stolen by
Story 511's overlapping X because the old ranking treated stroke misses within
0.05 px as equal and then preferred the nearer center. At the failing point,
the intended front-painted stroke miss was approximately `4e-14` px with a
6.095592 px center distance; the competing stroke miss was 0.014754 px with a
5.213973 px center distance. Center proximity was therefore overriding visible
paint ownership.

The 0.8.35 hit rule preserves a small deliberate center core, then ranks by
materially closest painted X stroke and actual front-most/later painter order.
The synthetic `paintedQuestionXEndpointTarget` regression keeps an underneath X
center closer to the pointer while requiring the visible front-painted endpoint
to retain hover and click ownership.

The non-mutating browser smoke against the real served IllTool 0.8.35 graph
passed: 40 semantic center cases and 40 physical center clicks had zero failures;
451 question-X samples had 17 legitimate paint occlusions and zero ownership
failures; 23 post-answer cases had zero failures. The decorative ring remained
pointer-transparent, 360x320, 320x260, and 280x240 routes passed, the drawer
resized from 461 to 557 px and persisted, six-answer failure/retry state held,
the discussion queue remained intercepted and non-mutating, and pan, pinch,
orbit, cursor, and explicit-close selection behavior all passed.
