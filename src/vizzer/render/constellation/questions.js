let questionContext=null, questionError='';
const questionDrafts=new Map();
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
  const status=!SERVED?'Read-only file · run vizzer serve to answer':questionError?esc(questionError):!questionContext?'Loading answer authority…':ready?'Ready':'Not answered';
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
function bindQuestionControls(){
  const forms=[...dbody.querySelectorAll('form[data-question-id]')];
  const queue=dbody.querySelector('[data-question-queue]');
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
        :questionError?questionError:!questionContext?'Loading answer authority…':isReady?'Ready':'Not answered';
      syncQueue();
    };
    form.querySelectorAll('[data-question-option]').forEach(input=>input.addEventListener('change',()=>{
      if(!input.checked)return;const draft=draftFor(id);draft.kind='option';draft.optionId=input.value;sync();
    }));
    form.querySelector('[data-question-custom]')?.addEventListener('change',event=>{
      if(!event.currentTarget.checked)return;const draft=draftFor(id);draft.kind='freeform';draft.optionId='';sync();
    });
    const text=form.querySelector('[data-question-text]');
    text?.addEventListener('focus',()=>{
      const custom=form.querySelector('[data-question-custom]');if(custom&&!custom.checked){custom.checked=true;const draft=draftFor(id);draft.kind='freeform';draft.optionId='';sync();}
    });
    text?.addEventListener('input',event=>{const draft=draftFor(id);draft.kind='freeform';draft.optionId='';draft.text=event.currentTarget.value;sync();});
    form.addEventListener('submit',event=>event.preventDefault());
    sync();
  });
  const queueButton=queue.querySelector('button'), queueStatus=queue.querySelector('span');
  syncQueue=()=>{
    const count=forms.filter(form=>ready(draftFor(form.dataset.questionId))).length;
    queueStatus.textContent=`${count} of ${forms.length} ready`;
    queueButton.disabled=!questionContext||count!==forms.length;
  };
  syncQueue();
  queueButton.addEventListener('click',async()=>{
    if(!questionContext)return;
    const answers=forms.map(form=>{
      const id=form.dataset.questionId;
      const q=(DATA.questions||[]).find(value=>value.id===id);
      const draft=draftFor(id);
      return {questionId:id,expectedFingerprint:q.fingerprint,answer:draft.kind==='option'
        ?{kind:'option',optionId:draft.optionId}
        :{kind:'freeform',text:draft.text.trim()}};
    });
    if(answers.length!==forms.length||forms.some(form=>!ready(draftFor(form.dataset.questionId))))return;
    queue.setAttribute('aria-busy','true');queueButton.disabled=true;queueButton.textContent='Providing…';queueStatus.textContent='Recording owner decisions…';
    forms.forEach(form=>form.querySelector('fieldset').disabled=true);
    try{
      const response=await fetch('/api/questions/answers',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':questionContext.csrfToken},body:JSON.stringify({expectedRevision:questionContext.revision,answers})});
      const body=await response.json();if(!response.ok)throw new Error(body.error||'answers failed');
      reconcileAcceptedDecisions(body.decisions,body.revision);
    }catch(error){
      queue.removeAttribute('aria-busy');queueButton.textContent=forms.length===1?'Provide answer':`Provide ${forms.length} answers`;queueStatus.textContent=error.message||String(error);
      forms.forEach(form=>form.querySelector('fieldset').disabled=false);syncQueue();queueButton.focus();
    }
  });
}

function reconcileAcceptedDecisions(decisions,revision){
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
    questionDrafts.delete(q.id);
    const questionLane=DATA.assessment?.portfolio?.questions;
    if(Array.isArray(questionLane))DATA.assessment.portfolio.questions=questionLane.filter(id=>id!==node.id);
  }
  questionContext.revision=revision;
  questionContext.questions=(questionContext.questions||[]).filter(question=>
    !decisions.some(decision=>decision.question?.id===question.id));
  questionContext.decisions=[...(questionContext.decisions||[]),...(decisions||[])];
  updateViewStatus();
  if(sel>=0)openNode(sel);
}
