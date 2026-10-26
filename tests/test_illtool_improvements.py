"""Improvements first made in illtool's vendored engine: serve backlog, strict
declared-blocker headings, and selecting a story revealing it in the rail."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vizzer import cli
from vizzer.config import Config, DEFAULTS
from vizzer.model import (
    Graph, Group, Item, OwnerQuestion, OwnerQuestionOption, OwnerQuestionRecommendation,
)
from vizzer.render import render_all
from vizzer.story_sidebar import extract_story_sidebar_sections


def test_serve_server_listen_backlog_absorbs_a_page_load_burst():
    # The constellation page opens about a dozen API connections at once; the
    # socketserver default backlog of 5 made the kernel reset the overflow.
    assert cli._ServeHTTPServer.request_queue_size == 128
    assert issubclass(cli._ServeHTTPServer, cli.http.server.ThreadingHTTPServer)


@pytest.mark.parametrize("heading", [
    "Dependencies / frozen contracts",
    "Dependency notes",
    "Scenarios (user-action granularity)",
    "Scenarios (undo action granularity)",
    "Action items for review",
    "What happens next",
])
def test_lookalike_headings_are_not_blockers_or_next_action(heading):
    sections = extract_story_sidebar_sections(f"# Story\n\n## {heading}\n- Something.\n")
    assert sections["blockers"] is None and sections["next_action"] is None, sections


@pytest.mark.parametrize("heading,key", [
    ("Blockers", "blockers"),
    ("Declared blockers", "blockers"),
    ("Blocked by", "blockers"),
    ("Next action", "next_action"),
    ("Next steps", "next_action"),
])
def test_declared_blocker_and_next_action_headings_still_match(heading, key):
    sections = extract_story_sidebar_sections(f"# Story\n\n## {heading}\n- Wait on the export review.\n")
    assert sections[key] == "- Wait on the export review.", sections


def _support():
    spec = importlib.util.spec_from_file_location(
        "existing_constellation_test_support", Path(__file__).with_name("test_render_constellation.py")
    )
    assert spec and spec.loader
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    return support


def _run_rail_script(tmp_path, script: str) -> dict:
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
        # The DOM shim's prelude opens the first owner question.
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
    shim = _support()._CONSTELLATION_COUNT_DOM_SHIM.replace(
        "process.stdout.write(JSON.stringify(out));", script,
    ).replace(
        "this.listeners={};this.attributes={};",
        "this.listeners={};this.dataset={};this.attributes={};",
    ).replace(
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
    assert node is not None, "Node is required for the rail reveal regression"
    completed = subprocess.run([node, "-e", shim], input=html, text=True,
                               capture_output=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_selecting_a_story_reveals_and_marks_its_rail_leaf_and_dismiss_clears_it(tmp_path):
    state = _run_rail_script(tmp_path, r'''
const rail=ids.get('rail');
const leaf=desc(rail).find(e=>e.getAttribute('data-story-id')==='story:b');
const epic=desc(rail).find(e=>e.classList.contains('railgroup')&&desc(e).includes(leaf));
const scrolled=[];
if(leaf)leaf.scrollIntoView=()=>scrolled.push('leaf');
if(epic)epic.open=false;
ev(`openNode(nodeById.get('story:b'))`);
const opened={epicOpen:!!epic?.open,leafContext:leaf?.classList.contains('context'),
  leafCurrent:leaf?.getAttribute('aria-current')||null,scrolled:scrolled.slice(),
  crumbs:desc(ids.get('dossier')).filter(e=>e.classList.contains('crumb')).map(e=>e.textContent)};
ev(`dismissDossier({focusCanvas:false})`);
process.stdout.write(JSON.stringify({...opened,leafFound:!!leaf,epicFound:!!epic,
  clearedContext:!leaf?.classList.contains('context'),clearedCurrent:leaf?.getAttribute('aria-current')??null}));
''')
    assert state["leafFound"] and state["epicFound"], state
    assert state["epicOpen"] and state["leafContext"] and state["leafCurrent"] == "true", state
    assert state["scrolled"] == ["leaf"], state
    assert state["clearedContext"] and state["clearedCurrent"] is None, state


def test_story_dossier_shows_its_location_crumbs(tmp_path):
    state = _run_rail_script(tmp_path, r'''
ev(`openNode(nodeById.get('story:b'))`);
const nav=desc(ids.get('dossier')).find(e=>e.classList.contains('dossiercrumbs'));
process.stdout.write(JSON.stringify({html:ev(`dossierLocationMarkup(DATA.nodes[nodeById.get('story:b')])`),
  rendered:!!nav}));
''')
    assert 'data-crumb-group="epic:desktop/canvas/layers"' in state["html"], state
    assert "1/2 shipped in this" in state["html"], state
