// ---- dossier ----
const dossier = document.getElementById('dossier'), dbody = document.getElementById('dbody'), dossierIdentity = document.getElementById('dossieridentity');
document.getElementById('close').onclick = ()=>{
  sel=-1;dossier.classList.remove('open');dossier.setAttribute('aria-hidden','true');cv.focus();
};
function openNode(i){
  if(!Number.isInteger(i)||i<0||i>=DATA.nodes.length)return;
  sel = i; const n = DATA.nodes[i];
  const dep = (list,label)=> list.length ? `<h4>${esc(label)}</h4>`+list.map(j=>{
    const m = DATA.nodes[j];
    return `<button data-j="${j}"><i style="background:${C[m.g]}"></i>${esc(m.t)}</button>`;}).join('') : '';
  const rel = (list,label,incoming=false)=> list.length ? `<h4>${esc(label)}</h4>`+list.map(([j,k])=>{
    const m=DATA.nodes[j], kind=k.replace(/_/g,' ');
    return `<button data-j="${j}"><i style="background:${C[m.g]}"></i>${esc(incoming?kind+' by: '+m.t:kind+': '+m.t)}</button>`;
  }).join('') : '';
  const agentWork = lens.activity ? (n.aw||[]).map(wi=>{
    const w=DATA.work[wi], stale=Date.now()>=Date.parse(w.staleAt);
    const progress=w.total?`${w.done}/${w.total} checkpoints`:'0/0 checkpoints (not estimated)';
    const state=[w.state,stale?'stale':''].filter(Boolean).join(' · ');
    const checkpoint=!w.checkpoint?'':' · now: '+esc(w.checkpoint);
    return `<div class="workcard ${esc(w.state)}${stale?' stale':''}"><b>${esc(w.agent)} · ${esc(state)}</b>
      ${esc(w.task)}<small>${esc(progress)}${checkpoint}<br>
      updated ${esc(w.updatedAt)} · stale after ${esc(w.staleAt)}</small></div>`;
  }).join('') : '';
  const unresolvedOwnerQuestions=ownerQuestions(i);
  const ownerQuestionCards=unresolvedOwnerQuestions.map(questionCard).join('');
  const questionBlocker=unresolvedOwnerQuestions.length
    ?`<div class="questionblocker" role="status"><strong>Blocked — answer required</strong><span>${unresolvedOwnerQuestions.length} owner decision${unresolvedOwnerQuestions.length===1?'':'s'} must be resolved before this story is dispatchable. Select an option below or suggest something else.</span></div>`:'';
  const questionQueueActions=unresolvedOwnerQuestions.length
    ?`<div class="questionqueuefooter" data-question-queue><span>0 of ${unresolvedOwnerQuestions.length} ready</span><button type="button" disabled>Provide ${unresolvedOwnerQuestions.length===1?'answer':unresolvedOwnerQuestions.length+' answers'}</button></div>`:'';
  const ownerDecisionCards=ownerDecisions(i).map(decisionCard).join('');
  const touched = n.ts ? new Date(n.ts*1000).toISOString().slice(0,10) : '—';
  const trail = lens.progress ? progressText(n) : '';
  const assessment=n.assess||null;
  const assessedRange=assessment&&assessment.range
    ?assessment.range.filter(Boolean).join('–'):'?';
  const dimensionText=assessment
    ?Object.entries(assessment.dimensions||{}).map(([name,value])=>`${name} ${value.band||'?'} (${value.provenance||'unknown'})`).join(' · '):'';
  const assessmentEvidence=assessment
    ?(assessment.evidence||[]).slice(0,4).join(' · '):'';
  const assessmentUnknowns=assessment
    ?(assessment.unknowns||[]).slice(0,4).join(' · '):'';
  const facetText=Object.entries(n.facets||{}).map(([name,values])=>`${name}: ${(values||[]).join(', ')}`).join(' · ');
  const pinnedSummary=n.summary||trail||'';
  dossierIdentity.innerHTML=`<h2>${esc(n.t)}</h2><div class="dossierpills"><span class="pill" style="background:${C[n.g]}">${esc(n.st)}</span>${n.rec?'<span class="pill" style="background:var(--accent)">'+icon('star-fill',true)+' next step</span>':''}</div>${pinnedSummary?`<p class="dossiersummary">${esc(pinnedSummary)}</p>`:''}`;
  dbody.innerHTML = `<div class="kv"><span>role</span><b>${esc(ROLE_LABELS[n.role||'delivery']||n.role||'delivery')}</b>
      <span>area</span><b>${esc((n.c||'uncategorized').replace(/-/g,' '))}</b>
      ${facetText?`<span>facets</span><b>${esc(facetText)}</b>`:''}
      ${(n.tags||[]).length?`<span>tags</span><b>${esc(n.tags.join(', '))}</b>`:''}
      <span>epic</span><b>${esc(n.e)}</b><span>release</span><b>${esc(n.r||'—')}</b>
      <span>activity</span><b>${n.ac} spec commit${n.ac===1?'':'s'} · ${n.am} doc mention${n.am===1?'':'s'}</b>
      <span>visual</span><b>${Math.round(progressOpacity(n)*100)}% fill progress · ${esc(relKey(n))} ${Math.round(versionOpacity(n)*100)}% version ring</b>
      <span>touched</span><b>${touched}</b>
      ${trail?`<span>progress</span><b>${esc(trail)}</b>`:''}
      ${!assessment?'':`<span>delivery size</span><b>${esc(assessment.band||'unassessed')} · ${esc(assessment.uncertainty||'U3')} · plausible ${esc(assessedRange)} · ${esc(assessment.provenance||'unknown')}</b>
      <span>authored appetite</span><b>${esc(assessment.rawAuthoredAppetite||'—')}</b>
      <span>burden</span><b>${esc(dimensionText||'dimensions not established')}</b>
      <span>structural impact</span><b>${assessment.targetReach||0} target(s) · ${assessment.immediateUnlock||0} immediate unlock(s) · ${assessment.frontierReach||0} frontier · ${esc(assessment.impactProvenance||'unknown')}</b>
      <span>parallel safety</span><b>${esc(assessment.parallel||'unknown')}${assessment.lane?' · '+esc(assessment.lane)+' lane':''}</b>
      ${assessmentEvidence?`<span>assessment evidence</span><b>${esc(assessmentEvidence)}</b>`:''}
      ${assessmentUnknowns?`<span>assessment unknowns</span><b>${esc(assessmentUnknowns)}</b>`:''}`}
      ${!lens.delivery||n.ps==null?'':`<span>priority</span><b>#${n.pr} · ${n.ps} · ${n.pu||0} target dependents</b>
      <span>why</span><b>${esc(n.pw||'')}</b>`}
      ${!lens.delivery||n.dr==null?'':`<span>known-reach rank</span><b>#${n.dr} · ${n.dt||0} V1 targets · ${n.dd||0} downstream · ${n.dl==='bug-against'?'linked contract':'story-only estimate'}</b>
      <span>known graph reach</span><b>${esc(n.dw||'')}</b>`}</div>
    ${questionBlocker}
    ${agentWork}
    ${ownerQuestionCards}
    ${questionQueueActions}
    ${ownerDecisionCards}
    ${planSection(n)}
    ${n.h&&!SERVED?`<a class="story" href="${esc(n.h)}">open Markdown ${icon('arrow-up-right')}</a>`:''}
    ${n.id&&SERVED?`<button class="story" type="button" data-open-item="${esc(n.id)}">read story</button>`:''}
    ${DATA.root&&n.p?`<a class="story" href="obsidian://open?path=${esc(encodeURIComponent(DATA.root+'/'+n.p))}">obsidian</a>`:''}
    ${REPO&&n.p?`<a class="story" href="${esc(REPO+n.p)}" target="_blank" rel="noopener">source ${icon('arrow-up-right')}</a>`:''}
    <div id="deps">${lens.structure?dep(nbr[i].up,'depends on')+dep(nbr[i].dn,'unblocks')+
      rel(relNbr[i].out,'lineage')+rel(relNbr[i].inc,'reverse lineage',true):''}</div>`;
  dbody.querySelectorAll('#deps button').forEach(b=> b.onclick = ()=> openNode(+b.dataset.j));
  dbody.querySelectorAll('[data-open-item]').forEach(b=> b.onclick = async ()=>{
    b.disabled = true;
    try {
      const response = await fetch('/api/open/'+encodeURIComponent(b.dataset.openItem), {method:'POST'});
      if (!response.ok) throw new Error('open failed');
      b.textContent = 'story opened';
    } catch (_) {
      b.textContent = 'could not open'; b.disabled = false;
    }
  });
  bindQuestionControls();
  bindPlanControls(n);
  dbody.scrollTop=0;
  dossier.classList.add('open');dossier.setAttribute('aria-hidden','false');
}
