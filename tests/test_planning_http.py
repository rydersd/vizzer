import http.client
import json
import threading

from vizzer.cli import _make_serve_server, _read_graph, main


def _request(connection, method, path, body=None, headers=None):
    payload = None if body is None else json.dumps(body)
    merged = dict(headers or {})
    if payload is not None:
        merged["Content-Type"] = "application/json"
    connection.request(method, path, body=payload, headers=merged)
    response = connection.getresponse()
    data = json.loads(response.read())
    return response.status, data


def test_loopback_planning_requires_origin_csrf_and_current_revision(
    tmp_path, make_repo
):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(config.read_text() + "\n[planning]\nenabled = true\n")
    assert main(["refresh", "--root", str(repo)]) == 0
    graph = _read_graph(repo)
    server = _make_serve_server(
        repo, graph, repo / "vizzer/views", 0, csrf_token="test-token"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=2)
    origin = f"http://{host}:{port}"
    state = {
        "promote": ["story:canvas-core"], "defer": [],
        "order": ["story:canvas-core"],
    }
    try:
        status, context = _request(connection, "GET", "/api/plan")
        assert status == 200
        assert context["csrfToken"] == "test-token"
        assert context["overlay"]["revision"] == 0

        status, _ = _request(
            connection, "POST", "/api/plan/analyze", {"state": state}
        )
        assert status == 403

        guarded = {"Origin": origin, "X-Vizzer-CSRF": "test-token"}
        status, analyzed = _request(
            connection, "POST", "/api/plan/analyze", {"state": state}, guarded
        )
        assert status == 200
        assert analyzed["analysis"]["proposal"] == state

        status, applied = _request(connection, "POST", "/api/plan/apply", {
            "state": state, "expectedRevision": 0,
            "rationale": "Raise export for a customer proof",
        }, guarded)
        assert status == 200
        assert applied["overlay"]["revision"] == 1
        assert applied["reloadRequired"] is True

        status, stale = _request(connection, "POST", "/api/plan/apply", {
            "state": state, "expectedRevision": 0,
            "rationale": "stale tab must lose",
        }, guarded)
        assert status == 409
        assert "stale planning revision" in stale["error"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_loopback_planning_rejects_unknown_id_and_malformed_json(
    tmp_path, make_repo
):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(config.read_text() + "\n[planning]\nenabled = true\n")
    assert main(["refresh", "--root", str(repo)]) == 0
    graph = _read_graph(repo)
    server = _make_serve_server(
        repo, graph, repo / "vizzer/views", 0, csrf_token="test-token"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=2)
    guarded = {
        "Origin": f"http://{host}:{port}", "X-Vizzer-CSRF": "test-token",
        "Content-Type": "application/json",
    }
    try:
        status, unknown = _request(connection, "POST", "/api/plan/analyze", {
            "state": {"promote": ["story:../../nope"], "defer": [], "order": []},
        }, guarded)
        assert status == 400
        assert "unknown planning item" in unknown["error"]

        connection.request(
            "POST", "/api/plan/analyze", body="{bad", headers=guarded
        )
        response = connection.getresponse()
        assert response.status == 400
        assert "malformed JSON" in json.loads(response.read())["error"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_loopback_planning_rebuilds_graph_instead_of_accepting_launch_snapshot(
    tmp_path, make_repo
):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(config.read_text() + "\n[planning]\nenabled = true\n")
    assert main(["refresh", "--root", str(repo)]) == 0
    graph = _read_graph(repo)
    server = _make_serve_server(
        repo, graph, repo / "vizzer/views", 0, csrf_token="test-token"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=2)
    guarded = {
        "Origin": f"http://{host}:{port}", "X-Vizzer-CSRF": "test-token",
    }
    try:
        # The launch snapshot still has canvas-core; the current source tree no longer does.
        (repo / "spec/drawing/epics/tools/stories/canvas-core.md").unlink()
        status, body = _request(connection, "POST", "/api/plan/analyze", {
            "state": {"promote": ["story:canvas-core"], "defer": [], "order": []},
        }, guarded)
        assert status == 400
        assert "unknown planning item" in body["error"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
