# PR #7 adversarial review

Reviewed head: `8cfacdde9e65cc54b64a4fbe53e439d344ca1e1a`
Base: `9186eac63ea52a09d0b96e7b514ba226779e1ec9`
Verdict: REPAIR before merge or downstream integration.

## P2 — Retry identity is lost when the planning panel is reopened

`src/vizzer/render/constellation/dossier.js:379–387`

The request ID and request text exist only in one openPlanningArea invocation,
while the draft survives in areaDrafts. If the server commits a message but its
response is lost, closing/reopening the area restores the draft but loses its
request ID. Retrying creates a new ID and appends the same question twice. This
also creates duplicate work for the desktop timer.

Reproduced by executing the production openPlanningArea function in Node with a
bounded DOM/fetch harness: POST saved then threw a simulated lost-response error;
reopening and submitting the retained draft saved `id-1` and `id-2`, both with
text `Plan v0`. No real conversation was changed.

Repair: keep the pending request identity with the per-area draft, reconcile it
against saved messages after uncertain results, and cover close/reopen retries.

## P2 — Answer status ignores the content fingerprint

`src/vizzer/area_chat.py:50–53,77–88`

read_area declares a question answered using only replyTo. append_message also
rejects all further replies to that ID without considering replyToHash. The watch,
however, compares the parent ID AND current content hash, and the documented
protocol says an edited question receives a new reply referring to changed content.
Those two protocols disagree: the timer can identify work that the writer rejects.

Reproduced in a temporary repository: create question and reply, update the question
text/hash to represent an authored source revision, then read and answer again.
Observed pending=0 and `owner message already answered`, despite the reply naming
the old content hash. No real message file was changed.

Repair: either enforce immutable versioned questions end to end with a supported
edit/new-ID path, or compare the current parent fingerprint in answered-state and
reply deduplication. The writer should also accept/check the expected parent hash
so a response cannot silently attach to a question changed during reasoning.

## Downstream integration gate

IllTool has not received these changes. Its live serving checkout
`illtool-standalone-serve-main` is clean at `fa0b5729e` and contains substantial
fork-specific symbols, controls, session history and version identity. This review
does not approve replacing that engine with the upstream package.

Area-chat storage is currently fixed to Vizzer's `product-spec/planning/areas` and
the desktop heartbeat is a local Codex configuration, not installed by this PR.
An IllTool port must explicitly map its canonical spec paths and watcher ownership;
copying the code alone does not install the planning service or migrate staging.

## Evidence limits

Earlier 123 tests/9 subtests and the seven toolbar checks were implementation
validation, not proof against these failure cases. This review executed two new
bounded counterexamples against the reviewed code. It did not run product tests,
change IllTool, merge the PR or modify the live conversations. The PR remains draft.

## Repair review — 2026-09-13, before upstream merge

The two P2 findings are repaired. Pending IDs now live with per-area draft state;
GET and polling reconcile exact saved Owner IDs/text. A late response does not
clear a newer draft. Regression execution covers a request that failed before
reaching the server and a saved request whose response was lost, each followed by
panel reopen and retry. Both retain one request identity and one saved question.

Answer status and reply deduplication now compare ID plus SHA-256 of current text,
computed from text even if a manual edit left the stored hash stale. Writers must
supply expected_parent_hash from the text read before reasoning. The helper
rejects changed parents, retains previous replies, and accepts a replacement at
the new hash. README and the desktop heartbeat were updated together.

Additional CI failure repaired: title/menu alignment at 360px was outside the
existing two-pixel tolerance. Matching title line height fixes alignment; compact
appearance controls occupy a separate row and filter chips scroll horizontally,
leaving the routed view reachable. The existing physical Chrome dossier test
passes, including pointer-driven scrolling at 360x320.

Focused chat tests: 7 passed. Physical dossier regression: 1 passed. The full
suite is running; merge remains gated on its result and hosted checks. No IllTool
engine files or runtime have changed during this repair phase.

Full local suite completed: **636 passed, 9 subtests passed** in 203.15 seconds.
The additional parametrized request-before-save case subsequently passed with
all seven focused chat checks. No blocking finding remains in the repair scope.
Hosted checks remain the upstream merge gate; downstream still requires its own
composition and review. Local 8480 was refreshed/restarted and returns HTTP 200.
