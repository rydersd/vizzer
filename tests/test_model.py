import json
from vizzer.model import Graph, Group, Item, SCHEMA


def _graph():
    return Graph(
        groups=[Group(id="epic:b", kind="epic", title="B"),
                Group(id="epic:a", kind="epic", title="A", meta={"goal": "g"})],
        items=[Item(id="story:z", title="Z", deps=["story:a"]),
               Item(id="story:a", title="A", status="shipped", group="epic:a")],
        conflicts=[{"item": "story:z", "field": "status",
                    "kept": {"adapter": "spec_tree", "value": "building"},
                    "dropped": {"adapter": "dag_import", "value": "specced"}}],
        warnings=["w2", "w1"],
        vocab={"statuses": [{"name": "shipped", "emoji": "✅", "done": True}]},
    )


def test_to_dict_is_stable_sorted():
    d = _graph().to_dict()
    assert d["schema"] == SCHEMA
    assert [g["id"] for g in d["groups"]] == ["epic:a", "epic:b"]
    assert [i["id"] for i in d["items"]] == ["story:a", "story:z"]
    assert d["warnings"] == ["w1", "w2"]


def test_dumps_roundtrip():
    g = _graph()
    d = json.loads(g.dumps())
    g2 = Graph.from_dict(d)
    assert g2.dumps() == g.dumps()          # deterministic fixpoint
    assert g.dumps().endswith("\n")
    assert g2.item_map()["story:a"].status == "shipped"


def test_defaults():
    it = Item(id="x", title="X")
    assert it.status == "unknown" and it.deps == [] and it.activity == {}
    assert Group(id="g", kind="epic", title="T").meta == {}
