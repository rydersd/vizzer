# Vizzer for Vizzer

This repository uses its own current `src/vizzer` to render a local dashboard.
The small `engine/__main__.py` launcher deliberately does not vendor a second
package. Do not run `install` or `update` against this source repository: those
commands are for downstream installations and would create a competing engine.

From the repository root:

```sh
python3 vizzer/engine refresh
python3 vizzer/engine check
python3 vizzer/engine serve
```

Open <http://127.0.0.1:8480/constellation.html#dashboard>. The Views menu includes
the work graph, roadmap, and reference documents. The optional 2D view is at
<http://127.0.0.1:8480/developer-flow.html>.

## Source of truth

- `product-spec/stories/*.md`: current delivery work, including cross-project imports.
- `product-spec/*.md`, `wiki/**/*.md`, and `docs/**/*.md`: reference context.
- Old continuity ledgers and test fixtures are excluded from current work tracking.
- `vizzer/vizzer.toml`: explicit source map and stable local port.

Start with `product-spec/stories/cross-project-change-intake.md`. Add a separate
Story for each actual import or regression, retaining source provenance,
upstream comparison, acceptance criteria, and verification evidence. Do not
infer completion from a stale ledger or the presence of a similarly named file.

## Keeping the dashboard current

After changing a Story or pulling source changes, run `refresh` and `check`.
If a server is running when engine code changes, stop that server and start
`serve` again after refreshing; its identity guard intentionally rejects stale
processes. Reload the browser to display the fresh graph. This setup does not
automatically pull repositories, inventory forks, or run a background watcher.

Generated views, graph, render marker, cache, and runtime files are local and
gitignored. Authored Stories, configuration, and this source launcher are
reviewable repository files. Agents working in this repository should read this
document, update the authoritative Story first, and refresh after each meaningful
checkpoint. `AGENTS.md` is not modified by this setup.

## Empty dashboard or missing documents

The dashboard shows portfolio candidates or configured recommendations, not
every Story. This configuration recommends concrete open work. Use Roadmap or
Structure for the complete delivery register. Open Views → Features, select References or All under
item role and search to find specs, wiki and docs. A delivery-only view hides
reference documents by design.

After pulling, refresh/check and restart the local server when engine or config
changed. A stale browser may need a reload. Confirm the server is for this
checkout on port 8480; other projects have their own Vizzer processes.

Start reading: [product spec](../product-spec/README.md), [wiki](../wiki/index.md),
[documentation](../docs/README.md). These sources are tracked in the main repo;
there is no separate GitHub Wiki to synchronize.
