import json

import pytest

from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Graph, Item, Milestone, MilestonePhase
from vizzer.planning import (
    PlanningError, StaleRevisionError, analyze_change, apply_change,
    read_overlay, undo_change,
)
from vizzer.priority import apply_priorities


def _item(name, deps=(), *, status="specced", release="V1"):
    return Item(
        id=f"story:{name}", title=name, status=status, release=release,
        deps=[f"story:{dep}" for dep in deps], appetite="small",
    )


def _cfg(tmp_path, *, manifest=True):
    priority = {
        "enabled": True,
        "target_items": ["story:v1"] if not manifest else [],
        "target_manifest": "vizzer/v1-targets.json" if manifest else "",
        "limit": 2,
    }
    cfg = Config(data=deep_merge(DEFAULTS, {
        "priority": priority,
        "planning": {"enabled": True, "overlay_path": "vizzer/planning-overlay.json"},
    }))
    if manifest:
        path = tmp_path / "vizzer/v1-targets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": 1, "directTargetIds": ["story:v1"]}))
    return cfg


def _graph():
    return Graph(
        items=[
            _item("base"), _item("v1", ["base"]),
            _item("new-base"), _item("new", ["new-base"], release="V2"),
        ],
        milestones=[Milestone(
            id="M1", title="V1",
            phases=[MilestonePhase(name="floor", items=["story:v1"])],
        )],
    )


def test_overlay_composes_with_manifest_without_overwriting_it(tmp_path):
    graph = _graph()
    cfg = _cfg(tmp_path)
    apply_change(
        graph, cfg, tmp_path,
        {"promote": ["story:new"], "defer": ["story:v1"], "order": ["story:new"]},
        expected_revision=0, rationale="Explore V2 path first",
    )

    apply_priorities(graph, cfg, tmp_path)

    assert graph.priority["base_targets"] == ["story:v1"]
    assert graph.priority["effective_targets"] == ["story:new"]
    assert graph.priority["planning"]["revision"] == 1
    assert graph.priority["planning"]["author"] == "owner"
    assert graph.priority["planning"]["rationale"] == "Explore V2 path first"
    assert graph.priority["recommendations"] == ["story:new-base"]
    manifest = json.loads((tmp_path / "vizzer/v1-targets.json").read_text())
    assert manifest["directTargetIds"] == ["story:v1"]


def test_analysis_reports_dependency_readiness_opportunity_and_release_delta(tmp_path):
    graph = _graph()
    cfg = _cfg(tmp_path)
    apply_priorities(graph, cfg, tmp_path)

    analysis = analyze_change(graph, cfg, tmp_path, {
        "promote": ["story:new"], "defer": ["story:v1"], "order": ["story:new"],
    })

    assert analysis["delta"]["newPrerequisites"] == ["story:new-base"]
    assert analysis["delta"]["removedPrerequisites"] == ["story:base"]
    assert analysis["opportunityCost"]["displacedCurrentV1Targets"] == ["story:v1"]
    assert analysis["recommendations"]["before"] == ["story:base"]
    assert analysis["recommendations"]["after"] == ["story:new-base"]
    assert analysis["releaseImplications"]["affectedReleases"] == ["V1", "V2"]
    assert analysis["baseRevision"] == 0
    assert analysis["generatedAt"].endswith("Z")


def test_unknown_malformed_and_escaping_overlays_fail_closed(tmp_path):
    graph = _graph()
    cfg = _cfg(tmp_path, manifest=False)
    overlay = tmp_path / "vizzer/planning-overlay.json"
    overlay.parent.mkdir(exist_ok=True)
    overlay.write_text("{bad json")
    with pytest.raises(PlanningError, match="Expecting"):
        read_overlay(cfg, tmp_path, graph)

    overlay.write_text(json.dumps({
        "schema": 1, "revision": 0,
        "state": {"promote": ["story:missing"], "defer": [], "order": []},
        "history": [],
    }))
    with pytest.raises(PlanningError, match="unknown planning item"):
        read_overlay(cfg, tmp_path, graph)

    escaping = Config(data=deep_merge(cfg.data, {
        "planning": {"overlay_path": "../planning.json"},
    }))
    with pytest.raises(PlanningError, match="escapes"):
        read_overlay(escaping, tmp_path, graph)

    real = tmp_path / "vizzer/real-overlay.json"
    real.write_text(json.dumps({
        "schema": 1, "revision": 0, "state": {"promote": [], "defer": [], "order": []},
        "history": [],
    }))
    overlay.unlink()
    overlay.symlink_to(real)
    with pytest.raises(PlanningError, match="symlink"):
        read_overlay(cfg, tmp_path, graph)


def test_stale_revision_cannot_overwrite_and_undo_is_an_audited_revision(tmp_path):
    graph = _graph()
    cfg = _cfg(tmp_path, manifest=False)
    first = apply_change(
        graph, cfg, tmp_path,
        {"promote": ["story:new"], "defer": [], "order": ["story:new"]},
        expected_revision=0, rationale="Try the new lane",
    )
    assert first["revision"] == 1

    with pytest.raises(StaleRevisionError, match="current is 1"):
        apply_change(
            graph, cfg, tmp_path,
            {"promote": [], "defer": [], "order": []},
            expected_revision=0, rationale="stale browser tab",
        )

    undone = undo_change(
        graph, cfg, tmp_path, expected_revision=1,
        rationale="Restore the previous course",
    )
    assert undone["revision"] == 2
    assert undone["state"] == {"promote": [], "defer": [], "order": []}
    assert [entry["revision"] for entry in undone["history"]] == [0, 1, 2]
    assert undone["history"][-1]["rationale"] == "Restore the previous course"


def test_order_changes_uptake_without_making_blocked_story_ready(tmp_path):
    graph = Graph(items=[
        _item("left-base"), _item("left", ["left-base"]),
        _item("right-base"), _item("right", ["right-base"]),
    ])
    cfg = _cfg(tmp_path, manifest=False)
    cfg.data["priority"]["target_items"] = ["story:left", "story:right"]
    apply_priorities(
        graph, cfg, tmp_path,
        overlay_state={"promote": [], "defer": [], "order": ["story:right", "story:left"]},
    )

    assert graph.priority["recommendations"] == ["story:right-base", "story:left-base"]
    assert graph.item_map()["story:right"].priority["eligible"] is False
    assert "unready" in graph.item_map()["story:right"].priority["rationale"]


def test_analysis_warns_when_order_has_no_target_and_done_promotion_has_no_effect(tmp_path):
    graph = _graph()
    graph.item_map()["story:new"].status = "shipped"
    cfg = _cfg(tmp_path)
    apply_priorities(graph, cfg, tmp_path)

    analysis = analyze_change(graph, cfg, tmp_path, {
        "promote": ["story:new"], "defer": [], "order": ["story:new-base"],
    })

    assert "story:new" not in analysis["recommendations"]["after"]
    assert any("already done" in warning for warning in analysis["warnings"])
    assert any("not an effective target" in warning for warning in analysis["warnings"])
