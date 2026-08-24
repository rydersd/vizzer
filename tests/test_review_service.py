import base64
import hashlib
import http.client
import json
import threading
from pathlib import Path

from vizzer import __version__
from vizzer.cli import _make_serve_server, _read_graph, main
from vizzer.review_contract import plan_fingerprint


PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAA"
    "AABJRU5ErkJggg=="
)


def _prepare(tmp_path: Path, make_repo) -> tuple[Path, dict]:
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(config.read_text(encoding="utf-8") + """

[reviews]
enabled = true
plans_dir = "vizzer/reviews/plans"
runs_dir = "vizzer/reviews/runs"
evidence_dir = "vizzer/reviews/evidence"
""", encoding="utf-8")
    criteria = [
        "The status page renders its current service state.",
        "The desktop preview shows the same service state.",
    ]
    source = repo / "product-spec/status-review.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "## Definition of done\n\n" + "\n".join(criteria), encoding="utf-8"
    )
    source_record = {
        "itemId": "story:status-review",
        "path": "product-spec/status-review.md",
        "fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "adapter": "spec-tree",
    }
    plan = {
        "schema": 1,
        "id": "status-review",
        "title": "Service status acceptance",
        "description": "Repeat the same acceptance in a browser and desktop preview.",
        "rows": [{
            "id": "web-status",
            "title": "Web status",
            "source": source_record,
            "definitionOfDone": [criteria[0]],
            "steps": [{
                "id": "open-status",
                "instruction": "Open the status route.",
                "expected": "The current service state is visible.",
                "mode": "browser",
                "adapter": "browser-fixture",
                "operation": "open-route",
                "inputs": {"route": "/status"},
            }],
            "evidenceRequirements": [{
                "id": "done-state",
                "kind": "screenshot",
                "afterStepIds": ["open-status"],
                "required": True,
            }],
        }, {
            "id": "desktop-status",
            "title": "Desktop preview status",
            "source": source_record,
            "definitionOfDone": [criteria[1]],
            "steps": [{
                "id": "open-preview",
                "instruction": "Open the prepared desktop preview.",
                "expected": "The current service state is visible.",
                "mode": "local-app",
                "adapter": "desktop-fixture",
                "operation": "open-preview",
                "inputs": {"fixture": "service-status"},
            }],
            "evidenceRequirements": [{
                "id": "desktop-state",
                "kind": "screenshot",
                "afterStepIds": ["open-preview"],
                "required": True,
            }],
        }],
    }
    plans = repo / "vizzer/reviews/plans"
    plans.mkdir(parents=True)
    (plans / "status-review.json").write_text(json.dumps(plan), encoding="utf-8")
    (repo / "vizzer/reviews/adapters.json").write_text(json.dumps({
        "schema": 1,
        "adapters": [{
            "id": "browser-fixture",
            "modes": ["browser"],
            "operations": [{"id": "open-route", "requiredInputs": ["route"]}],
        }, {
            "id": "desktop-fixture",
            "modes": ["local-app"],
            "operations": [{"id": "open-preview", "requiredInputs": ["fixture"]}],
        }],
    }), encoding="utf-8")
    evidence = repo / "vizzer/reviews/evidence/status.png"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(PNG_1PX)
    assert main(["refresh", "--root", str(repo)]) == 0
    return repo, plan


def _event(plan: dict, *, actor: str = "agent", event_id: str = "agent-run-1") -> dict:
    event = {
        "eventId": event_id,
        "recordedAt": "2026-08-23T20:00:00Z",
        "actor": {"kind": actor, "id": "fixture-agent" if actor == "agent" else "project-owner"},
        "planId": plan["id"],
        "rowId": "web-status",
        "planFingerprint": plan_fingerprint(plan),
        "stepResults": [{"stepId": "open-status", "outcome": "pass"}],
        "evidence": [] if actor == "owner" else [{
            "requirementId": "done-state",
            "path": "vizzer/reviews/evidence/status.png",
            "sha256": hashlib.sha256(PNG_1PX).hexdigest(),
            "bytes": len(PNG_1PX),
            "mediaType": "image/png",
            "width": 1,
            "height": 1,
        }],
        "verdict": "pass",
    }
    if actor == "owner":
        event["basedOnAgentEventId"] = "agent-run-1"
    return event


def _request(connection, method: str, path: str, body=None, headers=None):
    payload = None if body is None else json.dumps(body)
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        request_headers["Content-Length"] = str(len(payload.encode("utf-8")))
    connection.request(method, path, payload, request_headers)
    response = connection.getresponse()
    raw = response.read()
    return response, raw


def test_review_cli_records_agents_and_keeps_plan_ledgers_independent(
    tmp_path, make_repo, capsys
):
    repo, plan = _prepare(tmp_path, make_repo)
    event_file = repo / "agent-event.json"
    event_file.write_text(json.dumps(_event(plan)), encoding="utf-8")
    assert main([
        "review", "record", "--root", str(repo), "--plan", plan["id"],
        "--file", str(event_file), "--expected-revision", "0",
    ]) == 0
    capsys.readouterr()
    assert main(["review", "show", "--root", str(repo)]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["plans"][0]["revision"] == 1
    row = state["plans"][0]["rows"][0]
    assert row["latest"]["agent"]["verdict"] == "pass"
    assert "path" not in row["latest"]["agent"]["evidence"][0]
    assert [path.name for path in (repo / "vizzer/reviews/runs").iterdir()] == [
        "status-review"
    ]


def test_plan_revision_starts_a_new_ledger_without_rewriting_history(
    tmp_path, make_repo, capsys
):
    repo, plan = _prepare(tmp_path, make_repo)
    event_file = repo / "agent-event.json"
    event_file.write_text(json.dumps(_event(plan)), encoding="utf-8")
    command = [
        "review", "record", "--root", str(repo), "--plan", plan["id"],
        "--file", str(event_file), "--expected-revision", "0",
    ]
    assert main(command) == 0
    capsys.readouterr()

    source = repo / plan["rows"][0]["source"]["path"]
    source.write_text(source.read_text() + "\nA revised source note.\n", encoding="utf-8")
    revised = json.loads(json.dumps(plan))
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    for row in revised["rows"]:
        row["source"]["fingerprint"] = fingerprint
    (repo / "vizzer/reviews/plans/status-review.json").write_text(
        json.dumps(revised), encoding="utf-8"
    )
    revised_event = _event(revised, event_id="agent-run-2")
    event_file.write_text(json.dumps(revised_event), encoding="utf-8")

    assert main(command) == 0
    ledgers = sorted((repo / "vizzer/reviews/runs/status-review").glob("*.json"))
    assert len(ledgers) == 2
    assert all(json.loads(path.read_text())["revision"] == 1 for path in ledgers)


def test_malformed_sibling_plan_does_not_block_a_valid_plan_mutation(
    tmp_path, make_repo, capsys
):
    repo, plan = _prepare(tmp_path, make_repo)
    (repo / "vizzer/reviews/plans/broken.json").write_text("{not json")
    event_file = repo / "agent-event.json"
    event_file.write_text(json.dumps(_event(plan)), encoding="utf-8")

    assert main([
        "review", "record", "--root", str(repo), "--plan", plan["id"],
        "--file", str(event_file), "--expected-revision", "0",
    ]) == 0
    capsys.readouterr()
    assert main(["review", "show", "--root", str(repo)]) == 0
    state = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in state["plans"]] == ["status-review"]
    assert state["warnings"][0]["file"] == "broken.json"
    assert "malformed JSON" in state["warnings"][0]["error"]


def test_review_storage_rejects_a_symlinked_parent_even_inside_the_project(
    tmp_path, make_repo, capsys
):
    repo, _ = _prepare(tmp_path, make_repo)
    reviews = repo / "vizzer/reviews"
    store = repo / "vizzer/review-store"
    reviews.rename(store)
    reviews.symlink_to(store, target_is_directory=True)

    assert main(["review", "show", "--root", str(repo)]) == 2
    assert "may not traverse a symlink" in capsys.readouterr().out


def test_check_gates_stale_review_source_fingerprints(tmp_path, make_repo, capsys):
    repo, plan = _prepare(tmp_path, make_repo)
    assert main(["check", "--root", str(repo)]) == 0
    capsys.readouterr()
    source = repo / plan["rows"][0]["source"]["path"]
    source.write_text("The acceptance contract changed.", encoding="utf-8")

    assert main(["check", "--root", str(repo)]) == 2
    assert "review source changed" in capsys.readouterr().out


def test_review_http_presents_agent_evidence_and_appends_owner_validation(
    tmp_path, make_repo
):
    repo, plan = _prepare(tmp_path, make_repo)
    event_file = repo / "agent-event.json"
    event_file.write_text(json.dumps(_event(plan)), encoding="utf-8")
    assert main([
        "review", "record", "--root", str(repo), "--plan", plan["id"],
        "--file", str(event_file), "--expected-revision", "0",
    ]) == 0
    graph = _read_graph(repo)
    server = _make_serve_server(repo, graph, repo / "vizzer/views", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection(*server.server_address[:2], timeout=2)
    try:
        response, raw = _request(connection, "GET", "/api/reviews")
        context = json.loads(raw)
        assert response.status == 200
        assert context["engineVersion"] == __version__

        response, raw = _request(
            connection, "GET", "/api/reviews", headers={"Host": "attacker.invalid"}
        )
        assert response.status == 421
        assert "loopback Host" in json.loads(raw)["error"]
        row = context["plans"][0]["rows"][0]
        evidence = row["latest"]["agent"]["evidence"][0]
        assert evidence["available"] is True
        assert evidence["url"].startswith("/api/reviews/evidence/status-review/")

        response, raw = _request(connection, "GET", evidence["url"])
        assert response.status == 200
        assert response.getheader("Content-Type") == "image/png"
        assert response.getheader("X-Content-Type-Options") == "nosniff"
        assert response.getheader("Cross-Origin-Resource-Policy") == "same-origin"
        assert raw == PNG_1PX

        evidence_file = repo / "vizzer/reviews/evidence/status.png"
        evidence_file.write_bytes(b"x" * len(PNG_1PX))
        response, raw = _request(connection, "GET", "/api/reviews")
        unavailable = json.loads(raw)["plans"][0]["rows"][0]["latest"]["agent"]["evidence"][0]
        assert unavailable["available"] is False
        assert "url" not in unavailable
        response, raw = _request(connection, "GET", evidence["url"])
        assert response.status == 404
        assert "recorded size and SHA-256" in json.loads(raw)["error"]
        evidence_file.write_bytes(PNG_1PX)

        owner = _event(plan, actor="owner", event_id="owner-run-1")
        guarded = {
            "Origin": f"http://{connection.host}:{connection.port}",
            "Host": f"{connection.host}:{connection.port}",
            "X-Vizzer-CSRF": context["csrfToken"],
        }
        response, raw = _request(connection, "POST", "/api/reviews/runs", {
            "expectedRevision": 1,
            "event": _event(plan, event_id="agent-http-run"),
        }, guarded)
        assert response.status == 400
        assert "owner runs" in json.loads(raw)["error"]

        response, raw = _request(connection, "POST", "/api/reviews/runs", {
            "expectedRevision": 1, "event": owner,
        })
        assert response.status == 403

        response, raw = _request(connection, "POST", "/api/reviews/runs", {
            "expectedRevision": 1, "event": owner,
        }, guarded)
        assert response.status == 200, raw
        assert json.loads(raw)["revision"] == 2

        response, raw = _request(connection, "GET", "/api/reviews")
        updated = json.loads(raw)
        assert updated["plans"][0]["rows"][0]["latest"]["owner"]["verdict"] == "pass"

        response, raw = _request(connection, "POST", "/api/reviews/runs", {
            "expectedRevision": 1,
            "event": _event(plan, actor="owner", event_id="owner-run-2"),
        }, guarded)
        assert response.status == 409
        assert "stale" in json.loads(raw)["error"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_review_boundaries_reject_http_agents_cli_owners_and_outside_evidence(
    tmp_path, make_repo, capsys
):
    repo, plan = _prepare(tmp_path, make_repo)
    owner_file = repo / "owner-event.json"
    owner_file.write_text(json.dumps(_event(plan, actor="owner")), encoding="utf-8")
    assert main([
        "review", "record", "--root", str(repo), "--plan", plan["id"],
        "--file", str(owner_file), "--expected-revision", "0",
    ]) == 2
    assert "owners validate through vizzer serve" in capsys.readouterr().out

    escaped = _event(plan)
    escaped["evidence"][0]["path"] = "product-spec/status-review.md"
    escaped["evidence"][0]["sha256"] = hashlib.sha256(
        (repo / "product-spec/status-review.md").read_bytes()
    ).hexdigest()
    escaped["evidence"][0]["bytes"] = (
        repo / "product-spec/status-review.md"
    ).stat().st_size
    escaped_file = repo / "escaped-event.json"
    escaped_file.write_text(json.dumps(escaped), encoding="utf-8")
    assert main([
        "review", "record", "--root", str(repo), "--plan", plan["id"],
        "--file", str(escaped_file), "--expected-revision", "0",
    ]) == 2
    assert "evidence_dir" in capsys.readouterr().out
