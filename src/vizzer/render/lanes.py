"""Read-only durable-workstream and optional project-register perspective."""
from __future__ import annotations

import re
from pathlib import Path

from ..config import Config
from ..model import Graph
from .common import item_link, source_link_prefix
from .perspective_common import safe_source_text


REGISTER_ENTRY = re.compile(
    r"^`([^`]+)`:\s*([^\n]*\b20\d{2}-\d{2}-\d{2}\b[^\n]*)", re.MULTILINE,
)


def _register(root: Path, relpath: str) -> list[tuple[str, str]]:
    text = safe_source_text(root, relpath)
    active = text.split("## Active", 1)[-1].split("\n## ", 1)[0] \
        if "## Active" in text else text
    return sorted(REGISTER_ENTRY.findall(active), key=lambda entry: entry[0])


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    if not cfg.get("perspectives.enabled", False):
        return {}
    prefix = source_link_prefix(cfg, root)
    item_map = graph.item_map()
    overlay = graph.workstreams if isinstance(graph.workstreams, dict) else {}
    streams = {
        stream.get("id"): stream for stream in overlay.get("workstreams", [])
        if isinstance(stream, dict) and isinstance(stream.get("id"), str)
    }
    lines = [
        "# Agent and lane perspective", "",
        "Read-only. Checked-in output uses durable workstream definitions. "
        "Machine-local leases and branch refs are intentionally absent; use "
        "`vizzer sessions show` for live runtime state.", "",
        "## Durable workstreams", "",
        "| Workstream | Lead / reviewer | State | Items | Progress | Checkpoint |",
        "|---|---|---|---|---:|---|",
    ]
    active = [stream for stream in streams.values() if stream.get("status") != "done"]
    for stream in sorted(active, key=lambda value: value["id"]):
        links = ", ".join(
            item_link(item_map[item_id], prefix)
            for item_id in stream.get("storyIds", []) if item_id in item_map
        ) or "—"
        checkpoint = str(stream.get("checkpoint", "")).replace("|", "\\|")
        lines.append(
            f"| **{stream.get('title', stream['id'])}** (`{stream['id']}`) | "
            f"{stream.get('lead', '—')} / {stream.get('reviewer', '—')} | "
            f"`{stream.get('status', 'unknown')}` | {links} | "
            f"{stream.get('completed', 0)}/{stream.get('total', 0)} | {checkpoint} |"
        )
    if not active:
        lines.append("| — | — | No live workstreams | — | — | — |")

    register_path = cfg.get("perspectives.register_path", "")
    if isinstance(register_path, str) and register_path:
        lines.extend([
            "", "## Project work register", "",
            f"Source: [`{register_path}`](../../{register_path}).", "",
            "| Lane / branch | Register record |", "|---|---|",
        ])
        records = _register(root, register_path)
        for lane, record in records:
            safe_record = " ".join(record.split()).replace("|", "\\|")
            lines.append(f"| `{lane}` | {safe_record} |")
        if not records:
            lines.append("| — | No active entries |")
    lines.append("")
    return {"lanes.md": "\n".join(lines)}
