"""Generic regressions for nested story navigation and project-scoped restart."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import plistlib
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from vizzer import cli
from vizzer.cli import _restart_project_service
from vizzer.config import Config, DEFAULTS
from vizzer.model import (
    Graph, Group, Item, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation,
)
from vizzer.render import render_all
from vizzer.startup import service_label_for_root
from vizzer.render.constellation import engine_badge_text, project_identity


def _payload(html: str) -> dict:
    match = re.search(r"const DATA=(\{.*?\});\n", html, re.S)
    assert match is not None
    return json.loads(match.group(1))


def test_nested_platform_capability_epic_and_legacy_capability_share_generic_contract(tmp_path):
    graph = Graph(
        vocab=Config(data=DEFAULTS).vocab,
        groups=[
            Group(id="platform:desktop", kind="platform", title="Desktop / macOS"),
            Group(id="capability:desktop/painting", kind="capability",
                  title="Color: & Mixing", parent="platform:desktop"),
            Group(id="epic:desktop/painting/palette", kind="epic",
                  title="Palette (custom)", parent="capability:desktop/painting"),
            Group(id="capability:legacy", kind="capability", title="Legacy root"),
        ],
        items=[
            Item(id="story:deep-unique", title="Deep story: [A&B]", status="building",
                 group="epic:desktop/painting/palette"),
            Item(id="story:legacy-unique", title="Legacy story", status="ready",
                 group="capability:legacy"),
            Item(id="reference:ungrouped-note", title="Ungrouped reference",
                 status="unknown", role="reference"),
        ],
    )
    html = render_all(graph, Config(data=DEFAULTS), tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _payload(html)
    groups = {group["id"]: group for group in data["groups"]}
    nodes = {node["id"]: node for node in data["nodes"]}

    assert data["projectId"] == project_identity(graph, Config(data=DEFAULTS))
    assert groups["platform:desktop"]["parent"] == ""
    assert groups["capability:desktop/painting"]["parent"] == "platform:desktop"
    assert groups["epic:desktop/painting/palette"]["parent"] == "capability:desktop/painting"
    assert nodes["story:deep-unique"]["group"] == "epic:desktop/painting/palette"
    assert nodes["story:legacy-unique"]["group"] == "capability:legacy"
    assert nodes["reference:ungrouped-note"]["group"] in (None, "")
    assert "Platforms" in html
    assert "railgroupbody" in html and "railstory" in html
    # Authored mixed case, punctuation and unsafe characters remain data; the
    # UI must render them as text rather than deriving display labels from IDs.
    assert nodes["story:deep-unique"]["t"] == "Deep story: [A&B]"
    assert "grid-template-columns:minmax(0,1fr)" in html
    assert ".railgroupbody{display:grid;gap:1px;padding:1px 0 3px 5px}" in html
    assert ".capcount{min-width:0" in html and "overflow-wrap:anywhere" in html
    assert "vizzer.rail.expanded." in html and "sessionStorage.setItem" in html
    assert "catch(_){}" in html
    second_path = tmp_path / "different-render-root"
    second_path.mkdir()
    second_html = render_all(graph, Config(data=DEFAULTS), second_path,
                             only={"constellation"})["constellation.html"]
    assert _payload(second_html)["projectId"] == data["projectId"]
    assert _payload(second_html) == data
    assert second_html == html


def test_recursive_rail_executes_nested_story_leaf_and_opens_matching_dossier(tmp_path):
    module_spec = importlib.util.spec_from_file_location(
        "existing_constellation_test_support", Path(__file__).with_name("test_render_constellation.py")
    )
    assert module_spec and module_spec.loader
    support = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(support)
    graph = Graph(
        vocab=Config(data=DEFAULTS).vocab,
        groups=[
        Group(id="platform:desktop", kind="platform", title="Desktop"),
        Group(id="capability:desktop/canvas", kind="capability", title="Canvas",
              parent="platform:desktop"),
        Group(id="epic:desktop/canvas/layers", kind="epic", title="Layer editing",
              parent="capability:desktop/canvas"),
        ],
        items=[
            Item(id="story:a", title="A", status="shipped", release="R0",
                 group="epic:desktop/canvas/layers"),
            Item(id="story:b", title="B", status="specced", release="R1",
                 group="epic:desktop/canvas/layers"),
        ],
        owner_questions=[OwnerQuestion(
        id="question:layers", story_id="story:b", owner="Fixture",
        prompt="Which layer behavior?", options=[
            OwnerQuestionOption(id="keep", label="Keep", tradeoff="Known behavior"),
            OwnerQuestionOption(id="change", label="Change", tradeoff="New behavior"),
        ], recommendation=OwnerQuestionRecommendation(
            option_id="keep", rationale="Preserve the current contract",
        ), falsifier="The canvas contract changes", evidence=["stories/layers.md"],
        )],
    )
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    shim = support._CONSTELLATION_COUNT_DOM_SHIM.replace(
        "process.stdout.write(JSON.stringify(out));",
        r'''
const nested=desc(ids.get('rail')).filter(e=>e.classList.contains('railgroup'));
const leaf=desc(ids.get('rail')).find(e=>e.getAttribute('data-story-id')==='story:b');
if(leaf)leaf.click();
process.stdout.write(JSON.stringify({nestedGroups:nested.length,leafTitle:leaf?.textContent||null,
      selected:ev(`sel>=0?DATA.nodes[sel].id:null`),dossierOpen:ids.get('dossier').classList.contains('open'),
      ariaLabel:leaf?.getAttribute('aria-label')||null}));
''',
    )
    shim = shim.replace(
        "this.listeners={};this.attributes={};",
        "this.listeners={};this.dataset={};this.attributes={};",
    )
    shim = shim.replace(
        "'hint','bgcv','cv'])",
        "'hint','bgcv','cv','cluster-background','background-panel','background-open',"
        "'background-file','background-opacity','background-remove','background-status',"
        "'background-value','background-close'])",
    ).replace(
        "const sandbox={console,document,location:",
        "class MutationObserver{observe(){}};class Image{};"
        "const indexedDB={open(){return {result:{createObjectStore(){}}}}};"
        "const sandbox={indexedDB,MutationObserver,Image,console,document,location:",
    )
    node = shutil.which("node")
    assert node is not None, "Node is required for recursive rail interaction regression"
    completed = subprocess.run([node, "-e", shim], input=html, text=True,
                               capture_output=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    state = json.loads(completed.stdout)
    assert state["nestedGroups"] == 2 and state["leafTitle"] == "B" and state["selected"] == "story:b" \
        and state["dossierOpen"] and state["ariaLabel"] == "Open story: B", state


@pytest.mark.parametrize("version", ["unknown", "v0.0.0-unknown", "0.8.0.unknown", ""])
def test_unknown_engine_badge_uses_render_identity(version):
    assert engine_badge_text(version, "abcdef0123456789") == "render abcdef012345"


def test_known_engine_badge_keeps_release_version_and_missing_identity_is_explicit():
    assert engine_badge_text(" 0.8.42 ", "abcdef0123456789") == "0.8.42"
    assert engine_badge_text("unknown", None) == "render identity unavailable"


def test_rail_disclosure_persistence_is_project_scoped_and_storage_failures_are_safe(tmp_path):
    graph = Graph(vocab=Config(data=DEFAULTS).vocab)
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    scripts = re.findall(r"<script>([\s\S]*?)</script>", html)
    script = next((candidate for candidate in scripts if "railDisclosureKey" in candidate), "")
    source = re.search(r"const railStorageScope=[\s\S]*?(?=const capTail=)", script)
    assert source
    node = shutil.which("node")
    assert node is not None, "Node is required for disclosure persistence regression"
    harness = r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const stored=new Map();
    function context(projectId,storage,configured=true){
          const sandbox={DATA:{projectId,projectIdConfigured:configured},location:{pathname:'/project/'+projectId},sessionStorage:storage,Object,JSON,String,Boolean,encodeURIComponent};
  sandbox.globalThis=sandbox;const cx=vm.createContext(sandbox);
  vm.runInContext(input.source,cx);
  return {cx,key:vm.runInContext('railDisclosureKey',cx)};
}
const storage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)};
const first=context('project-one',storage);
vm.runInContext("saveRailDisclosure('group:tools',true)",first.cx);
const second=context('project-two',storage);
const same=context('project-one',storage);
const denied=context('project-three',{getItem(){throw new Error('denied')},setItem(){throw new Error('denied')}});
    const fallback=context('fallback',storage,false);
    vm.runInContext("saveRailDisclosure('group:tools',true)",fallback.cx);
process.stdout.write(JSON.stringify({
  keysDistinct:first.key!==second.key,
  first:vm.runInContext("railDisclosureOpen('group:tools',false)",first.cx),
  second:vm.runInContext("railDisclosureOpen('group:tools',false)",second.cx),
  same:vm.runInContext("railDisclosureOpen('group:tools',false)",same.cx),
  denied:vm.runInContext("railDisclosureOpen('group:tools',false)",denied.cx),
      deniedWrite:vm.runInContext("saveRailDisclosure('group:tools',true);railDisclosureOpen('group:tools',false)",denied.cx),
      fallbackNotStored:!stored.has(fallback.key)
}));
'''
    completed = subprocess.run(
        [node, "-e", harness], input=json.dumps({"source": source.group(0)}),
        text=True, capture_output=True, timeout=5,
    )
    assert completed.returncode == 0, completed.stderr
    state = json.loads(completed.stdout)
    assert state == {"keysDistinct": True, "first": True, "second": False,
                     "same": True, "denied": False, "deniedWrite": True,
                     "fallbackNotStored": True}


def test_project_roots_get_distinct_stable_service_labels_and_restart_only_selected_root(
    tmp_path, monkeypatch
):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    expected = "com.vizzer.project." + hashlib.sha256(
        str(first.resolve()).encode()
    ).hexdigest()[:12] + ".server"
    assert service_label_for_root(first) == expected
    assert service_label_for_root(first / "nested" / "..") == expected
    assert service_label_for_root(second) != expected

    home = tmp_path / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    calls = []
    monkeypatch.setattr("vizzer.cli.os.getuid", lambda: 501)
    monkeypatch.setattr("vizzer.cli.subprocess.run", lambda args, **kwargs: calls.append(args))

    def install(root: Path, label: str, port: int) -> None:
        engine = str(root.resolve() / "vizzer" / "engine")
        config = {
            "Label": label,
            "WorkingDirectory": str(root.resolve()),
            "ProgramArguments": [sys.executable, "-u", engine, "serve", "--root",
                                 str(root.resolve()), "--port", str(port)],
        }
        (agents / f"{label}.plist").write_bytes(plistlib.dumps(config))

    first_label = service_label_for_root(first)
    second_label = service_label_for_root(second)
    install(first, first_label, 6201)
    install(second, second_label, 6202)

    assert _restart_project_service(second) == second_label
    assert calls == [["launchctl", "kickstart", "-k", f"gui/501/{second_label}"]]


@pytest.mark.parametrize("mutation", ["label", "working-directory", "engine", "port"])
def test_restart_refuses_a_service_not_matching_the_requested_project(
    tmp_path, monkeypatch, mutation
):
    root = tmp_path / "project"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    home = tmp_path / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    calls = []
    monkeypatch.setattr("vizzer.cli.subprocess.run", lambda args, **kwargs: calls.append(args))
    label = service_label_for_root(root)
    config = {
        "Label": label,
        "WorkingDirectory": str(root.resolve()),
        "ProgramArguments": [sys.executable, "-u", str(root / "vizzer/engine"),
                             "serve", "--root", str(root.resolve()), "--port", "6201"],
    }
    if mutation == "label":
        config["Label"] = "com.vizzer.project.someone-else.server"
    elif mutation == "working-directory":
        config["WorkingDirectory"] = str(other.resolve())
    elif mutation == "engine":
        config["ProgramArguments"][2] = str(other / "vizzer/engine")
    elif mutation == "port":
        config["ProgramArguments"][7] = "70000"
    (agents / f"{label}.plist").write_bytes(plistlib.dumps(config))

    with pytest.raises(ValueError):
        _restart_project_service(root)
    assert calls == []


def test_restart_without_installed_service_is_actionable_and_does_not_dispatch(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    calls = []
    monkeypatch.setattr("vizzer.cli.subprocess.run", lambda args, **kwargs: calls.append(args))

    with pytest.raises(ValueError, match="Run `python3 -m vizzer.startup"):
        _restart_project_service(root)
    assert calls == []


@pytest.mark.parametrize("headers", [
    {"Origin": "http://evil.example", "X-Vizzer-CSRF": "secret"},
    {"Origin": "http://127.0.0.1:{port}"},
])
def test_restart_endpoint_rejects_foreign_origin_or_missing_csrf(tmp_path, monkeypatch, headers):
    root = tmp_path / "project"
    root.mkdir()
    server = cli._make_serve_server(root, Graph(), tmp_path, 0,
                                    cfg=Config(data=DEFAULTS), csrf_token="secret")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    calls = []
    monkeypatch.setattr(cli, "_restart_project_service", lambda selected: calls.append(selected))
    port = server.server_port
    request_headers = {
        key: value.format(port=port) for key, value in headers.items()
    }
    request_headers["Host"] = f"127.0.0.1:{port}"
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/server/restart", data=b"{}",
        headers=request_headers, method="POST",
    )
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=3)
        assert error.value.code == 403
        assert calls == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_restart_endpoint_allows_same_origin_and_stale_engine_recovery(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    server = cli._make_serve_server(root, Graph(), tmp_path, 0,
                                    cfg=Config(data=DEFAULTS), csrf_token="secret")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    calls = []
    restarted = threading.Event()
    monkeypatch.setattr(cli, "_project_service_restart_target",
                        lambda selected: ("test.service", "gui/501", ["launchctl", "kickstart"]))
    def dispatch(selected):
        calls.append(selected)
        restarted.set()
        return "test.service"
    monkeypatch.setattr(cli, "_restart_project_service", dispatch)
    # Restart is the recovery path when the served render is stale; it must not
    # require the current-engine guard used by ordinary mutation endpoints.
    monkeypatch.setattr(cli, "_serve_version_error", lambda selected: "stale engine")
    port = server.server_port
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/server/restart", data=b"{}",
        headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}",
                 "X-Vizzer-CSRF": "secret"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            body = json.loads(response.read())
        assert response.status == 202
        assert body == {"accepted": True, "service": "test.service"}
        assert restarted.wait(timeout=3)
        assert calls == [root]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
