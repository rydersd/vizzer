// ---- top bar ----
const itemNodes = DATA.nodes.filter(n=>!n.foundation);
const deliveryNodes = itemNodes.filter(n=>(n.role||'delivery')==='delivery');
const questionStoryN = deliveryNodes.filter(nodeHasOwnerQuestions).length;
const meterFill=document.getElementById('meterfill'), meterLabel=document.getElementById('meterlab');
meterLabel.innerHTML = `<span id="shippedcount"></span> · <span id="defectcount" class="defectcount"></span> · <button type="button" id="questionfilter" class="questioncount" aria-pressed="false" aria-controls="cv"></button> · <span id="completioncount"></span>`;
const shippedCount=document.getElementById('shippedcount');
const defectCount=document.getElementById('defectcount');
const completionCount=document.getElementById('completioncount');
const questionFilter=document.getElementById('questionfilter');
const searchForm=document.getElementById('search'), searchInput=document.getElementById('searchinput');
const searchClear=document.getElementById('searchclear'), searchCount=document.getElementById('searchcount');
const viewEmpty=document.getElementById('viewempty');
const capabilityMeters=new Map();
let currentQuestionCountLabel='';
let currentQuestionButtonLabel='';
function updateVisibleCounts(){
  // Delivery health is intentionally scoped to delivery items. Catalog rows,
  // evidence ledgers, decisions, and references are useful context, not stories.
  const metricNodes=deliveryNodes.filter(n=>filt[n.g]&&rfilt[relKey(n)]&&passesAreaFilters(n)
    &&(!questionOnly||nodeHasOwnerQuestions(n))&&passesHierarchyFocus(n));
  const shipped=metricNodes.filter(n=>n.g==='shipped').length;
  const bugGaps=metricNodes.filter(n=>n.st==='bug-gap').length;
  const questionStories=metricNodes.filter(nodeHasOwnerQuestions).length;
  const questions=metricNodes.reduce((total,n)=>total+(n.oq||[]).length,0);
  const completion=100*shipped/Math.max(1,metricNodes.length);
  currentQuestionCountLabel=`${questions} open owner question${questions===1?'':'s'} across ${questionStories} stor${questionStories===1?'y':'ies'}`;
  currentQuestionButtonLabel=`${questions} answer${questions===1?'':'s'} required · ${questionStories} blocked stor${questionStories===1?'y':'ies'}`;
  meterFill.style.width=completion.toFixed(1)+'%';
  shippedCount.textContent=`${shipped}/${metricNodes.length} delivery shipped`;
  defectCount.textContent=`${bugGaps} bug gap${bugGaps===1?'':'s'} open`;
  questionFilter.textContent=currentQuestionButtonLabel;
  completionCount.textContent=completion.toFixed(0)+'%';
  questionFilter.disabled=questions===0&&!questionOnly;
  const action=questionOnly?'Remove owner-question filter':'Show only stories with explicit owner questions';
  questionFilter.title=questions===0&&!questionOnly?'No explicit owner questions in the current filters':action;
  questionFilter.setAttribute('aria-label',questions===0&&!questionOnly?questionFilter.title:`${action}. ${currentQuestionCountLabel}.`);
  for(const [cap,meter] of capabilityMeters){
    const nodes=deliveryNodes.filter(n=>meter.matches(n)&&filt[n.g]&&rfilt[relKey(n)]
      &&(!questionOnly||nodeHasOwnerQuestions(n)));
    const capShipped=nodes.filter(n=>n.g==='shipped').length;
    const capBugs=nodes.filter(n=>n.st==='bug-gap').length;
    const unfinished=foundationRemaining(nodes);
    if(unfinished||meter.foundational)meter.count.innerHTML=foundationCountMarkup(unfinished,meter.foundational)+`${capShipped}/${nodes.length}`;
    else meter.count.textContent=`${capShipped}/${nodes.length}`;
    meter.shipped.style.width=(100*capShipped/Math.max(1,nodes.length)).toFixed(1)+'%';
    meter.bugs.style.width=(100*capBugs/Math.max(1,nodes.length)).toFixed(1)+'%';
    const label=`${meter.label}, ${capShipped} of ${nodes.length} delivery items shipped, ${capBugs} bug gap${capBugs===1?'':'s'} open`;
    meter.element.setAttribute('aria-label',unfinished?`${label}, ${unfinished} unfinished foundational ${unfinished===1?'story':'stories'}`:label);
  }
}
function updateViewStatus(){
  let visibleCount=0, matchingCount=0, visibleQuestionCount=0;
  DATA.nodes.forEach((node,i)=>{
    if(node.foundation||!visible(node))return;
    visibleCount++;
    visibleQuestionCount+=(node.oq||[]).length;
    if(searchMatches[i])matchingCount++;
  });
  searchCount.textContent=searchTerms.length
    ?`${matchingCount} search result${matchingCount===1?'':'s'} within ${visibleCount} visible item${visibleCount===1?'':'s'}`
    :questionOnly
      ?`${visibleQuestionCount} owner question${visibleQuestionCount===1?'':'s'} across ${visibleCount} visible stor${visibleCount===1?'y':'ies'}`
      :`${visibleCount} items`;
  const empty=visibleCount===0;
  viewEmpty.textContent=empty
    ?(questionOnly?'No stories with owner questions match the current filters.':'No items match the current filters.')
    :'';
  viewEmpty.classList.toggle('show',empty);
  updateVisibleCounts();
  renderCurrentView();
}
function applyViewState(focusFallback=null){
  clearPointerState();
  retarget();
  updateViewStatus();
  refreshDossier();
}
function setQuestionFilter(active){
  questionOnly=Boolean(active&&questionStoryN);
  questionFilter.classList.toggle('on',questionOnly);
  questionFilter.setAttribute('aria-pressed',String(questionOnly));
  applyViewState(questionFilter);
}
questionFilter.addEventListener('click',()=>setQuestionFilter(!questionOnly));
function updateSearch(){
  searchTerms=searchInput.value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  searchMatches=DATA.nodes.map(matchesSearch);
  searchClear.disabled=searchTerms.length===0;
  updateViewStatus();
}
searchForm.addEventListener('submit',event=>event.preventDefault());
searchInput.addEventListener('input',updateSearch);
searchClear.addEventListener('click',()=>{ searchInput.value=''; updateSearch(); searchInput.focus(); });
addEventListener('keydown',event=>{
  if(event.key==='Escape'&&searchTerms.length&&
      !document.getElementById('dossier').classList.contains('open')){
    event.preventDefault(); searchInput.value=''; updateSearch(); searchInput.focus();
  }
});
updateSearch();
const chips = document.getElementById('chips');
function bindToggleOrSolo(button,key,keys,state,sync){
  let holdTimer=null,held=false,suppressClick=false;
  const clearHold=()=>{if(holdTimer!==null){clearTimeout(holdTimer);holdTimer=null;}};
  button.addEventListener('pointerdown',event=>{
    if(event.button!=null&&event.button!==0)return;
    held=false;suppressClick=false;clearHold();
    holdTimer=setTimeout(()=>{
      held=true;suppressClick=true;
      for(const candidate of keys)state[candidate]=candidate===key;
      sync();applyViewState(button);
    },700);
  });
  button.addEventListener('pointerup',clearHold);
  button.addEventListener('pointercancel',()=>{clearHold();held=false;suppressClick=false;});
  button.addEventListener('pointerleave',clearHold);
  button.addEventListener('click',event=>{
    clearHold();
    if(held||suppressClick){event.preventDefault();held=false;suppressClick=false;return;}
    state[key]=!state[key];sync();applyViewState(button);
  });
}
function syncLifecycle(){
  for(const group of Object.keys(GLAB)){
    lifecycleButtons[group].classList.toggle('on',filt[group]);
    lifecycleButtons[group].setAttribute('aria-pressed',String(filt[group]));
  }
}
for (const g of Object.keys(GLAB)){
  const b = document.createElement('button'); b.className='chip on'; b.innerHTML=`<i></i>${GLAB[g]}`;
  b.setAttribute('data-group',g);b.setAttribute('aria-pressed','true');
  b.title=`Click to toggle ${GLAB[g]}; hold to show only ${GLAB[g]}`;
  const dot = b.querySelector('i');
  if (g==='specced'){ dot.style.border = `1.5px solid var(--${g})`; }
  else if(g!=='shipped'&&g!=='buggap')dot.style.background = `var(--${g})`;
  lifecycleButtons[g]=b;
  bindToggleOrSolo(b,g,Object.keys(GLAB),filt,syncLifecycle);
  chips.appendChild(b);
}
// releases: segmented control (v0–v3 map to R0–R3, v? = unset) · click toggles ·
// press-and-hold ~1s solos that version · × resets to all
const rsep = document.createElement('span');
rsep.style.cssText = 'width:1px;align-self:stretch;background:var(--line);margin:0 4px';
chips.appendChild(rsep);
const seg = document.createElement('div'); seg.className='seg';
const segBtns = {};
function syncSeg(){ for (const r of RELS){segBtns[r].classList.toggle('on', rfilt[r]);segBtns[r].setAttribute('aria-pressed',String(rfilt[r]));} }
for (const r of RELS){
  const b = document.createElement('button'); b.className='on';
  b.textContent = r.replace('R','v');
  b.setAttribute('aria-pressed','true');
  b.title=`Click to toggle ${b.textContent}; hold to show only ${b.textContent}`;
  segBtns[r] = b; seg.appendChild(b);
  bindToggleOrSolo(b,r,RELS,rfilt,syncSeg);
}
chips.appendChild(seg);
const xb = document.createElement('button'); xb.className='clearx';
xb.innerHTML = icon('xmark'); xb.title = 'reset version filter'; xb.setAttribute('aria-label','reset version filter');
xb.onclick = ()=>{ for (const k of RELS) rfilt[k] = true; syncSeg(); applyViewState(xb); };
chips.appendChild(xb);
// Item roles keep delivery truth separate from supporting project records.
chips.appendChild(rsep.cloneNode());
const roleSeg=document.createElement('div');roleSeg.className='seg';
roleSeg.setAttribute('role','group');roleSeg.setAttribute('aria-label','Item role');
const roleButtons={};
const orderedRoles=['delivery','coverage','evidence','decision','reference'].filter(role=>availableRoles.includes(role));
for(const role of ['all',...orderedRoles]){
  const b=document.createElement('button');b.textContent=ROLE_LABELS[role]||role;
  b.className=roleFocus===role?'on':'';b.setAttribute('aria-pressed',String(roleFocus===role));
  b.onclick=()=>{roleFocus=role;
    for(const [key,button] of Object.entries(roleButtons)){
      button.classList.toggle('on',key===roleFocus);button.setAttribute('aria-pressed',String(key===roleFocus));
    }
    applyViewState(b);
  };
  roleButtons[role]=b;roleSeg.appendChild(b);
}
chips.appendChild(roleSeg);
// size-mode chips (radio): time concentration vs delivery-size evidence
chips.appendChild(rsep.cloneNode());
const sizeChips = {};
for (const m of ['time','delivery']){
  const b = document.createElement('button'); b.className = 'chip'+(sizeMode===m?' on':'');
  b.textContent = 'size: '+m;
  b.onclick = ()=>{ if (sizeMode===m) return; sizeMode = m;
    for (const k in sizeChips) sizeChips[k].classList.toggle('on', k===sizeMode);
    layout(); retarget(); };
  sizeChips[m] = b; chips.appendChild(b);
}
// Switchable lenses. Risk/history/judgment remain future data contracts, not placebo UI.
chips.appendChild(rsep.cloneNode());
const lensSeg = document.createElement('div'); lensSeg.className='seg';
lensSeg.setAttribute('role','group'); lensSeg.setAttribute('aria-label','Graph lenses');
for (const [key,label] of [['delivery','Delivery'],['activity','Activity'],['structure','Structure'],['progress','Progress']]){
  const b=document.createElement('button'); b.className='on'; b.textContent=label;
  b.setAttribute('aria-pressed','true'); b.setAttribute('aria-label',label+' lens');
  b.onclick=()=>{ lens[key]=!lens[key]; b.classList.toggle('on',lens[key]);
    b.setAttribute('aria-pressed',String(lens[key]));
    refreshDossier(); };
  lensButtons[key]=b;
  lensSeg.appendChild(b);
}
chips.appendChild(lensSeg);
// ---- rail ----
const rail = document.getElementById('rail');
// Rail elements by hierarchy id, so selecting a story on the canvas can open
// and mark where it lives (capability > nested groups > story leaf).
const railCapabilityDetails=new Map(),railGroupDetails=new Map(),railGroupRows=new Map(),railStoryButtons=new Map();
const structuralKindLabel=kind=>({capability:'capability',subcapability:'sub-capability',tool:'tool',utility:'utility',assistance:'assistance'}[kind]||kind||'');
const structuralTitle=group=>group.title.replace(/^(?:Subcapability|Tool|Utility|Assistance)\s*·\s*/i,'');
const railStorageScope=`${String(DATA.projectId||DATA.title||'project')}|${String(location.pathname||'')}`;
const railDisclosureKey=`vizzer.rail.expanded.${encodeURIComponent(railStorageScope)}`;
let savedRailDisclosure={};
if(DATA.projectIdConfigured){try{savedRailDisclosure=JSON.parse(sessionStorage.getItem(railDisclosureKey)||'{}');if(!savedRailDisclosure||typeof savedRailDisclosure!=='object'||Array.isArray(savedRailDisclosure))savedRailDisclosure={};}catch(_){savedRailDisclosure={};}}
function railDisclosureOpen(id,fallback=false){return Object.prototype.hasOwnProperty.call(savedRailDisclosure,id)?Boolean(savedRailDisclosure[id]):fallback;}
function saveRailDisclosure(id,open){savedRailDisclosure[id]=Boolean(open);if(DATA.projectIdConfigured){try{sessionStorage.setItem(railDisclosureKey,JSON.stringify(savedRailDisclosure));}catch(_){}}}
const capTail=id=>id.includes(':')?id.slice(id.indexOf(':')+1):id;
function foundationalGroup(group,nodes=[]){
  const seen=new Set();let current=group;
  while(current&&!seen.has(current.id)){
    seen.add(current.id);
    if(current.kind==='foundation'||current.foundational===true)return true;
    current=(DATA.groups||[]).find(parent=>parent.id===current.parent);
  }
  return nodes.some(node=>nodeFoundationTier(node)!==null);
}
const foundationChip=()=>'<span class="foundationchip" title="Foundational work" aria-label="Foundational">F</span>';
const groupsById=new Map((DATA.groups||[]).map(group=>[group.id,group]));
function nodeFoundationTier(node){
  if(node.foundational===true||(node.tags||[]).some(tag=>/^(foundation|foundational)$/i.test(tag)))return 'tagged';
  let groupId=node.group||'',seen=new Set();
  while(groupId&&!seen.has(groupId)){
    seen.add(groupId);const group=groupsById.get(groupId);if(!group)break;
    if(group.foundationTier!=null)return group.foundationTier;
    if(group.kind==='foundation'||group.foundational===true)return 'foundation';
    groupId=group.parent||'';
  }
  return null;
}
function foundationRemaining(nodes=[]){
  return new Set(nodes.filter(node=>!node.foundation&&(node.role||'delivery')==='delivery'&&node.g!=='shipped'&&nodeFoundationTier(node)!==null).map(node=>node.id)).size;
}
const foundationCountMarkup=(count,show=false)=>show||count?`<span class="foundationcount" title="${count} unfinished foundational ${count===1?'story':'stories'}">${count} F</span>`:'';
function groupProgressDetails(nodes=[]){
  const ids=new Set(nodes.map(node=>node.id));
  const prerequisites=new Set();
  for(const [from,to] of DATA.edges||[]){
    const dependency=DATA.nodes[from],dependent=DATA.nodes[to];
    if(dependent&&ids.has(dependent.id)&&dependency&&dependency.g!=='shipped')prerequisites.add(dependent.id);
  }
  const work=nodes.flatMap(node=>(node.aw||[]).map(index=>DATA.work[index]).filter(Boolean));
  const blockedTasks=work.filter(entry=>entry.state==='blocked').length;
  const checkpointDone=work.reduce((sum,entry)=>sum+(Number.isFinite(entry.done)?entry.done:0),0);
  const checkpointTotal=work.reduce((sum,entry)=>sum+(Number.isFinite(entry.total)?entry.total:0),0);
  return {declaredBlockers:nodes.filter(node=>Boolean(node.blockers)).length,
    blockedTasks,unmetPrerequisites:prerequisites.size,
    workStories:nodes.filter(node=>(node.aw||[]).length>0).length,
    checkpointDone,checkpointTotal,prerequisites};
}
function meterMarkup(label,total,shipped,bugs,kind='',foundational=false,nodes=[]){
  const remaining=foundationRemaining(nodes);
  const detail=groupProgressDetails(nodes),signals=[];
  if(detail.declaredBlockers)signals.push(`${detail.declaredBlockers} declared blocker${detail.declaredBlockers===1?'':'s'}`);
  if(detail.blockedTasks)signals.push(`${detail.blockedTasks} blocked task${detail.blockedTasks===1?'':'s'}`);
  if(detail.unmetPrerequisites)signals.push(`${detail.unmetPrerequisites} unmet prerequisite${detail.unmetPrerequisites===1?'':'s'}`);
  if(detail.workStories)signals.push(`${detail.workStories} stories with agent work`);
  if(detail.checkpointTotal)signals.push(`${detail.checkpointDone}/${detail.checkpointTotal} checkpoints`);
  return `<span class="caphead"><span class="caplabel">${kind?`<small>${esc(structuralKindLabel(kind))}</small>`:''}<span>${esc(label)}${foundational?foundationChip():''}</span></span><span class="capcount">${foundationCountMarkup(remaining,foundational)}${shipped}/${total} delivery shipped</span>${signals.length?`<span class="capactivity">${signals.map(esc).join(' · ')}</span>`:''}</span>
    <span class="capbar"><i style="width:${100*shipped/Math.max(1,total)}%"></i><b style="width:${100*bugs/Math.max(1,total)}%"></b></span>`;
}
function registerMeter(key,element,label,matches,foundational=false){
  capabilityMeters.set(key,{element,label,matches,foundational,count:element.querySelector('.capcount'),shipped:element.querySelector('.capbar i'),bugs:element.querySelector('.capbar b')});
}
function meterButton(key,label,matches,total,shipped,bugs,onSelect,container=rail,kind=''){
  const d=document.createElement('button');d.type='button';d.className='cap';d.setAttribute('aria-pressed','false');
  const group=(DATA.groups||[]).find(group=>group.id===key);
  const nodes=deliveryNodes.filter(matches);
  d.innerHTML=meterMarkup(label,total,shipped,bugs,kind,foundationalGroup(group,nodes),nodes);
  registerMeter(key,d,label,matches,foundationalGroup(group,nodes));
  d.onclick=()=>onSelect(d);container.appendChild(d);
  return d;
}
function syncRailSelection(active){
  rail.querySelectorAll('.cap').forEach(button=>{
    const selected=button===active&&Boolean(capFocus||groupFocus);
    button.classList.toggle('on',selected);
    button.setAttribute('aria-pressed',String(selected));
  });
}
function selectHierarchy(button,capability,groupId=null){
  if(typeof questionEditor!=='undefined'&&questionEditor)return false;
  const alreadySelected=capFocus===capability&&groupFocus===groupId;
  capFocus=alreadySelected?null:capability;
  groupFocus=alreadySelected?null:groupId;
  syncRailSelection(button);
  applyViewState(button);
  const area=planningAreaFor(capability,groupId);
  if(area)openPlanningArea(area.id);
  else if(groupId&&typeof openHierarchyDetails==='function')openHierarchyDetails(groupId);
}
function syncFocusExitControl(){
  let button=document.getElementById('focusexit');
  if(!button){
    button=document.createElement('button');button.type='button';button.id='focusexit';button.className='flycap';
    button.addEventListener('click',()=>exitClusterFocus());document.body.appendChild(button);
  }
  button.textContent=clusterFocus?`Exit ${capabilityTitle(clusterFocus)} focus (Esc)`:'';
  button.classList.toggle('show',Boolean(clusterFocus));button.setAttribute('aria-hidden',String(!clusterFocus));
}
addEventListener('keydown',event=>{
  if(event.key!=='Escape'||event.defaultPrevented||document.getElementById('dossier').classList.contains('open'))return;
  if(exitClusterFocus()){event.preventDefault();syncFocusExitControl();}
});
function renderCapabilityAccordions(){
  const heading=document.createElement('h2');heading.className='railhead';heading.textContent=(DATA.groups||[]).some(group=>!group.parent&&group.kind==='platform')?'Platforms':'Capabilities';rail.appendChild(heading);
  const groups=DATA.groups||[];
  const roots=new Map(groups.filter(group=>!group.parent).map(group=>[capTail(group.id),group]));
  const orderedCaps=[...caps].sort((a,b)=>DATA.caps[b].total-DATA.caps[a].total||a.localeCompare(b));
  orderedCaps.forEach((capability,index)=>{
    const root=roots.get(capability),summaryMatches=node=>node.c===capability;
    const summaryNodes=deliveryNodes.filter(summaryMatches);
    const summaryShipped=summaryNodes.filter(node=>node.g==='shipped').length;
    const summaryBugs=summaryNodes.filter(node=>node.st==='bug-gap').length;
    const details=document.createElement('details');details.className='railcapability';
    details.open=capFocus===capability||railDisclosureOpen(`root:${root?.id||capability}`,!capFocus&&index===0);
    details.setAttribute('data-rail-id',`root:${root?.id||capability}`);
    railCapabilityDetails.set(capability,details);
    const summary=document.createElement('summary');summary.innerHTML=meterMarkup(root?.title||capability.replace(/-/g,' ')||'Project',summaryNodes.length,summaryShipped,summaryBugs,'',foundationalGroup(root,summaryNodes),summaryNodes);
    summary.addEventListener('click',event=>{
      if(typeof questionEditor!=='undefined'&&questionEditor){event.preventDefault();return;}
      const area=planningAreaFor(capability);
      if(area)openPlanningArea(area.id);
      else{enterClusterFocus(capability);if(root)openHierarchyDetails(root.id);}
    });
    details.appendChild(summary);
    registerMeter(`capability:${capability}`,summary,root?.title||capability||'Project',summaryMatches,foundationalGroup(root,summaryNodes));
    details.addEventListener('toggle',()=>saveRailDisclosure(details.getAttribute('data-rail-id'),details.open));
    const children=document.createElement('div');children.className='railcapabilitybody';
    const appendStoryLeaf=(container,node)=>{
      const story=document.createElement('button');story.type='button';story.className='railstory';story.setAttribute('data-story-id',node.id);story.textContent=node.t;story.title=node.t;story.setAttribute('aria-label',`Open story: ${node.t}`);
      story.onclick=()=>{const nodeIndex=nodeById.get(node.id);if(nodeIndex!==undefined)openNode(nodeIndex);};container.appendChild(story);
      railStoryButtons.set(node.id,story);
    };
    meterButton(`all:${capability}`,'All work',summaryMatches,summaryNodes.length,summaryShipped,summaryBugs,
      button=>selectHierarchy(button,capability),children,'capability');
    const kindOrder={platform:0,capability:1,epic:2,tool:3,subcapability:4,utility:5,assistance:6};
    const childrenByParent=new Map();
    for(const group of groups){const siblings=childrenByParent.get(group.parent)||[];siblings.push(group);childrenByParent.set(group.parent,siblings);}
    const renderGroup=(group,container,depth)=>{
      const matches=node=>nodeBelongsToGroup(node,group.id),nodes=deliveryNodes.filter(matches);
      if(!nodes.length)return;
      const childGroups=(childrenByParent.get(group.id)||[]).sort((a,b)=>(kindOrder[a.kind]??9)-(kindOrder[b.kind]??9)||structuralTitle(a).localeCompare(structuralTitle(b)));
      const direct=deliveryNodes.filter(node=>node.group===group.id);
      const hasChildren=childGroups.length>0||direct.length>0;
      if(!hasChildren){
        const shipped=nodes.filter(node=>node.g==='shipped').length,bugs=nodes.filter(node=>node.st==='bug-gap').length;
        const button=meterButton(group.id,structuralTitle(group),matches,nodes.length,shipped,bugs,
          selected=>selectHierarchy(selected,capability,group.id),container,group.kind);
        button.classList.add('railgroup-leaf');railGroupRows.set(group.id,button);
        if(groupFocus===group.id){button.classList.add('on');button.setAttribute('aria-pressed','true');}
        return;
      }
      const detailsGroup=document.createElement('details');detailsGroup.className='railgroup';detailsGroup.setAttribute('data-rail-id',`group:${group.id}`);
      detailsGroup.open=groupFocus===group.id||railDisclosureOpen(detailsGroup.getAttribute('data-rail-id'),false);
      const summaryGroup=document.createElement('summary');summaryGroup.innerHTML=meterMarkup(structuralTitle(group),nodes.length,nodes.filter(node=>node.g==='shipped').length,nodes.filter(node=>node.st==='bug-gap').length,group.kind,foundationalGroup(group,nodes),nodes);
      registerMeter(`group-summary:${group.id}`,summaryGroup,structuralTitle(group),matches,foundationalGroup(group,nodes));
      summaryGroup.addEventListener('click',event=>{if(typeof questionEditor!=='undefined'&&questionEditor)event.preventDefault();else{enterClusterFocus(capability);openHierarchyDetails(group.id);}});
      detailsGroup.appendChild(summaryGroup);
      railGroupDetails.set(group.id,detailsGroup);railGroupRows.set(group.id,summaryGroup);
      const body=document.createElement('div');body.className='railgroupbody';body.setAttribute('data-depth',String(depth));
      detailsGroup.addEventListener('toggle',()=>saveRailDisclosure(detailsGroup.getAttribute('data-rail-id'),detailsGroup.open));
      const selected=meterButton(`all:${group.id}`,`All ${structuralKindLabel(group.kind)||'work'}`,matches,nodes.length,nodes.filter(node=>node.g==='shipped').length,nodes.filter(node=>node.st==='bug-gap').length,
        button=>selectHierarchy(button,capability,group.id),body,group.kind);
      detailsGroup.appendChild(body);
      if(groupFocus===group.id){selected.classList.add('on');selected.setAttribute('aria-pressed','true');}
      for(const child of childGroups)renderGroup(child,body,depth+1);
      for(const node of direct)appendStoryLeaf(body,node);
      container.appendChild(detailsGroup);
    };
    for(const node of deliveryNodes.filter(node=>node.group===root?.id||(node.c===capability&&!node.group)))appendStoryLeaf(children,node);
    (childrenByParent.get(root?.id)||[]).sort((a,b)=>(kindOrder[a.kind]??9)-(kindOrder[b.kind]??9)||structuralTitle(a).localeCompare(structuralTitle(b))).forEach(group=>renderGroup(group,children,1));
    details.appendChild(children);rail.appendChild(details);
  });
}
// Where a story lives: its capability, the root group and the chain of nested
// groups between the root and the story.
function nodeHierarchyPath(node){
  const chain=[],seen=new Set();let current=node?.group||'';
  while(current&&!seen.has(current)){
    seen.add(current);const group=hierarchyGroups.get(current);
    if(!group)break;chain.unshift(group);current=group.parent||'';
  }
  const capability=node?.c||'';
  const root=chain.find(group=>!group.parent)||(DATA.groups||[]).find(group=>!group.parent&&capTail(group.id)===capability)||null;
  return {capability,root,groups:chain.filter(group=>group!==root)};
}
function clearRailContext(){
  railGroupRows.forEach(row=>{row.classList.remove('context');row.removeAttribute('aria-current');});
  railStoryButtons.forEach(button=>{button.classList.remove('context');button.removeAttribute('aria-current');});
  railCapabilityDetails.forEach(details=>details.classList.remove('context'));
}
// Selecting a story opens its capability and every ancestor group, marks the
// deepest listed group as the location and the story leaf as current, and
// scrolls the leaf into view. Other open disclosures are left as they are.
function revealNodeInRail(node,{scroll=true}={}){
  clearRailContext();
  if(!node)return null;
  const path=nodeHierarchyPath(node);
  const details=railCapabilityDetails.get(path.capability);
  if(!details)return null;
  details.open=true;details.classList.add('context');
  for(const group of path.groups){const nested=railGroupDetails.get(group.id);if(nested)nested.open=true;}
  const deepest=[...path.groups].reverse().find(group=>railGroupRows.has(group.id))||null;
  const row=deepest?railGroupRows.get(deepest.id):null;
  if(row){row.classList.add('context');row.setAttribute('aria-current','location');}
  const leaf=railStoryButtons.get(node.id)||null;
  if(leaf){leaf.classList.add('context');leaf.setAttribute('aria-current','true');}
  const target=leaf||row||details.querySelector('summary');
  if(scroll&&target&&typeof target.scrollIntoView==='function')
    target.scrollIntoView({block:'nearest',behavior:reducedMotion?'auto':'smooth'});
  return {capability:path.capability,groupId:deepest?deepest.id:null,storyId:leaf?node.id:null};
}
function renderRail(){
  if(SERVED)setTimeout(()=>renderPlanningAreaLinks(),0);
  rail.replaceChildren();capabilityMeters.clear();
  railCapabilityDetails.clear();railGroupDetails.clear();railGroupRows.clear();railStoryButtons.clear();
  if(hasAreaFacets){
    const heading=document.createElement('h2');heading.className='railhead';heading.textContent='Areas';rail.appendChild(heading);
    const modes=document.createElement('div');modes.className='seg railseg';modes.setAttribute('role','group');modes.setAttribute('aria-label','Area type');
    for(const area of areaDefinitions){
      const b=document.createElement('button');b.textContent=area.title;b.className=areaMode===area.id?'on':'';
      b.setAttribute('aria-pressed',String(areaMode===area.id));
      b.onclick=()=>{if(areaMode===area.id)return;areaMode=area.id;areaFocus=null;renderRail();applyViewState(b);};
      modes.appendChild(b);
    }
    rail.appendChild(modes);
    const values=currentArea()?.values||[];
    for(const value of values){
      const matches=n=>nodeAreaValues(n).includes(value);
      const nodes=deliveryNodes.filter(matches), shipped=nodes.filter(n=>n.g==='shipped').length, bugs=nodes.filter(n=>n.st==='bug-gap').length;
      const label=value.charAt(0).toUpperCase()+value.slice(1);
      meterButton(value,label,matches,nodes.length,shipped,bugs,d=>{
        areaFocus=areaFocus===value?null:value;
        rail.querySelectorAll('.cap').forEach(x=>{x.classList.toggle('on',x===d&&Boolean(areaFocus));x.setAttribute('aria-pressed',String(x===d&&Boolean(areaFocus)));});
        applyViewState(d);
      });
    }
    return;
  }
  renderCapabilityAccordions();
  if(sel>=0)revealNodeInRail(DATA.nodes[sel],{scroll:false});
}
renderRail();
updateViewStatus();
switchView(currentView);
