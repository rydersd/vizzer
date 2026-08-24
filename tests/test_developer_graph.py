import copy
import json

import pytest

from vizzer.config import Config
from vizzer.developer_graph import (
    DeveloperGraphError,
    from_work_graph,
    validate_developer_graph,
)
from vizzer.model import ActiveWork, Graph, Group, Item, Relation
from vizzer.object_detail import object_detail_for


def neutral_graph():
    return Graph(
        groups=[
            Group(id="area:commerce", kind="area", title="Commerce"),
            Group(id="module:commerce/catalog", kind="module", title="Catalog",
                  parent="area:commerce"),
        ],
        items=[
            Item(
                id="service:catalog",
                title="Catalog API",
                status="building",
                group="module:commerce/catalog",
                one_liner="Lists published products.",
                deps=["database:catalog"],
                relations=[Relation(kind="tested-by", target="test:catalog-contract")],
                source={"adapter": "service-manifest", "path": "services/catalog.yaml"},
            ),
            Item(id="database:catalog", title="Catalog store", status="shipped",
                 group="area:commerce"),
            Item(id="test:catalog-contract", title="Catalog contract test", status="shipped",
                 group="module:commerce/catalog"),
        ],
        active_work=[ActiveWork(
            story_id="service:catalog", agent="runner-7", task="Verify public response",
            state="failed", completed=1, total=2,
            updated_at="2026-08-23T20:00:00Z",
            stale_at="2026-08-23T22:00:00Z",
            checkpoint="Health probe returned 503",
        )],
    )


def config(cap=900):
    return Config(data={
        "project": {"name": "Neutral service map"},
        "render": {"title": "System architecture"},
        "developer_flow": {"enabled": True, "materialization_cap": cap},
    })


def test_work_graph_projection_preserves_neutral_identity_relations_and_failure():
    value = from_work_graph(neutral_graph(), config())
    by_id = {entry["id"]: entry for entry in value["objects"]}
    groups = {entry["id"]: entry for entry in value["groups"]}

    assert by_id["service:catalog"]["kind"] == "service"
    assert by_id["service:catalog"]["groupId"] == "module:commerce/catalog"
    assert by_id["service:catalog"]["provenance"]["locator"] == "services/catalog.yaml"
    assert by_id["service:catalog"]["failure"]["message"] == "Health probe returned 503"
    assert by_id["service:catalog"]["statusRole"] == "blocked"
    assert value["limits"]["materializationCap"] == 900
    assert groups["area:commerce"]["detail"]["schema"] == "vizzer-object-detail/v1"
    assert groups["module:commerce/catalog"]["details"]["parentId"] == "area:commerce"
    assert groups["module:commerce/catalog"]["entityType"] == "group"
    assert {
        (edge["source"], edge["target"], edge["kind"])
        for edge in value["relations"]
    } == {
        ("service:catalog", "database:catalog", "depends-on"),
        ("service:catalog", "test:catalog-contract", "tested-by"),
    }


def test_adapter_injects_shared_detail_without_renderer_source_parsing():
    def details(item):
        return object_detail_for(item, sections={
            "definitionOfDone": [f"{item.title} passes its contract checks."],
        })

    value = from_work_graph(neutral_graph(), config(), detail_provider=details)
    assert value["objects"][0]["detail"]["sections"]["definitionOfDone"]


def test_contract_rejects_dangling_duplicate_cycle_and_count_lies():
    value = from_work_graph(neutral_graph(), config())

    dangling = copy.deepcopy(value)
    dangling["relations"][0]["target"] = "service:missing"
    with pytest.raises(DeveloperGraphError, match="dangling endpoint"):
        validate_developer_graph(dangling)

    duplicate = copy.deepcopy(value)
    duplicate["objects"].append(copy.deepcopy(duplicate["objects"][0]))
    duplicate["limits"]["sourceObjectCount"] += 1
    with pytest.raises(DeveloperGraphError, match="duplicate"):
        validate_developer_graph(duplicate)

    cycle = copy.deepcopy(value)
    cycle["groups"][0]["parentId"] = cycle["groups"][1]["id"]
    with pytest.raises(DeveloperGraphError, match="cycle"):
        validate_developer_graph(cycle)

    count_lie = copy.deepcopy(value)
    count_lie["limits"]["sourceObjectCount"] += 1
    with pytest.raises(DeveloperGraphError, match="does not match"):
        validate_developer_graph(count_lie)


@pytest.mark.parametrize("fixture_name", ["web_application.json", "data_pipeline.json"])
def test_unrelated_adapter_fixtures_share_the_portable_contract(fixture_name):
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "developer_graph" / fixture_name
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    validate_developer_graph(payload)
    assert payload["schema"] == 1
    assert payload["objects"]
    assert payload["provenance"]["source"].startswith("fixture-")


def test_shipped_source_and_generic_fixtures_contain_no_origin_project_identity():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    guarded = [root / "src" / "vizzer", root / "tests" / "fixtures" / "developer_graph"]
    forbidden = [
        "ill" + "tool",
        ".ill" + "tool",
        "ry" + "der",
        "application " + "support",
        "launch" + "services",
        "launch" + "d",
        "x" + "code",
    ]
    leaks = []
    for directory in guarded:
        if not directory.exists():
            continue
        for candidate in directory.rglob("*"):
            if candidate.is_file() and candidate.suffix in {
                ".py", ".json", ".js", ".css", ".html", ".md", ".toml",
            }:
                text = candidate.read_text(encoding="utf-8", errors="ignore").lower()
                for term in forbidden:
                    if term in text:
                        leaks.append(f"{candidate.relative_to(root)}: {term}")
    assert not leaks, "origin-project identity leaked:\n" + "\n".join(leaks)
