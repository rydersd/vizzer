# tests/test_reconcile.py
from vizzer.adapters import ScanResult
from vizzer.config import Config, DEFAULTS
from vizzer.model import Group, Item
from vizzer.reconcile import build_graph

def _cfg():
    return Config(data=DEFAULTS)

def _item(id, adapter, path, **kw):
    return Item(id=id, title=kw.pop("title", id), source={"adapter": adapter, "path": path}, **kw)

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

def test_groups_first_writer_wins_and_vocab_attached(tmp_path):
    scans = [("spec_tree", ScanResult(groups=[Group(id="g", kind="epic", title="One")])),
             ("ledgers", ScanResult(groups=[Group(id="g", kind="epic", title="Two")]))]
    g = build_graph(_cfg(), tmp_path, scans)
    assert [gr.title for gr in g.groups] == ["One"]
    assert any(s["name"] == "shipped" for s in g.vocab["statuses"])


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
