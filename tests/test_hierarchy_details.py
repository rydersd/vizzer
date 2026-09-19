"""Portable hierarchy rendering retains source-owned group detail."""
from __future__ import annotations

import json
import re

from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Graph, Group, Item
from vizzer.render import render_all


def _payload(html: str) -> dict:
    match = re.search(r"const DATA=(\{.*?\});\n", html, re.S)
    assert match is not None
    return json.loads(match.group(1))


def test_nested_group_contracts_render_without_project_specific_tiers(tmp_path) -> None:
    (tmp_path / "spec/planning").mkdir(parents=True)
    (tmp_path / "spec/canvas.md").write_text("# Canvas\nA shared canvas contract.", encoding="utf-8")
    (tmp_path / "spec/editing.md").write_text("# Editing\nKeep editing deterministic.", encoding="utf-8")
    (tmp_path / "spec/planning/plans.md").write_text("# Plan\nMeasure before changing.", encoding="utf-8")
    groups = [
        Group(id="capability:canvas", kind="capability", title="Canvas",
              meta={"source": {"path": "spec/canvas.md"}}),
        Group(id="epic:editing", kind="epic", title="Editing",
              parent="capability:canvas", meta={"source": {"path": "spec/editing.md"}}),
    ]
    graph = Graph(
        groups=groups,
        vocab=Config(data=DEFAULTS).vocab,
        items=[Item(id="story:select", title="Select", status="ready",
                    group="epic:editing", source={"path": "spec/select.md"})],
    )
    cfg = Config(data=deep_merge(DEFAULTS, {"project": {"name": "Fixture"}}))

    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]
    data = _payload(html)
    editing = next(group for group in data["groups"] if group["id"] == "epic:editing")

    assert editing["parent"] == "capability:canvas"
    assert editing["purpose"] == "# Editing\nKeep editing deterministic."
    assert editing["plans"] == "# Plan\nMeasure before changing."
    assert [node["group"] for node in data["nodes"]] == ["epic:editing"]
    assert "Project hierarchy" in html


def test_foundation_tiers_are_authored_by_configured_fixture_not_group_names(tmp_path) -> None:
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/foundation.md").write_text("# Foundation", encoding="utf-8")
    (tmp_path / "tiers.json").write_text(
        json.dumps({"tier-one": ["core"], "tier-two": ["epic:render"]}), encoding="utf-8",
    )
    graph = Graph(
        groups=[
            Group(id="epic:core", kind="epic", title="Core", meta={"source": {"path": "spec/foundation.md"}}),
            Group(id="epic:render", kind="epic", title="Render"),
            Group(id="epic:ordinary", kind="epic", title="Ordinary"),
        ],
        items=[Item(id="story:core", title="Core", status="ready", group="epic:core")],
        vocab=Config(data=DEFAULTS).vocab,
    )
    cfg = Config(data=deep_merge(DEFAULTS, {"render": {"foundation_tiers_path": "tiers.json"}}))

    data = _payload(render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"])
    tiers = {entry["id"]: entry.get("foundationTier") for entry in data["groups"]}

    assert tiers == {"epic:core": "tier-one", "epic:ordinary": None, "epic:render": "tier-two"}


def test_group_source_cannot_read_outside_the_render_root(tmp_path) -> None:
    outside = tmp_path.parent / "outside-source.md"
    outside.write_text("must not become constellation detail", encoding="utf-8")
    graph = Graph(
        groups=[Group(
            id="capability:unsafe", kind="capability", title="Unsafe",
            meta={"source": {"path": "../outside-source.md"}},
        )],
        items=[Item(id="story:unsafe", title="Unsafe", status="ready", group="capability:unsafe")],
        vocab=Config(data=DEFAULTS).vocab,
    )

    html = render_all(graph, Config(data=DEFAULTS), tmp_path, only={"constellation"})["constellation.html"]
    group = next(entry for entry in _payload(html)["groups"] if entry["id"] == "capability:unsafe")

    assert group["p"] == "../outside-source.md"
    assert "purpose" not in group
    assert "must not become constellation detail" not in html
