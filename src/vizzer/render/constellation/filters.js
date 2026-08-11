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
    &&(!questionOnly||nodeHasOwnerQuestions(n))&&(!capFocus||n.c===capFocus));
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
    meter.count.textContent=`${capShipped}/${nodes.length}`;
    meter.shipped.style.width=(100*capShipped/Math.max(1,nodes.length)).toFixed(1)+'%';
    meter.bugs.style.width=(100*capBugs/Math.max(1,nodes.length)).toFixed(1)+'%';
    meter.element.setAttribute('aria-label',`${meter.label}, ${capShipped} of ${nodes.length} delivery items shipped, ${capBugs} bug gap${capBugs===1?'':'s'} open`);
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
  if (g==='specced'){ dot.style.border = '1.5px solid '+C[g]; }
  else if(g!=='shipped'&&g!=='buggap')dot.style.background = C[g];
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
function meterButton(key,label,matches,total,shipped,bugs,onSelect){
  const d=document.createElement('button');d.type='button';d.className='cap';d.setAttribute('aria-pressed','false');
  d.innerHTML=`<span class="caphead">${esc(label)}<span>${shipped}/${total}</span></span>
    <span class="capbar"><i style="width:${100*shipped/Math.max(1,total)}%"></i><b style="width:${100*bugs/Math.max(1,total)}%"></b></span>`;
  capabilityMeters.set(key,{element:d,label,matches,count:d.querySelector('.caphead>span'),shipped:d.querySelector('.capbar i'),bugs:d.querySelector('.capbar b')});
  d.onclick=()=>onSelect(d);rail.appendChild(d);
}
function renderRail(){
  rail.replaceChildren();capabilityMeters.clear();
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
  caps.sort((a,b)=>DATA.caps[b].total-DATA.caps[a].total).forEach(c=>{
    const v=DATA.caps[c], matches=n=>n.c===c;
    const bg=deliveryNodes.filter(n=>matches(n)&&n.st==='bug-gap').length;
    meterButton(c,c.replace(/-/g,' '),matches,v.total,v.shipped,bg,d=>{
      capFocus=capFocus===c?null:c;
      rail.querySelectorAll('.cap').forEach(x=>{x.classList.toggle('on',x===d&&Boolean(capFocus));x.setAttribute('aria-pressed',String(x===d&&Boolean(capFocus)));});
      applyViewState(d);
    });
  });
}
renderRail();
updateViewStatus();
switchView(currentView);
