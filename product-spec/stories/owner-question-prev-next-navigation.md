# Step between open owner questions without closing the panel

> Status: building
> Deps: []
> Release: R1
> Tags: constellation, owner-decisions, served-ui, navigation

## Intent

Owner directive, 2026-09-26 (illtool-standalone):

> "when i start answering questions, and there are more than one. at the top of
> the panel i should just have a segmented control at the top to jump between
> next and prev, so i can get to the next one without closing the panel. update
> that in this project and then update upstream."

Origin: rydersd/illtool-standalone, story
`wiki/product-spec/capabilities/spec-ops/epics/owner-decision-loop/stories/owner-question-prev-next-navigation.md`.
This is the same behaviour built into Vizzer's own dossier, not a copy of the
illtool files (the two dossiers have diverged).

## Acceptance criteria

- With two or more open owner questions, the served dossier showing a story
  with an open question has a segmented control pinned at the top, above the
  title: Previous | "N of M" | Next. N is the shown question's place among all
  M open questions.
- Next / Previous move to the next / previous open question, across stories,
  in the owner question order (graph order of delivery items, then question
  order within an item; other roles, such as reference items, have no answer
  footer and are left out), and the dossier stays open.
- An option chosen on a card survives stepping away and back (the existing
  `questionDrafts` store).
- The ends do not wrap: Previous is disabled on 1 of M, Next on M of M.
- Focusing a question card makes it the counted question, so "N of M" follows
  the card the owner is working on.
- With exactly one open question there is no control. Once the shown question
  is answered (by Provide answers, or alone through the suggestion editor), the
  count drops and the dossier moves on to the next open question after it (or
  the nearest earlier one).
- Previous and Next are buttons with the accessible names "Previous owner
  question" and "Next owner question"; the position is announced; Left/Right
  arrows on the focused control step questions without also triggering the
  window-level work navigation. The read-only file:// build shows no control.

## Decisions taken (reversible)

- No wraparound: reaching the last question should be visible.
- After answering, the dossier advances: that is what gets the owner to the
  next question without closing the panel.
- Hidden, not inert, in file://: the static build cannot record answers.

## Evidence

Tests: `tests/test_question_navigation.py`.
