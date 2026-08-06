from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Graph, Group, Item
from vizzer.render import render_all

def _graph():
    g = [Group(id="capability:c", kind="capability", title="Cap")]
    mk = lambda i, st, dep=None: Item(id=f"story:{i}", title=i.upper(), status=st,
                                      release="R0", deps=[f"story:{dep}"] if dep else [],
                                      group="capability:c",
                                      source={"adapter": "spec_tree", "path": f"s/{i}.md"})
    return Graph(groups=g, vocab=Config(data=DEFAULTS).vocab, items=[
        mk("done1", "shipped"),
        mk("wip", "building"),
        mk("ready", "specced", dep="done1"),
        mk("blocked", "specced", dep="wip"),
        mk("gated", "specced"),
        Item(id="story:debty", title="D", status="verified", release="R0",
             flags=["debt"], group="capability:c",
             source={"adapter": "spec_tree", "path": "s/d.md"}),
    ])

def _cfg():
    return Config(data=deep_merge(DEFAULTS, {"gates": [
        {"item": "story:gated", "reason": "await pricing decision"}]}))

def test_dashboard(tmp_path):
    d = render_all(_graph(), _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]
    inprog = d.split("## In progress")[1].split("##")[0]
    assert "wip" in inprog and "ready" not in inprog
    ready = d.split("## Ready queue")[1].split("##")[0]
    assert "[ready]" in ready and "[blocked]" not in ready and "[gated]" not in ready
    assert "await pricing decision" in d.split("## Blocked on decisions")[1].split("##")[0]
    assert "2/6" in d.split("## Progress")[1]     # done statuses: done1 (shipped) + debty (verified)

def test_completion_sheet(tmp_path):
    c = render_all(_graph(), _cfg(), tmp_path, only={"completion_sheet"})["completion-sheet.md"]
    assert "| verified | 1 |" in c
    assert "| Verified-rate | 50.0% |" in c       # 1 verified / (1 shipped + 1 verified)
    assert "| Debt (flagged items) | 1 |" in c
    assert "story:debty" not in c                  # links use id tails, not raw ids
    assert "[debty](../../s/d.md)" in c
