# Adversarial review — saved Developer Flow views — 2026-08-23

> Scope: named views, notes, freehand annotations, sharing/export, the 100k cold index, and the
> capture/packaging residuals inherited from the upstream publication gate.

## Findings attacked and fixed

1. **Critical — a shared saved-view URL lost its authority before load.** The generic URL-state
   effect removed `saved=<id>` before the view-store request completed. A real copied-link browser
   test reopened an empty base view despite a correct persisted document. The saved id now has
   explicit state, survives normalization, and is cleared with a visible error only when the store
   proves it unavailable.
2. **High — sharing after edits could publish stale content.** An active saved view could be edited
   and shared without resaving; the link still referenced its older persisted revision. The UI now
   compares the complete active name/view/notes/annotation payload and refuses sharing until the
   latest changes are saved. A browser attack changed the note without saving and observed the
   explicit guard.
3. **High — small served graphs selected the wrong persistence authority.** Delivery mode can be
   `embedded` for a small graph even though the page is served. The first implementation treated
   that as static and wrote only browser storage. Persistence authority is now determined by the
   HTTP(S) origin; graph-query delivery remains an independent choice.
4. **Medium — exported annotation text could be clipped or overflow on long tokens.** Note wrapping
   had an eight-line ceiling and did not split long tokens. SVG note layout now wraps all bounded
   text, expands its bounds, escapes active markup, and carries annotation-specific color styling.
5. **Medium — screenshot semantics/redaction were implicit.** Historical ledgers remain readable,
   but new screenshot appends require a semantic caption and capture adapter/time/redaction
   attestation. The served projection exposes that provenance. This is auditable host testimony,
   not magical pixel truth.
6. **Medium — the 100k index repeated whole-graph validation and allocated a complete canonical
   byte copy.** Trusted internal adapter consumers now skip only the already-completed validation;
   public/adaptor construction remains fail-closed. Record-bounded hashing preserved the exact
   fingerprint while lowering measured cold-path wall/RSS from 8.09s/747MB to 6.28s/535MB.
7. **Low/time-bounded — packaging used setuptools' deprecated license table.** The build backend
   floor is now setuptools 77 and the project uses the SPDX `MIT` expression. Wheel and sdist build
   without the deprecation warning.

## Attacks that passed

- Project-relative containment and symlink rejection for the saved-view authority.
- Exact-field validation, finite coordinate/width bounds, per-stroke and aggregate point limits,
  view/annotation count limits, 4 MiB request/store limits, duplicate-id rejection, and atomic CAS.
- Same-origin/CSRF rejection and stale-revision `409` behavior through the real loopback HTTP path.
- Saved-link restore after navigation; note/stroke flow-coordinate anchoring through zoom; empty
  browser error/warning log.
- Annotation markup escaping in SVG, including a literal `<script>` attack.
- Full Python suite, frontend production build/audit, and Python wheel/sdist build.

## Residuals retained, not cosmetically renamed

- The service is deliberately loopback-only. Shared links work for clients that can reach the same
  served project origin; remote/multi-user sharing needs authenticated project identity and is not
  smuggled in as an unprotected bind flag.
- 535 MB for the complete 100k in-memory index is still too high for an enterprise-startup claim.
  Browser responses are bounded, but a persisted/incremental server index remains G-002's gate.
- Saved documents use revision conflict detection, not real-time collaborative merging. Conflicting
  writers fail visibly and must reload; automatic note/stroke merge needs its own product contract.
- Capture attestations make semantic/redaction claims inspectable. A malicious or mistaken adapter
  can still lie, so owner repetition remains the acceptance boundary.
