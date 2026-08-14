// ---- routed interactive views ----
// Every panel below reads the exact DATA object and shared filter state used by
// the constellation. Markdown is a deliberate export, never a second UI truth.
const viewPanel=document.getElementById('viewpanel');
const viewMenu=document.getElementById('viewmenu');
const exportMenu=document.getElementById('exportmenu');
const viewBackdrop=document.getElementById('bgcv');
const viewCanvas=document.getElementById('cv');
const viewEntries=()=>DATA.nodes.map((node,index)=>({node,index})).filter(({node,index})=>
  !node.foundation&&visible(node)&&searchMatches[index]);
const viewMeta=n=>[ROLE_LABELS[n.role||'delivery']||n.role,n.st,n.r||'unversioned',n.assess?.band?`size ${n.assess.band}/${n.assess.uncertainty}`:'size unassessed'].join(' · ');
function viewCard(index,detail=''){
  const n=DATA.nodes[index], blocked=(n.oq||[]).length>0;
  return `<button type="button" class="viewcard${blocked?' blocked':''}" data-view-node="${index}"><b>${esc(n.t)}</b><small>${blocked?'<span class="viewflag">answer required · </span>':''}${esc(detail||viewMeta(n))}</small></button>`;
}
const emptyPanel=message=>`<div class="viewemptycopy">${esc(message)}</div>`;
const panelHead=(title,copy)=>`<header class="viewhead"><div><h1>${esc(title)}</h1><p>${esc(copy)}</p></div></header>`;
function renderDashboard(entries){
  const available=new Set(entries.map(({node})=>node.id));
  const portfolio=DATA.assessment?.portfolio||{};
  const lanes=[
    ['small','High structural-leverage small candidates'],
    ['anchors','Larger anchors'],
    ['defects','Defects by known blast radius'],
    ['questions','Owner decisions'],
    ['occupied','Freshly owned work'],
    ['blocked','Unresolved blockers'],
  ];
  const sections=lanes.map(([key,label])=>{
    const indexes=(Array.isArray(portfolio[key])?portfolio[key]:[])
      .filter(id=>available.has(id)).map(id=>nodeById.get(id)).filter(index=>index!==undefined);
    if(!indexes.length)return '';
    return `<section class="viewsection"><h2>${esc(label)} <span>${indexes.length}</span></h2><div class="viewgrid">${indexes.map(index=>viewCard(index)).join('')}</div></section>`;
  }).join('');
  const fallback=entries.filter(({node})=>(node.role||'delivery')==='delivery'&&node.rec).map(({index})=>viewCard(index)).join('');
  return panelHead('Dashboard','Impact-ranked delivery candidates, blockers, defects, and active ownership under the current filters.')+
    (sections||fallback&&`<section class="viewsection"><h2>Recommended</h2><div class="viewgrid">${fallback}</div></section>`||emptyPanel('No dashboard candidates match the current filters.'));
}
function renderRoadmap(entries){
  const columns=RELS.map(release=>{
    const rows=entries.filter(({node})=>relKey(node)===release)
      .sort((a,b)=>(a.node.pr??999999)-(b.node.pr??999999)||a.node.t.localeCompare(b.node.t));
    return `<section class="viewcolumn"><h2>${esc(release.replace('R','v'))} · ${rows.length}</h2>${rows.length?rows.map(({index})=>viewCard(index)).join(''):emptyPanel('No matching items')}</section>`;
  }).join('');
  return panelHead('Roadmap','Release lanes remain dependency-aware; every item opens the same dossier used by the constellation.')+`<div class="viewcolumns">${columns}</div>`;
}
const structureGroups=new Map((DATA.groups||[]).map(group=>[group.id,group]));
const structureChildren=new Map();
for(const group of structureGroups.values()){
  const parent=group.parent||'';
  if(!structureChildren.has(parent))structureChildren.set(parent,[]);
  structureChildren.get(parent).push(group);
}
for(const children of structureChildren.values())children.sort((a,b)=>a.title.localeCompare(b.title));
function renderStructure(entries){
  const direct=new Map(),includedGroups=new Set();
  for(const entry of entries){
    const group=structureGroups.has(entry.node.group)?entry.node.group:'';
    if(!direct.has(group))direct.set(group,[]);
    direct.get(group).push(entry);
    let current=group,seen=new Set();
    while(current&&structureGroups.has(current)&&!seen.has(current)){
      includedGroups.add(current);seen.add(current);
      current=structureGroups.get(current).parent||'';
    }
  }
  // Product foundations are structural contracts even when no current Story
  // relation points at them. Omitting an unreferenced invariant makes the
  // hierarchy look healthier precisely when its wiring is incomplete.
  for(const group of structureGroups.values())if(group.kind==='foundation'){
    let current=group.id,seen=new Set();
    while(current&&structureGroups.has(current)&&!seen.has(current)){
      includedGroups.add(current);seen.add(current);
      current=structureGroups.get(current).parent||'';
    }
  }
  const descendants=new Map();
  const entriesUnder=id=>{
    if(descendants.has(id))return descendants.get(id);
    const result=[...(direct.get(id)||[])];
    for(const child of structureChildren.get(id)||[]){
      if(includedGroups.has(child.id))result.push(...entriesUnder(child.id));
    }
    descendants.set(id,result);return result;
  };
  const branch=(group,depth)=>{
    const rows=entriesUnder(group.id),delivery=rows.filter(({node})=>(node.role||'delivery')==='delivery');
    const shipped=delivery.filter(({node})=>node.g==='shipped').length;
    const own=(direct.get(group.id)||[]).sort((a,b)=>a.node.t.localeCompare(b.node.t));
    const children=(structureChildren.get(group.id)||[]).filter(child=>includedGroups.has(child.id));
    const open=depth<2||searchTerms.length?' open':'';
    const progress=delivery.length?` · ${shipped}/${delivery.length} delivery shipped`:'';
    const contract=group.p
      ?`<div class="structurecontract">${group.summary?`<p>${esc(group.summary)}</p>`:''}${group.h&&!SERVED?`<a href="${esc(group.h)}">read contract ${icon('arrow-up-right')}</a>`:`<button type="button" data-open-group="${esc(group.id)}">read contract</button>`}</div>`:'';
    return `<details class="structuregroup depth-${depth}"${open}><summary><span><b>${esc(group.title)}</b><small>${esc(group.kind)} · ${rows.length} item${rows.length===1?'':'s'}${esc(progress)}</small></span></summary><div class="structurebody">${contract}${children.map(child=>branch(child,depth+1)).join('')}${own.length?`<div class="structureitems">${own.map(({index})=>viewCard(index)).join('')}</div>`:''}</div></details>`;
  };
  const roots=[...includedGroups].map(id=>structureGroups.get(id)).filter(group=>
    group&&(!group.parent||!includedGroups.has(group.parent))).sort((a,b)=>a.title.localeCompare(b.title));
  const ungrouped=(direct.get('')||[]).sort((a,b)=>a.node.t.localeCompare(b.node.t));
  const body=roots.map(group=>branch(group,0)).join('')+
    (ungrouped.length?`<section class="viewsection"><h2>Ungrouped <span>${ungrouped.length}</span></h2><div class="viewgrid">${ungrouped.map(({index})=>viewCard(index)).join('')}</div></section>`:'');
  return panelHead('Project hierarchy','The source-owned hierarchy under the current area, role, lifecycle, release, and search filters. Facets describe cross-project membership; this tree shows where work is structurally owned.')+(body||emptyPanel('No structured items match the current filters.'));
}
function renderFeatures(entries){
  const grouped=new Map();
  for(const entry of entries){
    const keys=entry.node.facets?.capability?.length?entry.node.facets.capability:[entry.node.c||'uncategorized'];
    for(const key of keys){if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(entry);}
  }
  const sections=[...grouped.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([capability,rows])=>
    `<section class="viewsection"><h2>${esc(capability.replace(/-/g,' '))} <span>${rows.length}</span></h2><div class="viewgrid">${rows.sort((a,b)=>a.node.t.localeCompare(b.node.t)).map(({index})=>viewCard(index)).join('')}</div></section>`).join('');
  return panelHead('Features','A searchable capability index over the same visible item slice. Cross-capability items appear in every capability they serve.')+(sections||emptyPanel('No features match the current filters.'));
}
function renderCompletion(entries){
  const grouped=new Map();
  for(const entry of entries){const role=entry.node.role||'delivery';if(!grouped.has(role))grouped.set(role,[]);grouped.get(role).push(entry);}
  const sections=[...grouped.entries()].map(([role,roleEntries])=>{
    const total=roleEntries.length;
    const metrics=Object.entries(GLAB).map(([group,label])=>{
      const count=roleEntries.filter(({node})=>node.g===group).length;
      return `<button type="button" class="metric" data-view-group="${esc(group)}"><strong>${count}</strong><span>${esc(label)} · ${total?Math.round(100*count/total):0}%</span></button>`;
    }).join('');
    const questionCount=roleEntries.reduce((sum,{node})=>sum+(node.oq||[]).length,0);
    return `<section class="viewsection"><h2>${esc(ROLE_LABELS[role]||role)} <span>${total}</span></h2><div class="metricgrid">${metrics}${role==='delivery'?`<button type="button" class="metric" data-question-metric><strong>${questionCount}</strong><span>answers required</span></button>`:''}</div></section>`;
  }).join('');
  return panelHead('Completion','Lifecycle and regression debt are computed within each item role, so supporting records cannot inflate or dilute delivery completion.')+
    (sections||emptyPanel('No completion records match the current filters.'));
}
function renderWorkstreams(entries){
  const payload=DATA.workstreams||{}, streams=Array.isArray(payload.workstreams)?payload.workstreams:[];
  const sessions=Array.isArray(payload.sessions)?payload.sessions:[], discussions=Array.isArray(payload.discussions)?payload.discussions:[];
  const collisions=Array.isArray(payload.collisions)?payload.collisions:[];
  const visibleIds=new Set(entries.map(({node})=>node.id));
  const rows=streams.filter(stream=>!stream.storyIds.length||stream.storyIds.some(id=>visibleIds.has(id)));
  const sourceSummary=(DATA.sourceAreas||[]).map(area=>`${area.title} · ${area.role}`).join(' | ');
  const collisionCopy=collisions.length?`<section class="workstreamalerts"><h2>Coordination warnings <span>${collisions.length}</span></h2>${collisions.map(collision=>
    `<div class="workstreamalert"><b>${esc(collision.kind.replace(/-/g,' '))}</b><span>${esc(collision.workstreams.join(' ↔ '))}</span><small>${esc(collision.values.join(', '))}</small></div>`).join('')}</section>`:'';
  const cards=rows.map(stream=>{
    const streamSessions=sessions.filter(session=>session.workstreamId===stream.id);
    const streamDiscussions=discussions.filter(entry=>entry.workstreamId===stream.id);
    const stories=stream.storyIds.map(id=>nodeById.get(id)).filter(index=>index!==undefined&&visibleIds.has(DATA.nodes[index].id));
    const live=streamSessions.filter(session=>session.state==='active'&&Date.now()<Date.parse(session.leaseExpiresAt));
    const sessionRows=streamSessions.length?streamSessions.map(session=>{
      const fresh=session.state==='active'&&Date.now()<Date.parse(session.leaseExpiresAt);
      return `<li class="worksession ${fresh?'fresh':'stale'}"><b>${esc(session.actor)}</b><span>${esc(session.model)} · ${esc(session.role)} · ${fresh?'live':'stale/stopped'}</span><small>${esc(session.branch)} · lease ${esc(session.leaseExpiresAt)}</small></li>`;
    }).join(''):'<li class="worksession stale"><span>No registered session</span></li>';
    const discussionRows=streamDiscussions.length?streamDiscussions.slice(-8).map(entry=>
      `<li class="workdiscussion ${esc(entry.kind)}"><b>${esc(entry.author)} · ${esc(entry.kind)} · ${esc(entry.scope)}</b><span>${esc(entry.body)}</span>${entry.ownerQuestionId?`<small>owner question: ${esc(entry.ownerQuestionId)}</small>`:''}</li>`).join(''):'<li class="workdiscussion"><span>No peer discussion recorded</span></li>';
    return `<article class="workstreamcard" data-workstream="${esc(stream.id)}"><header><div><span class="workstatus">${esc(stream.status)}</span><h2>${esc(stream.title)}</h2><p>${esc(stream.objective)}</p></div><strong>${stream.total?`${stream.completed}/${stream.total}`:'unestimated'}</strong></header><div class="workprogress"><i style="width:${stream.total?Math.round(100*stream.completed/stream.total):0}%"></i></div><dl><div><dt>Lead</dt><dd>${esc(stream.lead)}</dd></div><div><dt>Reviewer</dt><dd>${esc(stream.reviewer)}</dd></div><div><dt>Checkpoint</dt><dd>${esc(stream.checkpoint)}</dd></div><div><dt>Live sessions</dt><dd>${live.length}</dd></div></dl><div class="workstories">${stories.map(index=>viewCard(index)).join('')}</div><details><summary>Sessions · ${streamSessions.length}</summary><ul>${sessionRows}</ul></details><details><summary>Peer discussion · ${streamDiscussions.length}</summary><ul>${discussionRows}</ul></details><details><summary>Scopes and sequencing</summary><p><b>Depends on:</b> ${esc(stream.dependsOn.join(', ')||'none')}</p><p><b>Allowed paths:</b> ${esc(stream.allowedPaths.join(', ')||'none')}</p><p><b>Shared paths:</b> ${esc(stream.sharedPaths.join(', ')||'none')}</p></details></article>`;
  }).join('');
  const meta=`Revision ${payload.revision??0} · runtime ${payload.runtimeRevision??0}${sourceSummary?` · sources: ${sourceSummary}`:''}`;
  return panelHead('Workstreams','Concurrent ownership, leased sessions, path scopes, peer discussion, escalation, and integration warnings. Chat memory is not coordination state.')+`<p class="viewsubmeta">${esc(meta)}</p>${collisionCopy}${cards?`<div class="workstreamgrid">${cards}</div>`:emptyPanel('No configured workstream intersects the current filters.')}`;
}
function renderLedgers(entries){
  const available=new Set(entries.map(({index})=>index));
  const rows=(DATA.work||[]).map((work,index)=>({work,index})).filter(({work})=>available.has(work.n))
    .sort((a,b)=>String(b.work.updatedAt).localeCompare(String(a.work.updatedAt)));
  if(!rows.length)return panelHead('Ledgers','Active ownership and checkpoint state under the current filters.')+emptyPanel('No ledger records match the current filters.');
  const body=rows.map(({work})=>`<tr><td><button type="button" data-view-node="${work.n}">${esc(DATA.nodes[work.n].t)}</button></td><td>${esc(work.agent)}</td><td>${esc(work.state)}</td><td>${work.total?`${work.done}/${work.total}`:'unestimated'}</td><td>${esc(work.checkpoint||'—')}</td><td>${esc(work.updatedAt)}</td></tr>`).join('');
  return panelHead('Ledgers','Sortable-by-source ownership, progress, blockers, and staleness; story rows open the shared dossier.')+`<table class="viewtable"><thead><tr><th>Story</th><th>Owner</th><th>State</th><th>Progress</th><th>Checkpoint</th><th>Updated</th></tr></thead><tbody>${body}</tbody></table>`;
}
function bindInteractiveView(){
  viewPanel.querySelectorAll('[data-view-node]').forEach(button=>button.addEventListener('click',()=>{
    const index=Number(button.dataset.viewNode);
    if(Number.isInteger(index)&&index>=0&&index<DATA.nodes.length)openNode(index);
  }));
  viewPanel.querySelectorAll('[data-view-group]').forEach(button=>button.addEventListener('click',()=>{
    const selected=button.dataset.viewGroup;
    for(const group of Object.keys(filt)){filt[group]=group===selected;lifecycleButtons[group]?.classList.toggle('on',filt[group]);}
    applyViewState(button);
  }));
  viewPanel.querySelector('[data-question-metric]')?.addEventListener('click',()=>setQuestionFilter(true));
  viewPanel.querySelectorAll('[data-open-group]').forEach(button=>button.addEventListener('click',async()=>{
    button.disabled=true;
    try{
      const response=await fetch('/api/open/'+encodeURIComponent(button.dataset.openGroup),{method:'POST'});
      if(!response.ok)throw new Error('open failed');
      button.textContent='contract opened';
    }catch(_){button.textContent='could not open';button.disabled=false;}
  }));
}
function renderCurrentView(){
  if(currentView==='constellation'){viewPanel.hidden=true;return;}
  const entries=viewEntries();
  viewPanel.hidden=false;
  viewPanel.innerHTML=currentView==='dashboard'?renderDashboard(entries)
    :currentView==='roadmap'?renderRoadmap(entries)
    :currentView==='structure'?renderStructure(entries)
    :currentView==='features'?renderFeatures(entries)
    :currentView==='completion'?renderCompletion(entries)
    :currentView==='workstreams'?renderWorkstreams(entries)
    :renderLedgers(entries);
  bindInteractiveView();
}
function switchView(view,focus=false){
  currentView=ROUTE_VIEWS.has(view)?view:'constellation';
  document.documentElement.setAttribute('data-view',currentView);
  viewBackdrop.hidden=currentView!=='constellation';
  viewCanvas.hidden=currentView!=='constellation';
  document.getElementById('hint').hidden=currentView!=='constellation';
  viewMenu.querySelectorAll('[data-view]').forEach(link=>{
    const active=link.dataset.view===currentView;
    if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
  });
  viewMenu.open=false;exportMenu.open=false;
  renderCurrentView();
  if(focus)(currentView==='constellation'?viewCanvas:viewPanel).focus();
}
addEventListener('hashchange',()=>switchView(requestedView(),true));
