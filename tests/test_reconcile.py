# tests/test_reconcile.py
from vizzer.adapters import ScanResult
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Group, Item, Milestone, MilestonePhase, Relation
from vizzer.reconcile import build_graph

def _cfg():
    return Config(data=DEFAULTS)

def _item(id, adapter, path, **kw):
    source = kw.pop("source_override", {"adapter": adapter, "path": path})
    return Item(id=id, title=kw.pop("title", id), source=source, **kw)

def test_status_conflict_recorded_higher_precedence_wins(tmp_path):
    scans = [("spec_tree", ScanResult(items=[
        _item("story:a", "spec_tree", "s/a.md", status="building"),
        _item("story:a", "dag_import", "dag.json", status="specced", release="R1"),
    ]))]
    g = build_graph(_cfg(), tmp_path, scans)
    [a] = [i for i in g.items if i.id == "story:a"]
    assert a.status == "building" and a.release == "R1"      # conflict kept + gap filled
    assert g.conflicts == [{"item": "story:a", "field": "status",
                            "kept": {"adapter": "spec_tree", "value": "building"},
                            "dropped": {"adapter": "dag_import", "value": "specced"}}]


def test_tags_and_facets_union_while_role_disagreement_is_a_visible_conflict(tmp_path):
    scans = [("spec_tree", ScanResult(items=[
        _item("story:a", "spec_tree", "s/a.md", role="delivery",
              tags=["markdown"], facets={"product": ["notes"]}),
        _item("story:a", "dag_import", "dag.json", role="coverage",
              tags=["shared"], facets={
                  "product": ["core"], "capability": ["core/markdown"],
              }),
    ]))]

    graph = build_graph(_cfg(), tmp_path, scans)
    item = graph.item_map()["story:a"]

    assert item.role == "delivery"
    assert item.tags == ["markdown", "shared"]
    assert item.facets == {
        "product": ["notes", "core"],
        "capability": ["core/markdown"],
    }
    assert any(conflict["field"] == "role" for conflict in graph.conflicts)


def test_explicit_empty_story_dependencies_beat_imported_dag(tmp_path):
    """codex-sequence-2026-08-08: explicit [] is data, not a missing value."""
    scans = [("spec_tree", ScanResult(items=[
        _item("story:a", "spec_tree", "s/a.md", deps=[],
              source_override={"adapter": "spec_tree", "path": "s/a.md",
                               "deps_declared": True}),
        _item("story:a", "dag_import", "dag.json", deps=["story:b"]),
        _item("story:b", "spec_tree", "s/b.md"),
    ]))]

    graph = build_graph(_cfg(), tmp_path, scans)

    assert graph.item_map()["story:a"].deps == []


def test_configured_dag_dependency_authority_preserves_story_provenance(tmp_path):
    """codex-sequence-2026-08-08: bootstrap authority is field-specific."""
    cfg = Config(data=deep_merge(DEFAULTS, {
        "reconcile": {"dependency_authority": "dag_import"},
    }))
    scans = [("spec_tree", ScanResult(items=[
        _item("story:a", "spec_tree", "s/a.md", deps=["story:b"],
              source_override={"adapter": "spec_tree", "path": "s/a.md",
                               "deps_declared": True}),
        _item("story:a", "dag_import", "dag.json", deps=[]),
        _item("story:b", "spec_tree", "s/b.md"),
    ]))]

    graph = build_graph(cfg, tmp_path, scans)

    assert graph.item_map()["story:a"].deps == []
    assert graph.item_map()["story:a"].source["path"] == "s/a.md"

def test_file_claim_drops_lower_precedence_duplicate(tmp_path):
    scans = [("spec_tree", ScanResult(items=[_item("story:a", "spec_tree", "x.md")])),
             ("loose_docs", ScanResult(items=[_item("doc:x", "loose_docs", "x.md")]))]
    g = build_graph(_cfg(), tmp_path, scans)
    assert [i.id for i in g.items] == ["story:a"]

def test_dangling_dep_dropped_with_warning(tmp_path):
    scans = [("spec_tree", ScanResult(items=[
        _item("story:a", "spec_tree", "a.md", deps=["story:ghost"])]))]
    g = build_graph(_cfg(), tmp_path, scans)
    assert g.item_map()["story:a"].deps == []
    assert "dangling dep story:a → story:ghost (edge dropped)" in g.warnings


def test_dangling_lineage_is_dropped_with_warning(tmp_path):
    scans = [("spec_tree", ScanResult(items=[
        _item("story:a", "spec_tree", "a.md", relations=[
            Relation(kind="revises", target="story:ghost")
        ])]))]

    graph = build_graph(_cfg(), tmp_path, scans)

    assert graph.item_map()["story:a"].relations == []
    assert any("dangling relation" in warning and "story:ghost" in warning
               for warning in graph.warnings)


def test_foundation_group_relation_survives_without_becoming_a_dependency(tmp_path):
    scans = [("spec_tree", ScanResult(
        groups=[Group(id="foundation:coordinate-truth", kind="foundation",
                      title="Coordinate Truth")],
        items=[_item("story:a", "dag_import", "dag.json", deps=[], relations=[
            Relation(kind="foundation_root", target="foundation:coordinate-truth")
        ])],
    ))]

    graph = build_graph(_cfg(), tmp_path, scans)
    story = graph.item_map()["story:a"]

    assert story.deps == []
    assert [(r.kind, r.target) for r in story.relations] == [
        ("foundation_root", "foundation:coordinate-truth")
    ]
    assert not any("foundation:coordinate-truth" in warning for warning in graph.warnings)


def test_dangling_milestone_member_dropped_with_warning(tmp_path):
    """codex-sequence-2026-08-08: milestone typos cannot fake progress totals."""
    scans = [("spec_tree", ScanResult(
        items=[_item("story:a", "spec_tree", "a.md")],
        milestones=[Milestone(
            id="M1",
            title="Usable slice",
            phases=[MilestonePhase(name="Floor", items=["story:a", "story:ghost"])],
        )],
    ))]

    graph = build_graph(_cfg(), tmp_path, scans)

    assert graph.milestones[0].phases[0].items == ["story:a"]
    assert any("story:ghost" in warning for warning in graph.warnings)

def test_groups_first_writer_wins_and_vocab_attached(tmp_path):
    scans = [("spec_tree", ScanResult(groups=[Group(id="g", kind="epic", title="One")])),
             ("ledgers", ScanResult(groups=[Group(id="g", kind="epic", title="Two")]))]
    g = build_graph(_cfg(), tmp_path, scans)
    assert [gr.title for gr in g.groups] == ["One"]
    assert any(s["name"] == "shipped" for s in g.vocab["statuses"])


def test_reconcile_applies_opt_in_assessment_after_priority_and_questions(tmp_path):
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))
    graph = build_graph(cfg, tmp_path, [("spec_tree", ScanResult(items=[
        _item("story:a", "spec_tree", "a.md", appetite="small"),
    ]))])

    assert graph.assessment["method"] == "deterministic-delivery-assessment-v1"
    assert graph.assessment["items"]["story:a"]["size"]["assessed_band"] == "S"


def test_duplicate_ids_from_different_files_are_reported(tmp_path):
    """Two distinct files yielding one id silently lose data today; that must be visible."""
    from vizzer.adapters import ScanResult
    from vizzer.config import Config, DEFAULTS
    from vizzer.model import Item

    scans = [("spec_tree", ScanResult(items=[
        Item(id="story:dup", title="First", status="specced",
             source={"adapter": "spec_tree", "path": "a/stories/dup.md"}),
        Item(id="story:dup", title="Second", status="specced",
             source={"adapter": "spec_tree", "path": "b/stories/dup.md"}),
    ]))]
    g = build_graph(Config(data=DEFAULTS), tmp_path, scans)
    assert len([i for i in g.items if i.id == "story:dup"]) == 1
    assert any("dup" in w and "b/stories/dup.md" in w for w in g.warnings), g.warnings


def test_cross_adapter_same_id_is_the_merge_path_not_a_duplicate(tmp_path):
    """dag_import deliberately re-states story ids; that is reconciliation, not data loss.

    Warning on it produced 524 false positives on a real repo — one per story — which
    drowns the genuine same-adapter duplicates the check exists to surface.
    """
    from vizzer.adapters import ScanResult
    from vizzer.config import Config, DEFAULTS
    from vizzer.model import Item

    scans = [("spec_tree", ScanResult(items=[
        Item(id="story:a", title="A", status="building",
             source={"adapter": "spec_tree", "path": "spec/a.md"}),
        Item(id="story:a", title="A", status="building", release="R1",
             source={"adapter": "dag_import", "path": "shaping/dag.json"}),
    ]))]
    g = build_graph(Config(data=DEFAULTS), tmp_path, scans)
    assert not any("duplicate id" in w for w in g.warnings), g.warnings
    assert g.item_map()["story:a"].release == "R1"    # still merged


def test_dependency_cycles_are_reported(tmp_path):
    """A cycle cannot be topologically ordered, so the roadmap order becomes arbitrary.

    Found in the field: two stories declared each other as dependencies. The roadmap
    silently emitted them in id order, which reads exactly like a correct ordering.
    The project's own DAG tracked the cycle; vizzer said nothing.
    """
    from vizzer.adapters import ScanResult
    from vizzer.config import Config, DEFAULTS
    from vizzer.model import Item

    scans = [("spec_tree", ScanResult(items=[
        Item(id="story:a", title="A", deps=["story:b"],
             source={"adapter": "spec_tree", "path": "s/a.md"}),
        Item(id="story:b", title="B", deps=["story:a"],
             source={"adapter": "spec_tree", "path": "s/b.md"}),
        Item(id="story:c", title="C", deps=["story:a"],
             source={"adapter": "spec_tree", "path": "s/c.md"}),
    ]))]
    g = build_graph(Config(data=DEFAULTS), tmp_path, scans)
    cyc = [w for w in g.warnings if "cycle" in w.lower()]
    assert len(cyc) == 1, g.warnings
    assert "story:a" in cyc[0] and "story:b" in cyc[0]
    assert "story:c" not in cyc[0]      # only the cycle members


def test_config_declared_groups_create_a_parent_level(tmp_path):
    """Express a level the directory tree does not encode, without moving any files.

    A monorepo whose capabilities each belong to one product should get product
    rollups from config alone — the filesystem must not be the only schema.
    """
    from vizzer.adapters import ScanResult
    from vizzer.config import Config, DEFAULTS, deep_merge
    from vizzer.model import Group, Item

    cfg = Config(data=deep_merge(DEFAULTS, {"group": [
        {"id": "product:time", "title": "Time",
         "contains": ["capability:billing", "capability:first-session"]},
        {"id": "product:core", "title": "Core", "contains": ["capability:core-platform"]},
    ]}))
    scans = [("spec_tree", ScanResult(
        groups=[Group(id="capability:billing", kind="capability", title="Billing"),
                Group(id="capability:first-session", kind="capability", title="First session"),
                Group(id="capability:core-platform", kind="capability", title="Core platform"),
                Group(id="epic:billing/ui", kind="epic", title="UI",
                      parent="capability:billing")],
        items=[Item(id="story:a", title="A", group="epic:billing/ui", status="shipped",
                    source={"adapter": "spec_tree", "path": "s/a.md"}),
               Item(id="story:b", title="B", group="capability:core-platform",
                    status="specced", source={"adapter": "spec_tree", "path": "s/b.md"})]))]
    g = build_graph(cfg, tmp_path, scans)
    by_id = {gr.id: gr for gr in g.groups}

    # the declared groups exist and sit at the top
    assert by_id["product:time"].title == "Time"
    assert by_id["product:time"].parent is None
    assert by_id["product:time"].kind == "product"
    # the named capabilities now hang beneath them
    assert by_id["capability:billing"].parent == "product:time"
    assert by_id["capability:core-platform"].parent == "product:core"
    # deeper levels are untouched, so the chain still walks up to the product
    assert by_id["epic:billing/ui"].parent == "capability:billing"


def test_config_declared_group_naming_an_unknown_child_warns(tmp_path):
    """A typo in the mapping must be visible, not silently produce an empty product."""
    from vizzer.adapters import ScanResult
    from vizzer.config import Config, DEFAULTS, deep_merge
    from vizzer.model import Group

    cfg = Config(data=deep_merge(DEFAULTS, {"group": [
        {"id": "product:time", "title": "Time", "contains": ["capability:typo"]}]}))
    scans = [("spec_tree", ScanResult(groups=[
        Group(id="capability:billing", kind="capability", title="Billing")]))]
    g = build_graph(cfg, tmp_path, scans)
    assert any("capability:typo" in w for w in g.warnings), g.warnings
