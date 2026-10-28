# Show the core features in the README with reproducible GIFs

> Status: building
> Deps: []
> Release: R1
> Tags: documentation, readme

## Intent

The owner asked for README GIFs that show what Vizzer does: capability
clusters, owner questions, and the other core features. The GIFs should show
the intent, not real projects. Recordings use the real UI over a fictional
"Sample Notes" project, so no IllTool or Vizzer backlog content appears.

## Acceptance criteria

- The README shows one GIF each for capability clusters, owner questions,
  views, workstreams, reviews, and Developer Flow, each with a short caption
  explaining what it is for.
- `python3 scripts/readme_media/record.py` rebuilds the fictional project and
  re-records every GIF. A scene that raises a page error, or whose target is
  not visible, fails instead of producing a misleading GIF.
- No GIF contains real project names or content.

## Test plan

- Done: every scene recorded with no page errors; contact sheets were checked
  frame by frame.
- RC pass: re-run the recorder after UI changes that touch these routes, and
  check the README renders on GitHub.
