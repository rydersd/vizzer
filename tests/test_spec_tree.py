import sys
import pytest
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
    assert gids["capability:drawing"].meta["source"]["path"] == \
        "spec/drawing/drawing.md"
    assert gids["epic:drawing/tools"].meta["source"]["path"] == \
        "spec/drawing/epics/tools/tools.md"
    assert snap.group == "epic:drawing/tools"
    assert "story:_Index_of_stories" not in items


def test_required_foundation_index_emits_source_backed_structural_contracts(tmp_path):
    foundations = tmp_path / "spec" / "foundations"
    foundations.mkdir(parents=True)
    (foundations / "foundations.md").write_text(
        "# Foundations\n\n## Required foundation specs\n\n"
        "| Spec | Purpose |\n|---|---|\n"
        "| [Coordinate Truth](coordinate-truth.md) | One coordinate contract. |\n"
        "| [Geometry Kernel](geometry-kernel.md) | One geometry contract. |\n\n"
        "## Notes\n\n| [Not required](migration-note.md) | Ignore me. |\n"
    )
    for name in ("coordinate-truth", "geometry-kernel", "migration-note"):
        (foundations / f"{name}.md").write_text(f"# {name}\n")
    configured = Config(data=deep_merge(DEFAULTS, {"sources": {"spec_tree": {
        "enabled": True,
        "foundation_index": "spec/foundations/foundations.md",
    }}}))

    result = spec_tree.scan(configured, tmp_path)
    groups = {group.id: group for group in result.groups}

    assert set(groups) == {
        "subject:foundations", "foundation:coordinate-truth", "foundation:geometry-kernel"
    }
    coordinate = groups["foundation:coordinate-truth"]
    assert coordinate.parent == "subject:foundations"
    assert coordinate.meta == {
        "source": {"adapter": "spec_tree", "path": "spec/foundations/coordinate-truth.md"},
        "summary": "One coordinate contract.",
    }
    assert result.warnings == []


@pytest.mark.parametrize(("authored", "expected"), [
    ("small-to-medium (one pass plus review)", "small-to-medium"),
    ("small/medium · Wave: A1", "small/medium"),
    ("**not yet assessable** — owner question changes scope", "not yet assessable"),
    ("small–medium (Unicode range)", "small–medium"),
    ("time-boxed to **1 pass** — hard stop", "time-boxed to **1 pass**"),
])
def test_appetite_parser_preserves_full_label_without_rationale(
    tmp_path, authored, expected,
):
    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    (stories / "a.md").write_text(
        f"# Story: A\n\n> Status: specced · Release: R1 · Appetite: {authored}\n"
    )

    [item] = spec_tree.scan(cfg(), tmp_path).items

    assert item.appetite == expected

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


@pytest.mark.parametrize("evidence", [
    "---\nstatus: shipped\ncompleted_on: 2026-08-08\n---\n# Story: A\n",
    "# Story: A\n\n> Status: shipped\n> Completed: 2026-08-08\n",
    "# Story: A\n\n> Status: shipped\n> Ship evidence (2026-08-08)\n",
])
def test_authored_completion_is_recorded_with_provenance(tmp_path, evidence):
    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    (stories / "a.md").write_text(evidence, encoding="utf-8")

    [item] = spec_tree.scan(cfg(), tmp_path).items

    assert item.completion == {"date": "2026-08-08", "provenance": "authored"}


def test_completion_on_non_done_status_warns_and_is_not_promoted(tmp_path):
    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    (stories / "a.md").write_text(
        "# Story: A\n\n> Status: specced\n> Completed: 2026-08-08\n",
        encoding="utf-8",
    )

    result = spec_tree.scan(cfg(), tmp_path)

    assert result.items[0].completion == {}
    assert any("not configured done" in warning for warning in result.warnings)


def test_git_completion_parser_requires_a_real_custom_done_transition():
    stream = """\x00COMMIT 2026-08-09T10:00:00Z
diff --git a/spec/a.md b/spec/a.md
--- a/spec/a.md
+++ b/spec/a.md
-status: finished
+status: finished
\x00COMMIT 2026-08-08T10:00:00Z
diff --git a/spec/a.md b/spec/a.md
--- a/spec/a.md
+++ b/spec/a.md
-status: building
+status: finished
\x00COMMIT 2026-08-07T10:00:00Z
diff --git a/spec/b.md b/spec/b.md
new file mode 100644
--- /dev/null
+++ b/spec/b.md
+status: finished
"""

    assert spec_tree._parse_status_flips(stream, {"finished"}) == {
        "spec/a.md": "2026-08-08"
    }


def test_scan_uses_configured_done_role_for_git_completion(tmp_path, monkeypatch):
    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    story = stories / "a.md"
    story.write_text("# Story: A\n\n> Status: finished\n", encoding="utf-8")
    configured = Config(data=deep_merge(DEFAULTS, {
        "status": [
            {"name": "queued", "role": "ready", "done": False},
            {"name": "finished", "role": "done", "done": True},
        ],
        "sources": {"spec_tree": {
            "enabled": True, "glob": "spec/*/epics/*/stories/*.md",
            "levels": ["capability", "epic"],
        }},
    }))
    seen = []
    monkeypatch.setattr(spec_tree, "_git_status_flip_dates", lambda root, glob, done: (
        seen.append((glob, done)) or {story.relative_to(tmp_path).as_posix(): "2026-08-08"}
    ))

    [item] = spec_tree.scan(configured, tmp_path).items

    assert seen == [("spec/*/epics/*/stories/*.md", {"finished"})]
    assert item.completion == {"date": "2026-08-08", "provenance": "git"}


def test_story_tags_and_product_capabilities_are_preserved_as_distinct_dimensions(tmp_path):
    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    (stories / "shared-editor.md").write_text(
        "# Story: Shared editor\n\n"
        "> Status: specced\n"
        "> Tags: markdown, research\n"
        "> Product capabilities: notes/editor, core/markdown\n",
        encoding="utf-8",
    )

    [item] = spec_tree.scan(cfg(), tmp_path).items

    assert item.role == "delivery"
    assert item.tags == ["markdown", "research"]
    assert item.facets == {
        "product": ["notes", "core"],
        "capability": ["notes/editor", "core/markdown"],
    }


def test_configured_product_tags_add_cross_product_membership_without_promoting_every_tag(tmp_path):
    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    (stories / "research.md").write_text(
        "# Story: Research\n\n> Status: specced\n"
        "> Tags: core, research\n"
        "> Product capabilities: notes/research\n",
        encoding="utf-8",
    )
    configured = Config(data=deep_merge(DEFAULTS, {"sources": {"spec_tree": {
        "enabled": True, "glob": "spec/*/epics/*/stories/*.md",
        "levels": ["capability", "epic"], "product_tags": ["core", "notes"],
    }}}))

    [item] = spec_tree.scan(configured, tmp_path).items

    assert item.tags == ["core", "research"]
    assert item.facets["product"] == ["notes", "core"]


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


def test_dag_import_preserves_milestone_phases_as_item_ids(tmp_path):
    """codex-sequence-2026-08-08: DAG milestones survive into the derived graph."""
    import json

    (tmp_path / "dag.json").write_text(json.dumps({
        "stories": [
            {"slug": "a", "status": "shipped"},
            {"slug": "b", "status": "building", "deps": ["a"]},
        ],
        "milestones": [{
            "id": "M1",
            "title": "Usable slice",
            "goal": "Prove it.",
            "phases": [{"name": "Floor", "stories": ["a", "b"]}],
        }],
    }))

    result = spec_tree.scan(cfg(dag="dag.json"), tmp_path)

    assert len(result.milestones) == 1
    milestone = result.milestones[0]
    assert milestone.id == "M1" and milestone.goal == "Prove it."
    assert milestone.phases[0].items == ["story:a", "story:b"]


@pytest.mark.parametrize(("value", "expected"), [
    ("[b](b.md) · Research spike: explain why", ["story:b"]),
    ("[] (no story-slug deps; the launch floor already supplies them)", []),
    ("`b`, `c`", ["story:b", "story:c"]),
])
def test_story_dependency_header_accepts_only_sanctioned_forms(tmp_path, value, expected):
    """codex-sequence-2026-08-08: match the migration contract's real forms."""
    story = tmp_path / "spec" / "cap" / "epics" / "tools" / "stories" / "a.md"
    story.parent.mkdir(parents=True)
    story.write_text(
        "# Story: A\n\n> Status: specced\n"
        f"> Deps: {value}\n",
        encoding="utf-8",
    )

    result = spec_tree.scan(cfg(), tmp_path)

    assert result.items[0].deps == expected
    assert result.items[0].source["deps_declared"] is True
    assert result.warnings == []


@pytest.mark.parametrize("value", [
    "[b](b.md), missing-tool",
    "[] except b",
    "[b](b.md) trailing prose",
])
def test_story_dependency_header_warns_on_unconsumed_residual_text(tmp_path, value):
    """codex-sequence-2026-08-08: malformed suffixes cannot produce a quiet graph."""
    story = tmp_path / "spec" / "cap" / "epics" / "tools" / "stories" / "a.md"
    story.parent.mkdir(parents=True)
    story.write_text(
        "# Story: A\n\n> Status: specced\n"
        f"> Deps: {value}\n",
        encoding="utf-8",
    )

    result = spec_tree.scan(cfg(), tmp_path)

    assert result.items[0].deps == []
    assert result.items[0].source["deps_declared"] is True
    assert len(result.warnings) == 1
    assert "invalid > Deps: header" in result.warnings[0]


def test_lowercase_deps_prose_is_not_a_story_dependency_header(tmp_path):
    """codex-sequence-2026-08-08: contract prose must not erase DAG edges."""
    story = tmp_path / "spec" / "cap" / "epics" / "tools" / "stories" / "a.md"
    story.parent.mkdir(parents=True)
    story.write_text(
        "# Story: A\n\n> Status: specced\n\n"
        "## Handoff\n\ndeps: `b` + sibling seams named in prose\n",
        encoding="utf-8",
    )

    result = spec_tree.scan(cfg(), tmp_path)

    assert result.items[0].deps == []
    assert "deps_declared" not in result.items[0].source


def test_dag_import_emits_stories_not_slugged_wrappers(tmp_path):
    import json

    (tmp_path / "dag.json").write_text(json.dumps({
        "capabilities": [{
            "slug": "drawing",
            "epics": [{
                "slug": "tools",
                "stories": [{"slug": "snap", "status": "ready"}],
            }],
        }],
    }))

    res = spec_tree.scan(cfg(dag="dag.json"), tmp_path)

    assert [item.id for item in res.items] == ["story:snap"]


def test_dag_contract_roots_inherit_to_capability_stories_without_hard_deps(tmp_path):
    """Explicit roots become story → foundation provenance, never readiness edges."""
    import json

    (tmp_path / "dag.json").write_text(json.dumps({
        "capabilities": [{
            "id": "CAP-drawing",
            "epics": [{"stories": [
                {"slug": "line", "status": "ready", "deps": []},
                {"slug": "shape", "status": "ready", "deps": ["line"]},
            ]}],
        }, {
            "slug": "other",
            "epics": [{"stories": [{"slug": "other-story", "status": "ready"}]}],
        }],
        "contractDeps": {"roots": {
            "coordinate-truth": ["drawing"],
        }},
    }))

    result = spec_tree.scan(cfg(dag="dag.json"), tmp_path)
    by_id = {item.id: item for item in result.items}

    assert {group.id for group in result.groups} == {"foundation:coordinate-truth"}
    assert [(r.kind, r.target) for r in by_id["story:line"].relations] == [
        ("foundation_root", "foundation:coordinate-truth")
    ]
    assert [(r.kind, r.target) for r in by_id["story:shape"].relations] == [
        ("foundation_root", "foundation:coordinate-truth")
    ]
    assert by_id["story:line"].deps == []
    assert by_id["story:shape"].deps == ["story:line"]
    assert by_id["story:other-story"].relations == []


def test_dag_contract_roots_warn_on_malformed_values_and_do_not_infer_prose(tmp_path):
    import json

    (tmp_path / "dag.json").write_text(json.dumps({
        "capabilities": [{
            "slug": "drawing",
            # This deliberately looks foundation-ish but is not contractDeps.
            "foundations": ["prose-foundation"],
            "epics": [{"stories": [{"slug": "line", "status": "ready"}]}],
        }],
        "contractDeps": {"roots": {
            "valid-root": "drawing",
            "other-root": ["drawing", 42, "missing"],
        }},
    }))

    result = spec_tree.scan(cfg(dag="dag.json"), tmp_path)
    [story] = result.items

    assert [(r.kind, r.target) for r in story.relations] == [
        ("foundation_root", "foundation:other-root")
    ]
    assert "foundation:prose-foundation" not in {group.id for group in result.groups}
    assert any("valid-root must map to a list" in warning for warning in result.warnings)
    assert any("other-root has malformed capability" in warning for warning in result.warnings)
    assert any("other-root references unknown capability missing" in warning
               for warning in result.warnings)


def test_dag_contract_roots_do_not_inflate_duplicate_relations(tmp_path):
    import json

    (tmp_path / "dag.json").write_text(json.dumps({
        "capabilities": [{
            "slug": "drawing",
            "epics": [{"stories": [{"slug": "line", "status": "ready"}]}],
        }],
        "contractDeps": {"roots": {"coordinate-truth": ["drawing", "drawing"]}},
    }))

    [story] = spec_tree.scan(cfg(dag="dag.json"), tmp_path).items

    assert [(r.kind, r.target) for r in story.relations] == [
        ("foundation_root", "foundation:coordinate-truth")
    ]


def test_non_utf8_group_overview_warns_and_uses_fallback_title(tmp_path):
    stories = tmp_path / "spec" / "cap" / "epics" / "ep" / "stories"
    stories.mkdir(parents=True)
    (stories / "story.md").write_text("# Story: Story\n\n> Status: ready\n")
    (tmp_path / "spec" / "cap" / "cap.md").write_bytes(b"\xff\xfe")

    res = spec_tree.scan(cfg(), tmp_path)

    assert [item.id for item in res.items] == ["story:story"]
    assert any("cap.md" in warning for warning in res.warnings)
    assert {group.title for group in res.groups} >= {"Cap"}


@pytest.mark.skipif(sys.version_info < (3, 11),
                    reason="int digit limit only exists on 3.11+")
def test_dag_import_skips_oversized_json_integer(tmp_path):
    (tmp_path / "dag.json").write_text(
        '{"stories": ['
        '{"slug": "a", "status": "ready"},'
        '{"slug": "b", "status": "ready"},'
        '{"slug": "c", "status": "ready"}'
        '], "hostile": ' + ("9" * 5000) + "}"
    )

    res = spec_tree.scan(cfg(dag="dag.json"), tmp_path)

    assert res.items == []
    assert any("dag.json" in warning for warning in res.warnings)


def test_story_lineage_headers_parse_as_typed_nonblocking_relations(tmp_path):
    stories = tmp_path / "spec" / "cap" / "epics" / "tools" / "stories"
    stories.mkdir(parents=True)
    (stories / "old.md").write_text("# Story: Old\n\n> Status: shipped\n")
    (stories / "floor.md").write_text("# Story: Floor\n\n> Status: shipped\n")
    (stories / "new.md").write_text(
        "# Story: New\n\n> Status: specced\n"
        "> Revises: old.md\n"
        "> Bug against: [floor](../stories/floor.md)\n"
    )

    result = spec_tree.scan(cfg(), tmp_path)
    item = {entry.id: entry for entry in result.items}["story:new"]

    assert [(relation.kind, relation.target) for relation in item.relations] == [
        ("bug_against", "story:floor"),
        ("revises", "story:old"),
    ]
    assert item.deps == []
    assert result.warnings == []


@pytest.mark.parametrize("value", [
    "old.md plus maybe floor.md",
    "https://example.test/old.md",
    "[wrong-label](old.md)",
    "old.txt",
])
def test_story_lineage_warns_and_drops_malformed_whole_values(tmp_path, value):
    story = tmp_path / "spec" / "cap" / "epics" / "tools" / "stories" / "new.md"
    story.parent.mkdir(parents=True)
    story.write_text(
        f"# Story: New\n\n> Status: specced\n> Revises: {value}\n"
    )

    result = spec_tree.scan(cfg(), tmp_path)

    assert result.items[0].relations == []
    assert len(result.warnings) == 1 and "invalid > revises:" in result.warnings[0]
