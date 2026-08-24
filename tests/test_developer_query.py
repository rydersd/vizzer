import copy
import json

import pytest

from vizzer.developer_query import (
    MAX_RESPONSE_BYTES, DeveloperGraphIndex, DeveloperQueryError,
)
from vizzer.developer_graph import from_work_graph
from vizzer.config import Config
from vizzer.model import Graph, Group, Item

from test_developer_flow import config, fixture


def _index() -> DeveloperGraphIndex:
    return DeveloperGraphIndex(from_work_graph(fixture(), config(True)))


def test_overview_is_aggregate_only_and_group_query_is_bounded():
    index = _index()
    overview = index.query({"schema": 1, "scope": {"kind": "overview"}})
    assert overview["objects"] == []
    assert overview["relations"] == []
    assert overview["summaries"]
    assert sum(row["objectCount"] for row in overview["summaries"]) >= 1

    group_id = overview["summaries"][0]["groupId"]
    page = index.query({
        "schema": 1,
        "scope": {"kind": "group", "id": group_id},
        "page": {"limit": 1},
    })
    assert len(page["objects"]) <= 1
    assert page["page"]["returned"] == len(page["objects"])
    assert all(entry["id"] != "" for entry in page["groups"])


def test_object_query_returns_only_focus_and_one_hop_with_relation_labels():
    index = _index()
    focus = next(object_id for object_id, edges in index.incident.items() if edges)
    result = index.query({
        "schema": 1,
        "scope": {"kind": "object", "id": focus},
        "filters": {"relationKinds": [index.incident[focus][0]["kind"]]},
    })
    returned = {entry["id"] for entry in result["objects"]}
    assert focus in returned
    assert result["relations"]
    assert all(
        relation["source"] in returned and relation["target"] in returned
        for relation in result["relations"]
    )


def test_group_query_preserves_cross_scope_dependencies_as_lightweight_boundaries():
    graph = Graph(
        groups=[
            Group(id="capability:orders", kind="capability", title="Orders"),
            Group(id="component:checkout", kind="component", title="Checkout",
                  parent="capability:orders"),
            Group(id="capability:identity", kind="capability", title="Identity"),
            Group(id="component:accounts", kind="component", title="Accounts",
                  parent="capability:identity"),
        ],
        items=[
            Item(id="service:checkout", title="Checkout", status="building",
                 group="component:checkout", deps=["service:accounts"]),
            Item(id="service:accounts", title="Accounts", status="shipped",
                 group="component:accounts"),
        ],
    )
    index = DeveloperGraphIndex(from_work_graph(graph, Config(data={
        "project": {"name": "Boundary fixture"},
        "developer_flow": {"enabled": True},
    })))
    result = index.query({
        "schema": 1,
        "scope": {"kind": "group", "id": "capability:orders"},
    })
    objects = {entry["id"]: entry for entry in result["objects"]}
    assert objects["service:checkout"].get("boundaryOnly") is not True
    assert objects["service:accounts"]["boundaryOnly"] is True
    assert objects["service:accounts"].get("detail") is None
    assert result["relations"][0]["kind"] == "depends-on"
    assert result["page"]["matched"] == 1
    assert result["page"]["boundaryMatched"] == 1
    assert result["page"]["boundaryReturned"] == 1
    assert result["page"]["boundaryOmitted"] == 0
    assert result["page"]["relationMatched"] == 1
    assert result["page"]["relationOmitted"] == 0
    assert all(entry["groupId"] != "capability:identity"
               for entry in result["summaries"])
    assert all(entry["id"] != "capability:identity"
               for entry in result["groups"])


def test_group_query_discloses_truncated_external_boundaries_and_relations():
    outside_count = 300
    graph = Graph(
        groups=[
            Group(id="capability:focus", kind="capability", title="Focus"),
            Group(id="capability:external", kind="capability", title="External"),
        ],
        items=[
            Item(id="service:focus", title="Focus", status="building",
                 group="capability:focus",
                 deps=[f"service:external-{index}" for index in range(outside_count)]),
            *(Item(id=f"service:external-{index}", title=f"External {index}",
                   status="shipped", group="capability:external")
              for index in range(outside_count)),
        ],
    )
    index = DeveloperGraphIndex(from_work_graph(graph, Config(data={
        "project": {"name": "Boundary disclosure fixture"},
        "developer_flow": {"enabled": True},
    })))
    result = index.query({
        "schema": 1,
        "scope": {"kind": "group", "id": "capability:focus"},
    })
    assert result["page"]["boundaryMatched"] == outside_count
    assert result["page"]["boundaryReturned"] == 250
    assert result["page"]["boundaryOmitted"] == 50
    assert result["page"]["relationMatched"] == outside_count
    assert result["page"]["relationReturned"] == 250
    assert result["page"]["relationOmitted"] == 50


def test_group_query_adapts_page_size_to_encoded_byte_budget():
    count = 100
    graph = Graph(
        groups=[Group(id="domain:large", kind="domain", title="Large")],
        items=[Item(id=f"object:{index}", title=f"Object {index}", status="ready",
                    group="domain:large") for index in range(count)],
    )
    projected = from_work_graph(graph, Config(data={
        "project": {"name": "Large details"},
        "developer_flow": {"enabled": True},
    }))
    for entry in projected["objects"]:
        entry["details"] = {"blob": "x" * 60_000}
    index = DeveloperGraphIndex(projected)
    result = index.query({
        "schema": 1, "scope": {"kind": "group", "id": "domain:large"},
        "page": {"limit": count},
    })
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= MAX_RESPONSE_BYTES
    assert 0 < result["page"]["primaryReturned"] < count
    assert result["page"]["nextCursor"]
    assert result["page"]["encodedBytes"] == len(encoded)
    assert result["page"]["encodedBytes"] <= result["page"]["maxEncodedBytes"]


def test_object_query_bounds_parallel_relationship_payloads():
    projected = from_work_graph(fixture(), config(True))
    template = projected["relations"][0]
    projected["relations"] = [
        {**template, "id": f"parallel:{index}:" + "x" * 470}
        for index in range(5_000)
    ]
    projected["limits"]["sourceRelationCount"] = len(projected["relations"])
    index = DeveloperGraphIndex(projected)
    result = index.query({
        "schema": 1,
        "scope": {"kind": "object", "id": template["source"]},
    })
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= MAX_RESPONSE_BYTES
    assert 0 < len(result["relations"]) < 5_000
    assert result["page"]["relationMatched"] == 5_000
    assert result["page"]["relationOmitted"] == 5_000 - len(result["relations"])
    assert result["page"]["encodedBytes"] == len(encoded)


def test_cursor_is_bound_to_snapshot_and_exact_query():
    graph = from_work_graph(fixture(), config(True))
    index = DeveloperGraphIndex(graph)
    group_id = next(iter(index.groups))
    first = index.query({
        "schema": 1, "scope": {"kind": "group", "id": group_id},
        "page": {"limit": 1},
    })
    cursor = first["page"]["nextCursor"]
    if cursor is None:
        pytest.skip("fixture group has only one matching object")
    with pytest.raises(DeveloperQueryError, match="another query"):
        index.query({
            "schema": 1, "scope": {"kind": "group", "id": group_id},
            "filters": {"query": "different"},
            "page": {"limit": 1, "cursor": cursor},
        })

    mutated = copy.deepcopy(graph)
    mutated["objects"][0]["id"] += "-changed"
    for relation in mutated["relations"]:
        if relation["source"] == graph["objects"][0]["id"]:
            relation["source"] = mutated["objects"][0]["id"]
        if relation["target"] == graph["objects"][0]["id"]:
            relation["target"] = mutated["objects"][0]["id"]
    with pytest.raises(DeveloperQueryError, match="stale"):
        DeveloperGraphIndex(mutated).query({
            "schema": 1, "scope": {"kind": "group", "id": group_id},
            "page": {"limit": 1, "cursor": cursor},
        })

    same_ids_changed_content = copy.deepcopy(graph)
    same_ids_changed_content["objects"][0]["status"] = "changed-with-stable-id"
    with pytest.raises(DeveloperQueryError, match="stale"):
        DeveloperGraphIndex(same_ids_changed_content).query({
            "schema": 1, "scope": {"kind": "group", "id": group_id},
            "page": {"limit": 1, "cursor": cursor},
        })


@pytest.mark.parametrize("query_case", [
    {"schema": 1, "scope": {"kind": "everything"}},
    {"schema": 1, "scope": {"kind": "overview"}, "unknown": True},
    {"schema": 1, "scope": {"kind": "group", "id": "missing"}},
    {"schema": 1, "scope": {"kind": "overview"}, "page": {"limit": 5001}},
])
def test_query_contract_fails_closed(query_case):
    with pytest.raises(DeveloperQueryError):
        _index().query(query_case)
