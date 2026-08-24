import http.client
import json
import threading
from urllib.parse import quote

from vizzer.config import Config
from vizzer.cli import _make_serve_server, _read_graph, main
from vizzer.developer_store import prepare_developer_store
from vizzer.model import Graph, Group, Item


def _get(connection, path):
    connection.request("GET", path)
    response = connection.getresponse()
    return response.status, json.loads(response.read())


def _enabled_repo(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        + "\n[developer_flow]\nenabled = true\nmaterialization_cap = 100\n",
        encoding="utf-8",
    )
    assert main(["refresh", "--root", str(repo)]) == 0
    return repo


def test_loopback_developer_queries_drill_from_capability_to_object_neighborhood(
    tmp_path, make_repo
):
    repo = _enabled_repo(tmp_path, make_repo)
    graph = _read_graph(repo)
    server = _make_serve_server(repo, graph, repo / "vizzer/views", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        status, overview = _get(connection, "/api/developer-flow?scope=overview")
        assert status == 200
        assert overview["objects"] == []
        drawing = next(
            summary for summary in overview["summaries"]
            if summary["groupId"] == "capability:drawing"
        )
        assert drawing["objectCount"] == 2

        status, capability = _get(
            connection,
            "/api/developer-flow?scope=group&id="
            + quote("capability:drawing", safe=""),
        )
        assert status == 200
        assert {entry["id"] for entry in capability["objects"]} == {
            "story:canvas-core", "story:snap-to-grid",
        }
        assert all(
            entry["detail"]["id"] == entry["id"]
            for entry in capability["objects"]
            if not entry.get("boundaryOnly")
        )

        status, neighborhood = _get(
            connection,
            "/api/developer-flow?scope=object&id="
            + quote("story:snap-to-grid", safe=""),
        )
        assert status == 200
        assert {entry["id"] for entry in neighborhood["objects"]} == {
            "story:canvas-core", "story:snap-to-grid",
        }
        assert all(entry["detail"]["id"] == entry["id"]
                   for entry in neighborhood["objects"])
        assert neighborhood["relations"][0]["kind"] == "depends-on"

        status, rejected = _get(
            connection, "/api/developer-flow?scope=overview&surprise=true"
        )
        assert status == 400 and "unknown parameter" in rejected["error"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_loopback_developer_query_is_absent_when_add_on_is_disabled(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["refresh", "--root", str(repo)]) == 0
    graph = _read_graph(repo)
    server = _make_serve_server(repo, graph, repo / "vizzer/views", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        status, body = _get(connection, "/api/developer-flow?scope=overview")
        assert status == 404 and body["error"] == "developer flow is disabled"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_loopback_uses_current_read_only_store_without_reprojecting(
    tmp_path, monkeypatch,
):
    root = tmp_path / "large"
    (root / "vizzer/views").mkdir(parents=True)
    graph = Graph(
        groups=[Group(id="capability:scale", kind="capability", title="Scale")],
        items=[
            Item(id=f"story:item-{index}", title=f"Item {index}", status="ready",
                 group="capability:scale")
            for index in range(101)
        ],
    )
    cfg = Config(data={
        "project": {"name": "Stored HTTP"},
        "developer_flow": {"enabled": True, "materialization_cap": 100},
    })
    (root / "vizzer/vizzer-graph.json").write_text(
        graph.dumps(), encoding="utf-8",
    )
    prepare_developer_store(graph, cfg, root)
    monkeypatch.setattr(
        "vizzer.serve_extensions.index_from_work_graph",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("persisted query unexpectedly reprojected the graph")
        ),
    )

    server = _make_serve_server(root, graph, root / "vizzer/views", 0, cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        status, body = _get(
            connection,
            "/api/developer-flow?scope=group&id=capability%3Ascale&limit=3",
        )
        assert status == 200
        assert body["page"]["primaryReturned"] == 3
        assert all(entry["detail"]["id"] == entry["id"]
                   for entry in body["objects"])
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
