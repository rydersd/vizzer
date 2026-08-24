import json

from vizzer.adapters import conflicts
from vizzer.config import Config, DEFAULTS, deep_merge


def _cfg():
    return Config(data=deep_merge(DEFAULTS, {
        "status": [
            {"name": "queued", "role": "ready", "done": False},
            {"name": "working", "role": "active", "done": False},
            {"name": "finished", "role": "done", "done": True},
        ],
        "sources": {"conflicts": {
            "enabled": True, "path": "records/conflicts.json",
        }},
    }))


def _record(state="open"):
    value = {
        "id": f"conflict:{state}-route",
        "title": f"{state.title()} route",
        "status": state,
        "type": "rule-vs-rule",
        "priority": "p1",
        "objects": [
            {"kind": "rule", "ref": "spec:a", "claim": "A must hold."},
            {"kind": "rule", "ref": "spec:b", "claim": "B forbids A."},
        ],
        "collision": "A and B cannot both hold.",
        "options": [
            {"id": "a", "label": "A", "tradeoff": "Lose B."},
            {"id": "b", "label": "B", "tradeoff": "Lose A."},
        ],
    }
    if state != "open":
        value["decision"] = {
            "optionId": "a", "by": "owner", "at": "2026-08-08",
            "rationale": "A is authoritative.",
        }
    return value


def test_conflicts_map_semantic_states_to_project_status_vocabulary(tmp_path):
    path = tmp_path / "records/conflicts.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "schema": 1,
        "conflicts": [_record("open"), _record("decided"), _record("applied")],
    }), encoding="utf-8")

    result = conflicts.scan(_cfg(), tmp_path)
    by_state = {item.facets["conflict-state"][0]: item for item in result.items}

    assert result.warnings == []
    assert {state: item.status for state, item in by_state.items()} == {
        "open": "queued", "decided": "working", "applied": "finished",
    }
    assert all(item.role == "decision" for item in result.items)
    assert result.groups[0].id == "conflicts:decisions"


def test_conflicts_fail_closed_on_ambiguous_or_unactionable_records(tmp_path):
    path = tmp_path / "records/conflicts.json"
    path.parent.mkdir()
    invalid = _record("open")
    invalid["options"] = []
    malformed = _record("applied")
    malformed.pop("decision")
    path.write_text(json.dumps({
        "schema": 1, "conflicts": [invalid, malformed],
    }), encoding="utf-8")

    result = conflicts.scan(_cfg(), tmp_path)

    assert result.items == [] and result.groups == []
    assert any("needs 2 or 3 options" in warning for warning in result.warnings)
    assert any("requires a recorded decision" in warning for warning in result.warnings)


def test_conflicts_reject_duplicate_json_keys(tmp_path):
    path = tmp_path / "records/conflicts.json"
    path.parent.mkdir()
    path.write_text(
        '{"schema":1,"schema":1,"conflicts":[]}', encoding="utf-8"
    )

    result = conflicts.scan(_cfg(), tmp_path)

    assert result.items == []
    assert result.warnings == [
        "records/conflicts.json: duplicate JSON key 'schema'"
    ]
