# Adversarial review — generic review-contract foundation

> Date: 2026-08-23
> Candidate: uncommitted `project_vizzer` review-contract slice before publication
> Method: assumption, evidence, architecture, validation, and change-risk lenses from the
> `adversarial-review` skill.

## Findings

### High — passing events trusted evidence metadata without opening the evidence

`parse_run_event` required a path, byte count, and digest, but the original `append_run` path only
validated their shape. A caller could append a passing agent run for nonexistent or substituted
bytes.

**Disposition:** fixed. `append_run` now requires `project_root`, verifies every source, resolves each
evidence requirement's kind, and validates the contained non-symlinked file, byte count, digest,
media structure, and dimensions before acquiring the mutation lock. A negative test replaces the
claimed PNG with same-sized junk and requires rejection.

### High — source fingerprints did not prove DoD provenance

A plan could faithfully fingerprint a source file while inventing an easier Definition of Done not
present in that file. The freshness claim would be true; the derivation claim would be false.

**Disposition:** fixed. Source verification now requires every DoD entry verbatim in the UTF-8
source bytes. A negative fixture fingerprints a real source containing a different contract and
requires rejection.

### High — compressed-image validation lacked a general decoded-pixel budget

PNG validation bounded decoded scanline bytes, but JPEG/WebP evidence could declare extremely large
dimensions inside a small valid container. Serving it later would hand a decode bomb to the browser.

**Disposition:** fixed at the evidence boundary. Screenshots above 32 MiPixels are rejected for all
accepted media types. A valid small WebP container declaring 16,384 × 16,384 is the negative control.

### Medium — ledger growth was unbounded

The fork caps its response ledger; the first upstream draft did not. A valid sequence could grow
until every CAS append became a memory/disk problem.

**Disposition:** fixed. Ledgers cap at 20,000 events and 32 MiB, checked both before parsing and
before atomic publication.

### Medium — an interrupted writer can leave the exclusive lock behind

The create-exclusive lock fails closed, but a process death between lock creation and cleanup leaves
manual recovery. Automatically expiring a lock by age is unsafe because a slow live writer can be
mistaken for a dead one.

**Disposition:** residual, not hidden. The initial service integration must record lock-owner
process/start metadata and offer an explicit inspected recovery command; it must not silently steal
an aged lock.

## Result

No unresolved merge blocker remains in this foundation slice. Residual uncertainty is concentrated
in the not-yet-built adapter/service layer: safe stale-lock recovery, origin policy for browser/HTTP
adapters, and owner-session authentication. Those capabilities are not claimed by this slice.
