import json
import time
from pathlib import Path

from vizzer.config import Config
from vizzer.developer_graph import from_work_graph
from vizzer.developer_query import MAX_RESPONSE_BYTES, DeveloperGraphIndex
from vizzer.model import Graph, Group, Item
from vizzer.render import developer_flow


ROOT = Path(__file__).resolve().parents[1]


def large_graph(count=10_000, group_count=50):
    groups = [
        Group(id=f"domain:d{index}", kind="domain", title=f"Domain {index}")
        for index in range(group_count)
    ]
    items = []
    for index in range(count):
        deps = []
        if index:
            deps.append(f"task:t{index - 1}")
        if index >= group_count:
            deps.append(f"task:t{index - group_count}")
        items.append(Item(
            id=f"task:t{index}", title=f"Task {index}",
            status="building" if index % 23 == 0 else "backlog",
            group=f"domain:d{index % group_count}", deps=deps,
        ))
    return Graph(groups=groups, items=items)


def test_10k_projection_is_linear_enough_and_materialization_is_bounded():
    cfg = Config(data={
        "project": {"name": "Large neutral corpus"},
        "render": {"title": "Large corpus"},
        "developer_flow": {
            "enabled": True,
            "materialization_cap": 600,
            "direction": "RIGHT",
        },
    })
    started = time.monotonic()
    data = from_work_graph(large_graph(), cfg)
    elapsed = time.monotonic() - started

    assert data["limits"]["sourceObjectCount"] == 10_000
    assert data["limits"]["sourceRelationCount"] > 19_000
    assert data["limits"]["materializationCap"] == 600
    assert elapsed < 10.0, f"10k projection took {elapsed:.2f}s"
    source = (ROOT / "tools" / "developer-flow" / "src" / "main.jsx").read_text()
    assert "const objectById=new Map" in source
    assert "onlyRenderVisibleElements" in source


def test_large_standalone_view_bootstraps_aggregates_not_the_enterprise_payload():
    cfg = Config(data={
        "project": {"name": "Large neutral corpus"},
        "render": {"title": "Large corpus"},
        "developer_flow": {
            "enabled": True,
            "materialization_cap": 600,
            "direction": "RIGHT",
        },
    })
    page = developer_flow.render(large_graph(), cfg, ROOT)["developer-flow.html"]
    assert '"mode":"served"' in page
    assert '"endpoint":"/api/developer-flow"' in page
    assert '"sourceObjectCount":10000' in page
    assert '"task:t9999"' not in page
    assert len(page.encode("utf-8")) < 3 * 1024 * 1024


def test_25k_enterprise_slice_is_bounded_and_discloses_omitted_objects():
    cfg = Config(data={
        "project": {"name": "Enterprise neutral corpus"},
        "render": {"title": "Enterprise corpus"},
        "developer_flow": {
            "enabled": True,
            "materialization_cap": 600,
            "direction": "RIGHT",
        },
    })
    started = time.monotonic()
    data = from_work_graph(large_graph(25_000, group_count=10), cfg)
    index = DeveloperGraphIndex(data)
    overview = index.query({"schema": 1, "scope": {"kind": "overview"}})
    group = index.query({
        "schema": 1,
        "scope": {"kind": "group", "id": overview["summaries"][0]["groupId"]},
        "page": {"limit": 600},
    })
    elapsed = time.monotonic() - started
    encoded = json.dumps(
        group, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    assert data["limits"]["sourceObjectCount"] == 25_000
    assert group["page"]["matched"] == 2_500
    assert group["page"]["primaryReturned"] == 600
    assert group["page"]["nextCursor"]
    assert group["page"]["encodedBytes"] == len(encoded) <= MAX_RESPONSE_BYTES
    assert elapsed < 25.0, f"25k normalization + indexing + query took {elapsed:.2f}s"
