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

## Tests

1. Infrastructure failure never displays as an executed result.
2. Disabled config: no route, no markup.
