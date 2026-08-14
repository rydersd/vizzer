from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Graph, Item, Milestone, MilestonePhase, Relation
from vizzer.priority import apply_priorities


def _cfg(**priority):
    return Config(data=deep_merge(DEFAULTS, {"priority": {
        "enabled": True,
        "target_items": ["story:v1"],
        "limit": 20,
        **priority,
    }}))


def _item(name, deps=(), *, status="specced", release="V1", appetite="small",
          flags=()):
    return Item(id=f"story:{name}", title=name, status=status, release=release,
                deps=[f"story:{dep}" for dep in deps], appetite=appetite,
                flags=list(flags))


def test_priority_is_explainable_and_uses_explicit_target_provenance():
    graph = Graph(items=[
        _item("foundation"),
        _item("middle", ["foundation"]),
        _item("v1", ["middle"]),
    ])

    apply_priorities(graph, _cfg())

    assert graph.priority["target_tier"] == "configured-items"
    assert graph.priority["targets"] == [
        {"item": "story:v1", "sources": ["configured-item"]}
    ]
    assert graph.priority["recommendations"] == ["story:foundation"]
    foundation = graph.item_map()["story:foundation"].priority
    assert foundation["components"]["target_dependents"] == 1
    assert foundation["components"]["critical_path_depth"] == 2
    assert "depth 2" in foundation["rationale"]
    # Middle and target are not ready; reach alone cannot smuggle them into uptake.
    assert graph.item_map()["story:middle"].priority["eligible"] is False
    assert "unready" in graph.item_map()["story:middle"].priority["rationale"]


def test_diamond_reach_counts_target_once():
    graph = Graph(items=[
        _item("root"),
        _item("left", ["root"]),
        _item("right", ["root"]),
        _item("v1", ["left", "right"]),
    ])

    apply_priorities(graph, _cfg())

    root = graph.item_map()["story:root"].priority
    assert root["components"]["target_dependents"] == 1
    assert root["target_items"] == ["story:v1"]


def test_authored_appetite_cannot_change_structural_priority():
    large = _item("a-large", appetite="large")
    small = _item("z-small", appetite="small")
    target = _item("v1", ["a-large", "z-small"])
    graph = Graph(items=[large, small, target])

    apply_priorities(graph, _cfg())

    assert large.priority["score"] == small.priority["score"]
    assert graph.priority["recommendations"][:2] == [large.id, small.id]
    assert "appetite" not in large.priority["rationale"]


def test_cycle_cannot_inflate_reach_or_depth():
    graph = Graph(items=[
        _item("entry"),
        _item("a", ["entry", "b"]),
        _item("b", ["a"]),
        _item("v1", ["b"]),
    ])

    apply_priorities(graph, _cfg())

    entry = graph.item_map()["story:entry"].priority
    assert entry["components"]["target_dependents"] == 1
    # entry -> condensed {a,b} -> v1: the cycle contributes one hop, not infinity.
    assert entry["components"]["critical_path_depth"] == 2


def test_unrelated_later_release_fanout_cannot_outrank_v1_chain():
    items = [_item("v1-root"), _item("v1", ["v1-root"])]
    items.append(_item("r3-root", release="R3"))
    items.extend(_item(f"r3-{index}", ["r3-root"], release="R3") for index in range(12))
    graph = Graph(items=items)

    apply_priorities(graph, _cfg())

    assert graph.priority["recommendations"] == ["story:v1-root"]
    assert graph.item_map()["story:r3-root"].priority["eligible"] is False
    assert "outside target dependency reach" in graph.item_map()["story:r3-root"].priority[
        "rationale"
    ]


def test_done_held_gated_flagged_and_unready_items_are_excluded():
    graph = Graph(items=[
        _item("v1"),
        _item("done", status="shipped"),
        _item("held", status="parked"),
        _item("gated"),
        _item("triage", flags=["triage"]),
        _item("unready", ["v1"]),
    ])
    cfg = Config(data=deep_merge(_cfg().data, {
        "priority": {"target_items": [
            "story:v1", "story:done", "story:held", "story:gated",
            "story:triage", "story:unready",
        ]},
        "gates": [{"item": "story:gated", "reason": "decision"}],
    }))

    apply_priorities(graph, cfg)

    assert graph.priority["recommendations"] == ["story:v1"]
    for item_id in ("story:done", "story:held", "story:gated", "story:triage",
                    "story:unready"):
        assert graph.item_map()[item_id].priority["eligible"] is False


def test_milestone_is_fallback_target_and_membership_is_scored():
    graph = Graph(
        items=[_item("floor")],
        milestones=[Milestone(
            id="M1", title="V1 floor",
            phases=[MilestonePhase(name="Floor", items=["story:floor"])],
        )],
    )
    cfg = _cfg(target_items=[])

    apply_priorities(graph, cfg)

    assert graph.priority["target_tier"] == "active-milestone"
    assert graph.item_map()["story:floor"].priority["components"]["milestone_member"] == 1


def test_target_manifest_is_strongest_and_validated(tmp_path):
    manifest = tmp_path / "vizzer" / "v1-targets.json"
    manifest.parent.mkdir()
    manifest.write_text(__import__("json").dumps({
        "schema": 1,
        "directTargetIds": ["story:v1", "story:v1", "story:unknown"],
    }))
    graph = Graph(items=[_item("v1"), _item("configured-but-not-manifest")])
    cfg = _cfg(
        target_manifest="vizzer/v1-targets.json",
        target_items=["story:configured-but-not-manifest"],
    )

    apply_priorities(graph, cfg, tmp_path)

    assert graph.priority["target_tier"] == "target-manifest"
    assert graph.priority["targets"] == [{
        "item": "story:v1",
        "sources": ["manifest:vizzer/v1-targets.json"],
    }]
    assert any("duplicates story:v1" in warning for warning in graph.warnings)
    assert any("story:unknown is unknown" in warning for warning in graph.warnings)


def test_target_manifest_cannot_escape_repo_or_fall_through(tmp_path):
    graph = Graph(items=[_item("v1")])
    cfg = _cfg(target_manifest="../outside.json")

    apply_priorities(graph, cfg, tmp_path)

    assert graph.priority["target_tier"] == "target-manifest"
    assert graph.priority["targets"] == []
    assert graph.priority["recommendations"] == []
    assert any("escapes the project root" in warning for warning in graph.warnings)


def test_long_dependency_chain_does_not_depend_on_python_recursion_limit():
    items = [_item("n0")]
    items.extend(_item(f"n{index}", [f"n{index - 1}"]) for index in range(1, 1200))
    graph = Graph(items=items)
    cfg = _cfg(target_items=["story:n1199"])

    apply_priorities(graph, cfg)

    assert graph.priority["recommendations"] == ["story:n0"]
    assert graph.item_map()["story:n0"].priority["components"][
        "critical_path_depth"
    ] == 1199


def test_defect_rank_inherits_known_blast_radius_from_bug_against_contract():
    contract = _item("contract", status="shipped")
    target = _item("v1", ["contract"])
    linked_gap = _item("linked-gap", status="bug-gap")
    linked_gap.relations = [Relation(kind="bug_against", target="story:contract")]
    isolated_gap = _item("isolated-gap", status="bug-gap")
    graph = Graph(items=[contract, target, linked_gap, isolated_gap])

    apply_priorities(graph, _cfg())

    linked = linked_gap.priority["defect"]
    isolated = isolated_gap.priority["defect"]
    assert linked["rank"] == 1
    assert linked["lineage"] == "bug-against"
    assert linked["affected_contracts"] == ["story:contract"]
    assert linked["target_items"] == ["story:v1"]
    assert linked["components"]["target_impact"] == 1
    assert isolated["rank"] == 2
    assert isolated["lineage"] == "story-only"
    assert "missing Bug against lineage" in isolated["rationale"]
    assert graph.priority["defects"] == ["story:linked-gap", "story:isolated-gap"]


def test_defect_rank_uses_graph_reach_without_calling_it_severity():
    wide = _item("wide", status="bug-gap")
    narrow = _item("narrow", status="bug-gap")
    graph = Graph(items=[
        wide,
        narrow,
        _item("wide-child", ["wide"], status="shipped"),
        _item("wide-grandchild", ["wide-child"], status="shipped"),
    ])

    apply_priorities(graph, _cfg(target_items=[]))

    wide_defect = wide.priority["defect"]
    narrow_defect = narrow.priority["defect"]
    assert wide_defect["rank"] < narrow_defect["rank"]
    assert wide_defect["components"]["total_dependents"] == 2
    assert wide_defect["components"]["incomplete_dependents"] == 0
    assert "severity" not in wide_defect["rationale"].lower()
