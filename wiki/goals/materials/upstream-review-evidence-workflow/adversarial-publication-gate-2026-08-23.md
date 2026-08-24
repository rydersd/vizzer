# Adversarial publication gate — upstream `main`

> Date: 2026-08-23
> Reviewed head: `ba468ef34da8666c91cb3d0f9525f6b67a8fda59`
> Previous upstream `main`: `8ae6462b9fa8022bd42e2105cfbfbc693f5e8058`
> Result: no merge blocker; upstream `main` fast-forwarded without force

## Findings

### High residual — the 100k safety ceiling is not a pleasant enterprise cold start

The existing adversarial corpus returned the correct bounded slice, but cold normalization and
indexing took 21.765 seconds and peaked near 1.0 GB RSS. That evidence directly falsifies an
“enterprise-performance-ready” claim. It does not block this publication because Developer Flow is
optional and off by default, the response remains bounded, and G-002 explicitly retains
persisted/incremental indexing and adapter aggregation as unfinished performance work. It would
become a release blocker if Vizzer advertised Salesforce-scale startup or enabled the add-on by
default before that work is measured.

### Medium residual — local owner identity is possession, not remote authentication

The review service's v1 owner boundary is loopback possession plus same-origin, CSRF, and revision
CAS checks. The tests reject remote Host headers, cross-origin requests, stale revisions, pre-agent
owner events, and wrong lineage. This is adequate for the documented local workflow, not a remote
multi-user deployment. Binding beyond loopback requires an authentication adapter and a new threat
model; changing only the listen address would be a security regression.

### Medium residual — screenshot meaning remains host-owned

Core validates containment, bytes, format, decoded dimensions, budgets, hashes, and immutable
delivery. It cannot infer that pixels depict the intended scenario or that a capture omitted
secrets. Production browser/native adapters still own semantic capture checks and redaction. The
contract says so explicitly, and screenshots remain evidence rather than automatic proof of DoD.

### Low residual — package license metadata has a dated deprecation warning

The fresh wheel/sdist build passed, but current setuptools warns that the TOML-table form of
`project.license` is deprecated for builds after 2027-02-18. Changing it safely may also require
raising the declared setuptools floor from 68 to a version that supports SPDX strings. Track that
as packaging maintenance before the cutoff; it is not a present artifact or install failure.

## Evidence that reduced uncertainty

- `origin/main` was an ancestor of the reviewed head; the nine-commit range contained no merge
  commits and `git diff --check` passed.
- The shipped `src/` tree and generic developer/review fixtures contained no IllTool, personal-path,
  Xcode, launchd, or Application Support vocabulary. A credential-pattern scan found no additions.
  IllTool names remain only in provenance/audit material that explains the migration boundary.
- The complete current suite passed: **491 tests in 64.59 seconds**.
- The optional frontend rebuilt from pinned dependencies; `npm audit --omit=dev` reported zero
  vulnerabilities. React Flow's visible attribution and the React, React DOM, React Flow, and ELK
  license texts ship with the bundle.
- Wheel and sdist builds passed. A fresh environment installed the wheel offline with no
  dependencies; runtime metadata declared no `Requires-Dist`, and optional assets/notices loaded.
- Two zipapp builds were byte-identical at SHA-256
  `6f542c912aaf1fc4fde2f64e127e42a7545bad855a5d11b77bfc90405da839df`.
- Source compilation and all local wiki links passed. The isolated worktree was clean before the
  guarded push.
- The non-forced push moved `main` from `8ae6462` to `ba468ef`; a subsequent fetch and independent
  `ls-remote` query both returned the reviewed head.

## Rollback boundary

Publication was a linear fast-forward, so the safe rollback is a normal revert of the published
commit range followed by the same build/test gate. Rewriting `main` is neither required nor
appropriate.
