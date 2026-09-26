"""Previous | "N of M" | Next across open owner questions, pinned at the top.

Owner directive 2026-09-26 (illtool-standalone): "when i start answering
questions, and there are more than one. at the top of the panel i should just
have a segmented control at the top to jump between next and prev, so i can get
to the next one without closing the panel."

Story: product-spec/stories/owner-question-prev-next-navigation.md

The rendered constellation runs in a DOM-less Node harness twice: once as the
served page (http:) and once as the read-only file:// build. The dossier's
three regions are event-capable stand-ins keyed to their rendered markup, so
the tests click the rendered Previous/Next and Provide-answer controls and
dispatch arrow keys through the control and then the window.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from vizzer.config import Config, DEFAULTS
from vizzer.model import (
    Graph, Group, Item, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation,
)
from vizzer.render import render_all

_RUNNER = r"""
const fs = require('fs');
const vm = require('vm');
class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach(value => this.values.add(value)); }
  remove(...values) { values.forEach(value => this.values.delete(value)); }
  contains(value) { return this.values.has(value); }
  toggle(value, force) {
    const enabled = force === undefined ? !this.values.has(value) : Boolean(force);
    if (enabled) this.values.add(value); else this.values.delete(value);
    return enabled;
  }
}
const noop = () => {};
const canvasContext = new Proxy({}, {
  get(_target, property) {
    if (property === 'measureText') return () => ({width: 0});
    if (property === 'createLinearGradient' || property === 'createRadialGradient') return () => ({addColorStop: noop});
    return noop;
  },
  set() { return true; },
});
const elements = new Map();
function element(id = '') {
  return {
    id, hidden: false, className: '', style: {setProperty: noop}, dataset: {},
    classList: new ClassList(), open: false, disabled: false, width: 0, height: 0,
    textContent: '', innerHTML: '', value: '', children: [],
    addEventListener: noop, appendChild: noop, append: noop, prepend: noop, remove: noop,
    replaceChildren: noop, contains: () => true,
    cloneNode: () => element(),
    focus: noop, setPointerCapture: noop, releasePointerCapture: noop,
    hasPointerCapture: () => false, getContext: () => canvasContext,
    getBoundingClientRect: () => ({left: 0, top: 0, right: 1280, bottom: 720, width: 1280, height: 720}),
    setAttribute: noop, getAttribute: () => null, removeAttribute: noop, querySelector: () => element(),
    querySelectorAll: () => [],
  };
}
const document = {
  title: 'fixture', documentElement: element('html'), body: element('body'),
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, element(id));
    return elements.get(id);
  },
  createElement: () => element(), createElementNS: () => element(),
  querySelector: () => element(), querySelectorAll: () => [],
};
const listeners = {};
const context = {
  __listeners: listeners, console, document, innerWidth: 1280, innerHeight: 720, devicePixelRatio: 1,
  location: {hash: '', search: ''}, visualViewport: null, performance: {now: () => 0},
  addEventListener: (type, handler) => {
    (listeners[type] || (listeners[type] = [])).push(handler);
  }, requestAnimationFrame: noop,
  getComputedStyle: () => ({getPropertyValue: () => 'rgb(1, 2, 3)', lineHeight: '20px'}),
  matchMedia: () => ({matches: false, addEventListener: noop}), MutationObserver: class { observe() {} },
  ResizeObserver: class { observe() {} disconnect() {} },
  sessionStorage: {getItem: () => null, setItem: noop},
  localStorage: {getItem: () => null, setItem: noop},
  setTimeout: () => 0, clearTimeout: noop, setInterval: () => 0, clearInterval: noop,
};
context.window = context;
(async () => { try {
  vm.runInNewContext(fs.readFileSync(0, 'utf8'), context, {filename: 'constellation-inline.js'});
  await context.__testDone;
  const boot = document.getElementById('boot');
  const result = context.__testResult || {bootHidden: boot.hidden, bootClass: boot.className};
  process.stdout.write(JSON.stringify(result));
  process.exit(boot.className !== 'error' ? 0 : 2);
} catch (error) {
  process.stdout.write(`${error.name}: ${error.message}`);
  process.exit(1);
}
})();
"""
_SERVED_RUNNER = _RUNNER.replace(
    "location: {hash: '', search: ''}",
    "location: {hash: '', search: '', protocol: 'http:', pathname: '/', origin: 'http://127.0.0.1'}, "
    "fetch: () => new Promise(() => {})",
)

DRIVER = r"""
;globalThis.__testDone=(async function(){
  // ---- an event-capable stand-in for the three dossier regions ----
  // Each region's innerHTML is the rendered truth; every write is a new
  // generation, and elements are looked up (and their listeners recorded) per
  // generation, exactly as a real innerHTML rebuild replaces the elements.
  let focused='';
  const fake=(name,html)=>{
    const el={name,listeners:{},dataset:{},hidden:false,disabled:false,checked:false,textContent:'',value:'',
      classList:{add(){},remove(){},toggle(){},contains(){return false;}},style:{},
      addEventListener(type,handler){(el.listeners[type]||(el.listeners[type]=[])).push(handler);},
      setAttribute(){},removeAttribute(){},focus(){focused=name;},scrollIntoView(){el.scrolled=true;},
      replaceWith(){},prepend(){},appendChild(){},remove(){},
      querySelector(selector){return child(selector);},querySelectorAll(){return [];}};
    // A selector finds something only when the element's own markup has it,
    // so a renamed or missing control reads as null, never as a free stand-in.
    const kids=new Map();
    const present=selector=>{
      const attribute=selector.match(/^\[([\w-]+)/);if(attribute)return html.includes(attribute[1]);
      const className=selector.match(/^\.([\w-]+)$/);if(className)return new RegExp(`class="[^"]*\\b${className[1]}\\b`).test(html);
      return new RegExp(`<${selector}[\\s>]`).test(html);
    };
    const child=selector=>{
      if(!present(selector))return null;
      if(!kids.has(selector)){
        const kid=fake(name+' '+selector,html);
        const attribute=selector.match(/^\[([\w-]+)\]$/);
        if(attribute)kid.disabled=new RegExp(`${attribute[1]}[^>]*disabled`).test(html);
        kids.set(selector,kid);
      }
      return kids.get(selector);
    };
    return el;
  };
  const regions={};
  for(const id of ['dossieridentity','dbody','dossierfooter']){
    const host=document.getElementById(id), original={qs:host.querySelector,qsa:host.querySelectorAll};
    let html='',generation=0;const cache=new Map();
    Object.defineProperty(host,'innerHTML',{get:()=>html,set:value=>{html=String(value);generation++;cache.clear();}});
    const memo=(key,make)=>{if(!cache.has(key))cache.set(key,make());return cache.get(key);};
    host.querySelector=selector=>{
      if(id==='dossieridentity'&&selector==='[data-question-nav]')
        return html.includes('data-question-nav')?memo('nav',()=>fake(`nav#${generation}`,html)):null;
      if(id==='dossierfooter'&&['[data-question-queue]','[data-story-actions]'].includes(selector))
        return html.includes(selector.slice(1,-1))?memo(selector,()=>fake(`${selector}#${generation}`,html)):null;
      return original.qs.call(host,selector);
    };
    host.querySelectorAll=selector=>{
      if(id==='dbody'&&selector==='form[data-question-id]')return memo('forms',()=>[...html.matchAll(/<form class="questioncard" data-question-id="([^"]+)"[\s\S]*?<\/form>/g)]
        .map(match=>{const form=fake(`form ${match[1]}#${generation}`,match[0]);form.dataset.questionId=match[1];return form;}));
      if(id==='dbody'&&selector==='[data-owner-question-stepper]')return memo('steppers',()=>[...html.matchAll(/<section class="ownerquestionstepper"[^>]*data-packet-id="([^"]+)" data-owner-question-index="(\d+)"[\s\S]*?<\/section>/g)]
        .map(match=>{const host=fake(`stepper ${match[1]}#${generation}`,match[0]);host.dataset.packetId=match[1];host.dataset.ownerQuestionIndex=match[2];return host;}));
      return original.qsa.call(host,selector);
    };
    regions[id]={host,generation:()=>generation};
  }
  const identity=()=>regions.dossieridentity.host.innerHTML;
  const body=()=>regions.dbody.host.innerHTML;
  const nav=()=>regions.dossieridentity.host.querySelector('[data-question-nav]');
  const click=el=>{if(!el||el.disabled)return [];return (el.listeners.click||[]).map(handler=>handler({}));};
  const clickNav=which=>click(nav()?.querySelector(`[data-question-nav-${which}]`));
  const key=name=>{
    const target=nav();
    const event={key:name,target,defaultPrevented:false,isComposing:false,altKey:false,ctrlKey:false,metaKey:false,shiftKey:false,
      preventDefault(){this.defaultPrevented=true;}};
    for(const handler of target?.listeners.keydown||[])handler(event);
    for(const handler of __listeners.keydown||[])handler(event); // the window, after bubbling
    return event;
  };
  let workLaneSteps=0;
  navigateWorkLane=()=>{workLaneSteps++;return true;};

  // ---- fixture: the graph carries four open questions on stories a, b, c ----
  const byId=id=>DATA.nodes.findIndex(node=>node.id===id);
  const [a,b,c]=['story:a','story:b','story:c'].map(byId);
  const stories=[a,b,c];
  const qIndex=id=>DATA.questions.findIndex(q=>q.id===id);
  const fixture=['question:nav-a1','question:nav-a2','question:nav-b1','question:nav-c1'].map(id=>DATA.questions[qIndex(id)]);
  DATA.decisions=DATA.decisions||[];
  const pin=sets=>{
    DATA.nodes.forEach(n=>{n.oq=[];});
    for(const [story,indexes] of sets)DATA.nodes[story].oq=indexes.map(k=>qIndex(fixture[k].id));
  };
  const allOpen=()=>pin([[a,[0,1]],[b,[2]],[c,[3]]]);
  const position=()=>{const m=identity().match(/data-question-nav-position>(\d+) of (\d+)</);return m?`${m[1]} of ${m[2]}`:null;};
  const hasNav=()=>identity().includes('data-question-nav');
  const reset=()=>{if(sel>=0)dismissDossier({focusCanvas:false});questionNavFocusId='';questionDrafts.clear();};
  const out={served:SERVED,stories};
  allOpen();

  // Scenario 1: pinned at the top.
  openNode(a);
  const markup=identity();
  out.top={hasNav:hasNav(),navBeforeTitle:markup.indexOf('data-question-nav')>=0&&markup.indexOf('data-question-nav')<markup.indexOf('<h2>'),
    position:position(),segments:(markup.match(/<button type="button" data-question-nav-(previous|next)/g)||[]).length};

  if(!SERVED){ // the file:// build: no control, nothing to step
    out.single={state:questionNavigatorState(a)};
    globalThis.__testResult=out;return;
  }

  // Scenario 2: click Next three times, then Previous, across stories.
  const walk=[];
  const record=()=>walk.push({sel,position:position(),open:document.getElementById('dossier').classList.contains('open')});
  clickNav('next');record();clickNav('next');record();clickNav('next');record();clickNav('previous');record();
  out.walk=walk;

  // Scenario 3: a chosen option survives a step away and back.
  reset();openNode(a);
  questionDrafts.set('question:nav-a1',{kind:'option',optionId:'opt-b',text:''});
  clickNav('next');clickNav('next'); // a2, then story b
  const awaySel=sel;
  clickNav('previous');clickNav('previous'); // back to a2, then a1
  out.drafts={awayOnOtherStory:awaySel===b,backSel:sel,position:position(),
    optionId:questionDrafts.get('question:nav-a1')?.optionId||'',
    cardChecked:/value="opt-b" data-question-option checked/.test(body().split('data-question-id="question:nav-a1"')[1]||'')};

  // Scenario 4: the ends do not wrap.
  reset();openNode(a);
  const first={position:position(),previousDisabled:nav().querySelector('[data-question-nav-previous]').disabled,
    nextDisabled:nav().querySelector('[data-question-nav-next]').disabled,moved:navigateOwnerQuestion(-1),sel};
  openNode(c);
  const last={position:position(),nextDisabled:nav().querySelector('[data-question-nav-next]').disabled,
    previousDisabled:nav().querySelector('[data-question-nav-previous]').disabled,moved:navigateOwnerQuestion(1),sel};
  out.ends={first,last};

  // Scenario 5a: exactly one open question shows no control.
  reset();pin([[c,[3]]]);
  openNode(c);
  out.single={hasNav:hasNav(),state:questionNavigatorState(c)};
  allOpen();

  // Scenario 5b: the footer's Provide answer button records the answer, the
  // count drops, and the panel moves on.
  reset();
  let revision=1;const open=new Set(fixture.map(q=>q.id));
  const decision=q=>({question:{id:q.id,fingerprint:q.fingerprint},fingerprint:q.fingerprint,revision:revision+1,
    answeredAt:'2026-09-26T13:00:00-07:00',answeredBy:'owner',kind:'option',optionId:'opt-a',text:''});
  const json=body=>({ok:true,status:200,json:async()=>body});
  fetch=async(url,init={})=>{
    if(url==='/api/questions')return json({renderId:RENDER_ID,csrfToken:'t',revision,decisions:[],
      questions:fixture.filter(q=>open.has(q.id)).map(q=>({id:q.id,fingerprint:q.fingerprint,storyId:DATA.nodes[q.n].id}))});
    if(url==='/api/questions/answers'){
      const posted=JSON.parse(init.body).answers.map(answer=>fixture.find(q=>q.id===answer.questionId));
      const decisions=posted.map(decision);revision++;posted.forEach(q=>open.delete(q.id));
      return json({decisions,revision});
    }
    return new Promise(()=>{});
  };
  questionContext={renderId:RENDER_ID,csrfToken:'t',revision,decisions:[],questions:[]};
  const provide=async story=>{
    for(const q of ownerQuestions(story))questionDrafts.set(q.id,{kind:'option',optionId:'opt-a',text:''});
    openNode(story);
    const submit=regions.dossierfooter.host.querySelector('[data-question-queue]')?.querySelector('[data-question-submit]');
    const disabled=Boolean(submit?.disabled);
    await Promise.all(click(submit));
    return disabled;
  };
  questionNavFocusId='';
  const before=(openNode(b),position());
  const middleDisabled=await provide(b);
  const afterMiddle={sel,position:position()};
  const lastDisabled=await provide(c);
  out.answered={before,middleDisabled,lastDisabled,afterMiddle,afterLast:{sel,position:position()}};
  fetch=()=>new Promise(()=>{});
  allOpen();

  // Scenario 6: keyboard and accessible names.
  reset();openNode(a);
  const labels=identity();
  const keyboard={
    previousName:/<button type="button" data-question-nav-previous aria-label="Previous owner question"/.test(labels),
    nextName:/<button type="button" data-question-nav-next aria-label="Next owner question"/.test(labels),
    groupName:/aria-label="Owner questions"/.test(labels),
    positionAnnounced:/aria-live="polite" data-question-nav-position/.test(labels),
  };
  // Right: 1 -> 2 of 4, focus stays on Next. Left: back to 1 of 4, where
  // Previous is disabled, so focus lands on Next.
  const right=key('ArrowRight');
  keyboard.right={prevented:right.defaultPrevented,position:position(),focus:focused.replace(/^nav#\d+ /,'')};
  const left=key('ArrowLeft');
  keyboard.left={prevented:left.defaultPrevented,position:position(),focus:focused.replace(/^nav#\d+ /,'')};
  keyboard.other=key('ArrowUp').defaultPrevented;keyboard.sel=sel;
  keyboard.workLaneSteps=workLaneSteps;
  out.keyboard=keyboard;

  globalThis.__testResult=out;
})();
"""


def _question(qid, story):
    return OwnerQuestion(
        id=qid, story_id=story, owner="Ryder", prompt=f"Pick {qid}?",
        options=[OwnerQuestionOption("opt-a", "Option A", ""),
                 OwnerQuestionOption("opt-b", "Option B", "")],
        recommendation=OwnerQuestionRecommendation("opt-a", ""),
        falsifier="", evidence=[],
    )


def _graph():
    graph = Graph(
        groups=[Group(id="capability:c", kind="capability", title="Cap")],
        vocab=Config(data=DEFAULTS).vocab,
        items=[Item(id=f"story:{slug}", title=slug.upper(), status="specced", release="R0",
                    group="capability:c", source={"adapter": "spec_tree", "path": f"s/{slug}.md"})
               for slug in ("a", "b", "c")],
    )
    graph.owner_questions = [
        _question("question:nav-a1", "story:a"), _question("question:nav-a2", "story:a"),
        _question("question:nav-b1", "story:b"), _question("question:nav-c1", "story:c"),
    ]
    return graph


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    node = shutil.which("node")
    assert node is not None, "Node is required to execute constellation JavaScript tests"
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path_factory.mktemp("render"),
                      only={"constellation"})["constellation.html"]
    source = "\n".join(re.findall(r"<script>\s*(.*?)</script>", html, flags=re.DOTALL)) + DRIVER

    def run(runner):
        proc = subprocess.run([node, "-e", runner], input=source, text=True,
                              capture_output=True, timeout=60)
        return {"code": proc.returncode, "stdout": proc.stdout + proc.stderr,
                "result": json.loads(proc.stdout) if proc.returncode == 0 else None}
    return {"served": run(_SERVED_RUNNER), "static": run(_RUNNER)}


def _served(runs):
    served = runs["served"]
    assert served["code"] == 0, served["stdout"]
    assert served["result"]["served"] is True
    return served["result"]


def test_segmented_control_is_pinned_at_the_top_with_position_and_count(runs):
    top = _served(runs)["top"]
    assert top == {"hasNav": True, "navBeforeTitle": True, "position": "1 of 4", "segments": 2}


def test_next_and_previous_walk_open_questions_across_stories_in_list_order(runs):
    result = _served(runs)
    a, b, c = result["stories"]
    assert [(s["sel"], s["position"], s["open"]) for s in result["walk"]] == [
        (a, "2 of 4", True), (b, "3 of 4", True), (c, "4 of 4", True), (b, "3 of 4", True)]


def test_draft_answers_survive_navigating_away_and_back(runs):
    result = _served(runs)
    assert result["drafts"] == {"awayOnOtherStory": True, "backSel": result["stories"][0],
                                "position": "1 of 4", "optionId": "opt-b", "cardChecked": True}


def test_ends_disable_previous_and_next_without_wraparound(runs):
    result = _served(runs)
    a, _, c = result["stories"]
    assert result["ends"] == {
        "first": {"position": "1 of 4", "previousDisabled": True, "nextDisabled": False,
                  "moved": False, "sel": a},
        "last": {"position": "4 of 4", "nextDisabled": True, "previousDisabled": False,
                 "moved": False, "sel": c},
    }


def test_single_open_question_hides_the_control(runs):
    assert _served(runs)["single"] == {"hasNav": False, "state": None}


def test_providing_answers_updates_the_count_and_moves_to_the_next_question(runs):
    result = _served(runs)
    a, _, c = result["stories"]
    assert result["answered"] == {
        "before": "3 of 4", "middleDisabled": False, "lastDisabled": False,
        # b answered: the dossier moves on to c, now 3 of 3.
        "afterMiddle": {"sel": c, "position": "3 of 3"},
        # c (the last) answered: the nearest earlier open question, a's second.
        "afterLast": {"sel": a, "position": "2 of 2"},
    }


def test_control_is_keyboard_reachable_with_accessible_names(runs):
    result = _served(runs)
    assert result["keyboard"] == {
        "previousName": True, "nextName": True, "groupName": True, "positionAnnounced": True,
        "right": {"prevented": True, "position": "2 of 4", "focus": "[data-question-nav-next]"},
        "left": {"prevented": True, "position": "1 of 4", "focus": "[data-question-nav-next]"},
        # ArrowUp is not the control's key: the window-level work navigation
        # takes it (once), and it never also fired for Left/Right.
        "other": True, "workLaneSteps": 1, "sel": result["stories"][0],
    }


def test_static_file_build_boots_and_hides_the_control(runs):
    static = runs["static"]
    assert static["code"] == 0, static["stdout"]
    assert static["result"]["served"] is False
    assert static["result"]["top"]["hasNav"] is False
    assert static["result"]["single"] == {"state": None}
