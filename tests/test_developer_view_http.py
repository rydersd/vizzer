import http.client
import json
import threading

from vizzer.cli import _make_serve_server, _read_graph, main


def _document(identity="view-one"):
    return {
        "schema": 1, "id": identity, "name": "Drawing blockers",
        "view": {
            "schema": 1, "scope": "group", "id": "capability:drawing",
            "direction": "RIGHT", "selectedId": "story:snap-to-grid",
            "filters": {"query": "", "kind": "", "status": "",
                        "group": "", "relationKinds": ["depends-on"]},
        },
        "notes": "Owner walkthrough notes",
        "annotationsVisible": False,
        "annotations": [
            {"id": "note-one", "kind": "note", "color": "yellow",
             "x": 10, "y": 20, "text": "Check this dependency",
             "objectId": "story:snap-to-grid"},
            {"id": "stroke-one", "kind": "stroke", "color": "pink", "width": 3,
             "points": [[0, 0], [10, 10]]},
        ],
    }


def _request(connection, method, path, body=None, headers=None):
    payload = None if body is None else json.dumps(body).encode()
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers.update({
            "Content-Type": "application/json", "Content-Length": str(len(payload)),
        })
    connection.request(method, path, body=payload, headers=request_headers)
    response = connection.getresponse()
    return response.status, json.loads(response.read())


def _repo(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(
        config.read_text() + "\n[developer_flow]\nenabled = true\n"
        'views_path = "vizzer/developer-views.json"\n',
        encoding="utf-8",
    )
    assert main(["refresh", "--root", str(repo)]) == 0
    return repo


def test_served_views_persist_notes_sketches_share_ids_and_use_revision_cas(
    tmp_path, make_repo
):
    repo = _repo(tmp_path, make_repo)
    server = _make_serve_server(
        repo, _read_graph(repo), repo / "vizzer/views", 0, csrf_token="test-token"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=3)
    origin = f"http://{host}:{port}"
    guarded = {"Origin": origin, "X-Vizzer-CSRF": "test-token"}
    try:
        status, initial = _request(connection, "GET", "/api/developer-flow/views")
        assert status == 200
        assert initial["revision"] == 0 and initial["views"] == []
        assert initial["csrfToken"] == "test-token"

        status, stored = _request(connection, "POST", "/api/developer-flow/views", {
            "action": "upsert", "expectedRevision": 0, "view": _document(),
        }, guarded)
        assert status == 200 and stored["revision"] == 1
        assert stored["views"][0]["notes"] == "Owner walkthrough notes"
        assert stored["views"][0]["annotations"][1]["kind"] == "stroke"
        assert stored["views"][0]["annotationsVisible"] is False

        status, stale = _request(connection, "POST", "/api/developer-flow/views", {
            "action": "upsert", "expectedRevision": 0, "view": _document("other"),
        }, guarded)
        assert status == 409 and "stale" in stale["error"]

        status, forbidden = _request(connection, "POST", "/api/developer-flow/views", {
            "action": "delete", "expectedRevision": 1, "id": "view-one",
        })
        assert status == 403 and "CSRF" in forbidden["error"]

        status, deleted = _request(connection, "POST", "/api/developer-flow/views", {
            "action": "delete", "expectedRevision": 1, "id": "view-one",
        }, guarded)
        assert status == 200 and deleted["revision"] == 2
        assert deleted["views"] == []
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
