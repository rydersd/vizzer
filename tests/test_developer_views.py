import json

import pytest

from vizzer.config import Config
from vizzer.developer_views import (
    DeveloperViewError, delete_view, empty_view_store, load_view_store,
    parse_view_document, upsert_view,
)


def cfg():
    return Config(data={
        "developer_flow": {
            "enabled": True,
            "views_path": "vizzer/developer-views.json",
        },
    })


def document(identity="view-one"):
    return {
        "schema": 1,
        "id": identity,
        "name": "Release readiness",
        "view": {
            "schema": 1, "scope": "group", "id": "capability:drawing",
            "direction": "RIGHT", "selectedId": "story:canvas",
            "filters": {
                "query": "blocked", "kind": "story", "status": "building",
                "group": "capability:drawing", "relationKinds": ["depends-on"],
            },
        },
        "notes": "Confirm the dependency fan-out with the release owner.",
        "annotationsVisible": False,
        "annotations": [
            {"id": "note-one", "kind": "note", "color": "yellow",
             "x": 120, "y": 240, "text": "This dependency is disputed.",
             "objectId": "story:canvas"},
            {"id": "stroke-one", "kind": "stroke", "color": "pink", "width": 4,
             "points": [[10, 20], [15.5, 24], [22, 31]]},
        ],
    }


def test_view_document_preserves_notes_object_annotations_and_strokes():
    parsed = parse_view_document(document())
    assert parsed["view"]["scope"] == "group"
    assert parsed["notes"].startswith("Confirm")
    assert parsed["annotations"][0]["objectId"] == "story:canvas"
    assert parsed["annotations"][1]["points"][1] == [15.5, 24.0]
    assert parsed["annotationsVisible"] is False


def test_view_document_defaults_legacy_annotation_visibility_to_visible():
    value = document()
    del value["annotationsVisible"]
    assert parse_view_document(value)["annotationsVisible"] is True


@pytest.mark.parametrize("mutation, message", [
    (lambda value: value.update(extra=True), "unknown or missing field"),
    (lambda value: value["annotations"].append(value["annotations"][0]), "ids must be unique"),
    (lambda value: value["annotations"][1].update(width=99), "width must be"),
    (lambda value: value["annotations"][1].update(points=[[0, 0]]), "needs 2 through"),
    (lambda value: value["view"].update(scope="object", id=""), "needs an id"),
])
def test_view_document_rejects_ambiguous_or_unbounded_state(mutation, message):
    value = document()
    mutation(value)
    with pytest.raises(DeveloperViewError, match=message):
        parse_view_document(value)


def test_view_store_is_atomic_revisioned_and_deletable(tmp_path):
    assert load_view_store(cfg(), tmp_path) == empty_view_store()
    first = upsert_view(
        cfg(), tmp_path, document(), expected_revision=0,
        now="2026-08-24T01:00:00Z",
    )
    assert first["revision"] == 1
    assert first["views"][0]["updatedAt"] == "2026-08-24T01:00:00Z"

    changed = document()
    changed["notes"] = "Updated note"
    second = upsert_view(
        cfg(), tmp_path, changed, expected_revision=1,
        now="2026-08-24T01:02:00Z",
    )
    assert second["revision"] == 2
    assert len(second["views"]) == 1
    assert second["views"][0]["notes"] == "Updated note"

    with pytest.raises(DeveloperViewError, match="stale"):
        upsert_view(cfg(), tmp_path, document("second"), expected_revision=1)

    final = delete_view(cfg(), tmp_path, "view-one", expected_revision=2)
    assert final == {"schema": 1, "revision": 3, "views": []}
    persisted = json.loads(
        (tmp_path / "vizzer" / "developer-views.json").read_text()
    )
    assert persisted == final


def test_view_store_rejects_symlinked_authority(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "vizzer").symlink_to(outside, target_is_directory=True)
    with pytest.raises(DeveloperViewError, match="symlink"):
        load_view_store(cfg(), tmp_path)
