from pathlib import Path
import json

import pytest
import vizzer.assessment as assessment_module

from vizzer.assessment import (
    AssessmentSignals,
    apply_assessments,
    assess_graph,
    assess_story,
    assessment_is_current,
    normalize_appetite,
)
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Graph, Item
from vizzer.model import ActiveWork


def _item(name, deps=(), *, appetite=None, status="specced"):
    return Item(
        id=f"story:{name}", title=name, appetite=appetite, status=status,
        deps=[f"story:{dep}" for dep in deps],
    )


def _apply_with_known_burden(graph, cfg, tmp_path):
    """Bind explicit four-dimension proposals before testing dispatch policy."""
    cfg = Config(data=deep_merge(cfg.data, {
        "assessment": {"signals_path": "assessment-signals.json"},
    }))
    apply_assessments(graph, cfg, tmp_path)
    entries = {}
    for item in graph.items:
        band = normalize_appetite(item.appetite) or "S"
        entries[item.id] = {
            "scopeFingerprint": graph.assessment["items"][item.id]["scope_fingerprint"],
            "signals": {"authored_dimensions": {
                name: band for name in (
                    "implementation", "verification", "integration", "coordination",
                )
            }},
        }
    (tmp_path / "assessment-signals.json").write_text(json.dumps({
        "schema": 1, "items": entries,
    }), encoding="utf-8")
    apply_assessments(graph, cfg, tmp_path)


def test_appetite_normalizes_exact_aliases_but_retains_junk_drawer_verbatim():
    assert normalize_appetite("small") == "S"
    assert normalize_appetite("8") == "L"
    assert normalize_appetite("extra large") == "XL"
    assert normalize_appetite("small-to-medium") == "M"
    assert normalize_appetite("medium–large") == "L"
    assert normalize_appetite("quick / small-ish / maybe medium") is None

    graph = Graph(items=[_item("junk", appetite="quick / small-ish / maybe medium")])
    size = assess_story(graph, "story:junk")["size"]

    assert size["raw_authored_appetite"] == "quick / small-ish / maybe medium"
    assert size["normalized_appetite"] is None
    assert size["assessed_band"] is None
    assert size["uncertainty"] == "U3"
    assert any("retained verbatim" in value for value in size["unknowns"])


def test_authored_appetite_stays_separate_from_four_dimension_range():
    graph = Graph(items=[_item("cross-cutting", appetite="small")])
    result = assess_story(graph, "story:cross-cutting", signals=AssessmentSignals(
        authored_dimensions={
            "implementation": "S", "verification": "M",
            "integration": "L", "coordination": "M",
        },
        verification_harnesses=("pytest",),
    ))

    assert result["size"]["normalized_appetite"] == "S"
    assert result["size"]["assessed_band"] == "L"
    assert result["size"]["dimensions"]["integration"]["band"] == "L"
    assert result["size"]["plausible_range"] == {"min": "XS", "max": "XL"}
    assert result["size"]["uncertainty"] == "U2"


def test_authored_appetite_alone_never_becomes_assessed_burden():
    small = assess_story(Graph(items=[_item("small", appetite="small")]), "story:small")
    epic = assess_story(Graph(items=[_item("epic", appetite="epic")]), "story:epic")

    assert small["size"]["normalized_appetite"] == "S"
    assert epic["size"]["normalized_appetite"] == "XL"
    for result in (small, epic):
        assert result["size"]["assessed_band"] is None
        assert result["size"]["provenance"] == "unknown"
        assert result["size"]["plausible_range"] == {"min": "XS", "max": "XL"}
        assert result["size"]["uncertainty"] == "U3"


def test_invented_acceptance_test_names_do_not_improve_confidence_without_harness():
    graph = Graph(items=[_item("wishful", appetite="small")])
    named_only = assess_story(graph, "story:wishful", signals=AssessmentSignals(
        authored_dimensions={
            "implementation": "S", "integration": "XS", "coordination": "XS",
        },
        acceptance_checks=(
            "testEverythingIsPerfect", "testNoRegressionsEver", "testMagicWorks",
        ),
    ))
    executable = assess_story(graph, "story:wishful", signals=AssessmentSignals(
        authored_dimensions={
            "implementation": "S", "integration": "XS", "coordination": "XS",
        },
        acceptance_checks=("testEverythingIsPerfect",),
        verification_harnesses=("pytest",),
        harnessed_checks=("testEverythingIsPerfect",),
        verified_checks=("testEverythingIsPerfect",),
    ))

    verification = named_only["size"]["dimensions"]["verification"]
    assert verification["band"] is None
    assert verification["provenance"] == "unknown"
    assert named_only["size"]["uncertainty"] == "U2"
    assert executable["size"]["uncertainty"] == "U1"


def test_unresolved_questions_and_gates_force_at_least_u2():
    graph = Graph(items=[_item("gated", appetite="medium")])
    result = assess_story(graph, "story:gated", signals=AssessmentSignals(
        observed_dimensions={name: "M" for name in (
            "implementation", "verification", "integration", "coordination",
        )},
        unresolved_gates=("Apple signing account",),
        unresolved_questions=("question:storage-authority",),
    ))

    assert result["size"]["uncertainty"] == "U2"
    assert any("Apple signing account" in value for value in result["size"]["unknowns"])
    assert any("question:storage-authority" in value for value in result["size"]["unknowns"])


def test_impact_vector_is_structural_and_distinct_from_delivery_size():
    graph = Graph(items=[
        _item("foundation", appetite="large"),
        _item("first", ["foundation"]),
        _item("done-bridge", ["foundation"], status="shipped"),
        _item("second", ["done-bridge"]),
        _item("target", ["first", "second"]),
    ])
    result = assess_story(graph, "story:foundation", target_ids=["story:target"])

    assert result["size"]["normalized_appetite"] == "L"
    assert result["impact"] == {
        "structural_target_reach": 1,
        "immediate_unlock": 1,
        "frontier_reach": 2,
        "target_items": ["story:target"],
        "immediate_items": ["story:first"],
        "frontier_items": ["story:first", "story:second"],
        "provenance": "authored",
        "evidence": [
            "1 explicit target(s) in transitive dependency reach",
            "1 direct item(s) become dependency-ready after completion",
            "2 nearest unfinished downstream item(s)",
        ],
        "unknowns": [],
    }


def test_no_dependencies_is_not_parallel_safety_and_shared_writes_are_serial():
    graph = Graph(items=[_item("left"), _item("right"), _item("isolated")])
    results = assess_graph(graph, signals_by_item={
        "story:left": AssessmentSignals(
            write_surfaces=("src/shared.py",), parallel_evidence=("separate feature",),
        ),
        "story:right": AssessmentSignals(write_surfaces=("src/shared.py",)),
        "story:isolated": AssessmentSignals(),
    })

    assert results["story:left"]["parallelism"]["classification"] == "serial"
    assert results["story:right"]["parallelism"]["classification"] == "serial"
    assert "story:right" in results["story:left"]["parallelism"]["conflicts"][0]
    isolated = results["story:isolated"]["parallelism"]
    assert isolated["classification"] == "unknown"
    assert any("does not establish" in value for value in isolated["unknowns"])


def test_explicit_serial_surface_wins_over_parallel_claim():
    graph = Graph(items=[_item("build")])
    result = assess_story(graph, "story:build", signals=AssessmentSignals(
        write_surfaces=("Sources/Feature",),
        serial_surfaces=("shared Xcode project", "single simulator"),
        parallel_evidence=("source directories do not overlap",),
    ))

    assert result["parallelism"]["classification"] == "serial"
    assert any("shared Xcode project" in value for value in result["parallelism"]["conflicts"])
    assert result["size"]["dimensions"]["coordination"]["band"] == "L"


def test_scope_fingerprint_invalidates_estimate_when_contract_changes():
    item = _item("scoped", appetite="small")
    graph = Graph(items=[item])
    original_signals = AssessmentSignals(
        planned_surfaces=("editor",), acceptance_checks=("testUndo",),
    )
    original = assess_story(graph, item.id, signals=original_signals)

    assert assessment_is_current(original, item, original_signals)
    changed = AssessmentSignals(
        planned_surfaces=("editor", "persistence"),
        acceptance_checks=("testUndo", "testRestore"),
    )
    assert not assessment_is_current(original, item, changed)
    assert original["scope_fingerprint"] != assess_story(
        graph, item.id, signals=changed,
    )["scope_fingerprint"]


def test_assessment_rejects_unknown_signal_items_instead_of_silently_dropping_them():
    graph = Graph(items=[_item("known")])

    try:
        assess_graph(graph, signals_by_item={"story:typo": AssessmentSignals()})
    except KeyError as error:
        assert "story:typo" in str(error)
    else:
        raise AssertionError("unknown signal id should fail closed")


def test_observed_size_only_overrides_dimension_forecast_with_explicit_evidence():
    graph = Graph(items=[_item("history", appetite="large")])
    unsupported = assess_story(graph, "story:history", signals=AssessmentSignals(
        observed_size="S", authored_dimensions={"implementation": "M"},
    ))
    supported = assess_story(graph, "story:history", signals=AssessmentSignals(
        observed_size="S", authored_dimensions={"implementation": "M"},
        evidence=("p85 of 12 comparable completed stories",),
    ))

    assert unsupported["size"]["assessed_band"] == "M"
    assert unsupported["size"]["provenance"] == "authored"
    assert unsupported["size"]["uncertainty"] == "U3"
    assert any("lacks explicit evidence" in value for value in unsupported["size"]["unknowns"])
    assert supported["size"]["assessed_band"] == "S"
    assert supported["size"]["provenance"] == "observed"


def test_apply_assessments_is_opt_in_and_keeps_questions_out_of_delivery_lanes(tmp_path):
    story_dir = tmp_path / "wiki" / "stories"
    story_dir.mkdir(parents=True)
    (story_dir / "small.md").write_text(
        "# Small\n\nAppetite: small\n\nAcceptance: `testNamedButMissing`\n",
        encoding="utf-8",
    )
    small = _item("small", appetite="small")
    small.source = {"path": "wiki/stories/small.md", "deps_declared": True}
    anchor = _item("anchor", ["small"], appetite="large")
    anchor.source = {"deps_declared": True}
    graph = Graph(items=[small, anchor])
    graph.assessment = {"sentinel": True}

    disabled = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": False}}))
    apply_assessments(graph, disabled, tmp_path)
    assert graph.assessment == {"sentinel": True}

    # A minimal object with the same model contract avoids making this core
    # test depend on question-answer serialization details.
    graph.owner_questions = [type("Question", (), {
        "id": "question:small-route", "story_id": "story:small",
    })()]
    enabled = Config(data=deep_merge(DEFAULTS, {
        "assessment": {
            "enabled": True, "small_limit": 4, "anchor_limit": 2,
            "question_limit": 1,
        },
    }))
    apply_assessments(graph, enabled, tmp_path)

    assert graph.assessment["schema"] == 1
    assert set(graph.assessment["items"]) == {"story:anchor", "story:small"}
    small_result = graph.assessment["items"]["story:small"]
    assert small_result["size"]["uncertainty"] == "U3"
    assert any("lack an observed harness" in value
               for value in small_result["size"]["unknowns"])
    assert graph.assessment["portfolio"]["questions"] == ["story:small"]
    assert "story:small" not in graph.assessment["portfolio"]["small"]


def test_scope_fingerprint_changes_when_output_affecting_evidence_changes():
    item = _item("evidence", appetite="small")
    graph = Graph(items=[item])
    first = AssessmentSignals(
        write_surfaces=("src/a.py",), parallel_evidence=("isolated owner",),
        verified_checks=("testA",), evidence=("run:one",),
    )
    second = AssessmentSignals(
        write_surfaces=("src/a.py",), parallel_evidence=("shared reviewer",),
        verified_checks=("testB",), evidence=("run:two",),
    )
    assessment = assess_story(graph, item.id, signals=first)

    assert not assessment_is_current(assessment, item, second)


def test_signal_mapping_rejects_strings_where_sequences_are_required():
    graph = Graph(items=[_item("bad")])

    try:
        assess_story(graph, "story:bad", signals={"write_surfaces": "src/all.py"})
    except TypeError as error:
        assert "write_surfaces" in str(error)
    else:
        raise AssertionError("a string must not be split into character-sized surfaces")


def test_signal_mapping_rejects_unknown_dimension_size_values():
    graph = Graph(items=[_item("bad-dimension")])

    with pytest.raises(ValueError, match="unrecognized size values"):
        assess_story(graph, "story:bad-dimension", signals={
            "authored_dimensions": {"integration": "sort of medium-ish"},
        })


def test_empty_authored_dependencies_do_not_claim_zero_integration(tmp_path):
    source = tmp_path / "story.md"
    source.write_text("# Story\n\n> Deps: []\n\nAppetite: small\n", encoding="utf-8")
    story = _item("no-deps", appetite="small")
    story.source = {"path": "story.md", "deps_declared": True}
    graph = Graph(items=[story])
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    apply_assessments(graph, cfg, tmp_path)

    integration = graph.assessment["items"][story.id]["size"]["dimensions"]["integration"]
    assert integration["band"] is None
    assert integration["provenance"] == "unknown"


def test_portfolio_withholds_alphabetical_theater_without_target_scope(tmp_path):
    graph = Graph(items=[_item("a", appetite="small"), _item("b", appetite="medium")])
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    apply_assessments(graph, cfg, tmp_path)

    portfolio = graph.assessment["portfolio"]
    assert portfolio["small"] == []
    assert portfolio["anchors"] == []
    assert portfolio["warnings"] == [
        "delivery portfolio withheld: missing explicit target scope"
    ]


def test_empty_or_unknown_configured_targets_do_not_fake_target_scope(tmp_path):
    graph = Graph(
        items=[_item("small", appetite="small")],
        priority={"effective_targets": ["story:does-not-exist"]},
    )
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    apply_assessments(graph, cfg, tmp_path)

    assert graph.assessment["portfolio"]["small"] == []
    assert "missing explicit target scope" in graph.assessment["portfolio"]["warnings"][0]


def test_authored_appetite_without_four_dimension_burden_is_not_dispatch_size(tmp_path):
    proxy = _item("proxy-only", appetite="small")
    target = _item("target", ["proxy-only"], status="shipped")
    graph = Graph(items=[proxy, target], priority={
        "targets": [{"item": target.id, "sources": ["configured-item"]}],
    })
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    apply_assessments(graph, cfg, tmp_path)

    result = graph.assessment["items"][proxy.id]["size"]
    portfolio = graph.assessment["portfolio"]
    assert result["normalized_appetite"] == "S"
    assert result["assessed_band"] is None
    assert result["provenance"] == "unknown"
    assert all(value["band"] is None for value in result["dimensions"].values())
    assert proxy.id not in portfolio["small"]
    assert proxy.id in portfolio["unknown_size"]
    assert any("authored appetite is not an assessed burden profile" in warning
               for warning in portfolio["warnings"])


def test_portfolio_never_uses_xl_as_anchor_or_claims_two_unknown_parallel_anchors(tmp_path):
    medium = _item("medium", appetite="medium")
    medium.priority = {"eligible": True, "rank": 1, "components": {"course_order": None}}
    large = _item("large", appetite="large")
    large.priority = {"eligible": True, "rank": 2, "components": {"course_order": None}}
    xl = _item("xl", appetite="epic")
    xl.priority = {"eligible": True, "rank": 3, "components": {"course_order": None}}
    target = _item("target", ["medium", "large", "xl"], status="shipped")
    graph = Graph(items=[medium, large, xl, target], priority={
        "targets": [{"item": "story:target", "sources": ["configured-item"]}],
    })
    cfg = Config(data=deep_merge(DEFAULTS, {
        "assessment": {"enabled": True, "anchor_limit": 2},
    }))

    _apply_with_known_burden(graph, cfg, tmp_path)

    portfolio = graph.assessment["portfolio"]
    assert portfolio["anchors"] == ["story:medium"]
    assert "story:xl" not in portfolio["anchors"]
    assert any("second anchor withheld" in value for value in portfolio["warnings"])


def test_question_lane_includes_dependency_blocked_questions(tmp_path):
    blocked = _item("blocked", appetite="small")
    blocked.priority = {
        "eligible": False, "rank": None, "components": {"course_order": 0},
    }
    target = _item("target", ["blocked"], status="shipped")
    graph = Graph(items=[blocked, target], priority={
        "targets": [{"item": "story:target", "sources": ["configured-item"]}],
    })
    graph.owner_questions = [type("Question", (), {
        "id": "question:blocked-route", "story_id": "story:blocked",
    })()]
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    apply_assessments(graph, cfg, tmp_path)

    assert graph.assessment["portfolio"]["questions"] == ["story:blocked"]
    assert "story:blocked" not in graph.assessment["portfolio"]["small"]


def test_defect_portfolio_uses_separate_blast_radius_rank(tmp_path):
    low = _item("a-low", appetite="small", status="bug-gap")
    low.priority = {"defect": {"rank": 2}}
    high = _item("z-high", appetite="small", status="bug-gap")
    high.priority = {"defect": {"rank": 1}}
    graph = Graph(items=[low, high])
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    _apply_with_known_burden(graph, cfg, tmp_path)

    assert graph.assessment["portfolio"]["defects"] == [
        "story:z-high", "story:a-low",
    ]
    assert graph.assessment["portfolio"]["small"] == []


def test_defect_portfolio_withholds_questions_holds_and_unranked_items(tmp_path):
    ranked = _item("ranked", appetite="small", status="bug-gap")
    ranked.priority = {"defect": {"rank": 1}}
    questioned = _item("questioned", appetite="small", status="bug-gap")
    questioned.priority = {"defect": {"rank": 2}}
    unranked = _item("unranked", appetite="small", status="bug-gap")
    graph = Graph(items=[ranked, questioned, unranked])
    graph.owner_questions = [type("Question", (), {
        "id": "question:defect", "story_id": questioned.id,
    })()]
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    _apply_with_known_burden(graph, cfg, tmp_path)

    portfolio = graph.assessment["portfolio"]
    assert portfolio["defects"] == [ranked.id]
    assert portfolio["questions"] == [questioned.id]
    assert any("unranked" not in warning and "withheld" in warning
               for warning in portfolio["warnings"])


def test_candidate_test_source_text_is_not_promoted_to_observed_harness(tmp_path):
    story_dir = tmp_path / "wiki"
    test_dir = tmp_path / "tests"
    story_dir.mkdir()
    test_dir.mkdir()
    (story_dir / "story.md").write_text(
        "# Story\n\nAcceptance: `testCommentOnly`\n", encoding="utf-8",
    )
    (test_dir / "disabled.py").write_text(
        "# disabled someday: testCommentOnly\n", encoding="utf-8",
    )
    item = _item("story", appetite="small")
    item.source = {"path": "wiki/story.md"}
    graph = Graph(items=[item])
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    apply_assessments(graph, cfg, tmp_path)

    size = graph.assessment["items"]["story:story"]["size"]
    assert size["dimensions"]["verification"]["provenance"] == "unknown"
    assert size["uncertainty"] == "U3"
    assert any("execution unobserved" in value for value in size["evidence"])
    assert any("does not establish compilation" in value for value in size["unknowns"])


def test_owner_course_order_precedes_derived_impact_in_portfolio(tmp_path):
    owner_first = _item("owner-first", appetite="small")
    owner_first.priority = {
        "eligible": True, "rank": 2, "components": {"course_order": 0},
    }
    high_impact = _item("high-impact", appetite="small")
    high_impact.priority = {
        "eligible": True, "rank": 1, "components": {"course_order": 1},
    }
    target_one = _item("target-one", ["owner-first", "high-impact"], status="shipped")
    target_two = _item("target-two", ["high-impact"], status="shipped")
    graph = Graph(items=[owner_first, high_impact, target_one, target_two], priority={
        "targets": [
            {"item": "story:target-one", "sources": ["configured-item"]},
            {"item": "story:target-two", "sources": ["configured-item"]},
        ],
    })
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    _apply_with_known_burden(graph, cfg, tmp_path)

    assert graph.assessment["portfolio"]["small"][:2] == [
        "story:owner-first", "story:high-impact",
    ]


def test_active_blocked_and_paused_work_is_visible_but_not_new_dispatch(tmp_path):
    owned = _item("owned", appetite="small")
    available = _item("available", appetite="small")
    target = _item("target", ["owned", "available"], status="shipped")
    graph = Graph(items=[owned, available, target], priority={
        "targets": [{"item": target.id, "sources": ["configured-item"]}],
    }, activity={"as_of": "2026-08-10T10:30:00Z"}, active_work=[ActiveWork(
        story_id=owned.id, agent="Faraday", task="Audit", state="blocked",
        completed=1, total=2, updated_at="2026-08-10T10:00:00Z",
        stale_at="2026-08-10T12:00:00Z",
    )])
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    _apply_with_known_burden(graph, cfg, tmp_path)

    portfolio = graph.assessment["portfolio"]
    assert owned.id in portfolio["occupied"]
    assert owned.id not in portfolio["small"]
    assert available.id in portfolio["small"]


def test_stale_active_work_is_context_not_false_current_ownership(tmp_path):
    stale = _item("stale", appetite="small")
    target = _item("target", ["stale"], status="shipped")
    graph = Graph(
        items=[stale, target],
        priority={"targets": [{"item": target.id, "sources": ["configured-item"]}]},
        activity={"as_of": "2026-08-10T15:00:00Z"},
        active_work=[ActiveWork(
            story_id=stale.id, agent="Old agent", task="Old build", state="active",
            completed=1, total=2, updated_at="2026-08-10T10:00:00Z",
            stale_at="2026-08-10T12:00:00Z",
        )],
    )
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    _apply_with_known_burden(graph, cfg, tmp_path)

    portfolio = graph.assessment["portfolio"]
    assert stale.id in portfolio["stale_work"]
    assert stale.id not in portfolio["occupied"]
    assert stale.id in portfolio["small"]


def test_stale_blocked_work_remains_nondispatchable_until_resolved(tmp_path):
    blocked = _item("blocked", appetite="small")
    target = _item("target", ["blocked"], status="shipped")
    graph = Graph(
        items=[blocked, target],
        priority={"targets": [{"item": target.id, "sources": ["configured-item"]}]},
        activity={"as_of": "2026-08-10T15:00:00Z"},
        active_work=[ActiveWork(
            story_id=blocked.id, agent="Old agent", task="Owner ruling required",
            state="blocked", completed=1, total=2,
            updated_at="2026-08-10T10:00:00Z", stale_at="2026-08-10T12:00:00Z",
        )],
    )
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    _apply_with_known_burden(graph, cfg, tmp_path)

    portfolio = graph.assessment["portfolio"]
    assert blocked.id in portfolio["blocked"]
    assert blocked.id in portfolio["stale_work"]
    assert blocked.id not in portfolio["occupied"]
    assert blocked.id not in portfolio["small"]


def test_latest_activity_record_resolves_an_older_blocked_record(tmp_path):
    ready = _item("ready", appetite="small")
    target = _item("target", ["ready"], status="shipped")
    graph = Graph(
        items=[ready, target],
        priority={"targets": [{"item": target.id, "sources": ["configured-item"]}]},
        activity={"as_of": "2026-08-10T15:00:00Z"},
        active_work=[
            ActiveWork(
                story_id=ready.id, agent="Old agent", task="Blocked", state="blocked",
                completed=1, total=2, updated_at="2026-08-10T10:00:00Z",
                stale_at="2026-08-10T12:00:00Z",
            ),
            ActiveWork(
                story_id=ready.id, agent="Closer", task="Resolved", state="complete",
                completed=2, total=2, updated_at="2026-08-10T14:00:00Z",
                stale_at="2026-08-10T16:00:00Z",
            ),
        ],
    )
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    _apply_with_known_burden(graph, cfg, tmp_path)

    portfolio = graph.assessment["portfolio"]
    assert ready.id not in portfolio["blocked"]
    assert ready.id in portfolio["small"]


def test_custom_done_role_is_excluded_from_portfolio_and_unlocks_dependents(tmp_path):
    done = _item("done", appetite="small", status="finished")
    ready = _item("ready", ["done"], appetite="small", status="queued")
    ready.priority = {"eligible": True, "rank": 1, "components": {"course_order": 0}}
    target = _item("target", ["ready"], status="finished")
    graph = Graph(items=[done, ready, target], priority={
        "targets": [{"item": "story:target", "sources": ["configured-item"]}],
    })
    cfg = Config(data=deep_merge(DEFAULTS, {
        "status": [
            {"name": "queued", "role": "ready", "done": False},
            {"name": "finished", "role": "done", "done": True},
        ],
        "assessment": {"enabled": True},
    }))

    apply_assessments(graph, cfg, tmp_path)

    assert "story:done" not in graph.assessment["portfolio"]["small"]
    assert graph.assessment["items"]["story:done"]["impact"]["immediate_items"] == [
        "story:ready"
    ]


def test_shared_source_is_scanned_once_not_once_per_item(tmp_path, monkeypatch):
    source = tmp_path / "dag.json"
    source.write_text('{"acceptance":"testSharedContract"}', encoding="utf-8")
    left = _item("left", appetite="small")
    right = _item("right", appetite="small")
    left.source = {"path": "dag.json"}
    right.source = {"path": "dag.json"}
    graph = Graph(items=[left, right])
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))
    original = Path.read_bytes
    reads = []

    def tracked(path):
        if path.resolve() == source.resolve():
            reads.append(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", tracked)
    apply_assessments(graph, cfg, tmp_path)

    assert len(reads) == 1


def test_repo_local_signals_merge_explicit_evidence_without_erasing_live_gates(tmp_path):
    story = tmp_path / "story.md"
    story.write_text("# Story\n\nAcceptance: `testAutoContract`\n", encoding="utf-8")
    evidence_path = tmp_path / "vizzer" / "assessment-signals.json"
    evidence_path.parent.mkdir()
    item = _item("story", appetite="small")
    item.source = {"path": "story.md"}
    graph = Graph(items=[item])
    graph.owner_questions = [type("Question", (), {
        "id": "question:live", "story_id": "story:story",
    })()]
    cfg = Config(data=deep_merge(DEFAULTS, {
        "assessment": {
            "enabled": True,
            "signals_path": "vizzer/assessment-signals.json",
        },
        "gates": [{"item": "story:story", "reason": "owner approval"}],
    }))
    apply_assessments(graph, cfg, tmp_path)
    expected_scope = graph.assessment["items"]["story:story"]["scope_fingerprint"]
    evidence_path.write_text(json.dumps({
        "schema": 1,
        "items": {
            "story:story": {
                "scopeFingerprint": expected_scope,
                "signals": {
                "authored_dimensions": {"implementation": "L"},
                "integration_points": ["persistence boundary"],
                "planned_surfaces": ["editor", "storage"],
                "write_surfaces": ["src/editor.py"],
                "acceptance_checks": [],
                "scope_tokens": ["owner-assessment:v1"],
                "evidence": ["owner-reviewed scope"],
                "unknowns": ["migration volume unmeasured"],
                "unresolved_questions": [],
                "unresolved_gates": [],
                },
            },
            "story:removed": {"observed_size": "S"},
        },
    }), encoding="utf-8")

    apply_assessments(graph, cfg, tmp_path)

    result = graph.assessment["items"]["story:story"]
    assert result["size"]["dimensions"]["implementation"] == {
        "band": "L", "provenance": "authored",
        "evidence": ["authored implementation assessment: L"], "unknowns": [],
    }
    assert result["size"]["dimensions"]["verification"]["band"] is None
    assert result["size"]["dimensions"]["integration"]["band"] == "S"
    assert result["parallelism"]["write_surfaces"] == ["src/editor.py"]
    assert result["size"]["uncertainty"] == "U2"
    assert any("question:live" in value for value in result["size"]["unknowns"])
    assert any("owner approval" in value for value in result["size"]["unknowns"])
    assert "owner-reviewed scope" in result["size"]["evidence"]
    assert any("unknown item 'story:removed'" in warning for warning in graph.warnings)


def test_repo_local_signals_emit_a_reusable_pre_evidence_scope_fingerprint(tmp_path):
    story = tmp_path / "story.md"
    story.write_text("# Story\n\nAcceptance: `testBoundScope`\n", encoding="utf-8")
    item = _item("bound", appetite="small")
    item.source = {"path": "story.md"}
    graph = Graph(items=[item])
    cfg = Config(data=deep_merge(DEFAULTS, {
        "assessment": {"enabled": True, "signals_path": "signals.json"},
    }))

    apply_assessments(graph, cfg, tmp_path)
    source_scope = graph.assessment["items"][item.id]["scope_fingerprint"]
    signal_path = tmp_path / "signals.json"
    signal_path.write_text(json.dumps({
        "schema": 1,
        "items": {item.id: {
            "scopeFingerprint": source_scope,
            "signals": {
                "authored_dimensions": {"implementation": "L"},
                "evidence": ["owner-reviewed topology"],
            },
        }},
    }), encoding="utf-8")

    apply_assessments(graph, cfg, tmp_path)
    emitted_scope = graph.assessment["items"][item.id]["scope_fingerprint"]
    assert emitted_scope == source_scope

    # The documented refresh -> copy -> edit -> refresh loop must not make the
    # proposal self-invalidating merely because its own evidence was merged.
    signal_path.write_text(json.dumps({
        "schema": 1,
        "items": {item.id: {
            "scopeFingerprint": emitted_scope,
            "signals": {
                "authored_dimensions": {"implementation": "L"},
                "evidence": ["owner-reviewed topology", "second review"],
            },
        }},
    }), encoding="utf-8")
    apply_assessments(graph, cfg, tmp_path)

    result = graph.assessment["items"][item.id]
    assert result["size"]["dimensions"]["implementation"]["band"] == "L"
    assert not any("scope changed" in warning for warning in graph.warnings)


def test_repo_local_signals_can_supply_acceptance_when_source_scan_has_none(tmp_path):
    story = tmp_path / "story.md"
    story.write_text("# Research Story\n\nNo code selector is required.\n", encoding="utf-8")
    item = _item("research", appetite="small")
    item.source = {"path": "story.md"}
    graph = Graph(items=[item])
    cfg = Config(data=deep_merge(DEFAULTS, {
        "assessment": {"enabled": True, "signals_path": "signals.json"},
    }))
    apply_assessments(graph, cfg, tmp_path)
    scope = graph.assessment["items"][item.id]["scope_fingerprint"]
    (tmp_path / "signals.json").write_text(json.dumps({
        "schema": 1,
        "items": {item.id: {
            "scopeFingerprint": scope,
            "signals": {
                "acceptance_checks": ["pinned corpus replay"],
                "evidence": ["owner-reviewed research memo"],
            },
        }},
    }), encoding="utf-8")

    apply_assessments(graph, cfg, tmp_path)

    size = graph.assessment["items"][item.id]["size"]
    assert any("1 acceptance check name(s) lack an observed harness" in value
               for value in size["unknowns"])
    assert "owner-reviewed research memo" in size["evidence"]


def test_invalid_signals_entry_rejects_whole_manifest_without_crashing(tmp_path):
    evidence_path = tmp_path / "signals.json"
    graph = Graph(items=[
        _item("valid", appetite="small"), _item("invalid", appetite="small"),
    ])
    cfg = Config(data=deep_merge(DEFAULTS, {
        "assessment": {"enabled": True, "signals_path": "signals.json"},
    }))
    apply_assessments(graph, cfg, tmp_path)
    valid_scope = graph.assessment["items"]["story:valid"]["scope_fingerprint"]
    invalid_scope = graph.assessment["items"]["story:invalid"]["scope_fingerprint"]
    evidence_path.write_text(json.dumps({
        "schema": 1,
        "items": {
            "story:valid": {"scopeFingerprint": valid_scope, "signals": {
                "authored_dimensions": {"implementation": "L"},
            }},
            "story:invalid": {"scopeFingerprint": invalid_scope, "signals": {
                "authored_dimensions": {"implementation": "banana"},
            }},
        },
    }), encoding="utf-8")

    apply_assessments(graph, cfg, tmp_path)

    assert graph.assessment["items"]["story:valid"]["size"]["dimensions"][
        "implementation"
    ]["band"] is None
    assert any("manifest ignored" in warning and "banana" in warning
               for warning in graph.warnings)


def test_signals_manifest_rejects_self_certified_observation_and_stale_scope(tmp_path):
    story_path = tmp_path / "story.md"
    story_path.write_text("# Story\n\nAppetite: large\n", encoding="utf-8")
    item = _item("story", appetite="large")
    item.source = {"path": "story.md"}
    graph = Graph(items=[item])
    cfg = Config(data=deep_merge(DEFAULTS, {
        "assessment": {"enabled": True, "signals_path": "signals.json"},
    }))
    apply_assessments(graph, cfg, tmp_path)
    scope = graph.assessment["items"][item.id]["scope_fingerprint"]

    (tmp_path / "signals.json").write_text(json.dumps({
        "schema": 1, "items": {item.id: {
            "scopeFingerprint": scope,
            "signals": {"observed_size": "XS", "evidence": ["trust me"]},
        }},
    }), encoding="utf-8")
    apply_assessments(graph, cfg, tmp_path)
    assert graph.assessment["items"][item.id]["size"]["assessed_band"] is None
    assert any("cannot self-certify" in warning for warning in graph.warnings)

    # A source change invalidates otherwise-valid researched evidence.
    (tmp_path / "signals.json").write_text(json.dumps({
        "schema": 1, "items": {item.id: {
            "scopeFingerprint": scope,
            "signals": {"authored_dimensions": {"integration": "L"}},
        }},
    }), encoding="utf-8")
    story_path.write_text("# Story changed\n\nAppetite: large\n", encoding="utf-8")
    apply_assessments(graph, cfg, tmp_path)
    assert graph.assessment["items"][item.id]["size"]["dimensions"][
        "integration"
    ]["band"] is None
    assert any("scope changed" in warning for warning in graph.warnings)


@pytest.mark.parametrize("kind", ["escape", "symlink", "oversized", "malformed"])
def test_unsafe_or_malformed_signals_are_warned_and_ignored(
    tmp_path, monkeypatch, kind,
):
    outside = tmp_path.parent / f"outside-assessment-{tmp_path.name}.json"
    outside.write_text('{"schema":1,"items":{}}', encoding="utf-8")
    configured = "signals.json"
    path = tmp_path / configured
    if kind == "escape":
        configured = f"../{outside.name}"
    elif kind == "symlink":
        path.symlink_to(outside)
    elif kind == "oversized":
        path.write_text('{"schema":1,"items":{}}', encoding="utf-8")
        monkeypatch.setattr(assessment_module, "_MAX_SIGNALS_FILE_BYTES", 8)
    else:
        path.write_text("{ definitely not json", encoding="utf-8")
    graph = Graph(items=[_item("story", appetite="small")])
    cfg = Config(data=deep_merge(DEFAULTS, {
        "assessment": {"enabled": True, "signals_path": configured},
    }))

    apply_assessments(graph, cfg, tmp_path)

    assert graph.assessment["items"]["story:story"]["size"]["assessed_band"] is None
    assert any("assessment signals" in warning and "ignored" in warning
               for warning in graph.warnings)
    outside.unlink(missing_ok=True)


def test_unknown_target_intersections_do_not_claim_authored_impact_scope():
    graph = Graph(items=[_item("story", appetite="small")], priority={
        "effective_targets": ["story:missing"],
    })

    implicit = assess_story(graph, "story:story")
    supplied = assess_story(graph, "story:story", target_ids=["story:also-missing"])

    assert implicit["impact"]["provenance"] == "unknown"
    assert supplied["impact"]["provenance"] == "unknown"


def test_optional_default_signals_file_may_be_absent_without_warning(tmp_path):
    graph = Graph(items=[_item("story", appetite="small")])
    cfg = Config(data=deep_merge(DEFAULTS, {"assessment": {"enabled": True}}))

    apply_assessments(graph, cfg, tmp_path)

    assert not any("assessment signals" in warning for warning in graph.warnings)
