// ---- repeatable agent-to-owner acceptance ----
let reviewContext=null,reviewError='';
const reviewDrafts=new Map();
const reviewKey=(planId,rowId)=>`${planId}/${rowId}`;
const reviewStatus=event=>event?`${event.verdict} · ${event.actor.kind} · ${event.recordedAt}`:'not run';
function reviewEvidence(event){
  if(!event?.evidence?.length)return '<p class="reviewempty">No evidence attached.</p>';
  return `<div class="reviewevidence">${event.evidence.map(item=>!item.available
    ?`<div class="reviewmissing">${esc(item.error||'Evidence is unavailable.')}</div>`:item.kind==='screenshot'
    ?`<figure><a class="reviewevidencelink" href="${esc(item.url)}" target="_blank" rel="noopener" title="Open evidence at actual size"><img src="${esc(item.url)}" alt="${esc(item.caption||'Captured done state')}"></a><figcaption>${esc(item.caption||item.requirementId)}${item.width&&item.height?` · ${item.width}×${item.height}`:''} · open for actual size${item.available===null?' · check on open':''}</figcaption></figure>`
    :`<a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.caption||item.requirementId)} · ${esc(item.kind)}</a>`).join('')}</div>`;
}
function reviewRun(event,label){
  if(!event)return `<section class="reviewrun empty"><h4>${esc(label)}</h4><p>Not recorded.</p></section>`;
  return `<section class="reviewrun ${esc(event.verdict)}"><h4>${esc(label)} <span>${esc(reviewStatus(event))}</span></h4>
    <ol>${event.stepResults.map(result=>`<li><b>${esc(result.outcome)}</b>${result.observation?` · ${esc(result.observation)}`:''}</li>`).join('')}</ol>
    ${reviewEvidence(event)}${event.note?`<p class="reviewnote">${esc(event.note)}</p>`:''}</section>`;
}
function reviewOutcomeSelect(plan,row,step,index){
  const draft=reviewDrafts.get(reviewKey(plan.id,row.id))||{};
  const selected=draft.outcomes?.[step.id]||'';
  return `<label class="reviewstep"><span><b>${index+1}. ${esc(step.instruction)}</b><small>Expected · ${esc(step.expected)}</small></span>
    <select data-review-step="${esc(step.id)}" aria-label="Outcome for step ${index+1}">
      <option value="">Choose outcome</option>${['pass','fail','blocked','skipped'].map(value=>`<option value="${value}"${selected===value?' selected':''}>${value}</option>`).join('')}
    </select></label>`;
}
function reviewOwnerForm(plan,row){
  const draft=reviewDrafts.get(reviewKey(plan.id,row.id))||{};
  return `<form class="reviewowner" data-review-plan="${esc(plan.id)}" data-review-row="${esc(row.id)}">
    <h4>Your independent validation</h4>
    <p>Repeat the authored steps. This records a separate owner event; it does not edit or replace the agent run.</p>
    <div class="reviewsteps">${row.steps.map((step,index)=>reviewOutcomeSelect(plan,row,step,index)).join('')}</div>
    <label class="reviewnotefield"><span>Review note (optional)</span><textarea maxlength="2000" rows="2" placeholder="What differed, failed, or convinced you?">${esc(draft.note||'')}</textarea></label>
    <div class="reviewactions"><button type="submit">Record owner validation</button><output aria-live="polite"></output></div>
  </form>`;
}
function reviewRow(plan,row){
  const agent=row.latest?.agent,owner=row.latest?.owner;
  const ownerCurrent=owner&&(!agent||owner.revision>agent.revision);
  const summary=ownerCurrent?'owner '+owner.verdict:agent?'awaiting owner · agent '+agent.verdict:'awaiting agent';
  const summaryVerdict=ownerCurrent?owner.verdict:agent?.verdict||'pending';
  return `<details class="reviewrow" open><summary><span><b>${esc(row.title)}</b><small>${esc(row.source.itemId)} · ${row.runCount} recorded run${row.runCount===1?'':'s'}</small></span><span class="reviewverdict ${esc(summaryVerdict)}">${esc(summary)}</span></summary>
    ${row.description?`<p>${esc(row.description)}</p>`:''}${row.setup?`<p><b>Setup ·</b> ${esc(row.setup)}</p>`:''}
    <section class="reviewdod"><h4>Definition of Done</h4><ul>${row.definitionOfDone.map(value=>`<li>${esc(value)}</li>`).join('')}</ul></section>
    <section class="reviewinstructions"><h4>Repeatable steps</h4><ol>${row.steps.map(step=>`<li><b>${esc(step.instruction)}</b><small>Expected · ${esc(step.expected)}</small><em>${esc(step.mode)}</em></li>`).join('')}</ol></section>
    <div class="reviewruns">${reviewRun(agent,'Agent run')}${reviewRun(owner,'Latest owner run')}</div>
    ${SERVED?(agent?reviewOwnerForm(plan,row):'<p class="reviewawaiting">Owner validation opens after an agent records this row.</p>'):''}
  </details>`;
}
function renderReviews(){
  const intro=panelHead('Reviews','Agents show their work; owners repeat the same Definition-of-Done-derived steps and record an independent verdict. Agent pass is evidence, not approval.');
  if(!SERVED)return intro+emptyPanel('Review validation is read-only from file. Run vizzer serve to load plans and record owner results.');
  if(reviewError)return intro+`<div class="reviewerror">${esc(reviewError)}</div>`;
  if(!reviewContext)return intro+emptyPanel('Loading review authority…');
  const warnings=(reviewContext.warnings||[]).length?`<div class="reviewerror"><b>Some review plans are unavailable.</b>${reviewContext.warnings.map(warning=>`<div>${esc(warning.file)} · ${esc(warning.error)}</div>`).join('')}</div>`:'';
  if(!reviewContext.plans?.length)return intro+warnings+emptyPanel('No valid review plans are configured yet.');
  return intro+warnings+reviewContext.plans.map(plan=>`<section class="reviewplan"><header><div><h2>${esc(plan.title)}</h2>${plan.description?`<p>${esc(plan.description)}</p>`:''}</div><small>r${plan.revision} · ${esc(plan.id)}</small></header>${plan.rows.map(row=>reviewRow(plan,row)).join('')}</section>`).join('');
}
async function loadReviewContext(){
  try{
    const response=await fetch('/api/reviews',{cache:'no-store'}),body=await response.json();
    if(response.status===404){reviewError='Reviews are disabled for this project.';reviewContext=null;}
    else if(!response.ok)throw new Error(body.error||'reviews unavailable');
    else if(body.renderId!==RENDER_ID)throw new Error(`Vizzer server is out of date (${body.renderId||'unknown'} vs ${RENDER_ID}). Restart vizzer serve.`);
    else{reviewContext=body;reviewError='';}
  }catch(error){reviewError=error.message||String(error);reviewContext=null;}
  if(currentView==='reviews')renderCurrentView();
}
function reviewVerdict(outcomes){
  if(outcomes.includes('fail'))return 'fail';
  if(outcomes.includes('blocked'))return 'blocked';
  if(outcomes.includes('skipped'))return 'skipped';
  return 'pass';
}
function bindReviewView(){
  viewPanel.querySelectorAll('.reviewowner').forEach(form=>{
    const plan=reviewContext?.plans?.find(item=>item.id===form.dataset.reviewPlan);
    const row=plan?.rows?.find(item=>item.id===form.dataset.reviewRow);
    if(!plan||!row)return;
    const key=reviewKey(plan.id,row.id),draft=reviewDrafts.get(key)||{outcomes:{},note:''};
    reviewDrafts.set(key,draft);
    form.querySelectorAll('[data-review-step]').forEach(select=>select.onchange=()=>{draft.outcomes[select.dataset.reviewStep]=select.value;});
    form.querySelector('textarea').oninput=event=>{draft.note=event.target.value;};
    form.onsubmit=async event=>{
      event.preventDefault();
      const output=form.querySelector('output');
      const outcomes=row.steps.map(step=>draft.outcomes[step.id]||'');
      if(outcomes.some(value=>!value)){output.textContent='Choose an outcome for every step.';return;}
      const now=new Date(),eventId=`owner-${now.getTime().toString(36)}-${Math.random().toString(36).slice(2,10)}`;
      const reviewEvent={eventId,recordedAt:now.toISOString(),actor:{kind:'owner',id:'project-owner'},planId:plan.id,rowId:row.id,planFingerprint:plan.fingerprint,basedOnAgentEventId:row.latest.agent.eventId,
        stepResults:row.steps.map((step,index)=>({stepId:step.id,outcome:outcomes[index]})),evidence:[],verdict:reviewVerdict(outcomes)};
      if(draft.note.trim())reviewEvent.note=draft.note.trim();
      output.textContent='Recording…';
      try{
        const response=await fetch('/api/reviews/runs',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':reviewContext.csrfToken},body:JSON.stringify({expectedRevision:plan.revision,event:reviewEvent})});
        const body=await response.json();
        if(!response.ok)throw new Error(body.error||'owner validation failed');
        reviewDrafts.delete(key);await loadReviewContext();
      }catch(error){output.textContent=error.message||String(error);}
    };
  });
}
