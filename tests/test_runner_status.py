"""Runner fleet on the served map: classification, endpoint, determinism, frontend.

Contracts: the lane label comes from runner labels (never the name); a runner
with no routing labels is out of pool (neutral); only an in-pool offline runner
is the alarm; /api/runners makes one runners call per cache window, looks up
jobs only when a runner is busy (bounded), and a failed refresh never leaves a
last-known-green payload; rendered views never read runner state.
"""
from __future__ import annotations

import copy
import http.client
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

from vizzer import runner_status
from vizzer.cli import _make_serve_server, _read_graph, main
from vizzer.config import Config
from vizzer.render import render_all
from vizzer.render.constellation import render as render_constellation

RUNNERS_JS = (Path(__file__).resolve().parents[1]
              / "src/vizzer/render/constellation/runners.js")


def _label(name, kind="custom"):
    return {"name": name, "type": kind}


FLEET = [
    {"id": 22, "name": "illtool-mac-light", "status": "offline", "busy": False, "labels": []},
    {"id": 21, "name": "illtool-mac-selfhosted", "status": "online", "busy": True,
     "labels": [_label(n, "read-only") for n in ("self-hosted", "macOS", "ARM64")]},
    {"id": 23, "name": "illtool-mbp-uitest", "status": "online", "busy": True,
     "labels": [_label("uitest"), _label("mbp"), _label("xctest-pr"), _label("heavy")]},
    {"id": 24, "name": "illtool-mini-light", "status": "online", "busy": False,
     "labels": [_label("light"), _label("mini")]},
    {"id": 25, "name": "illtool-mini-linux", "status": "online", "busy": False,
     "labels": [_label("self-hosted"), _label("ARM64"), _label("linux"), _label("docker")]},
    {"id": 26, "name": "illtool-mini-xctest", "status": "online", "busy": False,
     "labels": [_label("xctest-pr"), _label("mini"), _label("heavy")]},
]
RUNS = [
    {"id": 900, "name": "XCTest", "head_branch": "lane", "pull_requests": [{"number": 1349}]},
    {"id": 901, "name": "Token value write-back", "head_branch": "main", "pull_requests": []},
]
JOBS = {
    900: [{"run_id": 900, "name": "Curated XCTest suite", "status": "in_progress",
           "runner_name": "illtool-mbp-uitest", "started_at": "2026-09-25T04:58:04Z",
           "html_url": "https://github.test/job/1"},
          {"run_id": 900, "name": "queued", "status": "queued", "runner_name": "",
           "started_at": None, "html_url": ""}],
    901: [{"run_id": 901, "name": "value-only-round-trip", "status": "in_progress",
           "runner_name": "illtool-mac-selfhosted", "started_at": "2026-09-25T04:58:04Z",
           "html_url": "https://github.test/job/2"}],
}


def _fake_gh(fleet=FLEET, runs=RUNS, jobs=JOBS, calls=None, job_error=None):
    def run_gh(arguments, _root, **_kwargs):
        path = arguments[1]
        if calls is not None:
            calls.append(path)
        if "/actions/runners" in path:
            return json.dumps({"runners": fleet})
        if "/actions/runs?" in path:
            return json.dumps({"workflow_runs": runs})
        if job_error is not None:
            raise job_error
        run_id = int(re.search(r"/runs/(\d+)/jobs", path).group(1))
        return json.dumps({"jobs": jobs.get(run_id, [])})
    return run_gh


def _by_name(payload):
    return {runner["name"]: runner for runner in payload["runners"]}


@pytest.fixture(autouse=True)
def _fresh_cache():
    runner_status.reset_cache()
    yield
    runner_status.reset_cache()


def test_lane_label_comes_from_labels_not_names():
    lanes = {r["name"]: runner_status.lane_label(r) for r in FLEET}
    assert lanes["illtool-mini-xctest"] == "xctest-pr · mini · heavy"
    assert lanes["illtool-mini-light"] == "light · mini"
    assert lanes["illtool-mini-linux"] == "docker"
    assert lanes["illtool-mac-selfhosted"] == ""
    assert lanes["illtool-mac-light"] == ""
    renamed = {"name": "illtool-heavy", "labels": [_label("light")]}
    assert runner_status.lane_label(renamed) == "light"
    only_defaults = {"labels": [_label("self-hosted"), _label("linux"), _label("ARM64")]}
    assert runner_status.lane_label(only_defaults) == "linux · ARM64"


def test_states_and_alarm():
    states = {r["name"]: runner_status.runner_state(r) for r in FLEET}
    assert states["illtool-mac-light"] == "out-of-pool"
    assert states["illtool-mac-selfhosted"] == "busy"
    assert states["illtool-mini-light"] == "idle"
    stopped = dict(FLEET[5], status="offline", busy=False)
    shaped = runner_status.shape_runner(stopped, None, "2026-09-25T05:00:00+00:00")
    assert shaped["state"] == "offline" and shaped["alarm"] and shaped["inPool"]
    assert not runner_status.shape_runner(FLEET[0], None, None)["alarm"]


def test_busy_runner_names_job_and_pr():
    with mock.patch.object(runner_status, "_run_gh", side_effect=_fake_gh()):
        payload = runner_status._build_payload(Path("."))
    runners = _by_name(payload)
    assert len(runners) == 6
    assert runners["illtool-mbp-uitest"]["job"]["pr"] == 1349
    assert runners["illtool-mac-selfhosted"]["job"]["branch"] == "main"
    assert runners["illtool-mini-light"]["job"] is None


def test_idle_fleet_costs_one_call_and_lookups_are_bounded():
    calls = []
    idle = [dict(r, busy=False) for r in FLEET]
    with mock.patch.object(runner_status, "_run_gh", side_effect=_fake_gh(fleet=idle, calls=calls)):
        runner_status._build_payload(Path("."))
    assert len(calls) == 1 and "/actions/runners" in calls[0]
    calls.clear()
    many = [{"id": 1000 + i, "name": "w", "pull_requests": []} for i in range(40)]
    with mock.patch.object(runner_status, "_run_gh", side_effect=_fake_gh(runs=many, calls=calls)):
        runner_status._build_payload(Path("."))
    assert len([c for c in calls if "/jobs" in c]) <= runner_status._MAX_RUN_LOOKUPS


def test_job_lookup_failure_keeps_runner_list_and_deadline_bounds_it():
    with mock.patch.object(runner_status, "_run_gh",
                           side_effect=_fake_gh(job_error=RuntimeError("HTTP 502"))):
        payload = runner_status._build_payload(Path("."))
    busy = _by_name(payload)["illtool-mbp-uitest"]
    assert payload["available"] and busy["job"] is None and busy["jobError"]
    base = _fake_gh()

    def slow(arguments, root, **kwargs):
        if "/jobs" in arguments[1]:
            time.sleep(0.3)
        return base(arguments, root, **kwargs)

    with mock.patch.object(runner_status, "_run_gh", side_effect=slow), \
            mock.patch.object(runner_status, "_COLLECT_TIMEOUT_SECONDS", 0.1):
        started = time.perf_counter()
        runner_status._build_payload(Path("."))
        assert time.perf_counter() - started < 0.25


def test_last_seen_and_failed_refresh_is_never_last_known_green():
    with mock.patch.object(runner_status, "_run_gh", side_effect=_fake_gh()):
        runner_status._refresh(Path("."), 0.0)
    stopped = copy.deepcopy(FLEET)
    stopped[5].update(status="offline", busy=False)
    with mock.patch.object(runner_status, "_run_gh", side_effect=_fake_gh(fleet=stopped)):
        payload = runner_status._build_payload(Path("."))
    assert _by_name(payload)["illtool-mini-xctest"]["lastSeenOnline"]
    with mock.patch.object(runner_status, "_run_gh", side_effect=RuntimeError("gh: offline")):
        runner_status._refresh(Path("."), runner_status.CACHE_SECONDS + 1)
    with mock.patch.object(runner_status, "_start_refresh"):
        body = runner_status.payload(Path("."), now=lambda: runner_status.CACHE_SECONDS + 2)
    assert not body["available"] and body["runners"] == []
    assert "Runner status unavailable" in body["error"]


def test_a_cold_cache_is_loading_and_a_failed_thread_start_never_sticks(_fresh_cache):
    with mock.patch.object(runner_status, "_start_refresh"):
        body = runner_status.payload(Path("."), now=lambda: 0.0)
    assert body["loading"] and body["available"] is None and body["runners"] == []
    runner_status.reset_cache()
    with mock.patch.object(runner_status.threading.Thread, "start",
                           side_effect=RuntimeError("can't start new thread")):
        body = runner_status.payload(Path("."), now=lambda: 0.0)
    assert not runner_status._CACHE["refreshing"] and not body["refreshing"]
    assert body["available"] is False and "could not start a refresh" in body["error"]


def _served(repo, enabled):
    if enabled:
        config = repo / "vizzer/vizzer.toml"
        config.write_text(config.read_text() + "\n[runners]\nenabled = true\n")
    assert main(["sync", "--root", str(repo)]) == 0
    server = _make_serve_server(repo, _read_graph(repo), repo / "vizzer/views", 0,
                                csrf_token="test-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _get(server, path):
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def _stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_endpoint_serves_fleet_once_per_window_and_degrades(tmp_path, make_repo):
    server, thread = _served(make_repo(tmp_path, "mixed_proj"), enabled=True)
    try:
        calls = []

        def settled():
            deadline = time.monotonic() + 3
            while True:
                status, body = _get(server, "/api/runners")
                assert status == 200
                if not body.get("refreshing"):
                    return body
                assert time.monotonic() < deadline
                time.sleep(0.01)

        with mock.patch.object(runner_status, "_run_gh", side_effect=_fake_gh(calls=calls)):
            body = settled()
            settled()
        assert body["available"] and len(body["runners"]) == 6
        assert sum("/actions/runners" in c for c in calls) == 1
        runner_status.reset_cache()
        with mock.patch.object(runner_status, "_run_gh", side_effect=RuntimeError("gh: not logged in")):
            body = settled()
        assert not body["available"] and "Runner status unavailable" in body["error"]
    finally:
        _stop(server, thread)


def test_endpoint_is_opt_in(tmp_path, make_repo):
    server, thread = _served(make_repo(tmp_path, "mixed_proj"), enabled=False)
    try:
        status, _body = _get(server, "/api/runners")
        assert status == 404
    finally:
        _stop(server, thread)


def test_rendered_views_never_read_runner_state(tmp_path, make_repo):
    repo = make_repo(tmp_path, "mixed_proj")
    assert main(["sync", "--root", str(repo)]) == 0
    cfg = Config.load(repo)
    graph = _read_graph(repo)
    baseline = render_constellation(graph, cfg, repo)["constellation.html"]
    with mock.patch.object(runner_status, "payload", side_effect=AssertionError("no runner reads")), \
            mock.patch.object(runner_status, "_run_gh", side_effect=AssertionError("no gh")):
        rendered = render_all(graph, cfg, repo, {"constellation"})["constellation.html"]
    assert rendered == baseline
    assert '<div id="runners" role="group" aria-label="CI runners" hidden></div>' in rendered
    assert '<div id="runnercard" role="tooltip" hidden></div>' in rendered


_FRONTEND = r"""
const elements=new Map();
const element=id=>{if(!elements.has(id))elements.set(id,{id,hidden:true,innerHTML:'',style:{},
  dataset:{},addEventListener(){}});return elements.get(id);};
globalThis.document={getElementById:element};
globalThis.esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
globalThis.SERVED=false;
const source=require('fs').readFileSync(process.argv[1],'utf8');
require('vm').runInThisContext(source);
const payload=JSON.parse(require('fs').readFileSync(0,'utf8'));
const out={};
applyRunnerStatus(payload);
out.markup=element('runners').innerHTML;out.hidden=element('runners').hidden;
const index=payload.runners.findIndex(r=>r.name==='illtool-mbp-uitest');
showRunnerCard({dataset:{runnerName:'illtool-mbp-uitest'},getBoundingClientRect:()=>({left:40,bottom:30})});
out.cardShown=element('runnercard').hidden===false;
dismissRunnerCardOnEscape({key:'Escape'});
out.escapeHidden=element('runnercard').hidden===true;
element('runnercard').offsetWidth=300;
showRunnerCard({dataset:{runnerName:'illtool-mini-linux'},getBoundingClientRect:()=>({left:1250,bottom:30})});
out.clampedLeft=element('runnercard').style.left;
let writes=0, markupNow=element('runners').innerHTML;
Object.defineProperty(element('runners'),'innerHTML',{get:()=>markupNow,set:value=>{writes+=1;markupNow=value;}});
applyRunnerStatus(JSON.parse(JSON.stringify(payload)));
out.writesWhenUnchanged=writes;out.cardStillOpen=element('runnercard').hidden===false;
const focusedBefore={dataset:{runnerName:'illtool-mini-linux'}};let refocused='';
document.activeElement=focusedBefore;element('runners').contains=e=>e===focusedBefore;
element('runners').querySelectorAll=()=>payload.runners.map(r=>({dataset:{runnerName:r.name},
  focus(){refocused=r.name;},getBoundingClientRect:()=>({left:10,bottom:30})}));
const changed=JSON.parse(JSON.stringify(payload));
changed.runners.find(r=>r.name==='illtool-mini-linux').state='busy';
applyRunnerStatus(changed);
out.writesWhenChanged=writes;out.refocused=refocused;
applyRunnerStatus({schema:1,available:null,loading:true,runners:[]});
out.loading=markupNow;out.loadingRepoll=runnerRepollDelay({loading:true});out.settledRepoll=runnerRepollDelay(payload);
hideRunnerCard();
const now=Date.parse('2026-09-25T05:01:11Z');
out.busyCard=runnerCardMarkup(payload.runners[index],payload,now);
const stopped=Object.assign({},payload.runners.find(r=>r.name==='illtool-mini-xctest'),
  {state:'offline',alarm:true,online:false,lastSeenOnline:'2026-09-25T04:59:11Z'});
out.stoppedText=runnerIndicatorText(stopped);
out.stoppedCard=runnerCardMarkup(stopped,payload,now);
applyRunnerStatus({schema:1,available:false,error:'Runner status unavailable: gh dead'});
out.unavailable=markupNow;
applyRunnerStatus(null);
out.disabledHidden=element('runners').hidden;
process.stdout.write(JSON.stringify(out));
"""


def test_frontend_indicators_and_hover_card():
    node = shutil.which("node")
    assert node is not None, "Node is required for the runner frontend test"
    with mock.patch.object(runner_status, "_run_gh", side_effect=_fake_gh()):
        payload = runner_status._build_payload(Path("."))
    completed = subprocess.run(
        [node, "-e", _FRONTEND, str(RUNNERS_JS)], input=json.dumps(payload),
        text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    out = json.loads(completed.stdout)
    assert not out["hidden"] and out["markup"].count('class="runner ') == 6
    assert "xctest-pr · mini · heavy" in out["markup"]
    assert 'class="runner out-of-pool"' in out["markup"]
    assert out["cardShown"]
    assert "PR #1349" in out["busyCard"] and "running 3m 07s" in out["busyCard"]
    assert out["stoppedText"] == "offline · xctest-pr · mini · heavy", (
        "the alarm word comes first, so a narrow window clips the lane")
    assert out["escapeHidden"] and out["clampedLeft"] == "972px"
    assert out["writesWhenUnchanged"] == 0 and out["cardStillOpen"]
    assert out["writesWhenChanged"] == 1 and out["refocused"] == "illtool-mini-linux"
    assert "runners…" in out["loading"] and "unavailable" not in out["loading"]
    assert out["loadingRepoll"] == 3000 and out["settledRepoll"] is None
    assert "Last seen online 2m 00s ago" in out["stoppedCard"]
    assert "runners unavailable" in out["unavailable"]
    assert out["disabledHidden"]
