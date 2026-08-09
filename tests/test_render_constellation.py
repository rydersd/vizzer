import json
import re

from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import ActiveWork, Graph, Group, Item, Relation
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


def _search_ids(data, query):
    """Mirror the page's documented all-token substring contract over its index."""
    tokens = query.casefold().split()
    return [
        node.get("id", f"foundation:{node['s']}")
        for node in data["nodes"]
        if all(token in node["q"].casefold() for token in tokens)
    ]


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


def test_constellation_keeps_file_mode_source_link_relative_and_http_open_by_id(tmp_path):
    cfg = Config(data=Config(data=DEFAULTS).data)
    html = render_all(_graph(), cfg, tmp_path, only={"constellation"})["constellation.html"]
    data = _data(html)

    assert data["nodes"][0]["h"] == "../../s/a.md"
    assert str(tmp_path) not in html
    assert "const SERVED = location.protocol === 'http:';" in html
    assert "n.h&&!SERVED" in html
    assert "n.id&&SERVED" in html
    assert "fetch('/api/open/'+encodeURIComponent(b.dataset.openItem)" in html


def test_constellation_default_never_serializes_root(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert '"root"' not in html
    assert str(tmp_path) not in html


def test_constellation_preserves_explicit_obsidian_opt_in(tmp_path):
    cfg = Config(data=deep_merge(DEFAULTS, {"render": {"obsidian_links": True}}))
    html = render_all(_graph(), cfg, tmp_path, only={"constellation"})["constellation.html"]

    assert _data(html)["root"] == str(tmp_path)
    assert "obsidian://open?path=" in html


def test_constellation_uses_configured_lifecycle_roles(tmp_path):
    """codex-sequence-2026-08-08: regression work cannot appear active here."""
    statuses = [
        {"name": "building", "emoji": "🔧", "done": False, "role": "active"},
        {"name": "in-flight", "emoji": "✈️", "done": False, "role": "regression"},
        {"name": "bug-gap", "emoji": "🐛", "done": False, "role": "regression"},
        {"name": "verified", "emoji": "🏁", "done": True, "role": "done"},
    ]
    cfg = Config(data=deep_merge(DEFAULTS, {"status": statuses}))
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:a", title="A", status="building"),
        Item(id="story:b", title="B", status="in-flight"),
        Item(id="story:c", title="C", status="bug-gap"),
        Item(id="story:d", title="D", status="verified"),
    ])

    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]
    groups = {node["s"]: node["g"] for node in _data(html)["nodes"]}

    assert groups == {"a": "active", "b": "buggap", "c": "buggap", "d": "shipped"}
    assert "'in-flight':'active'" not in html


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


def test_constellation_keeps_typed_lineage_separate_from_hard_edges(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:old", title="Old", status="shipped"),
        Item(id="story:new", title="New", status="specced",
             relations=[Relation(kind="revises", target="story:old")],
             priority={
                 "rank": 1, "score": 540,
                 "rationale": "1 incomplete target dependent(s), depth 1",
                 "components": {"target_dependents": 1},
             }),
    ], priority={"recommendations": ["story:new"]})

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)

    assert data["edges"] == []
    assert data["relations"] == [[0, 1, "revises"]]
    assert data["nodes"][0]["rec"] == 1
    assert data["nodes"][0]["pu"] == 1
    assert "reverse lineage" in html


def test_constellation_draws_foundation_group_targets_as_nonblocking_relations(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab,
                  groups=[Group(id="foundation:coordinate-truth", kind="foundation",
                                title="Coordinate Truth")],
                  items=[Item(id="story:line", title="Line", status="ready",
                              relations=[Relation(
                                  kind="foundation_root",
                                  target="foundation:coordinate-truth",
                              )])])

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)

    assert data["edges"] == []
    assert data["relations"] == [[0, 1, "foundation_root"]]
    assert data["nodes"][1]["foundation"] == 1
    assert data["nodes"][1]["t"] == "Coordinate Truth"
    assert "foundations" not in data["caps"]
    assert "foundation:'foundation'" in html
    # Synthetic relation targets still need a layout cluster. They remain out
    # of product completion counts instead of crashing on DATA.caps[...].total.
    assert "const layoutTotals = {};" in html
    assert "Math.sqrt(layoutTotals[n.c])" in html
    assert "DATA.caps[n.c].total" not in html


def test_constellation_activity_lens_pulses_only_explicit_fresh_work_links(tmp_path):
    graph = _graph()
    graph.active_work = [
        ActiveWork(
            story_id="story:a", agent="Galileo", task="Implement activity lens",
            state="active", completed=2, total=4,
            updated_at="2026-08-08T17:00:00Z",
            stale_at="2099-08-08T19:00:00Z", checkpoint="edge rendering",
            related_story_ids=["story:b"],
        ),
        ActiveWork(
            story_id="story:b", agent="Kepler", task="Old review",
            state="active", completed=0, total=0,
            updated_at="2020-08-08T17:00:00Z",
            stale_at="2020-08-08T19:00:00Z",
        ),
    ]

    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    data = _data(html)

    assert data["nodes"][0]["aw"] == [0]
    assert data["nodes"][1]["aw"] == [1]
    assert data["workLinks"] == [[0, 1]]
    assert data["work"][0]["done"] == 2 and data["work"][0]["total"] == 4
    assert "Date.now()<Date.parse(w.staleAt)" in html
    assert "const activeNode" in html
    assert "Explicit agent-work linkage pulses" in html
    assert "activeCount===2" in html and "activeCount===2?.55:.22" in html
    assert "ctx.setLineDash([4,4])" in html  # typed relation, not hard dependency


def test_constellation_lenses_are_accessible_and_reduced_motion_is_semantic(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "['progress','Progress']" in html
    assert "aria-pressed" in html and "aria-label','Graph lenses" in html
    assert "prefers-reduced-motion: reduce" in html
    assert "const reducedMotion" in html
    assert "reducedMotion ? .72" in html
    assert "ctx.lineDashOffset=reducedMotion?0" in html


def test_constellation_renders_semantic_progress_trails_and_capped_stall_markers(tmp_path):
    graph = _graph()
    graph.items[0].progress = {
        "events": [{"at": "2026-08-09T00:00:00Z", "kind": "lifecycle",
                    "source": "story lifecycle header", "detail": "ready → building"}],
        "hotWindowDays": 7,
        "stall": {"since": "2023-01-01T00:00:00Z",
                  "source": "story lifecycle header", "afterDays": 14,
                  "maxDays": 90},
    }
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    data = _data(html)
    assert data["nodes"][0]["pg"]["events"][0]["kind"] == "lifecycle"
    assert data["nodes"][0]["pg"]["stall"]["maxDays"] == 90
    assert "Circle-plus marks are a static history trail" in html
    assert "Math.min(blocked.maxDays,blocked.days)" in html
    assert "const ageDays = at =>" in html
    assert "role=\"tooltip\"" in html and "progressText" in html


def test_constellation_boot_failure_is_visible_and_older_webkit_is_supported(tmp_path):
    """codex-sequence-2026-08-08: standalone HTML must not fail as a blank page."""
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert 'id="boot" role="status"' in html
    assert "addEventListener('error',function(event)" in html
    assert "Vizzer could not start." in html
    assert "typeof colorSchemeQuery.addEventListener==='function'" in html
    assert "typeof colorSchemeQuery.addListener==='function'" in html
    assert "window.__vizzerBoot.ready();" in html


def test_agent_activity_text_cannot_escape_script_payload(tmp_path):
    graph = _graph()
    graph.active_work = [ActiveWork(
        story_id="story:a", agent="</script><script>alert(9)</script>",
        task='<img src=x onerror="alert(10)">', state="active",
        completed=1, total=2, updated_at="2026-08-08T17:00:00Z",
        stale_at="2099-08-08T19:00:00Z",
    )]

    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "</script><script>alert(9)" not in html
    assert _data(html)["work"][0]["agent"] == "</script><script>alert(9)</script>"


def test_constellation_has_portable_path_escaped_markdown_anchor(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:linked", title="Linked", status="specced",
             source={"adapter": "spec_tree", "path": "stories/a story#1.md"}),
    ])

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    node = _data(html)["nodes"][0]

    assert node["h"] == "../../stories/a%20story%231.md"
    assert node["id"] == "story:linked"
    assert str(tmp_path) not in html
    assert 'open Markdown ↗' in html
    assert "n.h&&!SERVED" in html and "n.id&&SERVED" in html
    assert "data-source-path" not in html


def test_constellation_drops_story_href_that_escapes_repository(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:escape", title="Escape", status="specced",
             source={"adapter": "spec_tree", "path": "../../outside.md"}),
    ])

    node = _data(render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ])["nodes"][0]

    assert node["h"] == ""


def test_constellation_search_indexes_every_authored_item_field_and_live_work(tmp_path):
    """codex-sequence-2026-08-08: search follows meaning, not just filenames."""
    cfg = Config(data=DEFAULTS)
    graph = Graph(
        vocab=cfg.vocab,
        groups=[
            Group(id="capability:design-system", kind="capability",
                  title="Interface foundations"),
            Group(id="epic:visual-language", kind="epic",
                  title="Captured visual language", parent="capability:design-system"),
        ],
        items=[
            Item(
                id="story:captured-visual-language",
                title="Captured visual language",
                one_liner="Give each designer style a reusable semantic home.",
                status="building",
                release="R1",
                group="epic:visual-language",
                source={"adapter": "spec_tree", "path": "stories/style-capture.md"},
            ),
            Item(id="story:unrelated", title="Export canvas", status="specced",
                 release="R2", source={"adapter": "spec_tree", "path": "export.md"}),
        ],
        active_work=[ActiveWork(
            story_id="story:captured-visual-language", agent="Galileo",
            task="Tune inspector swatches", state="active", completed=2, total=4,
            updated_at="2026-08-08T17:00:00Z", stale_at="2099-08-08T19:00:00Z",
            checkpoint="semantic contrast review",
        )],
    )

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)

    # The owner acceptance phrase spans one-liner words; all tokens must match
    # the same item, case-insensitively.
    assert _search_ids(data, "DESIGNER style") == [
        "story:captured-visual-language"
    ]
    for query in (
        "captured visual", "story:captured-visual-language", "building", "r1",
        "design-system", "interface foundations", "epic:visual-language",
        "stories/style-capture.md", "galileo", "inspector swatches",
        "semantic contrast",
    ):
        assert _search_ids(data, query) == ["story:captured-visual-language"]
    assert _search_ids(data, "designer export") == []


def test_constellation_search_is_accessible_local_and_topology_preserving(tmp_path):
    """codex-sequence-2026-08-08: search must work in a file:// constellation."""
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert 'role="search"' in html and 'aria-label="Search work items"' in html
    assert 'aria-live="polite"' in html and 'aria-label="Clear search"' in html
    assert "event.key==='Escape'" in html
    assert "toLocaleLowerCase" in html and "split(/\\s+/)" in html
    assert "searchTerms.every" in html
    assert "searchDim" in html
    # Search dims painter output; it does not enter visibility/layout filtering.
    visible_body = html.split("function visible(n)", 1)[1].split("}", 1)[0]
    assert "search" not in visible_body
    # Neither source-opening route becomes server-dependent merely because search exists.
    assert "n.h&&!SERVED" in html and "n.id&&SERVED" in html
    assert "fetch('/api/open/'+encodeURIComponent(b.dataset.openItem)" in html
    assert "prefers-reduced-motion: reduce" in html
