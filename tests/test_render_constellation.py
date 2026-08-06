import json
import re

from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Graph, Group, Item
from vizzer.render import render_all


def _graph():
    return Graph(groups=[Group(id="capability:c", kind="capability", title="Cap")],
                 vocab=Config(data=DEFAULTS).vocab,
                 items=[Item(id="story:a", title="A", status="shipped", release="R0",
                             group="capability:c", appetite="large",
                             source={"adapter": "spec_tree", "path": "s/a.md"},
                             activity={"commits": 3, "mentions": 1, "last_touched": 500}),
                        Item(id="story:b", title="B", status="specced", release="R0",
                             deps=["story:a"], group="capability:c",
                             source={"adapter": "spec_tree", "path": "s/b.md"},
                             activity={"commits": 1, "mentions": 0, "last_touched": 900})])


def _data(html):
    return json.loads(re.search(r"const DATA=(\{.*?\});\n", html, re.S).group(1))


def test_constellation_injects_data(tmp_path):
    cfg = Config(data=deep_merge(DEFAULTS, {"project": {"name": "demo"},
                                            "render": {"recommended": ["story:b"]}}))
    html = render_all(_graph(), cfg, tmp_path, only={"constellation"})["constellation.html"]
    assert "__DATA__" not in html and "__TITLE__" not in html and "demo" in html
    d = _data(html)
    assert len(d["nodes"]) == 2 and d["edges"] == [[0, 1]]
    assert d["now"] == 900                       # max last_touched — deterministic, no wall clock
    assert d["nodes"][1]["rec"] == 1
    assert d["nodes"][0]["w"] > d["nodes"][1]["w"]   # appetite large > default
    assert "root" not in d                       # no absolute paths unless obsidian_links=true
