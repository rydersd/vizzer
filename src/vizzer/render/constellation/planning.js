let planContext=null, planDraft=null, planAnalysis=null, planError='', planRationale='';
function planSection(n){
  if(!n.id||n.foundation) return '';
  const i=nodeById.get(n.id), acceptedCourse=ownerCourseText(i), impact=ownerImpactText(i);
  const ownerLabel=ACCEPTED_PLAN.author==='owner'?'owner':(ACCEPTED_PLAN.author||'owner');
  const acceptedSummary=`${acceptedCourse?`<span class="ownercourse">${esc(ownerLabel+' '+acceptedCourse)}</span>`:''}${impact?`<div class="planimpact">${esc(impact)}</div>`:''}`;
  if(!SERVED){
    const labels=[];
    if((ACCEPTED_PLAN.promote||[]).includes(n.id)) labels.push('promoted');
    if((ACCEPTED_PLAN.defer||[]).includes(n.id)) labels.push('deferred');
    const oi=(ACCEPTED_PLAN.order||[]).indexOf(n.id); if(oi>=0) labels.push(`course #${oi+1}`);
    return `<div class="plancard"><h3>Planning · accepted r${ACCEPTED_PLAN.revision||0}</h3>${acceptedSummary}<div class="planresult">${labels.length?esc(labels.join(' · '))+'\n':''}Read-only file. Run <b>vizzer serve</b> to analyze or accept a course change.</div></div>`;
  }
  if(planError) return `<div class="plancard"><h3>Planning</h3><div class="planresult">${esc(planError)}</div></div>`;
  if(!planContext||!planDraft) return `<div class="plancard"><h3>Planning</h3><div class="planresult">Loading accepted course…</div></div>`;
  const promoted=planDraft.promote.includes(n.id), deferred=planDraft.defer.includes(n.id);
  const first=planDraft.order[0]===n.id;
  const a=planAnalysis;
  const result=!a?'':[
    `new prerequisites: ${a.delta.newPrerequisites.length?a.delta.newPrerequisites.join(', '):'none'}`,
    `ready uptake: ${a.recommendations.after.length?a.recommendations.after.join(', '):'none'}`,
    `pushed out: ${a.recommendations.displaced.length?a.recommendations.displaced.join(', '):'none'}`,
    `V1 targets deferred: ${a.opportunityCost.displacedCurrentV1Targets.length?a.opportunityCost.displacedCurrentV1Targets.join(', '):'none'}`,
    `releases affected: ${a.releaseImplications.affectedReleases.length?a.releaseImplications.affectedReleases.join(', '):'none'}`,
    ...(a.warnings||[]).map(value=>'warning: '+value),
  ].join('\n');
  return `<div class="plancard"><h3>Planning · accepted r${planContext.overlay.revision}</h3>${acceptedSummary}
    <div class="planbuttons">
      <button type="button" data-plan="promote" class="${promoted?'on':''}">promote</button>
      <button type="button" data-plan="defer" class="${deferred?'on':''}">defer</button>
      <button type="button" data-plan="first" class="${first?'on':''}">take first</button>
    </div>
    <label for="planreason">Rationale</label><textarea id="planreason" placeholder="Why change course? What evidence changed?">${esc(planRationale)}</textarea>
    <button type="button" class="planaction" data-plan="analyze">analyze tradeoffs</button>
    <button type="button" class="planaction primary" data-plan="apply" ${a?'':'disabled'}>accept course</button>
    <div class="planresult" aria-live="polite">${esc(result)}</div></div>`;
}
function bindPlanControls(n){
  if(!planContext||!planDraft) return;
  const toggle=(field)=>{
    const values=planDraft[field], index=values.indexOf(n.id);
    if(index>=0) values.splice(index,1); else values.push(n.id);
    const opposite=field==='promote'?'defer':'promote';
    const oi=planDraft[opposite].indexOf(n.id); if(oi>=0) planDraft[opposite].splice(oi,1);
    planAnalysis=null; openNode(sel);
  };
  dbody.querySelector('[data-plan="promote"]')?.addEventListener('click',()=>toggle('promote'));
  dbody.querySelector('[data-plan="defer"]')?.addEventListener('click',()=>toggle('defer'));
  dbody.querySelector('[data-plan="first"]')?.addEventListener('click',()=>{
    if(!(ACCEPTED_PLAN.baseTargets||[]).includes(n.id)&&!planDraft.promote.includes(n.id)) planDraft.promote.push(n.id);
    planDraft.defer=planDraft.defer.filter(id=>id!==n.id);
    planDraft.order=planDraft.order.filter(id=>id!==n.id); planDraft.order.unshift(n.id);
    planAnalysis=null; openNode(sel);
  });
  dbody.querySelector('#planreason')?.addEventListener('input',event=>{
    planRationale=event.currentTarget.value;
  });
  dbody.querySelector('[data-plan="analyze"]')?.addEventListener('click',async event=>{
    event.currentTarget.disabled=true;
    try{
      const response=await fetch('/api/plan/analyze',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':planContext.csrfToken},body:JSON.stringify({state:planDraft})});
      const body=await response.json(); if(!response.ok) throw new Error(body.error||'analysis failed');
      planAnalysis=body.analysis; openNode(sel);
    }catch(error){planError=error.message||String(error);openNode(sel);}
  });
  dbody.querySelector('[data-plan="apply"]')?.addEventListener('click',async event=>{
    const rationale=planRationale.trim();
    if(!rationale){dbody.querySelector('#planreason')?.focus();return;}
    event.currentTarget.disabled=true;
    try{
      const response=await fetch('/api/plan/apply',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':planContext.csrfToken},body:JSON.stringify({state:planDraft,expectedRevision:planContext.overlay.revision,rationale})});
      const body=await response.json(); if(!response.ok) throw new Error(body.error||'course apply failed');
      location.reload();
    }catch(error){planError=error.message||String(error);openNode(sel);}
  });
}
