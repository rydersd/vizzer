import http.client
import json
import threading
import time
from contextlib import contextmanager
from urllib.parse import quote

import vizzer.cli as cli
from vizzer import __version__, render_id, write_marker
from vizzer.cli import _make_serve_server, _read_graph, main
from vizzer.install import _vendor, _write_version


def _question(prompt="Which route wins?"):
    return {
        "id": "question:route",
        "storyId": "story:canvas-core",
        "owner": "Ryder",
        "prompt": prompt,
        "options": [
            {"id": "shared", "label": "Shared", "tradeoff": "Portable."},
            {"id": "native", "label": "Native", "tradeoff": "Coupled."},
        ],
        "recommendation": {
            "optionId": "shared", "rationale": "Keeps the boundary portable.",
        },
        "falsifier": "A provider cannot express the shared contract.",
        "evidence": ["docs/architecture.md:12"],
    }


def _prepare_repo(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    config = repo / "vizzer/vizzer.toml"
    config.write_text(
        config.read_text() + '\n[activity]\npath = "vizzer/active-work.json"\n',
        encoding="utf-8",
    )
    _write_feed(repo, _question())
    assert main(["refresh", "--root", str(repo)]) == 0
    return repo


def _write_feed(repo, question):
    questions = question if isinstance(question, list) else [question]
    (repo / "vizzer/active-work.json").write_text(json.dumps({
        "schema": 1, "work": [], "questions": questions,
    }), encoding="utf-8")


def _request(connection, method, path, body=None, headers=None):
    payload = None if body is None else json.dumps(body)
    merged = dict(headers or {})
    if payload is not None:
        merged["Content-Type"] = "application/json"
    connection.request(method, path, body=payload, headers=merged)
    response = connection.getresponse()
    data = json.loads(response.read())
    return response.status, data


def _start(repo):
    graph = _read_graph(repo)
    server = _make_serve_server(
        repo, graph, repo / "vizzer/views", 0, csrf_token="test-token"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=3)
    headers = {
        "Origin": f"http://{host}:{port}", "X-Vizzer-CSRF": "test-token",
    }
    return server, thread, connection, headers


def _stop(server, thread, connection):
    connection.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_question_http_requires_csrf_and_accepts_nested_option_answer(
    tmp_path, make_repo
):
    repo = _prepare_repo(tmp_path, make_repo)
    activity_before = (repo / "vizzer/active-work.json").read_bytes()
    story = repo / "spec/drawing/epics/tools/stories/canvas-core.md"
    story_before = story.read_bytes()
    server, thread, connection, guarded = _start(repo)
    endpoint = f"/api/questions/{quote('question:route', safe='')}/answer"
    try:
        status, context = _request(connection, "GET", "/api/questions")
        assert status == 200
        assert context["engineVersion"] == __version__
        assert context["csrfToken"] == "test-token"
        assert context["revision"] == 0
        assert len(context["questions"]) == 1
        fingerprint = context["questions"][0]["fingerprint"]
        payload = {
            "expectedRevision": 0,
            "expectedFingerprint": fingerprint,
            "answer": {"kind": "option", "optionId": "shared"},
        }

        status, forbidden = _request(connection, "POST", endpoint, payload)
        assert status == 403
        assert "CSRF" in forbidden["error"]

        status, accepted = _request(
            connection, "POST", endpoint, payload, guarded
        )
        assert status == 200
        assert accepted["revision"] == 1
        assert accepted["decision"]["kind"] == "option"
        assert accepted["decision"]["optionId"] == "shared"
        assert accepted["reloadRequired"] is True
        assert (repo / "vizzer/active-work.json").read_bytes() == activity_before
        story_after = story.read_text(encoding="utf-8")
        assert story_after.encode("utf-8").startswith(story_before.rstrip(b"\n"))
        assert "## Evolution event — owner decision" in story_after
        assert "question:route" in story_after
        assert "accepted the recorded recommendation" in story_after

        status, updated = _request(connection, "GET", "/api/questions")
        assert status == 200
        assert updated["revision"] == 1
        assert updated["questions"] == []
        assert updated["decisions"][0]["question"]["id"] == "question:route"

        status, stale = _request(
            connection, "POST", endpoint, payload, guarded
        )
        assert status == 409
        assert "stale question answer revision" in stale["error"]
    finally:
        _stop(server, thread, connection)


def test_question_http_accepts_story_decision_queue_as_one_batch(
    tmp_path, make_repo
):
    repo = _prepare_repo(tmp_path, make_repo)
    second = _question(prompt="Which preview wins?")
    second["id"] = "question:preview"
    _write_feed(repo, [_question(), second])
    assert main(["refresh", "--root", str(repo)]) == 0
    server, thread, connection, guarded = _start(repo)
    try:
        status, context = _request(connection, "GET", "/api/questions")
        assert status == 200
        assert len(context["questions"]) == 2
        by_id = {question["id"]: question for question in context["questions"]}
        payload = {
            "expectedRevision": 0,
            "answers": [
                {"questionId": "question:route",
                 "expectedFingerprint": by_id["question:route"]["fingerprint"],
                 "answer": {"kind": "option", "optionId": "shared"}},
                {"questionId": "question:preview",
                 "expectedFingerprint": by_id["question:preview"]["fingerprint"],
                 "answer": {"kind": "freeform", "text": "Keep it exact."}},
            ],
        }
        status, accepted = _request(
            connection, "POST", "/api/questions/answers", payload, guarded,
        )
        assert status == 200
        assert accepted["revision"] == 2
        assert accepted["reloadRequired"] is False
        assert [decision["question"]["id"] for decision in accepted["decisions"]] == [
            "question:route", "question:preview",
        ]

        ledger = json.loads(
            (repo / "vizzer/question-answers.json").read_text(encoding="utf-8")
        )
        assert ledger["revision"] == 2
        assert len(ledger["answers"]) == 2
        story = repo / "spec/drawing/epics/tools/stories/canvas-core.md"
        assert story.read_text(encoding="utf-8").count(
            "## Evolution event — owner decision"
        ) == 2
        status, updated = _request(connection, "GET", "/api/questions")
        assert status == 200
        assert updated["questions"] == []
        assert len(updated["decisions"]) == 2
    finally:
        _stop(server, thread, connection)


def test_question_http_fingerprint_cas_and_validation(
    tmp_path, make_repo, monkeypatch
):
    """Answers are checked against the wording the page was served.

    A question reworded at its source but not yet refreshed is still the one
    the owner read, so his answer to it is accepted; the next refresh reopens
    the reworded question. A page still holding an older wording than the
    served one is refused.
    """
    repo = _prepare_repo(tmp_path, make_repo)
    monkeypatch.setattr(cli, "_schedule_background_refresh", lambda root: None)
    server, thread, connection, guarded = _start(repo)
    endpoint = "/api/questions/question%3Aroute/answer"
    try:
        _, context = _request(connection, "GET", "/api/questions")
        old_fingerprint = context["questions"][0]["fingerprint"]
        _write_feed(repo, _question(prompt="Which revised route wins?"))

        status, accepted = _request(connection, "POST", endpoint, {
            "expectedRevision": 0,
            "expectedFingerprint": old_fingerprint,
            "answer": {"kind": "option", "optionId": "shared"},
        }, guarded)
        assert status == 200, accepted
        assert accepted["revision"] == 1

        # The refresh publishes the revised wording, which reopens.
        assert main(["refresh", "--root", str(repo)]) == 0
        _, current = _request(connection, "GET", "/api/questions")
        assert [q["id"] for q in current["questions"]] == ["question:route"]
        assert current["questions"][0]["fingerprint"] != old_fingerprint
        assert [e["questionId"] for e in current["supersededAnswers"]] == [
            "question:route"]

        status, stale = _request(connection, "POST", endpoint, {
            "expectedRevision": 1,
            "expectedFingerprint": old_fingerprint,
            "answer": {"kind": "option", "optionId": "shared"},
        }, guarded)
        assert status == 409
        assert "stale question fingerprint" in stale["error"]

        status, invalid = _request(connection, "POST", endpoint, {
            "expectedRevision": 1,
            "expectedFingerprint": current["questions"][0]["fingerprint"],
            "answer": {"kind": "option", "optionId": "invented"},
        }, guarded)
        assert status == 400
        assert "current option" in invalid["error"]
        ledger = json.loads(
            (repo / "vizzer/question-answers.json").read_text(encoding="utf-8"))
        assert ledger["revision"] == 1
    finally:
        _stop(server, thread, connection)


def test_question_get_uses_rendered_graph_snapshot_without_repo_rescan(
    tmp_path, make_repo, monkeypatch
):
    repo = _prepare_repo(tmp_path, make_repo)
    server, thread, connection, _ = _start(repo)
    monkeypatch.setattr(
        cli, "_build_fresh_graph",
        lambda *_: (_ for _ in ()).throw(AssertionError("GET rescanned repo")),
    )
    try:
        status, context = _request(connection, "GET", "/api/questions")
        assert status == 200
        assert context["engineVersion"] == __version__
        assert [question["id"] for question in context["questions"]] == [
            "question:route"
        ]
    finally:
        _stop(server, thread, connection)


def test_question_http_rejects_writes_from_stale_running_engine(
    tmp_path, make_repo
):
    repo = _prepare_repo(tmp_path, make_repo)
    _vendor(repo / "vizzer/engine")
    _write_version(repo)
    installed_layout = (
        repo / "vizzer/engine/vizzer/render/constellation/layout.css"
    )
    installed_layout.write_text(
        installed_layout.read_text(encoding="utf-8") + "\n/* newer engine */\n",
        encoding="utf-8",
    )
    write_marker(repo, render_id(repo))
    server, thread, connection, guarded = _start(repo)
    try:
        status, stale = _request(connection, "GET", "/api/questions")
        assert status == 409
        assert stale["runningEngineVersion"] == __version__
        assert "Restart vizzer serve" in stale["error"]

        status, rejected = _request(
            connection, "POST", "/api/questions/answers",
            {"expectedRevision": 0, "answers": []}, guarded,
        )
        assert status == 409
        assert "out of date" in rejected["error"]
        assert not (repo / "vizzer/question-answers.json").exists()
    finally:
        _stop(server, thread, connection)


def _wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return predicate()


def _failing_refresh(monkeypatch):
    """Make every background refresh fail to render, retrying fast."""
    monkeypatch.setattr(cli, "_REFRESH_RETRY_DELAYS", (0.1, 0.1, 0.1))
    monkeypatch.setattr(cli, "_refresh_entries", lambda *args: None)


def test_question_http_keeps_the_answer_when_refresh_fails(
    tmp_path, make_repo, monkeypatch, capsys
):
    repo = _prepare_repo(tmp_path, make_repo)
    story = repo / "spec/drawing/epics/tools/stories/canvas-core.md"
    server, thread, connection, guarded = _start(repo)
    try:
        _, context = _request(connection, "GET", "/api/questions")
        _failing_refresh(monkeypatch)
        status, accepted = _request(
            connection, "POST", "/api/questions/question%3Aroute/answer", {
                "expectedRevision": 0,
                "expectedFingerprint": context["questions"][0]["fingerprint"],
                "answer": {"kind": "freeform", "text": "Use an adapter."},
            }, guarded,
        )
        assert status == 200, accepted
        assert accepted["revision"] == 1
        assert "## Evolution event — owner decision" in story.read_text(encoding="utf-8")

        def failed_twice():
            _, served = _request(connection, "GET", "/api/questions")
            failure = served.get("refreshFailure") or {}
            return served if failure.get("attempts", 0) >= 2 else None

        served = _wait_for(failed_twice)
        assert served, "the failed refresh was not retried"
        assert served["revision"] == 1, "the answer was never rolled back"
        assert served["questions"] == []
        assert served["viewsBehind"] is True
        assert "could not render" in served["refreshFailure"]["error"]
        ledger = json.loads(
            (repo / "vizzer/question-answers.json").read_text(encoding="utf-8"))
        assert ledger["revision"] == 1
        assert "view refresh attempt 2" in capsys.readouterr().err

        # Once the cause is gone the next retry catches the views up.
        monkeypatch.undo()

        def caught_up():
            _, served = _request(connection, "GET", "/api/questions")
            # The graph lands a moment before the worker clears its failure.
            return served if not served["viewsBehind"] and not served["refreshFailure"] else None

        served = _wait_for(caught_up)
        assert served and served["refreshFailure"] is None
        assert _read_graph(repo).owner_questions == []
    finally:
        _stop(server, thread, connection)


def test_question_batch_keeps_every_answer_when_refresh_fails(
    tmp_path, make_repo, monkeypatch
):
    repo = _prepare_repo(tmp_path, make_repo)
    second = _question(prompt="Which preview wins?")
    second["id"] = "question:preview"
    _write_feed(repo, [_question(), second])
    assert main(["refresh", "--root", str(repo)]) == 0
    server, thread, connection, guarded = _start(repo)
    try:
        _, context = _request(connection, "GET", "/api/questions")
        by_id = {question["id"]: question for question in context["questions"]}
        _failing_refresh(monkeypatch)
        status, accepted = _request(
            connection, "POST", "/api/questions/answers", {
                "expectedRevision": 0,
                "answers": [
                    {"questionId": question_id,
                     "expectedFingerprint": by_id[question_id]["fingerprint"],
                     "answer": {"kind": "option", "optionId": "shared"}}
                    for question_id in ("question:route", "question:preview")
                ],
            }, guarded,
        )
        assert status == 200, accepted
        assert accepted["revision"] == 2

        def failed():
            _, served = _request(connection, "GET", "/api/questions")
            return served if served.get("refreshFailure") else None

        served = _wait_for(failed)
        assert served and served["revision"] == 2 and served["questions"] == []
        ledger = json.loads(
            (repo / "vizzer/question-answers.json").read_text(encoding="utf-8"))
        assert len(ledger["answers"]) == 2
    finally:
        monkeypatch.undo()
        _stop(server, thread, connection)


def test_question_http_rolls_back_only_when_the_story_note_fails(
    tmp_path, make_repo, monkeypatch
):
    repo = _prepare_repo(tmp_path, make_repo)
    story = repo / "spec/drawing/epics/tools/stories/canvas-core.md"
    story_before = story.read_bytes()
    monkeypatch.setattr(cli, "_schedule_background_refresh", lambda root: None)
    server, thread, connection, guarded = _start(repo)
    try:
        _, context = _request(connection, "GET", "/api/questions")

        def fail(*_args):
            raise OSError("story is read-only")

        monkeypatch.setattr(cli, "append_evolution_events", fail)
        status, rejected = _request(
            connection, "POST", "/api/questions/question%3Aroute/answer", {
                "expectedRevision": 0,
                "expectedFingerprint": context["questions"][0]["fingerprint"],
                "answer": {"kind": "freeform", "text": "Use an adapter."},
            }, guarded,
        )
        assert status == 500
        assert rejected["revision"] == 0
        assert not (repo / "vizzer/question-answers.json").exists()
        assert story.read_bytes() == story_before
    finally:
        _stop(server, thread, connection)


def test_two_same_revision_answers_serialize_to_one_acceptance(
    tmp_path, make_repo, monkeypatch
):
    repo = _prepare_repo(tmp_path, make_repo)
    original_guard = cli._mutation_guard
    original_write = cli.write_answers
    attempts_lock = threading.Lock()
    both_attempted = threading.Event()
    attempts = 0

    @contextmanager
    def observed_guard(root):
        nonlocal attempts
        with attempts_lock:
            attempts += 1
            if attempts == 2:
                both_attempted.set()
        with original_guard(root):
            yield

    def held_write(cfg, root, ledger):
        assert both_attempted.wait(timeout=2), "second mutation never reached the lock"
        return original_write(cfg, root, ledger)

    monkeypatch.setattr(cli, "_mutation_guard", observed_guard)
    monkeypatch.setattr(cli, "write_answers", held_write)
    monkeypatch.setattr(cli, "_schedule_background_refresh", lambda root: None)
    server, thread, context_connection, guarded = _start(repo)
    try:
        _, context = _request(context_connection, "GET", "/api/questions")
        payload = {
            "expectedRevision": 0,
            "expectedFingerprint": context["questions"][0]["fingerprint"],
            "answer": {"kind": "option", "optionId": "shared"},
        }
        host, port = server.server_address[:2]
        start = threading.Barrier(3)
        results = []
        results_lock = threading.Lock()

        def answer_once():
            connection = http.client.HTTPConnection(host, port, timeout=4)
            start.wait()
            result = _request(
                connection, "POST", "/api/questions/question%3Aroute/answer",
                payload, guarded,
            )
            connection.close()
            with results_lock:
                results.append(result)

        workers = [threading.Thread(target=answer_once) for _ in range(2)]
        for worker in workers:
            worker.start()
        start.wait()
        for worker in workers:
            worker.join(timeout=5)
            assert not worker.is_alive()

        assert sorted(status for status, _ in results) == [200, 409]
        ledger = json.loads(
            (repo / "vizzer/question-answers.json").read_text(encoding="utf-8")
        )
        assert ledger["revision"] == 1
        assert len(ledger["answers"]) == 1
    finally:
        _stop(server, thread, context_connection)
