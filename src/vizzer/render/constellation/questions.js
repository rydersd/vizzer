// The editor lives outside the replaceable dossier DOM so polling cannot steal its caret.
let questionEditor=null;
function sizeQuestionInput(text){
  text.style.height='auto';
  const line=parseFloat(getComputedStyle(text).lineHeight)||24;
  text.style.height=(text.scrollHeight+line*2)+'px';
}
function openQuestionEditor(id,returnTarget){
  if(questionEditor)return;
  const q=(DATA.questions||[]).find(value=>value.id===id);
  if(!q||!questionContext)return;
  const draft=questionDrafts.get(id)||{kind:'freeform',optionId:'',text:''};
  draft.kind='freeform';draft.optionId='';questionDrafts.set(id,draft);
  const panel=document.createElement('section');questionEditor=panel;
  panel.className='questioneditor';panel.setAttribute('aria-label','Edit owner direction');
  panel.innerHTML=`<header><button type="button" data-editor-back>← Back</button><h2>${esc(q.prompt)}</h2></header><div class="questioneditorbody"><label for="question-editor-text">Your suggestion · Markdown supported</label><textarea id="question-editor-text" maxlength="2000" spellcheck="true"></textarea><details><summary>Markdown preview</summary><div class="storymarkdown" data-editor-preview></div></details></div><footer><p class="editorhint" data-editor-status>Draft saved in this browser. Submit saves the complete question and answer to the project.</p><span data-editor-count></span><button type="button" data-editor-submit>Submit answer</button></footer>`;
  const covered=[...dossier.children].filter(child=>child.id!=='dossierresize').map(child=>[child,child.inert]);
  covered.forEach(([child])=>child.inert=true);
  const uncover=()=>covered.forEach(([child,inert])=>child.inert=inert);
  dossier.append(panel);
  const text=panel.querySelector('textarea'),preview=panel.querySelector('[data-editor-preview]'),submit=panel.querySelector('[data-editor-submit]'),back=panel.querySelector('[data-editor-back]'),status=panel.querySelector('[data-editor-status]');
  let submitting=false;
  text.value=draft.text;
  const sync=()=>{draft.text=text.value;persistQuestionDrafts();sizeQuestionInput(text);if(preview)preview.innerHTML=renderStoryMarkdown(text.value);panel.querySelector('[data-editor-count]').textContent=`${text.value.length}/2000`;submit.disabled=submitting||!text.value.trim();};
  const finish=()=>{if(submitting)return;sync();resize.disconnect();uncover();panel._markdownDispose?.();panel.remove();questionEditor=null;refreshDossier();document.getElementById(returnTarget)?.focus();};
  text.addEventListener('input',sync);back.onclick=finish;
  panel.addEventListener('keydown',event=>{event.stopPropagation();if(event.key==='Escape'){event.preventDefault();finish();}});
  submit.onclick=async()=>{
    if(submitting||!text.value.trim())return;
    sync();submitting=true;submit.disabled=true;back.disabled=true;text.readOnly=true;status.textContent='Saving answer…';
    try{
      await preflightQuestionAuthority([{dataset:{questionId:id}}]);
      const response=await fetch('/api/questions/answers',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':questionContext.csrfToken},body:JSON.stringify({expectedRevision:questionContext.revision,answers:[{questionId:id,expectedFingerprint:q.fingerprint,answer:{kind:'freeform',text:text.value.trim()}}]})});
      const body=await response.json();if(!response.ok)throw new Error(body.error||'Answer could not be saved');
      resize.disconnect();uncover();panel._markdownDispose?.();panel.remove();questionEditor=null;reconcileAcceptedDecisions(body.decisions,body.revision,{showFromTop:true});
    }catch(error){status.textContent=error.message||String(error);status.setAttribute('role','alert');submitting=false;back.disabled=false;text.readOnly=false;sync();text.focus();}
  };
  sync();text.focus();text.setSelectionRange(text.value.length,text.value.length);
  const resize=new ResizeObserver(()=>{if(text.isConnected)sizeQuestionInput(text);else resize.disconnect();});resize.observe(panel);
  void mountMarkdownSurface(panel,text);

}

let questionContext=null, questionError='', questionSubmissionError='';
const questionDrafts=new Map();
// Owner directive 2026-08-22: a typed answer must never be lost to a reload or
// a server restart. Drafts mirror to localStorage on every edit and clear only
// when the answer is ACCEPTED by the server. Parked drafts persist the same
// way (they rehydrate as live drafts, which restores the half-written thought).
const QUESTION_DRAFT_STORE='vizzer-question-drafts:'+(DATA.root||location.origin);
try{
  const stored=JSON.parse(localStorage.getItem(QUESTION_DRAFT_STORE)||'{}');
  for(const [id,d] of Object.entries(stored)){
    if(d&&typeof d==='object'&&d.kind)questionDrafts.set(id,{kind:d.kind||'',optionId:d.optionId||'',text:d.text||''});
  }
}catch(e){/* storage unavailable: drafts stay in-tab only */}
function persistQuestionDrafts(){
  try{
    const obj={};
    for(const [id,d] of questionDrafts)if(d&&d.kind)obj[id]=d;
    if(typeof parkedDrafts!=='undefined')for(const [id,d] of parkedDrafts)if(d&&d.kind&&!obj[id])obj[id]=d;
    localStorage.setItem(QUESTION_DRAFT_STORE,JSON.stringify(obj));
  }catch(e){}
}

let discussionContext=null, discussionError='';
const discussionMessages=new Map();
const discussionProviderFrom=text=>{
  const value=String(text||'').toLowerCase();
  if(value.includes('claude'))return'claude';
  if(value.includes('codex'))return'codex';
  return'';
};
function defaultDiscussionProvider(n){
  const work=(n.aw||[]).map(index=>DATA.work[index]).filter(Boolean)
    .sort((a,b)=>String(b.updatedAt||'').localeCompare(String(a.updatedAt||'')));
  for(const entry of work){const provider=discussionProviderFrom(entry.agent);if(provider)return provider;}
  const streams=DATA.workstreams?.workstreams||[], sessions=DATA.workstreams?.sessions||[];
  const streamIds=new Set(streams.filter(stream=>(stream.storyIds||[]).includes(n.id)).map(stream=>stream.id));
  const relevant=sessions.filter(session=>streamIds.has(session.workstreamId))
    .sort((a,b)=>String(b.heartbeatAt||'').localeCompare(String(a.heartbeatAt||'')));
  for(const session of relevant){const provider=discussionProviderFrom(session.actor);if(provider)return provider;}
  return'codex';
}
function discussionQueuePosition(storyId){
  const queues=discussionContext?.queue?.queues||{};
  for(const provider of ['codex','claude']){
    const index=(queues[provider]||[]).indexOf(storyId);
    if(index>=0)return{provider,index};
  }
  return null;
}
function storyDiscussionActions(n,questions){
  const provider=defaultDiscussionProvider(n), queued=discussionQueuePosition(n.id);
  const message=discussionMessages.get(n.id)||discussionError||(
    queued?`Queued #${queued.index+1} · ${queued.provider}`:
    !SERVED?'Read-only file · run vizzer serve to queue discussion':
    !discussionContext?'Loading discussion queue…':`Default · ${provider} (last relevant touch)`
  );
  const answerButton=questions.length
    ?`<button type="button" data-question-submit disabled>Provide ${questions.length===1?'answer':questions.length+' answers'}</button>`:'';
  return `<div class="questionqueuefooter" data-story-actions${questions.length?' data-question-queue':''}>
    <div class="actionstatus">${questions.length?`<span data-question-queue-status>0 of ${questions.length} ready</span>`:''}<span data-discussion-status>${esc(message)}</span></div>
    <div class="dossieractions">${answerButton}<div class="chatsplit" data-chat-split>
      <button type="button" data-chat-primary data-provider="${provider}" ${discussionContext?'':'disabled'}>Chat · ${provider==='claude'?'Claude':'Codex'}</button>
      <button type="button" data-chat-overflow aria-label="Choose discussion provider" aria-expanded="false" ${discussionContext?'':'disabled'}>…</button>
      <div class="chatmenu" data-chat-menu hidden><button type="button" data-chat-provider="codex">Codex</button><button type="button" data-chat-provider="claude">Claude</button></div>
    </div></div></div>`;
}
const questionToken=q=>'question-'+Math.max(0,(DATA.questions||[]).indexOf(q));
function questionCard(q){
  const token=questionToken(q), draft=questionDrafts.get(q.id)||{kind:'',optionId:'',text:''};
  const writable=Boolean(SERVED&&questionContext&&!questionError);
  const controlsDisabled=writable?'':' disabled';
  const options=q.options.map((option,index)=>{
    const id=`${token}-option-${index}`, recommended=option.id===q.recommendation.optionId;
    return `<div><input class="questionradio" type="radio" id="${id}" name="${token}-answer" value="${esc(option.id)}" data-question-option ${draft.kind==='option'&&draft.optionId===option.id?'checked':''}${controlsDisabled}>
      <label class="questionoption" for="${id}"><b>${esc(option.label)}${recommended?' <em>recommended</em>':''}</b><span>${esc(option.tradeoff)}</span></label></div>`;
  }).join('');
  const customId=`${token}-custom`, custom=draft.kind==='freeform';
  const evidence=q.evidence.map(value=>`<code>${esc(value)}</code>`).join('<br>');
  const ready=(draft.kind==='option'&&draft.optionId)||(custom&&draft.text.trim());
  const status=!SERVED?'Read-only file · run vizzer serve to answer':questionError?esc(questionError):!questionContext?'Loading answer authority…':ready?'Selected · ready to answer':'Not answered';
  return `<form class="questioncard" data-question-id="${esc(q.id)}"><fieldset${controlsDisabled}><legend><strong>decision required · ${esc(q.owner)}</strong><h3>${esc(q.prompt)}</h3></legend>
    <div class="questionoptions">${options}<div><input class="questionradio" type="radio" id="${customId}" name="${token}-answer" value="__freeform" data-question-custom ${custom?'checked':''}${controlsDisabled}>
      <label class="questionoption" for="${customId}"><b>Suggest something else</b><span>Record a different owner direction in your own words.</span></label></div></div>
    <div class="questioncustom" ${custom?'':'hidden'}><button type="button" data-question-edit>Edit in Markdown panel</button><label for="${token}-text">Your suggestion · Markdown supported</label><textarea id="${token}-text" maxlength="2000" data-question-text ${custom&&writable?'':'disabled'}>${esc(draft.text)}</textarea></div>
    <div class="recommendation">recommended · ${esc(q.options.find(option=>option.id===q.recommendation.optionId)?.label||q.recommendation.optionId)} — ${esc(q.recommendation.rationale)}</div>
    <small>falsifier · ${esc(q.falsifier)}<br>evidence<br>${evidence}</small>
    <div class="questionstatus${ready?' ready':''}" aria-live="polite">${status}</div></fieldset></form>`;
}
function decisionCard(decision){
  const q=decision.question||decision;
  const chosen=decision.kind==='option'
    ?q.options?.find(option=>option.id===decision.optionId)?.label||decision.optionId
    :decision.text;
  return `<div class="questioncard answered"><strong>answered · ${esc(decision.answeredBy||q.owner||'owner')}</strong><h3>${esc(q.prompt)}</h3>
    <div class="acceptedanswer">${decision.kind==='option'?'accepted option · '+esc(chosen||''):'<div class="storymarkdown">'+renderStoryMarkdown(chosen||'')+'</div>'}</div>
    <small>recorded ${esc(decision.answeredAt||'')} · decision r${esc(decision.revision||1)} · fingerprint <code>${esc((decision.fingerprint||'').slice(0,12))}</code></small></div>`;
}
async function preflightQuestionAuthority(forms){
  const response=await fetch('/api/questions',{cache:'no-store'});
  const body=await response.json();
  if(!response.ok)throw new Error(body.error||'question authority unavailable');
  if(body.renderId!==RENDER_ID)throw new Error(
    `Vizzer version mismatch (page ${RENDER_ID||'unknown'}, server ${body.renderId||'unknown'}). Reload this page before answering.`);
  const liveQuestions=new Map((body.questions||[]).map(question=>[question.id,question]));
  for(const form of forms){
    const rendered=(DATA.questions||[]).find(question=>question.id===form.dataset.questionId);
    const live=liveQuestions.get(form.dataset.questionId);
    if(!rendered||!live)throw new Error(
      'Question authority changed while this page was open. Reload before answering.');
    if(live.fingerprint!==rendered.fingerprint)throw new Error(
      `Question ${rendered.id} changed while this page was open. Reload before answering.`);
  }
  // A same-version restart rotates the CSRF token. Refreshing the complete
  // authority also advances an unrelated ledger revision without discarding
  // any local draft; the exact questions/fingerprints above remain the CAS.
  questionContext=body;questionError='';
}
async function preflightDiscussionAuthority(){
  const [questionResponse,discussionResponse]=await Promise.all([
    fetch('/api/questions',{cache:'no-store'}),fetch('/api/discussions',{cache:'no-store'}),
  ]);
  const questionBody=await questionResponse.json(), discussionBody=await discussionResponse.json();
  if(!questionResponse.ok)throw new Error(questionBody.error||'question authority unavailable');
  if(!discussionResponse.ok)throw new Error(discussionBody.error||'discussion queue unavailable');
  if(questionBody.renderId!==RENDER_ID||discussionBody.renderId!==RENDER_ID)throw new Error(
    `Vizzer version mismatch (page ${RENDER_ID||'unknown'}, server ${questionBody.renderId||discussionBody.renderId||'unknown'}). Reload before queuing discussion.`);
  questionContext=questionBody;discussionContext=discussionBody;discussionError='';
  return questionBody;
}
function bindDiscussionControls(n,actions){
  if(!actions)return;
  const primary=actions.querySelector('[data-chat-primary]'), overflow=actions.querySelector('[data-chat-overflow]');
  const menu=actions.querySelector('[data-chat-menu]');
  overflow?.addEventListener('click',()=>{
    const opening=menu.hidden;menu.hidden=!opening;overflow.setAttribute('aria-expanded',String(opening));
  });
  const enqueue=async provider=>{
    if(!discussionContext)return;
    discussionMessages.set(n.id,`Queuing at top · ${provider}…`);refreshDossier();
    const currentActions=dossierFooter.querySelector('[data-story-actions]');
    currentActions?.querySelectorAll('[data-chat-primary],[data-chat-overflow],[data-chat-provider]').forEach(button=>button.disabled=true);
    try{
      const authority=await preflightDiscussionAuthority();
      const liveQuestions=(authority.questions||[]).filter(question=>question.storyId===n.id)
        .map(question=>({id:question.id,fingerprint:question.fingerprint}));
      const response=await fetch('/api/discussions/queue',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':discussionContext.csrfToken},body:JSON.stringify({
        expectedRevision:discussionContext.queue.revision,provider,storyId:n.id,questions:liveQuestions,
      })});
      const body=await response.json();if(!response.ok)throw new Error(body.error||'discussion queue failed');
      discussionContext.queue=body.queue;
      discussionMessages.set(n.id,body.changed?`Queued first · ${provider}`:`Already first · ${provider}`);
      refreshDossier();
    }catch(error){
      discussionMessages.set(n.id,error.message||String(error));refreshDossier();
      dossierFooter.querySelector('[data-chat-primary]')?.focus();
    }
  };
  primary?.addEventListener('click',()=>enqueue(primary.dataset.provider));
  menu?.querySelectorAll('[data-chat-provider]').forEach(button=>button.addEventListener('click',()=>enqueue(button.dataset.chatProvider)));
}
function bindQuestionControls(n){
  const forms=[...dbody.querySelectorAll('form[data-question-id]')];
  const queue=dossierFooter.querySelector('[data-question-queue]');
  bindDiscussionControls(n,dossierFooter.querySelector('[data-story-actions]'));
  if(!forms.length||!queue)return;
  const draftFor=id=>{
    if(!questionDrafts.has(id))questionDrafts.set(id,{kind:'',optionId:'',text:''});
    return questionDrafts.get(id);
  };
  const ready=draft=>(draft.kind==='option'&&Boolean(draft.optionId))||
    (draft.kind==='freeform'&&Boolean(draft.text.trim()));
  let syncQueue=()=>{};
  forms.forEach(form=>{
    const id=form.dataset.questionId;
    const sync=()=>{
      persistQuestionDrafts();
      const draft=draftFor(id), custom=draft.kind==='freeform';
      const panel=form.querySelector('.questioncustom'), text=form.querySelector('[data-question-text]');
      const status=form.querySelector('.questionstatus');
      panel.hidden=!custom;text.disabled=!custom||!questionContext;if(custom)sizeQuestionInput(text);
      const isReady=ready(draft);
      status.classList.toggle('ready',isReady);
      status.textContent=!SERVED?'Read-only file · run vizzer serve to answer'
        :questionError?questionError:!questionContext?'Loading answer authority…':isReady?'Selected · ready to answer':'Not answered';
      syncQueue();
    };
    form.querySelectorAll('[data-question-option]').forEach(input=>input.addEventListener('change',()=>{
      if(!input.checked)return;questionSubmissionError='';const draft=draftFor(id);draft.kind='option';draft.optionId=input.value;sync();
    }));
    form.querySelector('[data-question-custom]')?.addEventListener('change',event=>{
      if(!event.currentTarget.checked)return;questionSubmissionError='';const draft=draftFor(id);draft.kind='freeform';draft.optionId='';sync();openQuestionEditor(id,form.querySelector('[data-question-text]').id);
    });
    const text=form.querySelector('[data-question-text]');
    form.querySelector('[data-question-edit]')?.addEventListener('click',()=>openQuestionEditor(id,text.id));
    text?.addEventListener('click',()=>openQuestionEditor(id,text.id));
    text?.addEventListener('focus',()=>{
      const custom=form.querySelector('[data-question-custom]');if(custom&&!custom.checked){questionSubmissionError='';custom.checked=true;const draft=draftFor(id);draft.kind='freeform';draft.optionId='';sync();}
    });
    text?.addEventListener('input',event=>{questionSubmissionError='';const draft=draftFor(id);draft.kind='freeform';draft.optionId='';draft.text=event.currentTarget.value;sync();});
    form.addEventListener('submit',event=>event.preventDefault());
    sync();
  });
  const queueButton=queue.querySelector('[data-question-submit]'), queueStatus=queue.querySelector('[data-question-queue-status]');
  syncQueue=()=>{
    const count=forms.filter(form=>ready(draftFor(form.dataset.questionId))).length;
    const countText=forms.length===1
      ?(count?'Selected · ready to answer':'0 of 1 ready')
      :`${count} selected · ${forms.length-count} remaining`;
    queueStatus.textContent=questionSubmissionError||countText;
    queueButton.disabled=!questionContext||count!==forms.length;
    queueButton.setAttribute('aria-disabled',String(queueButton.disabled));
  };
  syncQueue();
  queueButton.addEventListener('click',async()=>{
    if(!questionContext)return;
    questionSubmissionError='';
    const answers=forms.map(form=>{
      const id=form.dataset.questionId;
      const q=(DATA.questions||[]).find(value=>value.id===id);
      const draft=draftFor(id);
      return {questionId:id,expectedFingerprint:q.fingerprint,answer:draft.kind==='option'
        ?{kind:'option',optionId:draft.optionId}
        :{kind:'freeform',text:draft.text.trim()}};
    });
    if(answers.length!==forms.length||forms.some(form=>!ready(draftFor(form.dataset.questionId))))return;
    queue.setAttribute('aria-busy','true');queueButton.disabled=true;queueButton.textContent='Providing…';queueStatus.textContent='Checking current Vizzer and question authority…';
    forms.forEach(form=>form.querySelector('fieldset').disabled=true);
    try{
      await preflightQuestionAuthority(forms);
      queueStatus.textContent='Recording owner decisions…';
      const response=await fetch('/api/questions/answers',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':questionContext.csrfToken},body:JSON.stringify({expectedRevision:questionContext.revision,answers})});
      const body=await response.json();if(!response.ok)throw new Error(body.error||'answers failed');
      reconcileAcceptedDecisions(body.decisions,body.revision,{showFromTop:true});
    }catch(error){
      queue.removeAttribute('aria-busy');queueButton.textContent=forms.length===1?'Provide answer':`Provide ${forms.length} answers`;
      forms.forEach(form=>form.querySelector('fieldset').disabled=false);
      questionSubmissionError=error.message||String(error);
      // Planning/question bootstrap may rebuild the dossier while this async
      // request is pending. Never write the useful failure into a detached
      // footer; reconcile the current dossier from durable state instead.
      if(dossierFooter.contains(queue))syncQueue();else refreshDossier();
      dossierFooter.querySelector('[data-question-queue] button')?.focus();
    }
  });
}

function reconcileAcceptedDecisions(decisions,revision,{showFromTop=false}={}){
  questionSubmissionError='';
  for(const decision of decisions||[]){
    const snapshot=decision.question||{};
    questionDrafts.delete(snapshot.id);persistQuestionDrafts();
    const q=(DATA.questions||[]).find(value=>value.id===snapshot.id);
    if(!q)continue;
    const node=DATA.nodes[q.n], questionIndex=DATA.questions.indexOf(q);
    node.oq=(node.oq||[]).filter(value=>value!==questionIndex);
    const accepted={...q,fingerprint:decision.fingerprint,revision:decision.revision,
      answeredAt:decision.answeredAt,answeredBy:decision.answeredBy,kind:decision.kind,
      optionId:decision.optionId,text:decision.text};
    const decisionIndex=DATA.decisions.push(accepted)-1;
    node.od=[...(node.od||[]),decisionIndex];
    const questionLane=DATA.assessment?.portfolio?.questions;
    if(Array.isArray(questionLane))DATA.assessment.portfolio.questions=questionLane.filter(id=>id!==node.id);
  }
  questionContext.revision=revision;
  questionContext.questions=(questionContext.questions||[]).filter(question=>
    !decisions.some(decision=>decision.question?.id===question.id));
  questionContext.decisions=[...(questionContext.decisions||[]),...(decisions||[])];
  updateViewStatus();
  // Draft edits and failures preserve the exact scroll position. Once the
  // Story update succeeds, rebuild the complete dossier from its top instead
  // of preserving a now-invalid question-form scroll extent and spacer.
  if(showFromTop&&sel>=0)openNode(sel);else refreshDossier();
}

// Owner revisions are review candidates, with exact source identity and durable diffs.
async function openStoryEditor(n){
  if(questionEditor)return;
  const panel=document.createElement('section');questionEditor=panel;
  panel.className='questioneditor';panel.setAttribute('aria-label','Edit story for review');
  const covered=[...dossier.children].filter(child=>child.id!=='dossierresize').map(child=>[child,child.inert]);
  covered.forEach(([child])=>child.inert=true);dossier.append(panel);
  panel.innerHTML=`<header><button type="button" data-edit-back>← Back</button><h2>${esc(n.t)}</h2></header><div class="questioneditorbody"><label for="story-editor-text">Story · Markdown</label><textarea id="story-editor-text" disabled></textarea><details><summary>Markdown preview</summary><div class="storymd" data-edit-preview></div></details></div><footer><p class="editorhint" role="status" data-edit-status>Loading story…</p><button type="button" data-edit-save disabled>Save for review</button></footer>`;
  const text=panel.querySelector('textarea'),status=panel.querySelector('[data-edit-status]'),save=panel.querySelector('[data-edit-save]'),back=panel.querySelector('[data-edit-back]');
  const key=`vizzer-story-draft:${DATA.root||location.origin}:${n.id}`;
  let state=null,busy=false,finished=false;
  const persist=()=>{if(state)try{localStorage.setItem(key,JSON.stringify({text:text.value,sourceHash:state.sourceHash,revision:state.revision}));}catch(_){}};
  const sync=()=>{persist();sizeQuestionInput(text);if(panel.querySelector('[data-edit-preview]'))panel.querySelector('[data-edit-preview]').innerHTML=renderStoryMarkdown(text.value);save.disabled=busy||!state||!text.value.trim();};
  const resize=new ResizeObserver(()=>{if(text.isConnected)sizeQuestionInput(text);});resize.observe(panel);
  const finish=()=>{if(busy)return;finished=true;persist();resize.disconnect();covered.forEach(([child,inert])=>child.inert=inert);panel._markdownDispose?.();panel.remove();questionEditor=null;refreshDossier();dbody.querySelector('[data-edit-story]')?.focus();};
  back.onclick=finish;panel.addEventListener('keydown',event=>{event.stopPropagation();if(event.key==='Escape'){event.preventDefault();finish();}});text.addEventListener('input',sync);
  try{
    const response=await fetch('/api/story-edits/'+encodeURIComponent(n.id),{cache:'no-store'});
    const body=await response.json();if(!response.ok)throw new Error(body.error||'Could not load story');if(finished)return;
    state=body;text.value=state.latest?.edited??state.source;
    let draft=null;try{draft=JSON.parse(localStorage.getItem(key)||'null');}catch(_){}
    if(draft&&typeof draft.text==='string'){text.value=draft.text;state.sourceHash=draft.sourceHash;state.revision=draft.revision;}
    text.disabled=false;status.textContent=state.latest?`Revision ${body.revision} pending review. Editing opens the latest submitted text.`:'Your changes will be saved with the original story and an exact diff for review.';
    sync();text.focus();void mountMarkdownSurface(panel,text);
  }catch(error){if(!finished){status.textContent=error.message||String(error);status.setAttribute('role','alert');}}
  save.onclick=async()=>{
    if(!state||busy)return;persist();busy=true;save.disabled=true;back.disabled=true;text.readOnly=true;status.textContent='Saving revision…';
    try{
      const authority=await fetch('/api/story-edits/'+encodeURIComponent(n.id),{cache:'no-store'});
      const current=await authority.json();if(!authority.ok)throw new Error(current.error||'Story authority unavailable');
      const response=await fetch('/api/story-edits',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':current.csrfToken},body:JSON.stringify({storyId:n.id,expectedSourceHash:state.sourceHash,expectedRevision:state.revision,text:text.value})});
      const result=await response.json();if(!response.ok)throw new Error(result.error||'Could not save revision');
      state.revision=result.revision;try{localStorage.removeItem(key);}catch(_){}
      status.textContent=`Revision ${result.revision} saved · pending review. You can continue editing or go Back.`;
      // Future edits continue from this submitted revision; keep the source hash for CAS.
      busy=false;back.disabled=false;text.readOnly=false;save.disabled=true;
    }catch(error){busy=false;back.disabled=false;text.readOnly=false;save.disabled=false;status.textContent=error.message||String(error);status.setAttribute('role','alert');text.focus();}
  };
}

// One editing surface: formatted Markdown by default, explicit source mode.
async function mountMarkdownSurface(panel,text){
  const body=panel.querySelector('.questioneditorbody');
  body.querySelector('details')?.remove();
  const controls=document.createElement('div');controls.className='markdownmode';
  controls.innerHTML='<button type="button" data-markdown-mode>Markdown source</button><span role="status" data-markdown-note></span>';
  const host=document.createElement('div');host.className='markdownsurface';
  text.before(controls,host);
  const mode=controls.querySelector('button'),note=controls.querySelector('span');
  let editor=null,source=false,disposed=false,initializing=false;
  const onChange=value=>{text.value=value;text.dispatchEvent(new Event('input',{bubbles:true}));};
  const destroy=()=>{const old=editor;editor=null;if(old)void old.destroy();host.replaceChildren();};
  const showSource=()=>{source=true;mode.textContent='Formatted editor';host.hidden=true;text.hidden=false;sizeQuestionInput(text);text.focus();};
  const showRich=async()=>{
    if(initializing||disposed)return;initializing=true;mode.disabled=true;note.textContent='Loading editor…';
    try{
      if(!window.VizzerMarkdownEditor)throw new Error('Formatted editor unavailable; your Markdown remains editable in source mode.');
      if(/^\s*<(?:details|summary|table|div)\b/im.test(text.value))throw new Error('Raw HTML blocks use source mode to preserve them exactly.');
      destroy();host.hidden=false;text.hidden=true;
      const before=text.value;editor=await window.VizzerMarkdownEditor.mount(host,before,onChange);
      if(disposed){destroy();return;}
      const metadata=value=>(value.match(/^> (?:Status|Release|Deps|Tags):.*$/gm)||[]).join('\n');
      if(metadata(before)!==metadata(editor.normalized))throw new Error('Story metadata requires source mode to preserve its exact headers.');
      source=false;mode.textContent='Markdown source';note.textContent='';editor.setReadonly(text.readOnly||text.disabled);editor.focus();
    }catch(error){destroy();showSource();note.textContent=error.message||String(error);}
    finally{initializing=false;mode.disabled=false;}
  };
  mode.onclick=()=>{if(source){void showRich();}else{if(editor)onChange(editor.getMarkdown());destroy();showSource();}};
  const readonly=new MutationObserver(()=>editor?.setReadonly(text.readOnly||text.disabled));readonly.observe(text,{attributes:true,attributeFilter:['readonly','disabled']});
  panel._markdownDispose=()=>{disposed=true;readonly.disconnect();destroy();};
  await showRich();
}
