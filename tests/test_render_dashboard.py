from pathlib import Path
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import ActiveWork, Graph, Group, Item, Milestone, MilestonePhase
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


def test_parked_items_never_enter_the_ready_queue_and_done_items_leave_gates():
    """Parked work is deliberately on hold; completed work is not decision-blocked."""
    from vizzer.config import Config, DEFAULTS, deep_merge
    from vizzer.model import Graph, Item
    from vizzer.render import render_all

    cfg = Config(data=deep_merge(DEFAULTS, {"gates": [
        {"item": "story:finished", "reason": "historical gate"}]}))
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:parked", title="Parked", status="parked", release="R0",
             source={"adapter": "spec_tree", "path": "s/p.md"}),
        Item(id="story:finished", title="Finished", status="shipped", release="R0",
             source={"adapter": "spec_tree", "path": "s/f.md"}),
        Item(id="story:open", title="Open", status="specced", release="R0",
             source={"adapter": "spec_tree", "path": "s/o.md"}),
    ])
    out = render_all(graph, cfg, Path("."), only={"dashboard"})["dashboard.md"]
    ready = out.split("## Ready queue")[1].split("##")[0]
    assert "[open]" in ready and "parked" not in ready
    blocked = out.split("## Blocked on decisions")[1].split("##")[0]
    assert "finished" not in blocked


def test_dashboard_uses_configured_roles_and_renders_active_milestone(tmp_path):
    """codex-sequence-2026-08-08: project lifecycle semantics stay configurable."""
    statuses = [
        {"name": "specced", "emoji": "📝", "done": False, "role": "ready"},
        {"name": "building", "emoji": "🔧", "done": False, "role": "active"},
        {"name": "bug-gap", "emoji": "🐛", "done": False, "role": "regression"},
        {"name": "shipped", "emoji": "✅", "done": True, "role": "done"},
    ]
    cfg = Config(data=deep_merge(DEFAULTS, {"status": statuses}))
    graph = Graph(
        groups=[Group(id="capability:c", kind="capability", title="Cap")],
        vocab=cfg.vocab,
        items=[
            Item(id="story:a", title="A", status="shipped", release="R0",
                 group="capability:c", source={"adapter": "spec_tree", "path": "s/a.md"}),
            Item(id="story:b", title="B", status="bug-gap", release="R0",
                 group="capability:c", deps=["story:a"],
                 source={"adapter": "spec_tree", "path": "s/b.md"}),
            Item(id="story:c", title="C", status="building", release="R0",
                 group="capability:c", source={"adapter": "spec_tree", "path": "s/c.md"}),
        ],
        milestones=[Milestone(
            id="M1", title="Usable slice", goal="Prove the workflow.",
            phases=[MilestonePhase(name="Floor", items=["story:a", "story:b"])],
        )],
    )

    out = render_all(graph, cfg, tmp_path, only={"dashboard"})["dashboard.md"]

    milestone = out.split("## Milestone: Usable slice")[1].split("## In progress")[0]
    assert "1/2" in milestone and "Next" in milestone and "[b]" in milestone
    active = out.split("## In progress")[1].split("##")[0]
    assert "[c]" in active and "[b]" not in active
    regression = out.split("## Regression queue")[1].split("##")[0]
    assert "[b]" in regression and "[c]" not in regression


def test_nonblocking_relations_do_not_block_ready_queue(tmp_path):
    from vizzer.model import Relation

    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:old", title="Old", status="specced", release="R0"),
        Item(id="story:new", title="New", status="specced", release="R0",
             relations=[Relation(kind="revises", target="story:old")]),
    ])

    out = render_all(graph, cfg, tmp_path, only={"dashboard"})["dashboard.md"]
    ready = out.split("## Ready queue")[1].split("##")[0]
    assert "new" in ready


def test_dashboard_renders_persisted_priority_rationale(tmp_path):
    graph = _graph()
    graph.priority = {
        "target_tier": "configured-items",
        "recommendations": ["story:ready"],
    }
    graph.item_map()["story:ready"].priority = {
        "rank": 1, "score": 940,
        "rationale": "1 incomplete target dependent(s), depth 1, role ready",
    }

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]

    section = out.split("## Recommended uptake")[1].split("##")[0]
    assert "score 940" in section and "depth 1" in section


def test_dashboard_renders_agent_checkpoint_evidence_without_fake_percent(tmp_path):
    graph = _graph()
    graph.active_work = [
        ActiveWork(
            story_id="story:wip", agent="Galileo", task="Implement tokens",
            state="active", completed=2, total=5,
            updated_at="2026-08-08T17:00:00Z",
            stale_at="2026-08-08T19:00:00Z", checkpoint="renderer tests",
        ),
        ActiveWork(
            story_id="story:ready", agent="Planck", task="Investigate",
            state="paused", completed=0, total=0,
            updated_at="2026-08-08T17:05:00Z",
            stale_at="2026-08-08T19:05:00Z",
        ),
    ]

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]
    section = out.split("## Agent work")[1].split("##")[0]

    assert "[wip](../../s/wip.md)" in section
    assert "2/5 checkpoints" in section and "now: renderer tests" in section
    assert "0/0 checkpoints (not estimated)" in section
    assert "%" not in section
    assert "stale after `2026-08-08T19:00:00Z`" in section


def test_dashboard_source_links_escape_markdown_path_delimiters(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:linked", title="Linked", status="building", release="R0",
             source={"adapter": "spec_tree", "path": "stories/a story#1(ready).md"}),
    ])

    out = render_all(graph, cfg, tmp_path, only={"dashboard"})["dashboard.md"]

    assert "[linked](../../stories/a%20story%231%28ready%29.md)" in out


def test_dashboard_progress_excludes_relation_only_foundation_groups(tmp_path):
    """codex-sequence-2026-08-08: structural roots are not 0/0 capabilities."""
    cfg = _cfg()
    graph = Graph(
        vocab=cfg.vocab,
        groups=[Group(id="foundation:geometry", kind="foundation", title="Geometry")],
        items=[Item(id="story:a", title="A", status="specced", release="R0")],
    )

    out = render_all(graph, cfg, tmp_path, only={"dashboard"})["dashboard.md"]

    assert "Geometry" not in out
