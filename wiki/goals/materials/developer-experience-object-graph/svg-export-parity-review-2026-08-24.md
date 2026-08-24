# SVG export presentation parity review — 2026-08-24

## Finding

The initial SVG export redrew Developer Flow with an independent, reduced card template. It emitted
titles as one SVG text line, clamped summaries to two lines, and omitted the live kind-icon box and
glyph. Browser CSS wrapping does not apply to SVG `text`, so the apparently convenient shortcut was
also the defect: long story names crossed card boundaries and exported diagrams lost their visual
object vocabulary.

## Remediation

- `vizzer_sf_symbols.mjs` carries the same generated SF Symbol outline catalog and lifecycle/group
  assignment as Vizzer, while `layout_contract.mjs` owns the glyph-aware line presentation used for
  both layout metrics and export. Object kind remains visible as text instead of being confused with
  lifecycle.
- Group frames, object cards, summaries, failure messages, annotations, and expanded details emit
  explicit SVG text lines. Expanded detail height is calculated because a downloaded SVG cannot
  inherit the live card's scrollbar.
- Export preserves level-of-detail behavior and renders the same vector lifecycle mark, status
  treatment, group aggregate, and failure symbol as the live card rather than substituting a
  Unicode glyph or generic box.

## Adversarial checks

- A 40-character all-`W` token was used to attack average-character-width assumptions.
- Long group, object, summary, failure, detail-key, and detail-value strings were rendered.
- A real browser geometry pass compared every card text rectangle to its object rectangle and every
  SVG element to the exported viewBox.
- Compact and glyph levels were checked independently so parity did not accidentally turn into
  “always export the most detailed card.”

## Residual risk

Line breaking is deterministic and glyph-aware, but it remains a font-independent estimate so the
SVG stays portable. A consumer substituting an unusually wide system font could still change text
metrics. The export deliberately leaves conservative horizontal space, and browser geometry tests
cover wide Latin tokens. If custom font embedding is added later, its exact metrics should replace
the estimate rather than creating another wrapping path.
