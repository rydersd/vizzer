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
import os
import shutil
import subprocess
import time
from pathlib import Path

import vizzer.cli as cli
from test_question_http import (
    _prepare_repo, _question, _request, _start, _stop, _write_feed,
)
from vizzer.cli import main
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
globalThis.document={getElementById:()=>null,querySelector:()=>null,querySelectorAll:()=>[]};
globalThis.sessionStorage={getItem:()=>null,setItem(){},removeItem(){}};globalThis.localStorage=globalThis.sessionStorage;
globalThis.addEventListener=()=>{};globalThis.location={hash:'',search:'',protocol:'http:'};
globalThis.RENDER_ID='render-1';globalThis.sel=-1;
globalThis.esc=value=>String(value??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
globalThis.updateViewStatus=()=>{};globalThis.refreshDossier=()=>{};globalThis.openNode=()=>{};
const option=(id,label)=>({id,label,tradeoff:''});
const question=(id,fingerprint)=>({id,fingerprint,n:0,owner:'owner',prompt:'Pick?',
  options:[option('placeholder-only-on-bar','Placeholder only on the bar'),option('diamond-on-both','Diamond on both')],
  recommendation:{optionId:'placeholder-only-on-bar',rationale:''},falsifier:'',evidence:[]});
const q1=question('question:bar-glyph','fp-1'), q2=question('question:hover-key','fp-2');
globalThis.DATA={questions:[q1,q2],nodes:[{id:'story:bar',oq:[0,1],od:[]}],decisions:[]};
vm.runInThisContext(require('fs').readFileSync(process.argv[1],'utf8'));
const decision=(q,revision,optionId)=>({question:{id:q.id,fingerprint:q.fingerprint},fingerprint:q.fingerprint,
  revision,answeredAt:'2026-09-24T22:03:00-07:00',answeredBy:'owner',kind:'option',optionId,text:''});
const answerFor=(q,optionId)=>({questionId:q.id,expectedFingerprint:q.fingerprint,answer:{kind:'option',optionId}});
const formFor=q=>({dataset:{questionId:q.id}});
const authority=(revision,decisions,open)=>({ok:true,status:200,json:async()=>({
  renderId:RENDER_ID,csrfToken:'rotated-token',revision,questions:open,decisions})});
function server(post,after,before=()=>authority(322,[],[q1,q2])){
  const calls={after:0};let posted=false;
  const fetchImpl=async url=>{
    if(url==='/api/questions/answers'){posted=true;return post();}
    if(url==='/api/questions')return posted?after(++calls.after):before();
    throw new Error('unexpected fetch '+url);
  };
  return {fetchImpl,calls};
}
const lost=async()=>{throw new TypeError('Failed to fetch');};
const refused=(status,error)=>async()=>({ok:false,status,json:async()=>({error})});
async function run(scripted,questions,answers,limit=200){
  questionContext={csrfToken:'old-token',revision:322};globalThis.fetch=scripted.fetchImpl;
  try{
    const value=await recordQuestionAnswers(questions.map(formFor),answers,{pollMs:1,pollLimitMs:limit});
    return {ok:true,reads:scripted.calls.after,revision:value.revision,
      ids:value.decisions.map(d=>d.question.id),notes:Object.fromEntries(value.notes),value,
      token:questionContext.csrfToken};
  }catch(error){return {ok:false,reads:scripted.calls.after,error:error.message};}
}
(async()=>{
  const out={};
  const mine=[answerFor(q1,'placeholder-only-on-bar')];
  out.lateWrite=await run(server(lost,n=>n<3?authority(322,[],[q1,q2]):authority(323,[decision(q1,323,'placeholder-only-on-bar')],[q2])),[q1],mine);
  out.overtaken=await run(server(lost,()=>authority(323,[],[q1,q2])),[q1],mine,5000);
  out.neverLands=await run(server(lost,()=>authority(322,[],[q1,q2])),[q1],mine,40);
  out.stale=await run(server(refused(409,'stale question answer revision 322; current is 323'),
    ()=>authority(323,[decision(q1,323,'placeholder-only-on-bar')],[q2])),[q1],mine,5000);
  out.genuine=await run(server(refused(500,'ledger write failed'),()=>authority(322,[],[q1,q2])),[q1],mine,5000);
  out.oldDecision=await run(server(refused(500,'ledger write failed'),
    ()=>authority(322,[decision(q1,300,'placeholder-only-on-bar')],[q1,q2])),[q1],mine,5000);
  const other=await run(server(refused(409,'stale question answer revision 322; current is 323'),
    ()=>authority(323,[decision(q1,323,'diamond-on-both')],[q2])),[q1],mine,5000);
  out.differs={ok:other.ok,ids:other.ids,notes:other.notes};
  questionDrafts.set(q1.id,{kind:'option',optionId:'placeholder-only-on-bar',text:''});
  reconcileAcceptedDecisions(other.value.decisions,other.value.revision,{notes:other.value.notes});
  out.differsDraftKept=questionDrafts.get(q1.id)?.optionId||'';
  out.differsCard=decisionCard(DATA.decisions[DATA.decisions.length-1]);
  out.nodeOpen=DATA.nodes[0].oq;
  const batch=[answerFor(q1,'placeholder-only-on-bar'),answerFor(q2,'diamond-on-both')];
  const partial=await run(server(refused(409,'stale question answer revision 322; current is 323'),
    ()=>authority(323,[decision(q1,323,'placeholder-only-on-bar')],[q2])),[q1,q2],batch,5000);
  out.partial={ok:partial.ok,ids:partial.ids,notes:partial.notes};
  process.stdout.write(JSON.stringify(out,(key,value)=>key==='value'?undefined:value));
})().catch(error=>{process.stdout.write(String(error.stack||error));process.exit(3);});
"""


def _page_outcomes():
    node = shutil.which("node")
    assert node is not None, "Node is required for the answer reconcile test"
    completed = subprocess.run([node, "-e", _DRIVER, str(QUESTIONS_JS)],
                               text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_a_reply_lost_before_the_write_is_accepted_when_the_answer_lands():
    late = _page_outcomes()["lateWrite"]
    assert late["ok"], late
    assert late["reads"] == 3, "the decision appeared on the third re-read"
    assert late["revision"] == 323 and late["notes"] == {}
    assert late["token"] == "rotated-token"


def test_no_http_reply_polls_until_the_ledger_moves_or_the_limit():
    out = _page_outcomes()
    assert out["overtaken"] == {"ok": False, "reads": 1, "error": "Failed to fetch"}
    assert not out["neverLands"]["ok"] and out["neverLands"]["reads"] > 1


def test_an_http_error_is_final_after_one_read():
    out = _page_outcomes()
    assert out["stale"]["ok"] and out["stale"]["reads"] == 1
    assert out["genuine"] == {"ok": False, "reads": 1, "error": "ledger write failed"}
    assert out["oldDecision"]["error"] == "ledger write failed", (
        "a decision from before this attempt is not this answer")


def test_an_answer_recorded_differently_says_so_and_keeps_the_draft():
    out = _page_outcomes()
    note = out["differs"]["notes"]["question:bar-glyph"]
    assert "Answered in another window as “Diamond on both”" in note
    assert "Your choice “Placeholder only on the bar” was not recorded" in note
    assert out["differsDraftKept"] == "placeholder-only-on-bar"
    assert "data-question-note" in out["differsCard"]
    assert out["nodeOpen"] == [1]


def test_a_partly_recorded_batch_accepts_what_landed_and_marks_the_rest():
    partial = _page_outcomes()["partial"]
    assert partial["ok"] and partial["ids"] == ["question:bar-glyph"]
    assert "Not recorded" in partial["notes"]["question:hover-key"]


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


# Round 2 (review 2026-09-25): the page reconciles on load, a reworded question
# shows the earlier answer, a failed refresh is retried, the ledger is last.

LOAD_DRIVER = r"""
const vm=require('vm');
globalThis.document={getElementById:()=>null,querySelector:()=>null,querySelectorAll:()=>[]};
globalThis.sessionStorage={getItem:()=>null,setItem(){},removeItem(){}};globalThis.localStorage=globalThis.sessionStorage;
globalThis.addEventListener=()=>{};globalThis.location={hash:'',search:'',protocol:'http:'};
globalThis.RENDER_ID='render-1';globalThis.SERVED=true;globalThis.sel=-1;
globalThis.esc=value=>String(value??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let redraws=0, openedFromTop=0;
globalThis.updateViewStatus=()=>{redraws++;};globalThis.refreshDossier=()=>{};
globalThis.openNode=()=>{openedFromTop++;};
const option=(id,label)=>({id,label,tradeoff:''});
const question=(id,fingerprint,n)=>({id,fingerprint,n,owner:'ryder',prompt:'Pick?',
  options:[option('opt-a','Option A'),option('opt-b','Option B')],
  recommendation:{optionId:'opt-a',rationale:''},falsifier:'',evidence:[]});
const q1=question('question:answered','a'.repeat(64),0), q2=question('question:reworded','b'.repeat(64),0);
globalThis.DATA={questions:[q1,q2],nodes:[{id:'story:s',oq:[0,1],od:[]}],decisions:[]};
vm.runInThisContext(require('fs').readFileSync(process.argv[1],'utf8'));
const decision=(q,revision,optionId)=>({question:{id:q.id,fingerprint:q.fingerprint},fingerprint:q.fingerprint,
  revision,answeredAt:'2026-09-24T22:03:00-07:00',answeredBy:'owner',kind:'option',optionId,text:''});
const out={};
const now=Date.parse('2026-09-25T18:30:00Z');
// The embedded map predates the answer to q1 (refresh failed or still running).
const body={renderId:RENDER_ID,csrfToken:'t',revision:7,questions:[q2],
  decisions:[decision(q1,7,'opt-b')],
  supersededAnswers:[{questionId:q2.id,revision:5,answeredAt:'2026-09-20T09:15:00-07:00',choice:'Option B'}],
  viewsBehind:true,viewsBehindSince:'2026-09-25T18:29:40Z',refreshFailure:null};
adoptQuestionAuthority(body,{now});
out.nodeOpen=DATA.nodes[0].oq;
out.decided=DATA.decisions.map(d=>d.id);
out.contextDecisions=questionContext.decisions.length;
out.redraws=redraws;out.openedFromTop=openedFromTop;
out.supersededNote=questionNotes.get(q2.id)||'';
out.card=questionCard(q2);
// Behind for only 20 s with no failure: the normal refresh window stays quiet.
out.quietNote=viewsBehindText(body,now);
// Behind for over a minute: say so.
out.slowNote=viewsBehindText({...body,viewsBehindSince:'2026-09-25T18:28:00Z'},now);
// A failed refresh is named at once, first line only.
out.failedNote=viewsBehindText({...body,refreshFailure:{error:'could not write derived artifacts: [Errno 13] Permission denied\nsecond line',failedAt:'2026-09-25T18:29:50Z',attempts:2}},now);
out.caughtUp=viewsBehindText({...body,viewsBehind:false},now);
// Adopting the same authority twice changes nothing.
adoptQuestionAuthority(body,{now});
out.decidedAgain=DATA.decisions.length;out.contextDecisionsAgain=questionContext.decisions.length;
process.stdout.write(JSON.stringify(out));
"""


def _load_outcomes():
    node = shutil.which("node")
    assert node is not None, "Node is required for the answer reconcile test"
    completed = subprocess.run([node, "-e", LOAD_DRIVER, str(QUESTIONS_JS)],
                               text=True, capture_output=True, check=False,
                               env={**os.environ, "TZ": "UTC"})
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_a_page_loaded_behind_the_ledger_shows_the_recorded_answer():
    out = _load_outcomes()
    assert out["nodeOpen"] == [1], "the answered question leaves the open list on load"
    assert len(out["decided"]) == 1 and out["contextDecisions"] == 1
    assert out["redraws"] >= 1 and out["openedFromTop"] == 0
    assert out["decidedAgain"] == 1 and out["contextDecisionsAgain"] == 1


def test_a_reworded_question_card_shows_the_earlier_answer():
    out = _load_outcomes()
    note = out["supersededNote"]
    assert "You answered an earlier wording on 2026-09-20" in note
    assert "“Option B”" in note and "The question changed since; answer again." in note
    assert "data-question-note" in out["card"]


def test_the_views_behind_note_is_quiet_in_the_normal_window_and_named_after():
    out = _load_outcomes()
    assert out["quietNote"] == ""
    assert out["slowNote"] == "Views are behind your answers since 18:28."
    assert out["failedNote"] == (
        "Views are behind your answers since 18:29 — refresh failed: could not "
        "write derived artifacts: [Errno 13] Permission denied. Retrying.")
    assert out["caughtUp"] == ""


STORY = "spec/drawing/epics/tools/stories/canvas-core.md"


def _answer(connection, guarded, fingerprint, revision=0, option="shared"):
    return _request(connection, "POST", "/api/questions/question%3Aroute/answer", {
        "expectedRevision": revision, "expectedFingerprint": fingerprint,
        "answer": {"kind": "option", "optionId": option},
    }, guarded)


def test_a_reworded_question_reopens_and_its_story_note_is_marked_superseded(
    tmp_path, make_repo, monkeypatch
):
    repo = _prepare_repo(tmp_path, make_repo)
    monkeypatch.setattr(cli, "_schedule_background_refresh", lambda root: None)
    story = repo / STORY
    server, thread, connection, guarded = _start(repo)
    try:
        _, context = _request(connection, "GET", "/api/questions")
        old = context["questions"][0]["fingerprint"]
        status, body = _answer(connection, guarded, old)
        assert status == 200, body
        assert main(["refresh", "--root", str(repo)]) == 0
        assert f"evolution-answer:{old}:begin" in story.read_text(encoding="utf-8")

        _write_feed(repo, _question(prompt="Which revised route wins?"))
        assert main(["refresh", "--root", str(repo)]) == 0
        _, served = _request(connection, "GET", "/api/questions")
        assert [q["id"] for q in served["questions"]] == ["question:route"]
        earlier = served["supersededAnswers"]
        assert [(e["questionId"], e["choice"], e["revision"]) for e in earlier] == [
            ("question:route", "Shared", 1)]
        text = story.read_text(encoding="utf-8")
        assert text.count(f"evolution-superseded:{old}:begin") == 1
        assert "owner answer superseded" in text
        assert main(["refresh", "--root", str(repo)]) == 0
        assert story.read_text(encoding="utf-8") == text, "the note is written once"

        status, body = _answer(connection, guarded,
                               served["questions"][0]["fingerprint"], 1, "native")
        assert status == 200, body
        _, served = _request(connection, "GET", "/api/questions")
        assert served["supersededAnswers"] == [] and served["questions"] == []
    finally:
        _stop(server, thread, connection)


def test_views_that_cannot_be_written_leave_the_answer_and_are_retried(
    tmp_path, make_repo, monkeypatch, capsys
):
    """The reviewer's repro: the views directory turns read-only after an answer."""
    repo = _prepare_repo(tmp_path, make_repo)
    views = repo / "vizzer/views"
    monkeypatch.setattr(cli, "_REFRESH_RETRY_DELAYS", (0.2, 0.2, 0.2))
    server, thread, connection, guarded = _start(repo)
    try:
        _, context = _request(connection, "GET", "/api/questions")
        views.chmod(0o555)
        status, body = _answer(connection, guarded, context["questions"][0]["fingerprint"])
        assert status == 200, body

        def failed_twice():
            _, served = _request(connection, "GET", "/api/questions")
            return served if (served.get("refreshFailure") or {}).get("attempts", 0) >= 2 else None

        served = _wait(failed_twice)
        assert served, "the failed refresh was not retried"
        assert served["revision"] == 1 and served["questions"] == []
        assert served["viewsBehind"] is True and served["viewsBehindSince"]
        assert "Permission denied" in served["refreshFailure"]["error"]
        assert "view refresh attempt 2" in capsys.readouterr().err

        views.chmod(0o755)

        def caught_up():
            _, served = _request(connection, "GET", "/api/questions")
            # The graph lands a moment before the worker clears its failure.
            return served if not served["viewsBehind"] and not served["refreshFailure"] else None

        served = _wait(caught_up)
        assert served and served["refreshFailure"] is None
        assert served["viewsBehindSince"] is None
    finally:
        views.chmod(0o755)
        _stop(server, thread, connection)


def test_the_story_note_is_written_before_the_ledger(tmp_path, make_repo, monkeypatch):
    repo = _prepare_repo(tmp_path, make_repo)
    monkeypatch.setattr(cli, "_schedule_background_refresh", lambda root: None)
    seen = []
    original = cli.append_evolution_events

    def observed(graph, root, decisions):
        seen.append((repo / "vizzer/question-answers.json").exists())
        return original(graph, root, decisions)

    monkeypatch.setattr(cli, "append_evolution_events", observed)
    server, thread, connection, guarded = _start(repo)
    try:
        _, context = _request(connection, "GET", "/api/questions")
        status, body = _answer(connection, guarded, context["questions"][0]["fingerprint"])
    finally:
        _stop(server, thread, connection)
    assert status == 200, body
    assert seen == [False], "the ledger is the commit point: written last"


def test_a_ledger_write_failure_restores_the_story_note(tmp_path, make_repo, monkeypatch):
    repo = _prepare_repo(tmp_path, make_repo)
    monkeypatch.setattr(cli, "_schedule_background_refresh", lambda root: None)
    story = repo / STORY
    before = story.read_bytes()

    def fail(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(cli, "write_answers", fail)
    server, thread, connection, guarded = _start(repo)
    try:
        _, context = _request(connection, "GET", "/api/questions")
        status, body = _answer(connection, guarded, context["questions"][0]["fingerprint"])
    finally:
        _stop(server, thread, connection)
    assert status == 500 and body["revision"] == 0
    assert story.read_bytes() == before
    assert not (repo / "vizzer/question-answers.json").exists()


def _wait(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return predicate()
