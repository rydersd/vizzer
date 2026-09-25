"""A recorded answer is shown as accepted even when its reply was lost.

Field report (illtool-standalone, 2026-09-24): the serve recorded an answer,
but the slow answer path outlived the browser's connection (BrokenPipeError on
the reply), the page showed a failure, and the retry was refused with "stale
question answer revision 322; current is 323".

Contracts: ``recordQuestionAnswers`` re-reads /api/questions on any failure and
returns the recorded decisions when every submitted question has one; a
genuine failure still propagates.  ``GET /api/questions`` partitions the stored
graph against the ledger, so it reports the decision even before the graph is
rewritten.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from test_question_http import _prepare_repo, _request, _start, _stop
from vizzer.cli import _read_graph
from vizzer.config import Config
from vizzer.model import owner_question_fingerprint
from vizzer.question_answers import (
    append_answer, current_questions_and_decisions, read_answers,
)

QUESTIONS_JS = (Path(__file__).resolve().parents[1]
                / "src/vizzer/render/constellation/questions.js")

_DRIVER = r"""
const vm=require('vm');
globalThis.document={getElementById:()=>null,querySelector:()=>null};
globalThis.sessionStorage={getItem:()=>null,setItem(){}};globalThis.localStorage=globalThis.sessionStorage;
globalThis.addEventListener=()=>{};globalThis.location={hash:'',search:'',protocol:'http:'};
globalThis.RENDER_ID='render-1';
const q={id:'question:bar-glyph',fingerprint:'fp-1'};
globalThis.DATA={questions:[q],nodes:[],decisions:[]};
vm.runInThisContext(require('fs').readFileSync(process.argv[1],'utf8'));
const decision={question:{id:q.id,fingerprint:q.fingerprint},fingerprint:q.fingerprint,
  revision:323,answeredAt:'2026-09-24T22:03:00-07:00',answeredBy:'owner',
  kind:'option',optionId:'placeholder-only-on-bar',text:''};
const forms=[{dataset:{questionId:q.id}}];
const answers=[{questionId:q.id,expectedFingerprint:q.fingerprint,
  answer:{kind:'option',optionId:'placeholder-only-on-bar'}}];
const authority=(decisions,revision)=>({ok:true,status:200,json:async()=>({
  renderId:RENDER_ID,csrfToken:'rotated-token',revision,
  questions:decisions.length?[]:[q],decisions})});
function server(postOutcome,afterPost){
  let posted=false;
  return async url=>{
    if(url==='/api/questions/answers'){posted=true;return postOutcome();}
    if(url==='/api/questions')return posted?afterPost():authority([],322);
    throw new Error('unexpected fetch '+url);
  };
}
async function run(fetchImpl){
  questionContext={csrfToken:'old-token',revision:322};globalThis.fetch=fetchImpl;
  try{return {ok:true,value:await recordQuestionAnswers(forms,answers)};}
  catch(error){return {ok:false,error:error.message};}
}
(async()=>{
  const out={};
  const lost=await run(server(async()=>{throw new TypeError('Failed to fetch');},
    async()=>authority([decision],323)));
  out.lost={ok:lost.ok,revision:lost.value?.revision,id:lost.value?.decisions[0].question.id,
    token:questionContext.csrfToken};
  const stale=await run(server(async()=>({ok:false,status:409,json:async()=>({
    error:'stale question answer revision 322; current is 323'})}),
    async()=>authority([decision],323)));
  out.stale={ok:stale.ok,revision:stale.value?.revision};
  const genuine=await run(server(async()=>({ok:false,status:500,json:async()=>({
    error:'ledger write failed'})}),async()=>authority([],322)));
  out.genuine=genuine;
  const unreadable=await run(server(async()=>{throw new TypeError('Failed to fetch');},
    async()=>{throw new TypeError('Failed to fetch');}));
  out.unreadable=unreadable;
  process.stdout.write(JSON.stringify(out));
})().catch(error=>{process.stdout.write(String(error.stack||error));process.exit(3);});
"""


def _page_outcomes():
    node = shutil.which("node")
    assert node is not None, "Node is required for the answer reconcile test"
    completed = subprocess.run([node, "-e", _DRIVER, str(QUESTIONS_JS)],
                               text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_lost_or_stale_reply_with_recorded_decision_is_accepted():
    out = _page_outcomes()
    assert out["lost"] == {"ok": True, "revision": 323, "id": "question:bar-glyph",
                           "token": "rotated-token"}
    assert out["stale"] == {"ok": True, "revision": 323}


def test_genuine_failure_and_unreadable_authority_still_surface_the_error():
    out = _page_outcomes()
    assert out["genuine"] == {"ok": False, "error": "ledger write failed"}
    assert out["unreadable"] == {"ok": False, "error": "Failed to fetch"}


def test_get_reports_an_answer_the_stored_graph_has_not_caught_up_with(
    tmp_path, make_repo
):
    """The field state: the ledger holds the answer, the graph is not rebuilt yet."""
    repo = _prepare_repo(tmp_path, make_repo)
    graph = _read_graph(repo)
    cfg = Config.load(repo)
    question = graph.owner_questions[0]
    unanswered, _ = read_answers(cfg, repo)
    assert current_questions_and_decisions(graph, unanswered)[0] == graph.owner_questions

    # Write the ledger only; no refresh, so the stored graph still lists it open.
    append_answer(graph, cfg, repo, question.id, expected_revision=0,
                  expected_fingerprint=owner_question_fingerprint(question),
                  kind="option", option_id="shared")
    assert [q.id for q in _read_graph(repo).owner_questions] == [question.id]
    ledger, _ = read_answers(cfg, repo)
    open_questions, decisions = current_questions_and_decisions(graph, ledger)
    assert open_questions == []
    assert [d.question.id for d in decisions] == [question.id]

    server, thread, connection, _ = _start(repo)
    try:
        status, context = _request(connection, "GET", "/api/questions")
    finally:
        _stop(server, thread, connection)
    assert status == 200
    assert context["revision"] == 1
    assert context["questions"] == []
    assert [d["question"]["id"] for d in context["decisions"]] == [question.id]
    assert context["decisions"][0]["optionId"] == "shared"
