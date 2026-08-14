from pathlib import Path
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import (
    ActiveWork, Graph, Group, Item, Milestone, MilestonePhase, OwnerQuestion,
    OwnerDecision, OwnerQuestionOption, OwnerQuestionRecommendation,
    owner_question_fingerprint,
)
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
    regression = out.split("## Regression queue", 1)[1].split("\n## ", 1)[0]
    assert "[b]" in regression and "[c]" not in regression


def test_regression_queue_sorts_v1_impact_and_separates_unranked_and_inflight(tmp_path):
    statuses = [
        {"name": "bug-gap", "emoji": "🐛", "done": False, "role": "regression"},
        {"name": "in-flight", "emoji": "✈️", "done": False, "role": "regression"},
    ]
    cfg = Config(data=deep_merge(DEFAULTS, {"status": statuses}))
    high = Item(id="story:z-high", title="High", status="bug-gap", release="R0")
    low = Item(id="story:a-low", title="Low", status="bug-gap", release="R0")
    unknown = Item(id="story:b-unknown", title="Unknown", status="bug-gap", release="R0")
    inflight = Item(id="story:c-inflight", title="Inflight", status="in-flight", release="R0")
    high.priority = {"defect": {
        "rank": 1, "lineage": "bug-against",
        "components": {"target_impact": 2, "incomplete_dependents": 4,
                       "total_dependents": 7},
    }}
    low.priority = {"defect": {
        "rank": 2, "lineage": "story-only",
        "components": {"target_impact": 0, "incomplete_dependents": 2,
                       "total_dependents": 3},
    }}
    graph = Graph(vocab=cfg.vocab, items=[low, unknown, inflight, high])

    out = render_all(graph, cfg, tmp_path, only={"dashboard"})["dashboard.md"]
    queue = out.split("## Regression queue", 1)[1].split("\n## ", 1)[0]

    assert queue.index("z-high") < queue.index("a-low") < queue.index("b-unknown")
    assert "### V1-impact bug gaps" in queue
    assert "Sorted by known hard-dependency blast radius, not guessed severity" in queue
    assert "### Remaining bug gaps by known graph reach" in queue
    assert "story-only estimate; missing `Bug against`" in queue
    assert "### Unscored bug gaps" in queue
    assert "### In-flight integration" in queue and "c-inflight" in queue


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


def test_dashboard_with_assessment_withholds_unassessed_priority_recommendation(tmp_path):
    graph = _graph()
    graph.priority = {
        "target_tier": "configured-items",
        "recommendations": ["story:ready"],
    }
    graph.assessment = {
        "items": {"story:ready": {
            "size": {"assessed_band": "S", "dimensions": {}},
            "impact": {}, "parallelism": {},
        }},
        "portfolio": {"small": [], "anchors": [], "defects": [],
                      "questions": [], "unknown_size": ["story:ready"]},
    }

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]

    assert "## Recommended uptake" not in out


def test_dashboard_renders_separate_assessed_portfolio_lanes(tmp_path):
    graph = _graph()
    profile = {
        "size": {
            "assessed_band": "S", "uncertainty": "U1",
            "plausible_range": {"min": "S", "max": "M"},
            "dimensions": {
                name: {"band": "S", "provenance": "authored"}
                for name in (
                    "implementation", "verification", "integration", "coordination",
                )
            },
        },
        "impact": {
            "structural_target_reach": 2, "immediate_unlock": 1,
        },
        "parallelism": {"classification": "candidate"},
    }
    graph.assessment = {
        "schema": 1,
        "method": "deterministic-delivery-assessment-v1",
        "items": {"story:ready": profile},
        "portfolio": {
            "small": ["story:ready"], "anchors": [], "defects": [],
            "questions": [], "unknown_size": ["story:blocked"],
        },
    }

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]

    section = out.split("## Provisional assessed portfolio", 1)[1].split("\n## ", 1)[0]
    assert "High structural-leverage small candidates" in section
    assert "S · U1" in section and "plausible S–M" in section
    assert "2 target(s), 1 immediate unlock(s)" in section
    assert "parallel: candidate" in section
    assert "1 otherwise eligible item(s) remain unsized" in section
    assert "universal AI speed multiplier" in section


def test_dashboard_labels_appetite_only_profile_unassessed(tmp_path):
    graph = _graph()
    graph.assessment = {
        "schema": 1,
        "items": {"story:ready": {
            "size": {
                "assessed_band": "S", "normalized_appetite": "S",
                "raw_authored_appetite": "small", "uncertainty": "U2",
                "plausible_range": {"min": "XS", "max": "M"},
                "dimensions": {
                    name: {"band": None, "provenance": "unknown"}
                    for name in (
                        "implementation", "verification", "integration", "coordination",
                    )
                },
            },
            "impact": {}, "parallelism": {"classification": "unknown"},
        }},
        "portfolio": {
            "small": [], "anchors": [], "defects": [], "questions": [],
            "unknown_size": ["story:ready"], "blocked": ["story:ready"],
        },
    }

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]

    assert "unassessed · U2 · authored-appetite proxy S" in out


def test_dashboard_renders_assessment_withholding_and_current_ownership(tmp_path):
    graph = _graph()
    graph.activity = {"as_of": "2026-08-10T10:30:00Z"}
    graph.active_work = [ActiveWork(
        story_id="story:ready", agent="Faraday", task="Size the route",
        state="blocked", completed=1, total=2,
        updated_at="2026-08-10T10:00:00Z",
        stale_at="2026-08-10T12:00:00Z",
    )]
    graph.assessment = {
        "schema": 1,
        "items": {"story:ready": {
            "size": {"assessed_band": "S", "uncertainty": "U2",
                     "plausible_range": {"min": "XS", "max": "M"}},
            "impact": {"structural_target_reach": 0, "immediate_unlock": 0},
            "parallelism": {"classification": "unknown"},
        }},
        "portfolio": {
            "small": [], "anchors": [], "defects": [], "questions": [],
            "occupied": ["story:ready"], "unknown_size": [],
            "warnings": ["delivery portfolio withheld: missing explicit target scope"],
        },
    }

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]

    assert "Freshly owned work" in out
    assert "Faraday: blocked — Size the route" in out
    assert "Assessment cautions" in out
    assert "missing explicit target scope" in out


def test_dashboard_keeps_stale_blockers_out_of_dispatch_lanes(tmp_path):
    graph = _graph()
    graph.active_work = [ActiveWork(
        story_id="story:ready", agent="Faraday", task="Owner ruling required",
        state="blocked", completed=1, total=2,
        updated_at="2026-08-10T08:00:00Z",
        stale_at="2026-08-10T10:00:00Z",
    )]
    graph.assessment = {
        "schema": 1,
        "items": {"story:ready": {
            "size": {"assessed_band": "S", "uncertainty": "U2",
                     "plausible_range": {"min": "XS", "max": "M"}},
            "impact": {"structural_target_reach": 1, "immediate_unlock": 1},
            "parallelism": {"classification": "unknown"},
        }},
        "portfolio": {
            "small": [], "anchors": [], "defects": [], "questions": [],
            "occupied": [], "blocked": ["story:ready"],
            "stale_work": ["story:ready"], "unknown_size": [],
        },
    }

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]

    assert "Unresolved stale blockers" in out
    assert "Faraday: blocked — Owner ruling required" in out
    assert "until a newer record or owner decision clears them" in out
    assert "High structural-leverage small candidates" not in out


def test_dashboard_degrades_malformed_persisted_assessment_without_markdown_injection(
    tmp_path,
):
    graph = _graph()
    graph.assessment = {
        "items": {"story:ready": {"size": [], "impact": "many", "parallelism": None}},
        "portfolio": {
            "small": ["story:ready", 42], "unknown_size": "not-a-list",
            "warnings": ["[click me](https://evil.invalid)\n## injected"],
        },
    }

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]

    assert "unassessed · U3 · unknown" in out
    assert "\\[click me\\]" in out
    assert "\n## injected" not in out


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


def test_dashboard_separates_owner_questions_from_operational_blockers(tmp_path):
    graph = _graph()
    graph.active_work = [ActiveWork(
        story_id="story:blocked", agent="Planck", task="Capture evidence",
        state="blocked", completed=0, total=1,
        updated_at="2026-08-08T17:00:00Z",
        stale_at="2026-08-08T19:00:00Z",
        checkpoint="Run the real corpus",
    )]
    graph.owner_questions = [OwnerQuestion(
        id="question:route",
        story_id="story:ready",
        owner="Ryder",
        prompt="Which route owns the decision?",
        options=[
            OwnerQuestionOption("shared", "Shared", "One authority."),
            OwnerQuestionOption("local", "Local", "Smaller patch."),
        ],
        recommendation=OwnerQuestionRecommendation(
            "shared", "Repeated concepts need one source.",
        ),
        falsifier="The concept remains permanently single-use.",
        evidence=["wiki/story.md:12"],
    )]

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]
    question_section = out.split("## Open owner questions")[1].split("##")[0]
    work_section = out.split("## Agent work")[1].split("##")[0]

    assert "Which route owns the decision?" in question_section
    assert "recommended: Shared" in question_section
    assert "Capture evidence" not in question_section
    assert "Capture evidence" in work_section and "question" not in work_section


def test_dashboard_separates_open_questions_from_accepted_decisions(tmp_path):
    graph = _graph()
    open_question = OwnerQuestion(
        id="question:open-route", story_id="story:ready", owner="Ryder",
        prompt="Which route remains open?",
        options=[
            OwnerQuestionOption("shared", "Shared", "One authority."),
            OwnerQuestionOption("local", "Local", "Smaller patch."),
        ],
        recommendation=OwnerQuestionRecommendation("shared", "Avoid drift."),
        falsifier="The concept stays single-use.", evidence=["wiki/story.md:12"],
    )
    answered_question = OwnerQuestion(
        id="question:answered-route", story_id="story:wip", owner="Ryder",
        prompt="Which route was accepted?",
        options=[
            OwnerQuestionOption("shared", "Shared", "One authority."),
            OwnerQuestionOption("local", "Local", "Smaller patch."),
        ],
        recommendation=OwnerQuestionRecommendation("shared", "Avoid drift."),
        falsifier="The concept stays single-use.", evidence=["wiki/story.md:20"],
    )
    graph.owner_questions = [open_question]
    graph.owner_decisions = [OwnerDecision(
        question=answered_question,
        fingerprint=owner_question_fingerprint(answered_question),
        revision=3,
        answered_at="2026-08-10T18:30:00Z",
        answered_by="Ryder",
        kind="option",
        option_id="shared",
        text=None,
    )]

    out = render_all(graph, _cfg(), tmp_path, only={"dashboard"})["dashboard.md"]
    open_section = out.split("## Open owner questions", 1)[1].split("\n## ", 1)[0]
    accepted = out.split("## Accepted owner decisions", 1)[1].split("\n## ", 1)[0]

    assert "Which route remains open?" in open_section
    assert "Which route was accepted?" not in open_section
    assert "Which route was accepted?" in accepted
    assert "selected **Shared** (`shared`)" in accepted
    assert "revision 3" in accepted and "Ryder" in accepted
    assert "Which route remains open?" not in accepted


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


def test_dashboard_strips_source_trailing_whitespace(tmp_path):
    """Generated Markdown hygiene cannot depend on source hard-break whitespace."""
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(
            id="story:spaced",
            title="Spaced",
            one_liner="A useful story with accidental trailing space   ",
            status="building",
            release="R0",
            source={"adapter": "spec_tree", "path": "s/spaced.md"},
        ),
    ])

    out = render_all(graph, cfg, tmp_path, only={"dashboard"})["dashboard.md"]

    assert not any(line.endswith((" ", "\t")) for line in out.splitlines())
