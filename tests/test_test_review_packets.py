import hashlib
import json
from pathlib import Path
import subprocess

from vizzer.render.constellation import _test_review_packets


FIELDS = {
    "Proposal ID": "packet-1", "Story": "story:a", "Test Risk": "B",
    "Goal": "Prove the production route changes visible state.",
    "Selectors": "testVisibleRoute", "Bounds": "one fixture; one attempt; 60 seconds",
    "Evidence": "raw result bundle", "Defect": "story:a",
    "Challenge": "an internal assertion could pass without presentation",
    "Opportunity": "add a visible negative control", "Source boundary": "abc123",
    "Falsifiers": "no-op mutation must fail", "Environment": "isolated local runner",
    "Executor": "executor-agent",
}


def fingerprint(fields=FIELDS):
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def packet(author="author-agent", goal=None):
    fields = dict(FIELDS)
    if goal is not None:
        fields["Goal"] = goal
    lines = ["TEST REVIEW PACKET", *(f"{key}: {value}" for key, value in fields.items()),
             f"Packet fingerprint: {fingerprint(fields)}", "State: ready", "Outcome: pending",
             "Phase: design", "Elapsed: 0s"]
    return {"id": "proposal-discussion", "workstreamId": "lane", "author": author,
            "createdAt": "2026-09-05T12:00:00Z", "body": "\n".join(lines)}


def verdict(author="reviewer-agent", reply="proposal-discussion", reviewer_session="review-1"):
    body = "\n".join(["TEST REVIEW VERDICT", "Proposal ID: packet-1", "Story: story:a",
                       f"Packet fingerprint: {fingerprint()}",
                       f"Reviewer session: {reviewer_session}", "Verdict: PASS"])
    return {"id": "verdict-discussion", "workstreamId": "lane", "author": author,
            "replyTo": reply, "createdAt": "2026-09-05T12:01:00Z", "body": body}


def workstreams(*discussions):
    return {"workstreams": [{"id": "lane", "storyIds": ["story:a"]}],
            "discussions": list(discussions)}


def test_separate_exact_verdict_authorizes_packet():
    rows = _test_review_packets(workstreams(packet(), verdict()), {"story:a": 0})
    assert len(rows) == 1
    assert (rows[0]["verdict"], rows[0]["state"], rows[0]["reviewerSession"]) == ("PASS", "ready", "review-1")


def test_changed_packet_cannot_reuse_verdict_and_self_review_fails_closed():
    changed = packet(goal="A changed claim.")
    rows = _test_review_packets(workstreams(changed, verdict()), {"story:a": 0})
    assert rows[0]["verdict"] == "PENDING"
    rows = _test_review_packets(workstreams(packet(), verdict(author=" AUTHOR-AGENT ")), {"story:a": 0})
    assert rows[0]["verdict"] == "PENDING"


def test_blank_or_newline_smuggled_identity_fields_invalidate():
    broken = packet().copy()
    broken["body"] = broken["body"].replace("Executor: executor-agent", "Executor:   \nState: ready")
    rows = _test_review_packets(workstreams(broken, verdict()), {"story:a": 0})
    assert rows[0]["state"] == "invalidated"


def test_constellation_exposes_state_outcome_and_durable_create_test_controls():
    root = Path(__file__).resolve().parents[1] / "src/vizzer/render/constellation"
    canvas = (root / "canvas.js").read_text()
    dossier = (root / "dossier.js").read_text()
    assert "function testReviewVisualState" in canvas
    for value in ("preparing", "under-review", "running", "unauthorized-execution",
                  "expected-red", "infrastructure-failure", "cancelled"):
        assert value in canvas
    assert "function activeTestDesignRequest" in dossier
    assert "request.provider===activeProvider" in dossier
    assert "data-create-test" in dossier
    assert "Risk B/C requires a separate testing-agent PASS" in dossier


def test_create_test_persists_before_best_effort_clipboard_and_visual_states_execute():
    root = Path(__file__).resolve().parents[1] / "src/vizzer/render/constellation"
    script = r"""
const fs=require('fs');
const dossier=fs.readFileSync(process.argv[1],'utf8');
const canvas=fs.readFileSync(process.argv[2],'utf8');
const dossierFns=dossier.slice(dossier.indexOf('function testDesignRequest'),dossier.indexOf('function openNode'));
const visualFn=canvas.slice(canvas.indexOf('function testReviewVisualState'),canvas.indexOf('function trailArrow'));
eval(dossierFns);eval(visualFn);
const DATA={nodes:[{id:'story:a',t:'A',p:'spec/a.md',acx:'Visible result',dod:'Bounded evidence'}]};
let discussionContext={csrfToken:'token',queue:{revision:0,queues:{codex:[],claude:[]},requests:[]}};
let refreshes=0,clipboardAttempts=0,toasts=[];
const refreshDossier=()=>{refreshes++};
const preflightDiscussionAuthority=async()=>({questions:[]});
const stored={revision:1,queues:{codex:['story:a'],claude:[]},requests:[{kind:'test-design',provider:'codex',storyId:'story:a',state:'queued',fingerprint:'abc'}]};
globalThis.fetch=async()=>({ok:true,json:async()=>({changed:true,queue:stored})});
Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{writeText:async()=>{clipboardAttempts++;throw new Error('denied')}}}});
const toast=(message,isError)=>toasts.push({message,isError});
const button={disabled:false,textContent:'Create bounded test'};
(async()=>{
  await queueTestDesignRequest(0,button);
  const active=activeTestDesignRequest('story:a',discussionContext.queue);
  const running=testReviewVisualState({state:'running',outcome:'pending',snag:''},{active:.75,slow:.25,reduced:false});
  const reduced=testReviewVisualState({state:'snagged',outcome:'infrastructure-failure',snag:'mutex'},{active:.75,slow:.25,reduced:true});
  process.stdout.write(JSON.stringify({button,refreshes,clipboardAttempts,toasts,active,running,reduced,queue:discussionContext.queue}));
})().catch(error=>{console.error(error);process.exit(1)});
"""
    run = subprocess.run(
        ["node", "-e", script, str(root / "dossier.js"), str(root / "canvas.js")],
        capture_output=True, text=True, check=True,
    )
    result = json.loads(run.stdout)
    assert result["queue"]["revision"] == 1
    assert result["active"]["provider"] == "codex"
    assert result["refreshes"] == 1 and result["clipboardAttempts"] == 1
    assert result["button"]["textContent"] == "Test review queued"
    assert result["button"]["disabled"] is True
    assert result["toasts"] == [{
        "message": "Test review was queued, but the prompt could not be copied.",
        "isError": True,
    }]
    assert result["running"]["running"] is True and result["running"]["wave"] == .75
    assert result["reduced"]["snag"] is True
    assert result["reduced"]["stateLabel"] == "S"
    assert result["reduced"]["outcomeBadge"] == "⚠"
