from pathlib import Path
from vizzer.adapters import spec_tree, get_adapters
from vizzer.config import Config, DEFAULTS, deep_merge

FIX = Path(__file__).parent / "fixtures" / "spec_proj"

def cfg(dag=""):
    d = deep_merge(DEFAULTS, {"sources": {"spec_tree": {
        "enabled": True, "glob": "spec/*/epics/*/stories/*.md",
        "levels": ["capability", "epic"], "dag_import": dag}}})
    return Config(data=d)

def test_scan_items_and_groups():
    res = spec_tree.scan(cfg(), FIX)
    items = {i.id: i for i in res.items}
    snap = items["story:snap-to-grid"]
    assert snap.title == "Snap to grid"
    assert snap.status == "building" and snap.release == "R0"
    assert snap.deps == ["story:canvas-core"]
    assert snap.appetite == "medium" and "debt" in snap.flags
    assert snap.one_liner.startswith("Dragging an object snaps")
    core = items["story:canvas-core"]
    assert core.status == "shipped" and core.one_liner == "Core canvas surface with pan and zoom."
    gids = {g.id: g for g in res.groups}
    assert gids["capability:drawing"].title == "Capability: Drawing".removeprefix("Capability: ")
    assert gids["epic:drawing/tools"].parent == "capability:drawing"
    assert gids["epic:drawing/tools"].title == "Drawing tools"
    assert snap.group == "epic:drawing/tools"
    assert "story:_Index_of_stories" not in items

def test_dag_import_emits_parallel_items():
    res = spec_tree.scan(cfg(dag="dag.json"), FIX)
    dag_items = [i for i in res.items if i.source["adapter"] == "dag_import"]
    assert {i.id for i in dag_items} == {"story:snap-to-grid", "story:canvas-core"}
    assert {i.status for i in dag_items if i.id == "story:snap-to-grid"} == {"specced"}

def test_registry_orders_by_precedence():
    c = cfg()
    assert [name for name, _ in get_adapters(c)] == ["spec_tree"]


def test_dep_slugs_normalize_markdown_links_and_backticks():
    """Real specs write deps as markdown links or code spans; both must resolve."""
    from vizzer.adapters.spec_tree import _dep_ids
    assert _dep_ids("[typed-anchor-model](typed-anchor-model.md)", "story") == \
        ["story:typed-anchor-model"]
    assert _dep_ids("[interaction-handle-chrome](../../other/stories/interaction-handle-chrome.md)",
                    "story") == ["story:interaction-handle-chrome"]
    assert _dep_ids("`non-destructive-chamfer-bevel`", "story") == \
        ["story:non-destructive-chamfer-bevel"]
    assert _dep_ids("`a-slug`, [b-slug](b-slug.md)", "story") == \
        ["story:a-slug", "story:b-slug"]


def test_dep_prose_is_discarded_not_turned_into_fake_slugs():
    """Prose in a Deps: line must be dropped, not emitted as a bogus dependency."""
    from vizzer.adapters.spec_tree import _dep_ids
    assert _dep_ids("assembler parameterization + slider atoms named · both real", "story") == []
    assert _dep_ids("[] (no story-slug deps; layers on the shipped launch path)", "story") == []
    assert _dep_ids("proof-panel shipped", "story") == []
