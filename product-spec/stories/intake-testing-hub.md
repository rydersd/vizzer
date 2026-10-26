# Testing hub strip

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: upstream, testing, served

## Origin

IllTool c4125322f (#1437), c1f7ca8af (#1635), c2dc97a12, 917d36849.

## Acceptance

- Opt-in served hub strip: worker restrictions, probe failure reasons, config
  acknowledgement, infrastructure failures distinct from executed results.
- The capacity probe is a configured adapter; GitHub is one implementation.
  When the probe hits limits, the local fallback is preserved and shown.
- Disabled: renders and serves nothing.

## Named tests

- (planned) `tests/test_testing_hub.py::test_infrastructure_failure_never_displays_as_executed_result`
- (planned) `tests/test_testing_hub.py::test_disabled_config_has_no_route_and_no_markup`

## Open contract questions

- Adapter declaration and result schema for the capacity probe.
- Timeout and cache policy for probe results.
- How are malformed, stale, unauthorized and unavailable results told apart?
