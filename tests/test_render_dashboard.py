from pathlib import Path
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


def test_in_progress_excludes_statuses_outside_the_vocabulary():
    """Prose statuses from doc headers must not be reported as active work.

    Real repos carry docs with `> Status: APPROVED` / `Diagnosis` / `PR`. The configured
    vocabulary is the lifecycle contract; an unrecognized string cannot be asserted active.
    """
    from vizzer.config import Config, DEFAULTS
    from vizzer.model import Graph, Item
    from vizzer.render import render_all

    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:real", title="Real", status="building", release="R0",
             source={"adapter": "spec_tree", "path": "s/real.md"}),
        Item(id="doc:noise", title="Noise", status="APPROVED",
             source={"adapter": "loose_docs", "path": "d/noise.md"}),
        Item(id="doc:noise2", title="Noise2", status="Diagnosis",
             source={"adapter": "loose_docs", "path": "d/noise2.md"}),
    ])
    section = render_all(graph, cfg, Path("."), only={"dashboard"})["dashboard.md"]
    inprog = section.split("## In progress")[1].split("##")[0]
    assert "real" in inprog
    assert "noise" not in inprog and "Diagnosis" not in inprog
