# Capability purpose, plans and desktop planning chat

> Status: building
> Deps: []
> Release: R1
> Tags: planning, constellation, product-spec

## Owner intent

Selecting a capability shows its overarching purpose and discussed plans. The
owner can ask questions in a persistent chat, with Codex responding on the desktop
timer as capacity permits, without an SDK or model API. Plans remain distinct from
executable Stories. Research and rationale survive for future article writing.

## Acceptance criteria

- Capability selection opens purpose, plans and a discussion composer.
- Saved messages survive reload, retain attribution, IDs and content hashes.
- Retried submissions are idempotent; a conflicting reuse of an ID is rejected.
- Replies refer to an owner message and its hash; duplicate answers are rejected.
- Cross-origin writes, unknown areas and symlink/path traversal are rejected.
- The desktop watch reads these files and appends real replies; UI polling never
  invokes a model and does not claim an unobserved agent is running.
- IllTool staging is conspicuously identified until canonical publication succeeds.
- Existing drafts survive polling and failed saves. Escaped messages cannot inject HTML.

## Validation — 2026-09-13

66 focused renderer, appearance, trail and area-chat tests passed (two physical
selectors excluded). Area-chat tests cover concurrent writes, idempotency,
conflicting IDs, reply hashes, duplicate replies, traversal, symlinks and HTTP
origin/CSRF enforcement. Browser verification saved Ryder's actual request,
then observed a real Codex reply appear through polling without a reload.
That reply was written during the active task, not a scheduled wake. The existing
15-minute desktop heartbeat was updated successfully; a future scheduled run
against this new inbox has not yet been observed. Claude is not connected.
