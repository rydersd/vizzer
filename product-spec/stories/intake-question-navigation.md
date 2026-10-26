# Question checklists and navigation

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, questions, constellation

## Origin

IllTool 29884954e (#1340), b62d13726 (#1400), 332006f9d.

## Acceptance

- A review testing plan renders as a checklist; checked state is an answer
  recorded through the existing answer ledger, not page-local state.
- Open owner questions show `Previous | N of M | Next`; arriving at another
  story's questions starts at its first one.
- Review-plan checklist progress is a distinct record from owner-question
  answers: checking a test item never answers an owner question or approves a review.

## Test plan (RC)

Keyboard navigation and a question edited mid-navigation are not automated.

## Named tests

- `tests/test_question_navigation.py::test_next_and_previous_walk_open_questions_across_stories_in_list_order`
- `tests/test_question_navigation.py::test_answering_through_real_serve_moves_to_the_next_question`
- `tests/test_question_navigation.py::test_draft_answers_survive_navigating_away_and_back`
- (planned) `tests/test_review_plans.py::test_checking_a_plan_item_never_answers_an_owner_question`
