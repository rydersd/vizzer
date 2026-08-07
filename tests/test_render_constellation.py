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


def test_titles_cannot_inject_html_or_break_out_of_the_script_block(tmp_path):
    """Project-controlled text must never become executable markup in the rendered page."""
    from vizzer.config import deep_merge
    from vizzer.model import Item as I

    cfg = Config(data=deep_merge(DEFAULTS, {
        "render": {"title": "<img src=x onerror=alert(1)>"}}))
    graph = Graph(vocab=Config(data=DEFAULTS).vocab, items=[
        I(id="story:x", title="</script><script>alert(1)</script>",
          source={"adapter": "spec_tree", "path": "s/x.md"},
          activity={"commits": 0, "mentions": 0, "last_touched": 0})])
    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]

    # the config-supplied page title must be escaped, not injected as live markup
    assert "<img src=x onerror=" not in html
    # no data value may terminate the script element that carries the JSON payload
    assert "</script><script>alert(1)" not in html
    # the payload must still parse and preserve the original text
    data = _data(html)
    assert data["nodes"][0]["t"] == "</script><script>alert(1)</script>"


def test_placeholder_in_config_cannot_smuggle_the_payload_into_html(tmp_path):
    """Substitutions must be single-pass: replaced text must never be re-scanned.

    Escaping the title and then replacing __DATA__ meant a title containing the
    literal string `__DATA__` had the JSON payload injected into the HTML body,
    where node titles are not HTML-escaped — reintroducing live markup.
    """
    from vizzer.config import deep_merge
    from vizzer.model import Item as I

    cfg = Config(data=deep_merge(DEFAULTS, {"render": {"title": "x__DATA__y"}}))
    graph = Graph(vocab=Config(data=DEFAULTS).vocab, items=[
        I(id="story:a", title="<img src=x onerror=alert(7)>",
          source={"adapter": "spec_tree", "path": "s/a.md"},
          activity={"commits": 0, "mentions": 0, "last_touched": 0})])
    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]

    # the payload belongs in the script element and nowhere else
    assert html.count('"nodes":') == 1
    head, _, tail = html.partition('id="title"')
    title_region = tail[:200]
    assert "x__DATA__y" in title_region          # the literal title, escaped
    assert '"nodes":' not in title_region        # not the smuggled payload
    # the value survives intact inside the data block
    assert _data(html)["nodes"][0]["t"] == "<img src=x onerror=alert(7)>"


def test_non_numeric_activity_values_cannot_reach_the_page_as_markup(tmp_path):
    """A hand-edited graph can carry junk in activity; the page must not interpolate it raw."""
    from vizzer.model import Item as I

    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        I(id="story:a", title="A", source={"adapter": "spec_tree", "path": "s/a.md"},
          activity={"commits": "<img src=x onerror=alert(8)>", "mentions": None,
                    "last_touched": "not-a-number"})])
    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]
    assert "onerror=alert(8)" not in html
    node = _data(html)["nodes"][0]
    assert isinstance(node["ac"], int) and isinstance(node["am"], int)
    assert isinstance(node["ts"], int)
