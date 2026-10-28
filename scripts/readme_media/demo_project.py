"""Write the fictional demo project the README GIFs are recorded against.

The README shows what Vizzer does, not what any real project is building, so
every capability, story, question, and agent session here is invented. The
shape is chosen to exercise each feature on camera: several capability
clusters with cross-cluster dependencies, a spread of lifecycle states, open
owner questions on more than one story, and concurrent agent work.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# capability -> epic -> [(slug, title, status, release, deps, intent)]
SPEC = {
    "accounts": ("Accounts", {
        "sign-in": ("Sign-in", [
            ("email-sign-in", "Email sign-in", "shipped", "R0", [], "A person signs in with email and a one-time code."),
            ("passkeys", "Passkeys", "building", "R1", ["email-sign-in"], "A returning person signs in with a passkey."),
            ("session-recovery", "Session recovery", "specced", "R1", ["email-sign-in"], "An expired session resumes without losing a draft."),
        ]),
        "profiles": ("Profiles", [
            ("profile-basics", "Profile basics", "shipped", "R0", ["email-sign-in"], "A person sets a display name and avatar."),
            ("workspace-roles", "Workspace roles", "specced", "R2", ["profile-basics"], "Owners grant editor or viewer roles."),
        ]),
    }),
    "editor": ("Editor", {
        "writing": ("Writing", [
            ("rich-text", "Rich text", "shipped", "R0", [], "Headings, lists, and links render as typed."),
            ("slash-commands", "Slash commands", "building", "R1", ["rich-text"], "Typing / opens an insert menu."),
            ("inline-images", "Inline images", "specced", "R1", ["rich-text"], "Pasted images upload and render inline."),
            ("tables", "Tables", "proposed", "R2", ["rich-text"], "A note can hold an editable table."),
        ]),
        "history": ("History", [
            ("undo-redo", "Undo and redo", "shipped", "R0", ["rich-text"], "Every edit can be undone and redone."),
            ("version-history", "Version history", "specced", "R2", ["undo-redo", "offline-queue"], "Restore any earlier version of a note."),
        ]),
    }),
    "search": ("Search", {
        "find": ("Find", [
            ("full-text-search", "Full-text search", "shipped", "R0", ["rich-text"], "Search finds words anywhere in a note."),
            ("search-filters", "Search filters", "building", "R1", ["full-text-search"], "Narrow results by tag, author, or date."),
            ("saved-searches", "Saved searches", "specced", "R2", ["search-filters"], "Pin a search to the sidebar."),
            ("search-ranking", "Relevance ranking", "proposed", "R2", ["full-text-search"], "Recent and frequently opened notes rank first."),
        ]),
    }),
    "sync": ("Sync", {
        "devices": ("Devices", [
            ("cloud-sync", "Cloud sync", "shipped", "R0", ["email-sign-in"], "Notes sync across a person's devices."),
            ("offline-queue", "Offline queue", "building", "R1", ["cloud-sync"], "Edits made offline replay in order on reconnect."),
            ("conflict-merge", "Conflict merge", "specced", "R1", ["offline-queue"], "Two offline edits to one note merge without loss."),
            ("selective-sync", "Selective sync", "proposed", "R3", ["cloud-sync"], "Choose which notebooks stay on a device."),
        ]),
    }),
    "sharing": ("Sharing", {
        "collaborate": ("Collaborate", [
            ("share-links", "Share links", "shipped", "R1", ["cloud-sync", "profile-basics"], "Share a read-only link to a note."),
            ("live-cursors", "Live cursors", "building", "R1", ["share-links", "conflict-merge"], "See collaborators' cursors while editing."),
            ("comments", "Comments", "specced", "R2", ["share-links"], "Comment on a selection and resolve threads."),
            ("mentions", "Mentions", "proposed", "R2", ["comments", "workspace-roles"], "Mention a teammate to notify them."),
        ]),
    }),
    "billing": ("Billing", {
        "plans": ("Plans", [
            ("plan-picker", "Plan picker", "specced", "R2", ["workspace-roles"], "Choose a free or team plan."),
            ("usage-limits", "Usage limits", "proposed", "R3", ["plan-picker", "cloud-sync"], "Storage limits warn before they block."),
        ]),
    }),
}

QUESTIONS = [
    ("q-conflict-default", "conflict-merge",
     "When two offline edits touch the same paragraph, what should a person see first?",
     [("keep-both", "Keep both versions inline", "Nothing is lost, but the note needs tidying."),
      ("latest-wins", "Latest edit wins, earlier one in history", "Clean note; the loser is one click away."),
      ("ask", "Ask before merging", "Explicit, but interrupts reconnect.")],
     "keep-both", "Data loss is the failure that hurts most; tidying is cheap."),
    ("q-passkey-fallback", "passkeys",
     "Should a device without passkey support fall back to email codes silently?",
     [("silent", "Fall back silently", "Smooth, but people never learn passkeys exist."),
      ("prompt", "Offer email with a one-line explanation", "One extra sentence; keeps trust.")],
     "prompt", "A silent downgrade reads as a bug when it is noticed."),
    ("q-live-cursor-scale", "live-cursors",
     "How many collaborator cursors should render before they collapse into a count?",
     [("five", "Five", "Readable on small screens."),
      ("ten", "Ten", "Matches typical team size; can crowd mobile."),
      ("all", "All of them", "Complete but noisy.")],
     "five", "Beyond five, cursors stop carrying location information."),
    ("q-image-limit", "inline-images",
     "What should happen when a pasted image is larger than the upload limit?",
     [("downscale", "Downscale automatically", "Always works; quality drops."),
      ("refuse", "Refuse with the limit shown", "Honest; the paste fails.")],
     "downscale", "A paste that fails silently loses work."),
]

WORK = [
    ("passkeys", "Claude", "Wire passkey registration into sign-in", "active", 2, 4),
    ("offline-queue", "Codex", "Replay queued edits in causal order", "active", 3, 5),
    ("live-cursors", "Claude", "Throttle cursor broadcasts", "blocked", 1, 3),
    ("search-filters", "Human", "Design the filter chips", "active", 1, 2),
    ("slash-commands", "Codex", "Keyboard navigation in the insert menu", "paused", 2, 3),
]


def _story(title: str, status: str, release: str, deps: list[str], intent: str) -> str:
    dep_line = f"\n> Deps: {', '.join(deps)}" if deps else ""
    return (f"# Story: {title}\n\n> Status: {status} · Release: {release}{dep_line}\n\n"
            f"## Intent\n{intent}\n\n## Definition of done\n\n{intent}\n")


def write(root: Path, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    spec = root / "spec"
    for cap, (cap_title, epics) in SPEC.items():
        (spec / cap).mkdir(parents=True, exist_ok=True)
        (spec / cap / f"{cap}.md").write_text(f"# Capability: {cap_title}\n", encoding="utf-8")
        for epic, (epic_title, stories) in epics.items():
            stories_dir = spec / cap / "epics" / epic / "stories"
            stories_dir.mkdir(parents=True, exist_ok=True)
            (spec / cap / "epics" / epic / f"{epic}.md").write_text(
                f"# Epic: {epic_title}\n", encoding="utf-8")
            for slug, title, status, release, deps, intent in stories:
                (stories_dir / f"{slug}.md").write_text(
                    _story(title, status, release, deps, intent), encoding="utf-8")

    stamp = lambda minutes: (now - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")
    feed = {
        "schema": 1,
        "work": [{
            "storyId": f"story:{slug}", "agent": agent, "task": task, "state": state,
            "checkpoints": {"completed": done, "total": total},
            "startedAt": stamp(90 + index * 7), "updatedAt": stamp(4 + index * 3),
        } for index, (slug, agent, task, state, done, total) in enumerate(WORK)],
        "questions": [{
            "id": f"question:{qid}", "storyId": f"story:{slug}", "owner": "Product owner", "prompt": prompt,
            "options": [{"id": oid, "label": label, "tradeoff": tradeoff}
                        for oid, label, tradeoff in options],
            "recommendation": {"optionId": rec, "rationale": rationale},
            "falsifier": "A usability session shows people choosing otherwise.",
            "evidence": [f"spec story {slug}"],
        } for qid, slug, prompt, options, rec, rationale in QUESTIONS],
    }
    (root / "vizzer").mkdir(exist_ok=True)
    (root / "vizzer" / "active-work.json").write_text(json.dumps(feed, indent=2), encoding="utf-8")
    (root / "README.md").write_text(
        "# Sample Notes\n\nA fictional note-taking app used to demonstrate Vizzer.\n",
        encoding="utf-8")


WORKSTREAMS = {
    "workstreams": [{
        "id": "offline", "title": "Offline editing", "objective": "Edits survive a lost connection",
        "status": "active", "lead": "Codex", "reviewer": "Claude",
        "storyIds": ["story:offline-queue", "story:conflict-merge"], "dependsOn": [],
        "allowedPaths": ["app/sync"], "sharedPaths": ["vizzer/active-work.json"],
        "checkpoint": "Replay ordering", "completed": 3, "total": 5,
    }, {
        "id": "together", "title": "Real-time collaboration", "objective": "See each other while editing",
        "status": "active", "lead": "Claude", "reviewer": "Codex",
        "storyIds": ["story:live-cursors", "story:comments"], "dependsOn": ["offline"],
        "allowedPaths": ["app/collab"], "sharedPaths": ["vizzer/active-work.json"],
        "checkpoint": "Cursor throttling", "completed": 1, "total": 3,
    }, {
        "id": "sign-in", "title": "Modern sign-in", "objective": "Passkeys with a safe fallback",
        "status": "active", "lead": "Claude", "reviewer": "Human",
        "storyIds": ["story:passkeys", "story:session-recovery"], "dependsOn": [],
        "allowedPaths": ["app/auth"], "sharedPaths": ["vizzer/active-work.json"],
        "checkpoint": "Registration flow", "completed": 2, "total": 4,
    }],
    "discussions": [],
}

# (session id, actor, model, role, workstream, branch)
SESSIONS = [
    ("codex-offline", "Codex", "gpt-5", "lead", "offline", "codex/offline-queue"),
    ("claude-collab", "Claude", "Opus", "lead", "together", "claude/live-cursors"),
    ("claude-signin", "Claude", "Sonnet", "lead", "sign-in", "claude/passkeys"),
]

REVIEW_STORY = ("story:search-filters", "spec/search/epics/find/stories/search-filters.md")

def configure(root: Path) -> None:
    """Point the installed config at every capability and enable each feature on camera."""
    config = root / "vizzer" / "vizzer.toml"
    text = config.read_text(encoding="utf-8")
    # The installer detects one capability folder; widen it to the whole spec tree.
    patterns = [
        (r'(\[\[source_area\]\]\nid = )"[^"]*"\ntitle = "[^"]*"', r'\1"product"\ntitle = "Product spec"'),
        (r'path = "spec/[^"/]+"', 'path = "spec"'),
        (r'glob = "spec/[^"/]+/epics/\*/stories/\*\.md"', 'glob = "spec/*/epics/*/stories/*.md"'),
        (r'levels = \["epic"\]', 'levels = ["capability", "epic"]'),
    ]
    for pattern, replacement in patterns:
        text, count = re.subn(pattern, replacement, text, count=1)
        if not count:
            raise SystemExit(f"installer config changed shape; expected {pattern!r}")
    text = _set_key(text, "project", "name", '"Sample Notes"')
    text = _set_key(text, "render", "title", '"Sample Notes"')
    text = _set_key(text, "activity", "path", '"vizzer/active-work.json"')
    for section in ("developer_flow", "workstreams", "reviews"):
        text = _set_key(text, section, "enabled", "true")
    config.write_text(text, encoding="utf-8")


def _set_key(text: str, section: str, key: str, value: str) -> str:
    """Replace the first `key = ...` line inside `[section]` of the installer's TOML."""
    lines = text.splitlines(keepends=True)
    inside = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            inside = stripped == f"[{section}]"
        elif inside and stripped.startswith(f"{key} ="):
            lines[index] = f"{key} = {value}\n"
            return "".join(lines)
    raise SystemExit(f"installer config has no {key} in [{section}]")


def review_plan(root: Path) -> dict:
    """One acceptance row for the Search filters story, run in a browser."""
    story_id, rel = REVIEW_STORY
    source = root / rel
    return {
        "schema": 1, "id": "search-filters", "title": "Search filters acceptance",
        "description": "Repeat the story's definition of done against the running app.",
        "rows": [{
            "id": "filter-by-tag", "title": "Filter results by tag",
            "source": {"itemId": story_id, "path": rel, "adapter": "spec-tree",
                       "fingerprint": hashlib.sha256(source.read_bytes()).hexdigest()},
            "definitionOfDone": ["Narrow results by tag, author, or date."],
            "steps": [{
                "id": "apply-tag", "instruction": "Search for 'roadmap' and choose the #planning tag.",
                "expected": "Only notes tagged #planning remain.", "mode": "browser",
                "adapter": "browser", "operation": "open-route", "inputs": {"route": "/search"},
            }],
            "evidenceRequirements": [{"id": "filtered", "kind": "screenshot",
                                      "afterStepIds": ["apply-tag"], "required": True}],
        }],
    }


ADAPTERS = {"schema": 1, "adapters": [{
    "id": "browser", "modes": ["browser"],
    "operations": [{"id": "open-route", "requiredInputs": ["route"]}],
}]}


if __name__ == "__main__":
    write(Path(sys.argv[1]))
