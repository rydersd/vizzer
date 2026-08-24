import http.client
import json
import threading
from urllib.parse import quote

from vizzer.cli import _make_serve_server, _read_graph, main


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

        status, neighborhood = _get(
            connection,
            "/api/developer-flow?scope=object&id="
            + quote("story:snap-to-grid", safe=""),
        )
        assert status == 200
        assert {entry["id"] for entry in neighborhood["objects"]} == {
            "story:canvas-core", "story:snap-to-grid",
        }
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
