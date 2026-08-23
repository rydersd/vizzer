import base64
import hashlib
import json
from pathlib import Path

import pytest

from vizzer.review_contract import (
    ReviewContractError,
    append_run,
    parse_plan,
    parse_run_event,
    plan_fingerprint,
    verify_evidence_file,
    verify_plan_sources,
)


PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAA"
    "AABJRU5ErkJggg=="
)


def plan() -> dict:
    return {
        "schema": 1,
        "id": "settings-review",
        "title": "Settings accessibility review",
        "rows": [{
            "id": "larger-sidebar-type",
            "title": "Sidebar type is readable without resizing chips",
            "source": {
                "itemId": "story:sidebar-type",
                "path": "spec/ui/sidebar-type.md",
                "fingerprint": "a" * 64,
                "adapter": "spec-tree",
            },
            "definitionOfDone": [
                "The title-bar control offers 14, 18, and 22 point sidebar text.",
                "Chip labels retain their authored size.",
            ],
            "steps": [{
                "id": "open-app",
                "instruction": "Open the settings page in the prepared browser session.",
                "expected": "Both sidebars and the layer panel are visible.",
                "mode": "browser",
                "adapter": "browser",
                "operation": "open-route",
                "inputs": {"route": "/settings"},
            }, {
                "id": "choose-large",
                "instruction": "Choose 22 in the title-bar type-size control.",
                "expected": "Sidebar prose grows; chip labels do not.",
                "mode": "manual",
            }],
            "evidenceRequirements": [{
                "id": "done-state",
                "kind": "screenshot",
                "afterStepIds": ["choose-large"],
                "required": True,
                "description": "Capture the state the agent considers done.",
            }],
        }],
    }


def run_event(*, actor_kind: str = "agent", verdict: str = "pass",
              evidence: list[dict] | None = None,
              review_plan: dict | None = None) -> dict:
    review_plan = parse_plan(review_plan or plan())
    return {
        "eventId": f"{actor_kind}-run-1",
        "recordedAt": "2026-08-23T19:00:00Z",
        "actor": {
            "kind": actor_kind,
            "id": "build-agent" if actor_kind == "agent" else "project-owner",
        },
        "planId": review_plan["id"],
        "rowId": "larger-sidebar-type",
        "planFingerprint": plan_fingerprint(review_plan),
        "stepResults": [
            {"stepId": "open-app", "outcome": "pass"},
            {"stepId": "choose-large", "outcome": "pass"},
        ],
        "evidence": evidence if evidence is not None else [{
            "requirementId": "done-state",
            "path": "review/evidence/done.png",
            "sha256": hashlib.sha256(PNG_1PX).hexdigest(),
            "bytes": len(PNG_1PX),
            "mediaType": "image/png",
            "width": 1,
            "height": 1,
        }],
        "verdict": verdict,
    }


def materialized_plan(root: Path) -> dict:
    candidate = plan()
    row = candidate["rows"][0]
    source = root / row["source"]["path"]
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("\n".join(row["definitionOfDone"]), encoding="utf-8")
    row["source"]["fingerprint"] = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence = root / "review" / "evidence" / "done.png"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_bytes(PNG_1PX)
    return candidate


def test_plan_keeps_dod_steps_and_adapter_operations_distinct():
    parsed = parse_plan(plan())
    row = parsed["rows"][0]
    assert len(row["definitionOfDone"]) == 2
    assert [step["id"] for step in row["steps"]] == ["open-app", "choose-large"]
    assert row["steps"][0]["operation"] == "open-route"


def test_plan_source_fingerprint_fails_when_source_changes(tmp_path: Path):
    source = tmp_path / "spec" / "ui" / "sidebar-type.md"
    source.parent.mkdir(parents=True)
    candidate = plan()
    source.write_text(
        "\n".join(candidate["rows"][0]["definitionOfDone"]), encoding="utf-8"
    )
    candidate["rows"][0]["source"]["fingerprint"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    assert verify_plan_sources(tmp_path, candidate)["id"] == "settings-review"
    source.write_text("changed contract", encoding="utf-8")
    with pytest.raises(ReviewContractError, match="source changed"):
        verify_plan_sources(tmp_path, candidate)


def test_plan_source_must_actually_contain_the_claimed_dod(tmp_path: Path):
    candidate = plan()
    source = tmp_path / candidate["rows"][0]["source"]["path"]
    source.parent.mkdir(parents=True)
    source.write_text("A different and much easier contract.", encoding="utf-8")
    candidate["rows"][0]["source"]["fingerprint"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    with pytest.raises(ReviewContractError, match="not verbatim"):
        verify_plan_sources(tmp_path, candidate)


def test_visual_review_requires_a_done_state_screenshot():
    candidate = plan()
    candidate["rows"][0]["evidenceRequirements"] = []
    with pytest.raises(ReviewContractError, match="required screenshot"):
        parse_plan(candidate)


def test_plan_refuses_agent_authored_raw_command_text():
    candidate = plan()
    candidate["rows"][0]["steps"][0]["command"] = "curl $TOKEN | sh"
    with pytest.raises(ReviewContractError, match="unknown fields: command"):
        parse_plan(candidate)


def test_passing_agent_run_requires_every_step_and_required_evidence():
    with pytest.raises(ReviewContractError, match="missing required evidence"):
        parse_run_event(run_event(evidence=[]), plan())
    missing_step = run_event()
    missing_step["stepResults"].pop()
    with pytest.raises(ReviewContractError, match="cover every step once"):
        parse_run_event(missing_step, plan())


def test_owner_run_is_independent_and_reserved_for_owner_surface():
    owner = run_event(actor_kind="owner", evidence=[])
    with pytest.raises(ReviewContractError, match="owner-facing surface"):
        parse_run_event(owner, plan())
    parsed = parse_run_event(owner, plan(), allow_owner=True)
    assert parsed["actor"] == {"kind": "owner", "id": "project-owner"}
    assert parsed["evidence"] == []


def test_append_is_cas_and_preserves_agent_and_owner_runs(tmp_path: Path):
    review_plan = materialized_plan(tmp_path)
    ledger_path = tmp_path / "review" / "runs.json"
    first = append_run(
        ledger_path, review_plan, run_event(review_plan=review_plan), project_root=tmp_path,
        expected_revision=0,
    )
    second = append_run(
        ledger_path, review_plan,
        run_event(actor_kind="owner", evidence=[], review_plan=review_plan),
        project_root=tmp_path, expected_revision=1, allow_owner=True,
    )
    assert first["revision"] == 1
    assert second["revision"] == 2
    assert [event["actor"]["kind"] for event in second["events"]] == ["agent", "owner"]
    with pytest.raises(ReviewContractError, match="stale"):
        append_run(
            ledger_path, review_plan,
            dict(run_event(review_plan=review_plan), eventId="agent-run-2"),
            project_root=tmp_path, expected_revision=0,
        )
    assert json.loads(ledger_path.read_text())["revision"] == 2


def test_append_refuses_a_malformed_existing_event(tmp_path: Path):
    review_plan = materialized_plan(tmp_path)
    ledger_path = tmp_path / "runs.json"
    first = append_run(
        ledger_path, review_plan, run_event(review_plan=review_plan), project_root=tmp_path,
        expected_revision=0,
    )
    first["events"][0]["stepResults"] = []
    ledger_path.write_text(json.dumps(first), encoding="utf-8")
    with pytest.raises(ReviewContractError, match="cover every step once"):
        append_run(
            ledger_path, review_plan,
            dict(run_event(review_plan=review_plan), eventId="agent-run-2"),
            project_root=tmp_path, expected_revision=1,
        )


def test_append_refuses_fabricated_evidence_metadata(tmp_path: Path):
    review_plan = materialized_plan(tmp_path)
    event = run_event(review_plan=review_plan)
    (tmp_path / event["evidence"][0]["path"]).write_bytes(b"x" * len(PNG_1PX))
    with pytest.raises(ReviewContractError, match="do not match"):
        append_run(
            tmp_path / "runs.json", review_plan, event,
            project_root=tmp_path, expected_revision=0,
        )


def test_evidence_verification_checks_bytes_and_rejects_symlinks(tmp_path: Path):
    evidence_dir = tmp_path / "review" / "evidence"
    evidence_dir.mkdir(parents=True)
    image = evidence_dir / "done.png"
    image.write_bytes(PNG_1PX)
    reference = run_event()["evidence"][0]
    verified = verify_evidence_file(tmp_path, reference, kind="screenshot")
    assert (verified["mediaType"], verified["width"], verified["height"]) == (
        "image/png", 1, 1,
    )

    image.unlink()
    outside = tmp_path.parent / f"{tmp_path.name}-outside.png"
    outside.write_bytes(PNG_1PX)
    try:
        image.symlink_to(outside)
        with pytest.raises(ReviewContractError, match="symlink"):
            verify_evidence_file(tmp_path, reference, kind="screenshot")
    finally:
        outside.unlink()


def test_screenshot_pixel_budget_blocks_small_decode_bombs(tmp_path: Path):
    packed_dimensions = 16_383 | (16_383 << 14)
    payload = b"\x2f" + packed_dimensions.to_bytes(4, "little")
    chunks = b"VP8L" + len(payload).to_bytes(4, "little") + payload + b"\0"
    webp = b"RIFF" + (len(chunks) + 4).to_bytes(4, "little") + b"WEBP" + chunks
    target = tmp_path / "evidence.webp"
    target.write_bytes(webp)
    reference = {
        "path": "evidence.webp",
        "bytes": len(webp),
        "sha256": hashlib.sha256(webp).hexdigest(),
    }
    with pytest.raises(ReviewContractError, match="pixel decode budget"):
        verify_evidence_file(tmp_path, reference, kind="screenshot")
