# Field report: what a real deployment found, and how it was fixed

> Date: 2026-08-07 · Applies to: vizzer v0.1.0 (post-release)
> Trigger: an independent trial install against a real, complex project

vizzer shipped with 64 passing tests, a five-version CI matrix, and a clean run
against a 1,656-item repository. Then someone trial-installed it against a
different real project and found five defects in an afternoon. A follow-up
adversarial review of the fixes found six more — including one created by a fix.

This document records what they were, why the test suite could not see them, and
what changed. It is written for the next person who wonders whether a green suite
means a working tool.

## The short version

| # | Defect | Impact | Status |
|---|---|---|---|
| 1 | DAG detection assumed list-shaped collections | All 43 stories skipped; ready queue flat and non-dependency-aware | Fixed |
| 2 | `loose_docs` auto-enabled alongside real sources | Documentation became 111 of 154 graph items | Fixed |
| 3 | Declared Python floor was wrong (`>=3.10`) | Contradicted by reality; understated compatibility | Fixed |
| 4 | No warning when a source lives under a gitignored path | Committed views nobody else can reproduce | Fixed |
| 5 | No hint when a spec tree yields zero dependency edges | Silent, plausible-looking wrong output | Fixed |

All five are fixed, verified against the real project, and covered by tests. A
second round (documented below) fixed six more. The suite went from 64 to 84 tests.

## 1. The DAG shape assumption

**What happened.** vizzer's `dag_import` never engaged. The project's dependency
graph lives in `.shape-spec-dag.json`, but detection returned an empty path, so the
ready queue came out as a flat alphabetical list of every unstarted story.

**Root cause.** The first implementation recognized exactly one shape:

```json
{"capabilities": [ {"epics": [ {"stories": [ {"slug": "..."} ]} ]} ]}
```

Lists at every level. The real project keys its collections by slug instead:

```json
{"capabilities": {"billing-narrative": {"title": "...", "epics": {
   "billable-model-ui": {"stories": [{"slug": "billable-fields-ui", "deps": []}]}}}}}
```

Iterating a dict yields its keys — strings, not records — so every story was
skipped. Detection failed silently and the importer would have found nothing even
if pointed at the file by hand.

**The fix.** A DAG is now recognized by its *records* rather than by one key path:
walk dicts and lists alike to a bounded depth and look for objects carrying a
string `slug`. The importer walks the same way. Both shapes work. A guard keeps
ordinary project JSON (lockfiles, tsconfigs) from being mistaken for a work source.

**Verified.** 39 dependency edges recovered across the 27 stories that carry them;
the ready queue narrowed from 23 flat entries to 12 dependency-satisfied ones.

## 2. `loose_docs` was an always-on adapter

**What happened.** The adapter swept every markdown file under `docs/` and `wiki/`,
so 111 of 154 graph items were documentation. That produced meaningless progress
rows like `wiki/concepts 0/18` and would have dominated the constellation.

**Root cause.** `detect()` enabled `loose_docs` whenever any doc glob matched — even
when a real spec tree was present. Documentation is *corpus*, not work items.

The same pattern had appeared once before, during pre-release dogfooding on another
repository: 738 of 1,498 items were docs. It was noted and not acted on. Two
independent observations of the same failure is a signal, not a coincidence.

**The fix.** `loose_docs` is now what it was always meant to be — the fallback for
repositories with no structured source. It auto-enables only when no spec tree, DAG,
ledgers, or TODO files were found. The detected globs are still written to the
config so enabling it later is a one-word edit, and the install output states the
choice explicitly rather than making it silently:

```
loose_docs: docs/**/*.md, wiki/**/*.md (disabled — fallback only)
```

**Verified.** The same project now produces 43 items instead of 154.

## 3. The Python floor was wrong

**What happened.** The trial ran vizzer successfully on system Python 3.9.6, despite
`requires-python = ">=3.10"`. As the report put it: one of those two things is wrong.

**Root cause.** The floor was asserted during design and never tested. It was simply
inaccurate — nothing in the codebase requires 3.10.

**The fix.** The full suite was run on 3.9.6: all tests passed. The floor is now
`>=3.9`, and 3.9 was added to the CI matrix so the claim stays honest.

This *strengthens* the tool's central promise. vizzer's pitch is "no dependencies
beyond system `python3`" — and macOS ships 3.9. Declaring 3.10 quietly excluded the
default interpreter on every Mac.

## 4. Sources under gitignored paths

**What happened.** The ledger adapter auto-disabled itself and the ledger table came
out empty, because the project's `thoughts/` directory is gitignored. Enabling it
locally works — but the resulting committed views would be derived from files that
no teammate and no CI run can see.

**Root cause.** vizzer had no notion that a source might be invisible to everyone
else. This is a design gap, not a parsing bug: the tool's whole contract is that
views are *regenerable*, and a view derived from ignored files is not.

**The fix.** `sync` now consults `git check-ignore` for each source directory and
warns:

```
warning: thoughts/ is gitignored — views derived from it cannot be reproduced by CI or teammates
```

It is a warning, not an error. Local-only orientation is a legitimate choice; making
it silently is not.

## 5. Silence when a spec tree has no dependencies

**What happened.** Nothing in the output indicated that the ready queue was not
dependency-aware. The queue looked plausible — it was simply wrong.

**The fix.** After `sync`, if a spec tree produced items but zero dependency edges,
vizzer prints:

```
hint: 43 items, 0 dependency edges — if your dependencies live in a DAG file,
      set sources.spec_tree.dag_import in vizzer/vizzer.toml
```

This one message would have caught defect #1 in *both* deployments, on day one,
without anyone needing to notice that a queue was suspiciously alphabetical.

## Why 64 passing tests missed all of this

Every defect above shares one property: **the tests were built from the same
assumptions as the code.**

- Fixtures used list-shaped DAGs because that was the shape the author had seen.
  A fixture cannot disagree with its author.
- Fixtures were small and clean, so a doc-heavy graph never arose.
- Tests ran in-process on one interpreter, so the version floor was never exercised.
- Fixtures were fully tracked in git, so gitignored sources were unrepresentable.
- No test asserted anything about *output quality* — only correctness. A flat ready
  queue is correct given no edges; it is also useless.

Synthetic fixtures verify that code does what its author meant. Only real data
reveals what the author failed to imagine. The pre-release dogfooding session had
already demonstrated this — it found four defects the suite could not, including a
completely broken `.pyz` install path — and this trial demonstrated it again against
a project with a different shape.

**The practice worth keeping:** before trusting a green suite, run the tool against a
repository nobody designed it for.

## A finding that was not a vizzer bug

The trial noted that `commit-revenue-target` appeared in the ready queue although the
project's delivery log records it as blocked.

Investigation showed the story carries **no dependencies in the DAG**. vizzer was
reporting the graph accurately; the graph is missing a dependency the delivery log
knows about. The tool did not get this wrong — it surfaced a gap between two sources
of truth in the project.

This is worth stating because the natural reading was "vizzer recommends blocked
work," and acting on that reading would have meant changing correct code.

## Governance note

The trial raised a question no code change can answer: the project already has a
selector (`next-story.py`) that the ship-feature loop consults, and vizzer's dashboard
answers the same question with different ranking. Deploying vizzer creates a second
answer to "what's next."

The recommendation on record: vizzer owns orientation and visualization;
`next-story.py` remains the selector. With `dag_import` wired, the two at least agree
on what is blocked. That is a project decision, not a tooling one.

## Round two: re-reviewing the fixes found a bug the fixes created

After these changes landed, roughly half the codebase had turned over since the last
independent review — so a second adversarial pass was run over the changed code, with
instructions to *attack* the fixes rather than confirm them. It found six more defects,
including one high-severity.

**The escaping fix was incomplete, and the gap was created by the fix itself.** The
renderer escaped the title, then replaced the `__DATA__` placeholder — two sequential
passes. That let the first substitution's output be re-scanned by the second, so a
title containing the literal string `__DATA__` smuggled the entire JSON payload into
the HTML body, *outside* the script element, where node titles are not HTML-escaped. A
story titled `<img src=x onerror=…>` became live markup again.

The fix: resolve both placeholders in a single `re.sub` pass, so replaced text is never
re-scanned. Hand-editable `activity` values are also coerced to integers now, since the
template interpolates them into the page.

The other five, all reproduced on small inputs:

- **One stray checkbox discarded every real ledger phase.** The heading fallback engaged
  only when a file contained no checkbox *anywhere*, so a ledger with proper
  `Done`/`Now`/`Next` sections plus an unrelated `- [ ] CI is green` under "Working set"
  emitted only that stray checkbox. Parsing is now per-section.
- **DAG detection had over-corrected.** Making it shape-tolerant made it accept any dict
  with a `slug` inside a list, so an ordinary `content.json` containing
  `{"pages":[{"slug":"about"}]}` was auto-selected as the project DAG, and capability and
  epic wrappers were emitted as stories.
- **Malformed graphs could hang or crash rendering** — a group-parent cycle looped
  forever, and ids without a `:` raised `IndexError`. Validation now rejects both.
- **Hostile input still raised** — a non-UTF-8 overview (`UnicodeError` uncaught) and, on
  3.11+, a JSON integer exceeding the interpreter's digit limit.
- **Archive containment had a symlink-swap race**: the destination was validated, then
  reopened by pathname. Moves now go through a directory file descriptor, and a symlinked
  archive directory is refused outright.

### One judgment call worth recording

The proposed fix for the over-broad DAG detection required at least three slug-bearing
records. That would have rejected legitimate small DAGs — including existing test
fixtures — for no benefit, because the real discriminator is the **work-item signal**: a
DAG carries `deps`/`status`/`release`/`wave` alongside a slug; a content manifest carries
only slugs. The count was dropped and the signal kept. Both directions were verified: the
`content.json` false positive is still rejected, and a genuine two-story DAG is still
found.

A fix that trades a false positive for a false negative has not solved the problem.

### And the tests lied four times

Across this work, four test assertions failed against *correct* code:

- two set a config key the fixture did not contain, so the edit was a silent no-op;
- one asserted a threshold its own fixture was too small to reach;
- one forbade a string anywhere in the document when the real invariant was "not outside
  the script block" — the value belongs in the JSON payload.

Each would have sent someone editing working code. **Read why a test is red before
believing it.** A red test is a claim, not a verdict.

## Changes

| Commit | Change |
|---|---|
| `641e88b` | Python 3.9 support, `loose_docs` as fallback, gitignore and zero-edge warnings |
| `410ce09` | Slug-keyed DAG detection and import |
| `2e9cb2e` | Single-pass placeholder substitution; activity coercion (high severity) |
| `bd5a58a` | Per-section ledger parsing, stricter DAG signal, graph validation, decode/limit errors, archive symlink race |

Tests: 64 → 84. Verified on Python 3.9.6 and 3.12, and end-to-end against the real
project using the system interpreter. Two tests are version-guarded: they assert
behavior from the 3.11+ integer digit limit.

## The pattern, stated plainly

Three rounds of scrutiny found fifteen defects in code that had a green test suite the
whole time:

1. **Dogfooding on a real repository** — four defects, including a completely broken
   `.pyz` install path and a graph where every dependency edge was silently dropped.
2. **An independent trial by someone else, on a project with a different shape** — five
   defects, including a DAG shape assumption that skipped all 43 stories.
3. **An adversarial review of the fixes themselves** — six defects, including a
   high-severity hole introduced by the previous round's fix.

None of the three could have been replaced by writing more tests in the same style,
because the tests and the code shared their assumptions. What worked was changing *who*
or *what* was doing the looking: real data, a different person, and an adversary pointed
at the diff.
