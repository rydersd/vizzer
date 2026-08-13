"""Renderer registry and orchestration."""
from __future__ import annotations

import importlib
from pathlib import Path

from ..config import Config
from ..model import Graph


# Values are relative module names so importing this package does not require
# every renderer to exist during the staged build. Dict insertion order is the
# canonical output order.
RENDERERS = {
    "roadmap": "roadmap",
    "feature_index": "feature_index",
    "dashboard": "dashboard",
    "decision_journal": "decision_journal",
    "discussion_queue": "discussion_queue",
    "completion_sheet": "completion_sheet",
    "ledger_table": "ledger_table",
    "manifest": "manifest",
    "constellation": "constellation",
}


def render_all(
    graph: Graph,
    cfg: Config,
    root: Path,
    only: set[str] | None = None,
) -> dict[str, str]:
    """Render selected views and return output filenames mapped to contents."""
    selected = set(RENDERERS) if only is None else set(only)
    unknown = selected.difference(RENDERERS)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unknown renderer(s): {names}")

    output: dict[str, str] = {}
    for name, module_name in RENDERERS.items():
        if name not in selected:
            continue
        module = importlib.import_module(f".{module_name}", __name__)
        output.update(module.render(graph, cfg, root))
    return output
