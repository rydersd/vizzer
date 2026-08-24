# Adversarial review — review service and owner UI

> Date: 2026-08-23
> Scope: the opt-in review service, adapter registry, served routes, owner UI, and shared reading
> controls added after the first contract review.

## Findings fixed before completion audit

### High — changed evidence retained an unqualified green presentation

The run ledger correctly preserved the agent's historical claim, but `GET /api/reviews` did not
recheck current evidence bytes. A removed or replaced screenshot therefore left the card looking
green until its image request failed. The state projection now performs bounded current-byte
verification, marks changed/unavailable evidence explicitly, omits its URL, and rechecks again at
delivery. Aggregate file/byte budgets prevent the availability pass from becoming an I/O denial of
service; evidence beyond the display budget is labeled for check-on-open.

### High — a legitimate plan revision permanently blocked future runs

The first service draft kept one ledger per plan id and revalidated every historical event against
the latest plan fingerprint. Updating a source fingerprint or DoD would preserve history but make
the ledger impossible to append. Ledgers now rotate by full normalized plan fingerprint. A revised
plan begins a fresh revision-0 acceptance epoch while the old epoch remains immutable on disk.

### Medium — owner validation could precede the agent handoff

The initial page rendered an owner form even for a row with no agent run. The form is now gated on
an existing agent event. An owner verdict is also considered current only when its ledger revision
is newer than the latest agent run; a newer agent run returns the row to `awaiting owner`.

### Medium — an invalid sibling plan coupled unrelated mutations

Loading one target plan parsed every sibling first, so an unrelated malformed JSON file blocked a
valid plan's agent or owner append. Plan filenames now equal their safe plan ids, target mutations
load only that plan, and the read surface isolates invalid siblings as explicit warnings.

### Medium — evidence could be embedded cross-origin

Evidence GETs were protected from script reads by browser origin policy, but lacked an explicit
resource policy. Responses now send `Cross-Origin-Resource-Policy: same-origin` in addition to
`nosniff`, sandbox CSP, opaque id routing, and fresh byte verification.

### Medium — crash marker was mistaken for a live writer

Exclusive marker creation made a process crash a permanent lock. Unix now uses advisory file locks;
the marker is not authority and an orphaned marker does not block the next CAS append. The process
lock remains the portable fallback boundary.

### Medium — stale review sources were absent from `vizzer check`

Writes failed closed, but CI could report the project current while enabled review plans cited stale
source bytes. `vizzer check` now validates all enabled plan/source/adapter contracts.

### Low — nonpassing verdicts could contradict every step

An authored event could claim `blocked`, `skipped`, or `fail` while all steps said `pass`. The
contract now requires at least one step with the overall nonpassing outcome. The owner UI derives
the verdict from step outcomes and satisfies the same invariant.

### Low — the hidden gesture hint still painted over non-constellation views

Live browser capture showed the fixed-position hint over Reviews because the authored flex display
overrode the user-agent hidden rule. An explicit `#hint[hidden]{display:none}` fixed it.

### High — source fingerprinting did not prove the claimed DoD was applicable

A valid source fingerprint plus a verbatim substring check still allowed a plan to lift an easier
sentence from a story introduction and call it the DoD. Markdown review rows now require a
recognized authored Definition of Done or acceptance-test section, and every claimed criterion must
occur inside that section. A negative test puts the claim elsewhere in the same correctly hashed
file and proves rejection.

### Medium — screenshot thumbnails defeated the review itself

The first owner surface placed agent and owner runs side by side and constrained evidence to a tiny
fixed box. That proved an image existed while making its text and layout practically unreviewable.
Runs now stack at full content width; screenshots keep their natural aspect ratio, grow to the
available width, retain a bounded viewport height, and link to their actual-size bytes. Browser
measurement proved a 1280×720 source at 918×516 inline. The misleading old capture was removed from
the durable materials.

### Medium — copied views looked durable on an ephemeral server origin

Named views use browser storage and shared views use URLs, both scoped to the current origin. With
the default ephemeral `server.port = 0`, a restart changes that origin. Generated data now declares
whether the configured origin is restart-stable, and Save/Share explicitly tells the user to set a
nonzero port when it is not.

## Residual uncertainty

- Host adapters deliberately remain outside Vizzer core. The committed web and local fixtures prove
  the interface and trusted-operation mapping, but production browser/native harnesses still need
  project-owned implementations.
- Owner identity is a local `project-owner` label backed by loopback possession, same-origin checks,
  CSRF, and CAS—not cryptographic multi-user authentication. Binding beyond loopback would require a
  different trust model.
- Historical plan-fingerprint ledgers are preserved but the first UI shows only the current epoch and
  latest agent/owner events. A history browser is follow-up UX, not missing durability.
- Review sources and evidence use descriptor-relative `openat` traversal with `O_NOFOLLOW` on every
  component where the platform supports it. The remaining hostile-swap surface is the append-only
  storage directory itself; treating a project-local attacker as hostile would require a broader
  storage backend and threat model.

No unresolved high-severity issue remained after the final attack pass. The residuals are bounded
architectural extensions rather than contradictions in the shipped local workflow.
