"""Open owner story comments, grouped by story, for the orchestrator's grill sessions."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..model import Graph
from ..story_comments import STORE_RELPATH, StoryCommentError, load_store, render_comments_markdown


def render(graph: Graph, cfg: Config, root: Path) -> dict[str, str]:
    try:
        entries = load_store(root)
    except StoryCommentError as exc:
        reason = ("is over its limits (store over limit)" if exc.status == 413
                  else "could not be read")
        return {"story-comments.md": "# Story comments\n\n"
                f"`{STORE_RELPATH}` {reason}, so open comments cannot be listed. "
                "Fix or restore that file; it has not been modified.\n"}
    return {"story-comments.md": render_comments_markdown(entries)}
