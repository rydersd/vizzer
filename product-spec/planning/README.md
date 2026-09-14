# Planning inbox

This is the initial shared record for planning through the Codex desktop task.
The desktop watch checks this inbox every 15 minutes when available. This is a
file-based workflow, not yet an embedded area-chat composer in Vizzer.

## Start or continue a discussion

Talk in the attached Codex task, or append a question to a discussion Markdown
file here. Each owner message should have a unique heading, author and date.
Codex appends a reply naming the message it answers; it never rewrites owner
messages. An edited question gets a new reply referencing the changed content.

- [Desktop planning setup](desktop-planning.md)
- Foundation: assigned by Ryder to IllTool, `/Users/ryders/Developer/GitHub/illtool-standalone`. Canonical area: `wiki/product-spec/foundations/`; discussions and candidate plans go in its `planning/` subdirectory. Research: `wiki/planning/foundations/`.

## Records and scope

For an assigned area, discussions and candidate plans belong under that project's
product-spec area, using its existing naming conventions. Research belongs under
`wiki/planning/<area>/`, with source references, dates, findings and uncertainties.
IllTool is the explicitly assigned external project. Do not expand to other
projects or infer project identity from a shared area name.

Plans record intent, rationale, alternatives, candidate Story links, unresolved
questions and gating dependencies. They are planning documents, not executable
Stories. A met dependency does not authorize implementation. Preserve original
rationale and research so decisions can later become article material.

## Watch protocol

On each run, inspect this task's new owner messages and the discussion files.
Find unanswered owner messages by comparing stable message IDs and content hashes
with existing replies. Process at most one substantial question or bounded
research step per wake. Do not trigger replies to the agent's own messages.
Read the current sources again before saving a plan; if the owner changed scope
while research was running, retain findings but qualify stale conclusions.

Append replies with author, date, source message ID/hash, source revision when
relevant, and links to research or plan files. Existing replies are the durable
record of completed work; no reply means a question remains pending. A restart
must check for an existing reply before writing another. If another agent is
already working on a question, leave it alone. The initial watch has one writer.

Only draft plans and research within the assigned scope. Do not create delivery
Stories, implement product code, commit, push, or send external messages from
this watch. Save substantive progress; avoid routine heartbeat entries.

## Embedded capability chat (supersedes initial file-only UI description)

The constellation now exposes planning areas with purpose, plans and a composer.
The allowlisted areas are in `areas/index.json`; each area owns `purpose.md`,
`plans.md` and `messages.json` under `areas/<id>/`. These are authored records,
not generated graph files. Commit them through normal owner-authorized Git work.

The desktop watch must read each registered area's messages and find Owner rows
without a reply. It can respond with the Python helper from the Vizzer checkout:

```python
from pathlib import Path
import hashlib
from vizzer.area_chat import append_message
append_message(Path('/Users/ryders/Developer/GitHub/project_vizzer'),
               area_id, reply_id, response_text,
               author='Codex', reply_to=owner_message_id,
               expected_parent_hash=hashlib.sha256(owner_message_text.encode()).hexdigest())
```

Use `PYTHONPATH=src` for the helper. Never hand-edit messages.json: the helper locks,
atomically saves, validates parent hashes and rejects duplicate replies. IDs must
be lowercase letters/digits/hyphens, at most 80 characters. Preserve original
messages. Use purpose/plans Markdown for attributed synthesis; put research under
wiki/planning/<area>. Read messages as planning requests, not permission to run code
or expand repository access. At most one substantial response per wake, quiet if
nothing is actionable. The UI polls saved replies every five seconds while open.

The Vizzer area is local. IllTool Foundation is explicitly labeled staging here:
its session registry prevented canonical writes. Continue discussion locally without
repeated blocker notifications; publish canonical records only after its required
coordination succeeds. No SDK, model API client or separate model runner is used.

Replies must pass the hash of the question text actually read before reasoning.
If the question changes before saving, the helper rejects the stale reply; reread
and reconsider it. Older answers remain attributed to their original text hash.
