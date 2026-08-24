let questionContext=null, questionError='', questionSubmissionError='';
const questionDrafts=new Map();
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
    <div class="questioncustom" ${custom?'':'hidden'}><label for="${token}-text">Your suggestion</label><textarea id="${token}-text" maxlength="2000" data-question-text ${custom&&writable?'':'disabled'}>${esc(draft.text)}</textarea></div>
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
    <div class="acceptedanswer">${decision.kind==='option'?'accepted option':'owner suggestion'} · ${esc(chosen||'')}</div>
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
      const draft=draftFor(id), custom=draft.kind==='freeform';
      const panel=form.querySelector('.questioncustom'), text=form.querySelector('[data-question-text]');
      const status=form.querySelector('.questionstatus');
      panel.hidden=!custom;text.disabled=!custom||!questionContext;
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
      if(!event.currentTarget.checked)return;questionSubmissionError='';const draft=draftFor(id);draft.kind='freeform';draft.optionId='';sync();
    });
    const text=form.querySelector('[data-question-text]');
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
