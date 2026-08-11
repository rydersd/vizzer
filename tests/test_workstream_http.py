import http.client
import json
import threading

from vizzer import __version__
from vizzer.cli import _make_serve_server, _read_graph, main


def test_loopback_workstream_get_reads_live_leases_without_rebuilding_static_html(
    tmp_path, make_repo,
):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(config.read_text() + """
[workstreams]
enabled = true
definitions_path = "vizzer/workstreams.json"
runtime_path = ".vizzer/runtime/sessions.json"
lease_minutes = 30
""")
    state = {"workstreams": [{
        "id": "canvas", "title": "Canvas", "objective": "Ship canvas",
        "status": "active", "lead": "Claude", "reviewer": "Codex",
        "storyIds": ["story:canvas-core"], "dependsOn": [],
        "allowedPaths": ["src/canvas"], "sharedPaths": [],
        "checkpoint": "Acceptance", "completed": 1, "total": 2,
    }], "discussions": []}
    request = repo / "workstreams.json"
    request.write_text(json.dumps(state))
    assert main([
        "workstreams", "apply", "--root", str(repo), "--file", str(request),
        "--expected-revision", "0", "--actor", "Ryder", "--rationale", "Split lane",
    ]) == 0
    assert main([
        "sessions", "start", "--root", str(repo), "--id", "claude",
        "--actor", "Claude", "--model", "Opus", "--role", "lead",
        "--workstream", "canvas", "--branch", "claude/canvas",
        "--worktree", "/private/tmp/canvas", "--expected-revision", "0",
    ]) == 0
    graph = _read_graph(repo)
    server = _make_serve_server(
        repo, graph, repo / "vizzer/views", 0, csrf_token="test-token"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=2)
    try:
        connection.request("GET", "/api/workstreams")
        response = connection.getresponse()
        body = json.loads(response.read())
        assert response.status == 200
        assert body["engineVersion"] == __version__
        assert body["workstreams"]["runtimeRevision"] == 1
        assert body["workstreams"]["sessions"][0]["actor"] == "Claude"
        assert body["workstreams"]["sessions"][0]["worktree"] == "canvas"
        assert "/private/tmp" not in json.dumps(body)
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
