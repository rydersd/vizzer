import json
from vizzer.model import ActiveWork, Graph, Group, Item, Milestone, MilestonePhase, Relation, SCHEMA


def _graph():
    return Graph(
        groups=[Group(id="epic:b", kind="epic", title="B"),
                Group(id="epic:a", kind="epic", title="A", meta={"goal": "g"})],
        items=[Item(id="story:z", title="Z", deps=["story:a"],
                    relations=[Relation(kind="revises", target="story:a")]),
               Item(id="story:a", title="A", status="shipped", group="epic:a")],
        conflicts=[{"item": "story:z", "field": "status",
                    "kept": {"adapter": "spec_tree", "value": "building"},
                    "dropped": {"adapter": "dag_import", "value": "specced"}}],
        warnings=["w2", "w1"],
        vocab={"statuses": [{"name": "shipped", "emoji": "✅", "done": True}]},
        milestones=[Milestone(
            id="M1",
            title="First usable slice",
            goal="Prove the workflow.",
            phases=[MilestonePhase(name="Floor", items=["story:a", "story:z"])],
        )],
        active_work=[ActiveWork(
            story_id="story:z", agent="Kepler", task="Test the overlay",
            state="active", completed=1, total=2,
            updated_at="2026-08-08T17:00:00Z",
            stale_at="2026-08-08T19:00:00Z",
            checkpoint="negative controls", related_story_ids=["story:a"],
        )],
        activity={"source": "vizzer/active-work.json", "stale_after_minutes": 120},
    )


def test_to_dict_is_stable_sorted():
    d = _graph().to_dict()
    assert d["schema"] == SCHEMA
    assert [g["id"] for g in d["groups"]] == ["epic:a", "epic:b"]
    assert [i["id"] for i in d["items"]] == ["story:a", "story:z"]
    assert d["warnings"] == ["w1", "w2"]
    assert d["milestones"][0]["phases"][0]["items"] == ["story:a", "story:z"]


def test_dumps_roundtrip():
    g = _graph()
    d = json.loads(g.dumps())
    g2 = Graph.from_dict(d)
    assert g2.dumps() == g.dumps()          # deterministic fixpoint
    assert g.dumps().endswith("\n")
    assert g2.item_map()["story:a"].status == "shipped"
    assert g2.active_work[0].checkpoint == "negative controls"


def test_defaults():
    it = Item(id="x", title="X")
    assert it.status == "unknown" and it.deps == [] and it.relations == []
    assert it.activity == {} and it.priority == {}
    assert Group(id="g", kind="epic", title="T").meta == {}
    assert Milestone(id="M", title="T").phases == []


def test_from_dict_rejects_group_parent_cycle():
    data = _graph().to_dict()
    data["groups"] = [
        {"id": "epic:a", "kind": "epic", "title": "A", "parent": "epic:b"},
        {"id": "epic:b", "kind": "epic", "title": "B", "parent": "epic:a"},
    ]

    try:
        Graph.from_dict(data)
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("cyclic group parents were accepted")


def test_from_dict_rejects_ids_without_nonempty_kind_and_slug():
    for collection, bad_id in (
        ("items", "story"),
        ("groups", ":orphan"),
        ("groups", "epic:"),
    ):
        data = _graph().to_dict()
        data[collection][0]["id"] = bad_id

        try:
            Graph.from_dict(data)
        except ValueError as exc:
            assert "id" in str(exc).lower()
        else:
            raise AssertionError(f"malformed {collection} id {bad_id!r} was accepted")


def test_from_dict_rejects_non_numeric_activity_metrics():
    data = _graph().to_dict()
    data["items"][0]["activity"] = {"commits": "many", "mentions": None}

    try:
        Graph.from_dict(data)
    except ValueError as exc:
        assert "activity" in str(exc).lower()
    else:
        raise AssertionError("non-numeric activity was accepted")


def test_from_dict_rejects_malformed_milestone_items():
    """codex-sequence-2026-08-08: persisted milestone membership is typed."""
    data = _graph().to_dict()
    data["milestones"][0]["phases"][0]["items"] = "story:a"

    try:
        Graph.from_dict(data)
    except ValueError as exc:
        assert "milestone" in str(exc).lower()
    else:
        raise AssertionError("malformed milestone items were accepted")


def test_typed_relations_roundtrip_and_reject_malformed_kind():
    data = _graph().to_dict()
    relation = next(item for item in data["items"] if item["id"] == "story:z")[
        "relations"
    ][0]
    assert relation == {"kind": "revises", "target": "story:a"}
    assert Graph.from_dict(data).item_map()["story:z"].relations == [
        Relation(kind="revises", target="story:a")
    ]

    relation["kind"] = "vague prose"
    with __import__("pytest").raises(ValueError, match="relation kind"):
        Graph.from_dict(data)
