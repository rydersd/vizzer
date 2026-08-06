# tests/test_render_roadmap.py
from pathlib import Path
from vizzer.config import Config, DEFAULTS
from vizzer.model import Graph, Group, Item
from vizzer.render import render_all
from vizzer.render.common import topo

def _graph():
    return Graph(
        groups=[Group(id="capability:d", kind="capability", title="Drawing"),
                Group(id="epic:d/t", kind="epic", title="Tools", parent="capability:d")],
        items=[Item(id="story:b", title="B", status="specced", release="R0",
                    deps=["story:a"], group="epic:d/t",
                    source={"adapter": "spec_tree", "path": "spec/b.md"}),
               Item(id="story:a", title="A", one_liner="Does A.", status="shipped",
                    release="R0", group="epic:d/t",
                    source={"adapter": "spec_tree", "path": "spec/a.md"})],
        vocab=Config(data=DEFAULTS).vocab)

def test_topo_orders_deps_first_and_tolerates_cycles():
    a = Item(id="a", title="a"); b = Item(id="b", title="b", deps=["a"])
    assert [i.id for i in topo([b, a], {"a": [], "b": ["a"]})] == ["a", "b"]
    c1 = Item(id="c1", title="", deps=["c2"]); c2 = Item(id="c2", title="", deps=["c1"])
    assert {i.id for i in topo([c1, c2], {"c1": ["c2"], "c2": ["c1"]})} == {"c1", "c2"}

def test_roadmap_and_index(tmp_path):
    out = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                     only={"roadmap", "feature_index"})
    rm = out["roadmap.md"]
    assert "## R0" in rm
    assert rm.index("[a](../../spec/a.md)") < rm.index("[b](../../spec/b.md)")
    assert "✅ shipped" in rm
    fi = out["feature-index.md"]
    assert "## Drawing" in fi and "### Tools" in fi and "Does A." in fi

def test_render_all_rejects_unknown_view(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        render_all(_graph(), Config(data=DEFAULTS), tmp_path, only={"nope"})
