// ---- dossier ----
function storySidebarSectionBody(content,missing){
  return content?`<div class="storymd">${renderStoryMarkdown(content)}</div>`
    :`<p class="storysectionmissing">${esc(missing)}</p>`;
}
function storyDeepLink(id){
  const raw=location.hash.replace(/^#/,'');
  const view=ROUTE_VIEWS.has(raw.split('?')[0])?raw.split('?')[0]:currentView;
  const query=(raw.includes('?')?raw.slice(raw.indexOf('?')+1):'').split('&')
    .filter(pair=>pair&&decodeURIComponent(pair.split('=',1)[0])!=='story');
  query.push(`story=${encodeURIComponent(id)}`);
  const base=String(location.href||location.pathname||'constellation.html').split('#',1)[0];
  return `${base}#${view}?${query.join('&')}`;
}
function storyDeepLinkMarkup(n){
  if(!n.id)return '';
  const link=storyDeepLink(n.id);
  return `<div class="deeplink"><label>Share this object<input type="text" readonly value="${esc(link)}"></label><button type="button" data-copy-story-link>Copy link</button></div>`;
}
function storyFullBodyMarkup(n){
  if(!SERVED||!n.id)return '';
  return `<section class="storyaccordion"><button type="button" data-story-accordion="full-story" aria-expanded="false">Full story</button>`
    +`<div data-story-accordion-panel="full-story" hidden>`
    +`<p class="storysectionmissing" data-story-body="${esc(n.id)}">Loading story…</p></div></section>`;
}
function storySidebarSectionsMarkup(n){
  if(n.foundation)return '';
  return `<section class="reviewsteps" data-story-section="review-steps"><h3>Review steps</h3>`
    +storySidebarSectionBody(n.rs,'No review steps written yet for this item.')+`</section>`
    +`<section class="storyaccordion acceptance"><button type="button" data-story-accordion="acceptance" aria-expanded="true">Acceptance criteria</button>`
    +`<div data-story-accordion-panel="acceptance">`
    +storySidebarSectionBody(n.acx,'No acceptance criteria written yet for this item.')+`</div></section>`
    +`<section class="storyaccordion acceptance"><button type="button" data-story-accordion="definition-of-done" aria-expanded="false">Definition of done</button>`
    +`<div data-story-accordion-panel="definition-of-done" hidden>`
    +storySidebarSectionBody(n.dod,'No definition of done written yet for this item.')+`</div></section>`
    +storyFullBodyMarkup(n);
}
function bindStorySidebar(container){
  container.querySelector('[data-copy-story-link]')?.addEventListener('click',async event=>{
    const button=event.currentTarget,input=button.parentElement?.querySelector('input');
    if(!input)return;
    try{await navigator.clipboard.writeText(input.value);button.textContent='Copied';}
    catch(_){input.select();button.textContent='Select and copy';}
  });
  container.querySelectorAll('[data-story-accordion]').forEach(button=>{
    const key=button.dataset.storyAccordion;
    const panel=container.querySelector(`[data-story-accordion-panel="${key}"]`);
    if(!panel)return;
    button.addEventListener('click',async()=>{
      const expanded=button.getAttribute('aria-expanded')!=='true';
      button.setAttribute('aria-expanded',String(expanded));panel.hidden=!expanded;
      const host=expanded&&key==='full-story'?panel.querySelector('[data-story-body]'):null;
      if(!host||host.dataset.loading==='true')return;
      host.dataset.loading='true';
      try{
        const response=await fetch('/api/story/'+encodeURIComponent(host.dataset.storyBody)+'/body');
        if(!response.ok)throw new Error('story body fetch failed');
        const rendered=document.createElement('div');
        rendered.className='storymd storyfull';rendered.innerHTML=renderStoryMarkdown(await response.text());
        host.replaceWith(rendered);
      }catch(_){host.textContent='Could not load the story body.';host.dataset.loading='false';}
    });
  });
}
const dossier = document.getElementById('dossier'), dbody = document.getElementById('dbody'), dossierFooter = document.getElementById('dossierfooter'), dossierIdentity = document.getElementById('dossieridentity'), dossierResize = document.getElementById('dossierresize');
const DOSSIER_MIN=320,DOSSIER_MAX=720,DOSSIER_CANVAS_MIN=260,DOSSIER_COMPACT=760;
const dossierStorageKey=`vizzer:dossier-width:${document.title}`;
let dossierWidth=0,preferredDossierWidth=0,dossierResizeState=null,dossierUserSized=false;
function dossierWidthBounds(){
  return{min:DOSSIER_MIN,max:Math.max(DOSSIER_MIN,Math.min(DOSSIER_MAX,innerWidth-DOSSIER_CANVAS_MIN))};
}
function defaultDossierWidth(){
  const bounds=dossierWidthBounds();return Math.max(bounds.min,Math.min(bounds.max,innerWidth*.36));
}
function applyDossierWidth(value,{persist=false,remember=true}={}){
  const bounds=dossierWidthBounds(),parsed=Number(value);
  dossierWidth=Math.round(Math.max(bounds.min,Math.min(bounds.max,Number.isFinite(parsed)?parsed:defaultDossierWidth())));
  if(remember&&innerWidth>DOSSIER_COMPACT)preferredDossierWidth=dossierWidth;
  document.documentElement.style.setProperty('--dossier-width',`${dossierWidth}px`);
  dossierResize.setAttribute('aria-valuemin',String(bounds.min));
  dossierResize.setAttribute('aria-valuemax',String(bounds.max));
  dossierResize.setAttribute('aria-valuenow',String(dossierWidth));
  if(persist){try{sessionStorage.setItem(dossierStorageKey,String(dossierWidth));}catch(_){}}
}
let storedDossierWidth=null;try{storedDossierWidth=sessionStorage.getItem(dossierStorageKey);}catch(_){}
dossierUserSized=storedDossierWidth!==null;
if(dossierUserSized&&Number.isFinite(Number(storedDossierWidth)))preferredDossierWidth=Number(storedDossierWidth);
applyDossierWidth(storedDossierWidth||defaultDossierWidth());
dossierResize.addEventListener('pointerdown',event=>{
  if(innerWidth<=DOSSIER_COMPACT)return;
  event.preventDefault();dossierResize.setPointerCapture(event.pointerId);
  dossierResizeState={pointerId:event.pointerId,startX:event.clientX,startWidth:dossier.getBoundingClientRect().width};
  dossierResize.classList.add('dragging');
});
dossierResize.addEventListener('pointermove',event=>{
  if(!dossierResizeState||event.pointerId!==dossierResizeState.pointerId)return;
  applyDossierWidth(dossierResizeState.startWidth+dossierResizeState.startX-event.clientX);
});
function finishDossierResize(event){
  if(!dossierResizeState||event.pointerId!==dossierResizeState.pointerId)return;
  if(dossierResize.hasPointerCapture(event.pointerId))dossierResize.releasePointerCapture(event.pointerId);
  dossierResizeState=null;dossierResize.classList.remove('dragging');dossierUserSized=true;applyDossierWidth(dossierWidth,{persist:true});
}
dossierResize.addEventListener('pointerup',finishDossierResize);
dossierResize.addEventListener('pointercancel',finishDossierResize);
dossierResize.addEventListener('dblclick',()=>{dossierUserSized=true;applyDossierWidth(defaultDossierWidth(),{persist:true});});
dossierResize.addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','Home'].includes(event.key)||innerWidth<=DOSSIER_COMPACT)return;
  event.preventDefault();const step=event.shiftKey?48:16;
  dossierUserSized=true;
  applyDossierWidth(event.key==='Home'?defaultDossierWidth():dossierWidth+(event.key==='ArrowLeft'?step:-step),{persist:true});
});
addEventListener('resize',()=>{
  // The compact layout is always full-width. Keep the desktop preference
  // intact so rotating a tablet or narrowing a window does not erase it.
  if(innerWidth<=DOSSIER_COMPACT)return;
  applyDossierWidth(dossierUserSized?(preferredDossierWidth||dossierWidth):defaultDossierWidth(),{remember:false});
});
function dismissDossier({focusCanvas=true}={}){
  if(typeof questionEditor!=='undefined'&&questionEditor)return false;
  sel=-1;
  dossier.classList.remove('open');
  dossier.setAttribute('aria-hidden','true');
  document.documentElement.classList.remove('dossier-open');
  if(focusCanvas)cv.focus();
}
document.getElementById('close').onclick = ()=>dismissDossier();
addEventListener('keydown',event=>{
  if(event.key==='Escape'&&dossier.classList.contains('open')){
    event.preventDefault();dismissDossier();
  }
});
function refreshDossier(){
  if(sel>=0)openNode(sel,{inPlace:true});
}
function openNode(i,{inPlace=false}={}){
  if(typeof questionEditor!=='undefined'&&questionEditor)return false;
  if(!Number.isInteger(i)||i<0||i>=DATA.nodes.length)return;
  const previousScroll=inPlace&&sel===i?dbody.scrollTop:0;
  const previousScrollExtent=inPlace&&sel===i?(dbody.scrollHeight||0):0;
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
  const storyActions=storyDiscussionActions(n,unresolvedOwnerQuestions);
  const ownerDecisionCards=ownerDecisions(i).map(decisionCard).join('');
  const touched = n.ts ? new Date(n.ts*1000).toISOString().slice(0,10) : '—';
  const trail = lens.progress ? progressText(n) : '';
  const assessment=n.assess||null;
  const assessedRange=assessment&&assessment.range
    ?assessment.range.filter(Boolean).join('–'):'?';
  const dimensionText=assessment
    ?Object.entries(assessment.dimensions||{}).map(([name,value])=>`${name} ${value.band||'?'} (${value.provenance||'unknown'})`).join(' · '):'';
  const burdenEstablished=assessment?assessment.burdenEstablished===true:false;
  const deliverySizeText=!assessment?'':burdenEstablished
    ?`${assessment.band||'unassessed'} · ${assessment.uncertainty||'U3'} · plausible ${assessedRange} · ${assessment.provenance||'unknown'}`
    :`unassessed · authored-appetite proxy ${assessment.appetiteBand||'?'} · ${assessment.uncertainty||'U3'} · plausible ${assessedRange}`;
  const assessmentEvidence=assessment
    ?(assessment.evidence||[]).slice(0,4).join(' · '):'';
  const assessmentUnknowns=assessment
    ?(assessment.unknowns||[]).slice(0,4).join(' · '):'';
  const facetText=Object.entries(n.facets||{}).map(([name,values])=>`${name}: ${(values||[]).join(', ')}`).join(' · ');
  const pinnedSummary=n.summary||trail||'';
  dossierIdentity.innerHTML=`<h2>${esc(n.t)}</h2><div class="dossierpills"><span class="pill" style="background:${C[n.g]}">${esc(n.st)}</span>${n.rec?'<span class="pill" style="background:var(--accent)">'+icon('star-fill',true)+' next step</span>':''}</div>${pinnedSummary?`<p class="dossiersummary">${esc(pinnedSummary)}</p>`:''}${workNavigationHint()}`;
  dbody.innerHTML = `<div class="kv"><span>role</span><b>${esc(ROLE_LABELS[n.role||'delivery']||n.role||'delivery')}</b>
      <span>area</span><b>${esc((n.c||'uncategorized').replace(/-/g,' '))}</b>
      ${facetText?`<span>facets</span><b>${esc(facetText)}</b>`:''}
      ${(n.tags||[]).length?`<span>tags</span><b>${esc(n.tags.join(', '))}</b>`:''}
      <span>epic</span><b>${esc(n.e)}</b><span>release</span><b>${esc(n.r||'—')}</b>
      <span>activity</span><b>${n.ac} spec commit${n.ac===1?'':'s'} · ${n.am} doc mention${n.am===1?'':'s'}</b>
      <span>visual</span><b>${Math.round(progressOpacity(n)*100)}% fill progress · ${esc(relKey(n))} ${Math.round(versionOpacity(n)*100)}% version ring</b>
      <span>touched</span><b>${touched}</b>
      ${trail?`<span>progress</span><b>${esc(trail)}</b>`:''}
      ${!assessment?'':`<span>delivery size</span><b>${esc(deliverySizeText)}</b>
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
    ${ownerDecisionCards}
    ${planSection(n)}
    ${storyDeepLinkMarkup(n)}
    ${storySidebarSectionsMarkup(n)}
    ${n.h&&!SERVED?`<a class="story" href="${esc(n.h)}">open Markdown ${icon('arrow-up-right')}</a>`:''}
    ${n.id&&SERVED?`<button class="story" type="button" data-open-item="${esc(n.id)}">read story</button>`:''}
    ${DATA.root&&n.p?`<a class="story" href="obsidian://open?path=${esc(encodeURIComponent(DATA.root+'/'+n.p))}">obsidian</a>`:''}
    ${REPO&&n.p?`<a class="story" href="${esc(REPO+n.p)}" target="_blank" rel="noopener">source ${icon('arrow-up-right')}</a>`:''}
    <div id="deps">${lens.structure?dep(nbr[i].up,'depends on')+dep(nbr[i].dn,'unblocks')+
      rel(relNbr[i].out,'lineage')+rel(relNbr[i].inc,'reverse lineage',true):''}</div>`;
  dossierFooter.innerHTML=storyActions;
  if(SERVED&&n.id?.startsWith('story:')){
    const edit=document.createElement('button');edit.type='button';edit.className='story';edit.dataset.editStory=n.id;edit.textContent='Edit story';edit.onclick=()=>openStoryEditor(n);
    dbody.prepend(edit);
  }

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
  bindQuestionControls(n);
  bindPlanControls(n);
  bindStorySidebar(dbody);
  // Reconciliation can replace long question forms with compact answer cards.
  // Preserve the old scrollable extent until an explicit close/reopen, or the
  // browser clamps the requested scrollTop to zero and makes the drawer jump.
  if(previousScrollExtent>(dbody.scrollHeight||0)){
    const spacer=document.createElement('div');
    spacer.setAttribute('data-scroll-preserver','');spacer.setAttribute('aria-hidden','true');
    spacer.style.height=(previousScrollExtent-dbody.scrollHeight)+'px';
    spacer.style.pointerEvents='none';dbody.appendChild(spacer);
  }
  dbody.scrollTop=previousScroll;
  dossier.classList.add('open');dossier.setAttribute('aria-hidden','false');
  document.documentElement.classList.add('dossier-open');
}
