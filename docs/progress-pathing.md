# Progress pathing and owner revisions

**Progress pathing** is the public name for Vizzer's recorded work paths and their evolution over time. The existing renderer connects explicit chronological checkpoints and fades older paths. It does not infer a journey from unrelated Story mentions. Internal `agentTrails` fields remain compatible.

## Record and replay

With the current engine installed in a project, run:

```sh
python3 /project/vizzer/engine/vizzer/evolution.py --root /project record --caption "What changed"
python3 /project/vizzer/engine/vizzer/evolution.py --root /project watch
```

The recorder currently uses POSIX locking (macOS/Linux). Open **Views → Progress pathing playback**. The view provides recorded checkpoints, bottom annotations, scrub/step/play controls and a clean recording view. It can be recorded later with a screen recorder. No history means an explicit empty state.

A watcher observes completed, validated refreshes; one batch refresh produces one checkpoint. It does not refresh half-written specifications. Stop it with Ctrl-C. Only one watcher owns a project. `render` rebuilds playback projections and verifies the immutable history hashes; `verify` does the same verification/rebuild.

Version `vizzer/evolution/events.jsonl`, `snapshots/` and compressed `frames/` together. Ignore rebuildable `vizzer/views/evolution/` and `evolution.html`. Frames use frozen relative time, offline mode, sandboxing, and early CSP that blocks connections and forms. Historical frames cannot answer current questions. This is recorded graph/layout state, not pixel-exact screenshots or invented continuous motion. No automatic retention/deletion policy is applied.

## Owner answer editing

“Suggest something else” takes over the existing Story sidebar. The question stays above a scrolling Markdown editor and Submit below it. Text matches the sidebar reading-size control and grows with the content plus two spare lines. Formatted editing and accepted freeform answers render Markdown. Back/Escape preserves the draft and returns to the question. Background sidebar refreshes cannot replace the active editor. Submission retains the existing CSRF, revision and fingerprint guards; accepted drafts are cleared only after server success.

## Edit a Story for review

**Edit story → Save for review** captures the full Markdown as a pending owner revision. This creates a review candidate; it does not replace the authoritative source or approve itself. Back retains a browser draft. Reopening shows the latest submitted candidate. Stale source hashes and competing pending revisions return a conflict while retaining the draft.

`vizzer/story-edits/<story-id-hash>.json` stores ordered revisions with original Markdown, edited Markdown, hashes, unified diff, source path, timestamp, and pending-review status. Review the exact delta against the current source, record findings/disposition separately, and apply only after reconciliation. Preserve the submitted history. Neither Save nor the watcher launches an LLM, commits, or pushes. A consumer can process these ledgers at the start of its next review task.

## Project identity colors

Optional tag colors distinguish tooling or other categories while lifecycle remains explicit in the dossier:

```toml
[render.tag_colors]
vizzer = "#FF6A00"
```

The first valid configured tag on a node wins. Unconfigured or malformed colors retain the normal lifecycle color.

## macOS login startup

After installing the engine, stop this project's manually launched server/recorder and choose an unused loopback port:

```sh
python3 /project/vizzer/engine/vizzer/startup.py --root /project --port 57727
```

The installer creates two project-path-scoped LaunchAgents (server and progress-pathing watcher), prints their labels, and starts them immediately. They run at login and restart on exit; no browser is opened. Logs are under `~/Library/Logs/Vizzer/<project-hash>/`. Reinstall after moving the checkout or changing Python; boot out and remove the old printed plist paths when retiring a project path. No startup services are installed by merely importing or updating Vizzer.

## Formatted Markdown and attribution

Milkdown/Crepe 7.22.1 now supplies a single full-height, Word-like formatted Markdown editor with formatting controls and optional source mode. Source and formatted editing use the same area. There is no split preview. The question/title and submission actions remain pinned.

Milkdown is MIT-licensed and built on ProseMirror and remark. **Views → About Vizzer** includes its attribution and links to the complete bundled third-party notices. The pinned npm lockfile and reproducible esbuild wrapper are in `tools/markdown-editor/`; generated JS/CSS/notices are included in installed engine assets, with no CDN dependency. Run `npm ci --ignore-scripts` then `npm run build` from that tools directory using a supported Node LTS.

No-op opening preserves original Markdown bytes. List marker and trailing-newline conventions are retained, and the browser round-trip test checks headers, dependencies, a list, and a fenced Gherkin block while changing only a heading. Raw HTML blocks such as `<details>` stay in source mode so unsupported markup cannot disappear.
