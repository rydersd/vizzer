# Distribution output

This directory is for generated release artifacts. The authoritative readable
implementation is [`../src/vizzer/`](../src/vizzer/); do not edit a `.pyz` or
copy extracted archive contents back into source.

Build the standalone distributable from the repository root:

```bash
python3 scripts/build_pyz.py dist/vizzer.pyz
```

Only this README is tracked. `dist/vizzer.pyz` is reproducible build output and
is attached to releases by the release process.
