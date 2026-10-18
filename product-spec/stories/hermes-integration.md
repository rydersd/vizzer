# Hermes Agent integration

> Status: specced
> Deps: [illtool-intake-2026-10](illtool-intake-2026-10.md)
> Release: R1
> Tags: agents, hermes, install

## Origin

Owner request 2026-10-17. Facts from Hermes Agent 2823fbe679
(`agent/prompt_builder.py`, `agent/skill_utils.py`, hooks and MCP docs).

Hermes loads exactly one project context type per session, first found wins:
`.hermes.md`/`HERMES.md` (cwd to git root), then the AGENTS.md chain (git root to
cwd), then CLAUDE.md (cwd only). A context file matching its injection patterns
is replaced wholesale by a `[BLOCKED]` marker. Project skills load from
`<root>/.agents/skills/` or `.hermes/skills/` only after `hermes skills trust`.
MCP servers and session-start hooks are profile config only. Tool subprocesses
receive `AI_AGENT=hermes-agent`, `HERMES_AGENT=true`, `HERMES_SESSION_ID`.

## Acceptance

- Registration reaches the file Hermes reads: when both CLAUDE.md and AGENTS.md
  exist, the managed block is written to both (or AGENTS.md references it);
  an existing `.hermes.md` also receives it. Today `install.py` prefers CLAUDE.md,
  which Hermes never reads when AGENTS.md is non-empty.
- The managed block passes Hermes's context injection scan.
- Install ships an agentskills.io-format skill at `.agents/skills/vizzer/SKILL.md`
  (also usable by other harnesses) and tells the owner the one-time
  `hermes skills trust` step; optional printed snippets for an
  `on_session_start` refresh hook and an MCP entry, never written into the
  owner's profile by Vizzer.
- Answers written from a Hermes session record provider provenance from the
  environment (`hermes-agent`, session id) without changing decision identity.

## Tests

1. Project with CLAUDE.md + AGENTS.md: block present in the file Hermes loads.
2. Managed block scanned with Hermes's `context` patterns yields no finding.
3. Answer recorded under `AI_AGENT=hermes-agent` carries Hermes provenance; same
   answer from another provider is the same decision.

## Test plan (RC)

Live Hermes session in an installed project: context visible, skill listed after
trust, refresh hook and MCP snippet exercised by the owner.
