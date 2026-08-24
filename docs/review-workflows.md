# Repeatable review workflows

Vizzer review data keeps four claims separate:

1. the source Definition of Done;
2. the ordered procedure derived from it;
3. an agent's execution and evidence;
4. the owner's independent repetition and verdict.

That separation is the contract. A screenshot can show what an agent considered done, but it does
not certify the Definition of Done, and an owner pass does not rewrite or replace the machine run.

The implementation starts in `vizzer.review_contract`. It is dependency-free and host-neutral; UI,
browser, local-app, and CI integrations sit on top through named adapter operations.

## Authored plan

A schema-1 plan contains one or more rows. Every row names its source item and source fingerprint,
quotes the applicable Definition of Done, provides an ordered procedure, and declares its evidence
requirements.

```json
{
  "schema": 1,
  "id": "account-review",
  "title": "Account settings review",
  "rows": [{
    "id": "save-name",
    "title": "A saved display name survives reload",
    "source": {
      "itemId": "story:save-display-name",
      "path": "spec/account/save-display-name.md",
      "fingerprint": "<lowercase sha256>",
      "adapter": "spec-tree"
    },
    "definitionOfDone": [
      "The saved display name remains after a full reload."
    ],
    "steps": [{
      "id": "open-settings",
      "instruction": "Open account settings in the prepared session.",
      "expected": "The display-name field is visible.",
      "mode": "browser",
      "adapter": "browser",
      "operation": "open-route",
      "inputs": {"route": "/settings/account"}
    }, {
      "id": "save-and-reload",
      "instruction": "Change the display name, save, and reload the page.",
      "expected": "The new name remains after reload.",
      "mode": "manual"
    }],
    "evidenceRequirements": [{
      "id": "done-state",
      "kind": "screenshot",
      "afterStepIds": ["save-and-reload"],
      "required": true,
      "description": "Capture the state the agent considers complete."
    }]
  }]
}
```

`mode` is one of `manual`, `browser`, `local-app`, `http`, or `command`. Automation is an optional
named `adapter` + `operation` + JSON `inputs` request. Plans cannot embed raw command text. A host
may map an operation to a command in trusted configuration, but the review artifact itself is data,
not an executable script. Browser and local-app rows must require screenshot evidence.

## Run ledger

Agent and owner runs use the same event shape and append to one CAS-protected schema-1 ledger per
plan fingerprint. This keeps revisions and corruption domains independent when a project has
several plans, and lets a revised DoD start a fresh acceptance epoch without rewriting or trying to
reinterpret historical runs under a new procedure. An
event cites the normalized plan fingerprint, covers every step exactly once and in authored order,
and records `pass`, `fail`, `blocked`, or `skipped` for both steps and the overall verdict.

Agent `pass` requires every step to pass and every required evidence slot to be populated. Owner
runs are independent: they repeat every step but may validate without uploading a second screenshot.
Only an owner-facing surface may set `actor.kind` to `owner`; agent/CLI code must leave
`allow_owner` false. Every owner event must name `basedOnAgentEventId`, and append requires it to
be the latest preceding agent run for the same row. An older screenshot cannot be quietly approved
after a newer agent run supersedes it.

Evidence references contain a project-relative path, byte length, and SHA-256. Screenshot evidence
may additionally record media type and dimensions. `verify_evidence_file` rejects absolute and
parent-relative paths, symlink traversal, non-regular files, oversize files, hash/length mismatch,
and malformed PNG/JPEG/WebP bytes. It derives image dimensions without `sips`, Pillow, or another
host-specific dependency. `append_run` requires the project root and performs this verification for
every attached artifact before it publishes an event; callers cannot opt into a metadata-only pass.
It also reopens the cited source, checks its fingerprint, and requires every quoted DoD entry
verbatim in that source. For Markdown sources, the entry must occur inside the authored Definition
of Done/acceptance-test section recognized by the shared story-detail adapter; mentioning an easier
claim elsewhere in the file cannot impersonate the contract.

## Adapter boundary

Core validates contracts and preserves records. Optional adapters own side effects:

| Capability | Core request | Adapter responsibility |
|---|---|---|
| Browser | operation + JSON inputs | open/navigate an approved local or configured origin; capture the intended page/window |
| Local app | operation + JSON inputs | stage mutable fixtures when needed, launch/focus the app, identify the correct window |
| HTTP | operation + JSON inputs | enforce origin, method, credential, and response-size policy |
| Command | operation + JSON inputs | map a predeclared operation to argv; never interpolate an authored shell string |
| Evidence store | repo-relative reference + digest | create exclusively, enforce budgets, then return immutable metadata |

When the review service loads a plan with adapter operations, it also loads the schema-1 registry
at `reviews.adapters_path`. The registry declares adapter ids, supported modes, operation ids, and
required/optional JSON input names. It deliberately cannot contain `argv`, shell, credentials, or
an executable implementation. The actual browser/local/HTTP harness remains a host integration;
the registry prevents a plan from quietly inventing operations or smuggling extra inputs into it.

## Project service and owner loop

Reviews are opt-in:

```toml
[reviews]
enabled = true
plans_dir = "vizzer/reviews/plans"
runs_dir = "vizzer/reviews/runs"
evidence_dir = "vizzer/reviews/evidence"
adapters_path = "vizzer/reviews/adapters.json"
```

The three storage directories must be distinct, contained, and non-overlapping. Plan files are
bounded JSON documents discovered directly under `plans_dir`. Evidence attached to a service run
must live under `evidence_dir`; the served API exposes opaque plan/event/requirement URLs instead
of caller-supplied paths and rechecks the bytes before delivery.

Evidence stays project-local and may contain sensitive screen content. Capture integrations must
stage or redact credentials, personal data, notifications, unrelated windows, and environment
paths before recording an artifact. Vizzer does not pretend it can infer which pixels are secrets.
The loopback server rejects non-loopback `Host` headers (including DNS-rebinding requests), applies
same-origin resource policy to evidence, and never turns a shared Developer Flow URL into a public
evidence URL.

An agent records its completed event with:

```console
python3 vizzer/engine review record --plan account-review \
  --file review-event.json --expected-revision 0
python3 vizzer/engine review show
```

`review record` refuses owner actors. Owners use the **Reviews** view under `vizzer serve`, inspect
the agent's latest evidence, repeat every ordered step, choose a step outcome, and append their own
event. Same-origin/CSRF checks and revision CAS protect the write. File-mode output explains that
it is read-only rather than offering a fake validation control.

The title bar also owns the shared 14/18/22-point sidebar reading preference. It changes sidebar
prose and the dossier/layer detail text but leaves chips and pills fixed. The left rail has a
keyboard- and pointer-resizable separator; both preferences are session-scoped per project view.

The IllTool fork's `.illtool` packages, Application Support paths, LaunchServices commands, Preview
annotation flow, XCUITest selectors, and screenshot queue remain host adapters. They are useful
evidence for the interface, not defaults in upstream Vizzer.
