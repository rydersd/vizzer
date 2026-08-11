import http.client
import json
import threading

from vizzer import __version__
from vizzer.cli import _make_serve_server, _read_graph, main


def _request(connection, method, path, body=None, headers=None):
    payload = None if body is None else json.dumps(body)
    merged = dict(headers or {})
    if payload is not None:
        merged["Content-Type"] = "application/json"
    connection.request(method, path, body=payload, headers=merged)
    response = connection.getresponse()
    return response.status, json.loads(response.read())


def test_loopback_discussion_queue_is_guarded_audited_and_refreshes_markdown(
    tmp_path, make_repo
):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["refresh", "--root", str(repo)]) == 0
    graph = _read_graph(repo)
    server = _make_serve_server(
        repo, graph, repo / "vizzer/views", 0, csrf_token="test-token"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=3)
    guarded = {
        "Origin": f"http://{host}:{port}", "X-Vizzer-CSRF": "test-token",
    }
    request = {
        "expectedRevision": 0, "provider": "codex",
        "storyId": "story:canvas-core", "questions": [],
    }
    try:
        status, context = _request(connection, "GET", "/api/discussions")
        assert status == 200 and context["engineVersion"] == __version__
        assert context["queue"]["revision"] == 0

        status, denied = _request(
            connection, "POST", "/api/discussions/queue", request
        )
        assert status == 403 and "same-origin" in denied["error"]

        status, queued = _request(
            connection, "POST", "/api/discussions/queue", request, guarded
        )
        assert status == 200 and queued["changed"] is True
        assert queued["queue"]["queues"]["codex"][0] == "story:canvas-core"
        assert queued["queue"]["history"][0]["questionIds"] == []
        markdown = (repo / "vizzer/views/discussion-queue.md").read_text()
        assert "## Codex" in markdown and "canvas-core" in markdown
        assert "general Story discussion" in markdown

        status, stale = _request(
            connection, "POST", "/api/discussions/queue", request, guarded
        )
        assert status == 409 and "stale discussion queue revision" in stale["error"]

        retry = {**request, "expectedRevision": 1, "provider": "claude"}
        status, moved = _request(
            connection, "POST", "/api/discussions/queue", retry, guarded
        )
        assert status == 200
        assert moved["queue"]["queues"] == {
            "codex": [], "claude": ["story:canvas-core"],
        }
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_discussion_queue_rolls_back_when_refresh_fails(
    tmp_path, make_repo, monkeypatch
):
    import vizzer.cli as cli

    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["refresh", "--root", str(repo)]) == 0
    before = (repo / "vizzer/views/discussion-queue.md").read_text()
    graph = _read_graph(repo)
    server = _make_serve_server(
        repo, graph, repo / "vizzer/views", 0, csrf_token="test-token"
    )
    monkeypatch.setattr(cli, "_refresh", lambda root: 2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=3)
    guarded = {
        "Origin": f"http://{host}:{port}", "X-Vizzer-CSRF": "test-token",
    }
    try:
        status, failed = _request(connection, "POST", "/api/discussions/queue", {
            "expectedRevision": 0, "provider": "codex",
            "storyId": "story:canvas-core", "questions": [],
        }, guarded)
        assert status == 500 and "could not refresh" in failed["error"]
        assert not (repo / "vizzer/discussion-queue.json").exists()
        assert (repo / "vizzer/views/discussion-queue.md").read_text() == before
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
