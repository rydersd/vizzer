# IllTool Vizzer upstream intake

## Goal
Abstract last week's downstream updates; test, review, PR and merge upstream.
## Constraints
External-drive branch only; preserve both original checkouts; no private data;
no gate bypass; current source and portable tests rather than historical claims.
## Key Decisions
Import incremental engine changes f8c4f2b66..b6a67bb80 onto upstream 2ba0172.
Generalize velocity configuration and restrict stale graph fallback to reads.
## Done
Compared history, checked open PRs (#1 docs, #2 older interaction work), created
external clone and codex/illtool-vizzer-upstream-20260919 branch.
## Now
Port complete; local suite 664 passed / 2 skipped. Package build and check pass.
Independent backend and final committed-PR frontend reviews passed; final
no-epic oracle correction is 29/29 green. Claude attempted review but hit weekly quota before
reading source (NO VERDICT). Browser verification caught and rechecked the flat
project layout repair. Existing original checkouts untouched.
## Next
PR https://github.com/rydersd/vizzer/pull/12 (source 4c4212336071f95fa8de6027056ac2c4e4d2ed5a)
is published with clean external checkout; hosted CI and verified merge next.
## Open Questions
None requiring owner decision yet; runtime portability is under investigation.
## Working Set
External checkout: vizzer-illtool-upstream-co (owner's external drive).
Source: rydersd/illtool-standalone; target: rydersd/vizzer.
