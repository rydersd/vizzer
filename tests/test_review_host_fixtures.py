import hashlib
import http.server
import json
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.images import image_dimensions, image_media_type
from vizzer.review_contract import plan_fingerprint
from vizzer.review_service import append_review_event, review_state


FIXTURES = Path(__file__).parent / "fixtures"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


def _configured_root(tmp_path: Path) -> tuple[Config, dict]:
    criteria = [
        "The web status page reports that all systems are ready.",
        "The project-local status probe records a passing report.",
    ]
    source = tmp_path / "product-spec/service-status.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "## Definition of done\n\n" + "\n".join(criteria), encoding="utf-8"
    )
    source_record = {
        "itemId": "story:service-status",
        "path": "product-spec/service-status.md",
        "fingerprint": hashlib.sha256(source.read_bytes()).hexdigest(),
        "adapter": "loose-docs",
    }
    plan = {
        "schema": 1,
        "id": "portable-status",
        "title": "Portable service status",
        "rows": [{
            "id": "web-ready",
            "title": "Browser status",
            "source": source_record,
            "definitionOfDone": [criteria[0]],
            "steps": [{
                "id": "open-status",
                "instruction": "Open the prepared status page.",
                "expected": "The page reports that all systems are ready.",
                "mode": "browser",
                "adapter": "web-fixture",
                "operation": "open-route",
                "inputs": {"route": "/status.html"},
            }],
            "evidenceRequirements": [{
                "id": "browser-state",
                "kind": "screenshot",
                "afterStepIds": ["open-status"],
                "required": True,
            }],
        }, {
            "id": "local-ready",
            "title": "Local status probe",
            "source": source_record,
            "definitionOfDone": [criteria[1]],
            "steps": [{
                "id": "probe-status",
                "instruction": "Run the trusted project-local status probe.",
                "expected": "The generated report records a passing outcome.",
                "mode": "command",
                "adapter": "local-fixture",
                "operation": "probe-status",
                "inputs": {"fixtureId": "sample-worker"},
            }],
            "evidenceRequirements": [{
                "id": "probe-report",
                "kind": "report",
                "afterStepIds": ["probe-status"],
                "required": True,
            }],
        }],
    }
    review_root = tmp_path / "vizzer/reviews"
    (review_root / "plans").mkdir(parents=True)
    (review_root / "evidence").mkdir()
    (review_root / "plans/portable-status.json").write_text(
        json.dumps(plan), encoding="utf-8"
    )
    (review_root / "adapters.json").write_text(json.dumps({
        "schema": 1,
        "adapters": [{
            "id": "web-fixture",
            "modes": ["browser"],
            "operations": [{"id": "open-route", "requiredInputs": ["route"]}],
        }, {
            "id": "local-fixture",
            "modes": ["command"],
            "operations": [{
                "id": "probe-status", "requiredInputs": ["fixtureId"],
            }],
        }],
    }), encoding="utf-8")
    cfg = Config(data=deep_merge(DEFAULTS, {"reviews": {
        "enabled": True,
        "plans_dir": "vizzer/reviews/plans",
        "runs_dir": "vizzer/reviews/runs",
        "evidence_dir": "vizzer/reviews/evidence",
        "adapters_path": "vizzer/reviews/adapters.json",
    }}))
    cfg.validate()
    return cfg, plan


def _event(plan: dict, row_id: str, step_id: str, requirement_id: str,
           evidence_path: Path, root: Path, kind: str, event_id: str) -> dict:
    payload = evidence_path.read_bytes()
    evidence = {
        "requirementId": requirement_id,
        "path": evidence_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }
    if kind == "screenshot":
        width, height = image_dimensions(payload)
        evidence.update({"mediaType": image_media_type(payload),
                         "width": width, "height": height})
    return {
        "eventId": event_id,
        "recordedAt": "2026-08-23T21:00:00Z",
        "actor": {"kind": "agent", "id": "fixture-agent"},
        "planId": plan["id"],
        "rowId": row_id,
        "planFingerprint": plan_fingerprint(plan),
        "stepResults": [{"stepId": step_id, "outcome": "pass"}],
        "evidence": [evidence],
        "verdict": "pass",
    }


def test_generic_web_and_local_hosts_execute_then_record_review_evidence(tmp_path):
    cfg, plan = _configured_root(tmp_path)
    web_root = FIXTURES / "review_web"
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        lambda *args, **kwargs: QuietHandler(*args, directory=str(web_root), **kwargs),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_address[1]}/status.html", timeout=2
        ) as response:
            assert response.status == 200
            assert b"All systems ready" in response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    screenshot = tmp_path / "vizzer/reviews/evidence/web-status.jpg"
    shutil.copyfile(web_root / "status.jpg", screenshot)
    first = append_review_event(
        cfg, tmp_path, plan["id"],
        _event(plan, "web-ready", "open-status", "browser-state",
               screenshot, tmp_path, "screenshot", "agent-web-1"),
        expected_revision=0, allow_owner=False,
    )
    assert first["revision"] == 1

    # The plan requests a symbolic operation. The trusted host integration,
    # outside the plan, supplies exact argv and mutable destination paths.
    report = tmp_path / "vizzer/reviews/evidence/local-report.json"
    completed = subprocess.run([
        sys.executable,
        str(FIXTURES / "review_local/status_probe.py"),
        str(FIXTURES / "review_local/status.json"),
        str(report),
    ], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(report.read_text())["outcome"] == "pass"
    second = append_review_event(
        cfg, tmp_path, plan["id"],
        _event(plan, "local-ready", "probe-status", "probe-report",
               report, tmp_path, "report", "agent-local-1"),
        expected_revision=1, allow_owner=False,
    )
    assert second["revision"] == 2
    state = review_state(cfg, tmp_path)
    assert [row["latest"]["agent"]["verdict"]
            for row in state["plans"][0]["rows"]] == ["pass", "pass"]


def test_review_runtime_and_generic_fixtures_have_no_originating_project_leaks():
    forbidden = [
        "ill" + "tool", "." + "ill" + "tool", "application" + " support",
        "launch" + "d", "x" + "code", "ry" + "der", "clau" + "de",
    ]
    paths = [
        Path(__file__).parents[1] / "src/vizzer/review_contract.py",
        Path(__file__).parents[1] / "src/vizzer/review_service.py",
        Path(__file__).parents[1] / "src/vizzer/review_adapters.py",
        Path(__file__).parents[1] / "src/vizzer/serve_extensions.py",
        *sorted((FIXTURES / "review_web").iterdir()),
        *sorted((FIXTURES / "review_local").iterdir()),
    ]
    for path in paths:
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        text = path.read_text(encoding="utf-8").casefold()
        assert not any(term in text for term in forbidden), path
