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


def test_front_matter_release_is_honored(tmp_path):
    """README documents front-matter `release`; it must not be body-only."""
    from vizzer.adapters import spec_tree as st
    from vizzer.config import Config, DEFAULTS, deep_merge

    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    (stories / "a.md").write_text("---\nstatus: specced\nrelease: R2\nwave: W1\n---\n# Story: A\n")
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"spec_tree": {
        "enabled": True, "glob": "spec/*/epics/*/stories/*.md",
        "levels": ["capability", "epic"]}}}))
    [item] = [i for i in st.scan(cfg, tmp_path).items if i.id == "story:a"]
    assert item.release == "R2"
    assert item.wave == "W1"


def test_undecodable_file_degrades_with_warning(tmp_path):
    """A file that is not valid UTF-8 must warn, never raise."""
    from vizzer.adapters import spec_tree as st
    from vizzer.config import Config, DEFAULTS, deep_merge

    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    (stories / "ok.md").write_text("# Story: OK\n\n> Status: specced\n")
    (stories / "bad.md").write_bytes(b"\xff\xfe\x00binary garbage\n")
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"spec_tree": {
        "enabled": True, "glob": "spec/*/epics/*/stories/*.md",
        "levels": ["capability", "epic"]}}}))
    res = st.scan(cfg, tmp_path)
    assert any(i.id == "story:ok" for i in res.items)
    assert any("bad.md" in w for w in res.warnings)


def test_absolute_glob_does_not_raise(tmp_path):
    """An absolute pattern in config must degrade to a warning, not NotImplementedError."""
    from vizzer.adapters import spec_tree as st
    from vizzer.config import Config, DEFAULTS, deep_merge

    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"spec_tree": {
        "enabled": True, "glob": "/absolute/*/stories/*.md", "levels": ["capability"]}}}))
    res = st.scan(cfg, tmp_path)
    assert res.items == []
    assert res.warnings


def test_dag_import_walks_slug_keyed_collections(tmp_path):
    """Real DAGs key capabilities and epics by slug (dicts), not as lists.

    Assuming lists made the importer skip every story, so a project with 27 of 43
    stories carrying dependencies produced a flat, non-dependency-aware queue.
    """
    import json
    from vizzer.adapters import spec_tree as st
    from vizzer.config import Config, DEFAULTS, deep_merge

    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "dag.json").write_text(json.dumps({
        "capabilities": {
            "billing": {"title": "Billing", "wave": "R0", "epics": {
                "ui": {"stories": [
                    {"slug": "billable-fields-ui", "deps": [], "status": "specced",
                     "wave": "R0"},
                    {"slug": "weekly-summary", "deps": ["billable-fields-ui"],
                     "status": "specced", "wave": "R0"},
                ]}}}}}))
    cfg = Config(data=deep_merge(DEFAULTS, {"sources": {"spec_tree": {
        "enabled": True, "glob": "", "dag_import": "wiki/dag.json"}}}))
    res = st.scan(cfg, tmp_path)
    by_id = {i.id: i for i in res.items}
    assert set(by_id) == {"story:billable-fields-ui", "story:weekly-summary"}
    assert by_id["story:weekly-summary"].deps == ["story:billable-fields-ui"]
    assert by_id["story:weekly-summary"].wave == "R0"
    assert by_id["story:billable-fields-ui"].status == "specced"
