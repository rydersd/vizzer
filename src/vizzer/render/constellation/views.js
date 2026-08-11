// ---- routed interactive views ----
// Every panel below reads the exact DATA object and shared filter state used by
// the constellation. Markdown is a deliberate export, never a second UI truth.
const viewPanel=document.getElementById('viewpanel');
const viewMenu=document.getElementById('viewmenu');
const exportMenu=document.getElementById('exportmenu');
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
    return `<details class="structuregroup depth-${depth}"${open}><summary><span><b>${esc(group.title)}</b><small>${esc(group.kind)} · ${rows.length} item${rows.length===1?'':'s'}${esc(progress)}</small></span></summary><div class="structurebody">${children.map(child=>branch(child,depth+1)).join('')}${own.length?`<div class="structureitems">${own.map(({index})=>viewCard(index)).join('')}</div>`:''}</div></details>`;
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
    :renderLedgers(entries);
  bindInteractiveView();
}
function switchView(view,focus=false){
  currentView=ROUTE_VIEWS.has(view)?view:'constellation';
  document.documentElement.setAttribute('data-view',currentView);
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
