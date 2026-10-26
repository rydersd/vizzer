# Bug pulse

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, bugs, views

## Origin

IllTool 31135c71b (#1408), 2b820da05, 69f3a16e5.

## Acceptance

- A bug pulse view shows open bugs, their trend, parked bugs and a delivery-value order.
- Bug classification (product vs tooling) is project configuration, not a
  hard-coded path; the bugs chip counts product bugs, a tooling chip the rest,
  and the completion view counts both consistently.

## Named tests

- (planned) `tests/test_bug_pulse.py::test_counts_and_trend_from_synthetic_history`
- (planned) `tests/test_bug_pulse.py::test_configured_tooling_bugs_leave_the_bugs_chip`
