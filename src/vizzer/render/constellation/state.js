const DATA=__DATA__;
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = (name,fill=false) => `<svg class="symbol${fill?' fill':''}" aria-hidden="true"><use href="#sym-${name}"/></svg>`;

const REPO = DATA.repo || '';
const ENGINE_VERSION=DATA.engineVersion||'';
// codex-sequence-2026-08-08: the local app opener exists only behind loopback HTTP.
const SERVED = location.protocol === 'http:';
const ACCEPTED_PLAN=DATA.planning||{};
// codex-sequence-2026-08-08: node groups are derived from configured roles in Python.
const GLAB = {shipped:'done', active:'active', ready:'ready', buggap:'regression', specced:'specced', faint:'backlog/idea', parked:'parked', foundation:'foundation'};
const css = k => getComputedStyle(document.documentElement).getPropertyValue('--'+k).trim();
let C = {}, RGB = {};
function rgbOf(col){ col=col.trim(); const m=col.match(/^#([0-9a-f]{6})\b/i);
  if (m){ const v=parseInt(m[1],16); return [v>>16&255,(v>>8)&255,v&255]; }
  const mm=col.match(/(\d+)[, ]+(\d+)[, ]+(\d+)/); return mm?[+mm[1],+mm[2],+mm[3]]:[128,128,128]; }
const mixA = (a,b,t)=> a.map((v,i)=>Math.round(v+(b[i]-v)*t));
const rgbCss = a => 'rgb('+a.join(',')+')';
function recolor(){ for (const g of ['shipped','active','ready','buggap','specced','faint','parked','foundation']){ C[g]=css(g); RGB[g]=rgbOf(C[g]); }
  C.owner=css('owner-override'); RGB.owner=rgbOf(C.owner);
  C.trails=Array.from({length:6},(_,i)=>css(`agent-trail-${i+1}`));
  RGB.fade = rgbOf(css('faint')); }
recolor();
if (typeof MutationObserver==='function')
  new MutationObserver(recolor).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
// codex-sequence-2026-08-08: Quick Look and older WebKit expose addListener,
// while current browsers expose addEventListener. Either host must boot.
const mediaQuery = query => typeof matchMedia==='function' ? matchMedia(query) : {matches:false};
const colorSchemeQuery = mediaQuery('(prefers-color-scheme: dark)');
const colorSchemeChanged = ()=>setTimeout(recolor,50);
if (typeof colorSchemeQuery.addEventListener==='function') colorSchemeQuery.addEventListener('change',colorSchemeChanged);
else if (typeof colorSchemeQuery.addListener==='function') colorSchemeQuery.addListener(colorSchemeChanged);

// ---- layout: capability clusters on a fibonacci sphere, nodes as gaussian blobs ----
// codex-sequence-2026-08-08: layout includes synthetic relation targets such as
// foundations even though product completion counts intentionally exclude them.
const caps = Object.keys(DATA.caps);
const layoutTotals = {};
DATA.nodes.forEach(n=>{ layoutTotals[n.c]=(layoutTotals[n.c]||0)+1; });
const layoutCaps = Object.keys(layoutTotals);
const R = 340;
const capPos = {};
layoutCaps.forEach((c,i)=>{
  const k = i + .5, phi = Math.acos(1 - 2*k/layoutCaps.length), th = Math.PI*(1+Math.sqrt(5))*k;
  capPos[c] = [R*Math.cos(th)*Math.sin(phi), R*Math.sin(th)*Math.sin(phi), R*Math.cos(phi)];
});
let seed = 42; const rnd = ()=> (seed = (seed*1103515245+12345) & 0x7fffffff) / 0x7fffffff;
const gauss = ()=> (rnd()+rnd()+rnd()-1.5)*1.1;
DATA.nodes.forEach(n=>{
  n.ox = gauss(); n.oy = gauss(); n.oz = gauss();
  n.g = n.g || 'specced';
});
// node size modes — 'time': where the activity accumulated; 'delivery': the
// assessed delivery band when enabled, otherwise the retained authored appetite.
// Unknown assessed size remains visibly compact instead of impersonating medium.
let sizeMode = 'time';
// Lifecycle is the base; progress has its own durable-evidence lens.
const lens = {delivery:true, activity:true, structure:true, progress:true};
const reducedMotion = mediaQuery('(prefers-reduced-motion: reduce)').matches;
function layout(){
  const mul = sizeMode==='time' ? 1.6 : 1;
  for (const n of DATA.nodes){
    const cp = capPos[n.c], spread = (26 + 13*Math.sqrt(layoutTotals[n.c]))*mul;
    n.x = cp[0]+n.ox*spread; n.y = cp[1]+n.oy*spread; n.z = cp[2]+n.oz*spread;
  }
}
layout();
{ // activity weight (time mode), same units as the delivery weight n.w
  const amax = Math.max(1, ...DATA.nodes.map(n=>n.ac+n.am));
  // steeper curve + wider range so scale differences read at a glance (~4x radius min→max)
  DATA.nodes.forEach(n=>{ n.tw = 0.6 + 2.8*Math.pow((n.ac+n.am)/amax, .75); });
}
// ---- state ----
const filt = Object.fromEntries(Object.keys(GLAB).map(g=>[g,true]));
const RELS = ['R0','R1','R2','R3','R?'];
const rfilt = Object.fromEntries(RELS.map(r=>[r,true]));
const relKey = n => RELS.includes(n.r) ? n.r : 'R?';
const ROLE_LABELS={delivery:'Delivery',coverage:'Coverage',evidence:'Evidence',decision:'Decisions',reference:'References',all:'All'};
const availableRoles=[...new Set(DATA.nodes.filter(n=>!n.foundation).map(n=>n.role||'delivery'))];
let roleFocus=availableRoles.includes('delivery')?'delivery':'all';
const configuredAreas=Array.isArray(DATA.areas)?DATA.areas.filter(area=>area&&area.id&&area.title&&area.facet&&Array.isArray(area.values)):[];
const discoveredProducts=[...new Set(DATA.nodes.flatMap(n=>(n.facets?.product||[])))].sort();
const areaDefinitions=configuredAreas.length?configuredAreas:(discoveredProducts.length?[{id:'products',title:'Products',facet:'product',values:discoveredProducts}]:[]);
const hasAreaFacets=areaDefinitions.length>0;
let areaMode=areaDefinitions[0]?.id||null;
let areaFocus=null;
let capFocus = null, groupFocus = null, sel = -1, hover = -1, questionOnly = false;
const lensButtons = {};
const lifecycleButtons = {};
const ROUTE_VIEWS=new Set(['constellation','dashboard','roadmap','structure','features','completion','workstreams','ledgers']);
const requestedView=()=>{const candidate=location.hash.replace(/^#/,'');return ROUTE_VIEWS.has(candidate)?candidate:'constellation';};
let currentView=requestedView();
// codex-sequence-2026-08-08: every whitespace-delimited query token must occur
// in the same renderer-built item index. Search dims; it never changes layout.
let searchTerms = [];
let searchMatches = DATA.nodes.map(()=>true);
const matchesSearch = n => searchTerms.length===0 || (!n.foundation &&
  searchTerms.every(token=>n.q.toLocaleLowerCase().includes(token)));
// camera centre: eases toward the centroid of whatever is visible
let cc = {x:0,y:0,z:0}, ct = {x:0,y:0,z:0};
const nodeHasOwnerQuestions = n => (n.oq||[]).length>0;
const hierarchyGroups=new Map((DATA.groups||[]).map(group=>[group.id,group]));
const nodeBelongsToGroup=(node,groupId)=>{
  let current=node.group||'',seen=new Set();
  while(current&&!seen.has(current)){
    if(current===groupId)return true;
    seen.add(current);
    current=hierarchyGroups.get(current)?.parent||'';
  }
  return false;
};
const currentArea=()=>areaDefinitions.find(area=>area.id===areaMode)||areaDefinitions[0]||null;
const nodeAreaValues=n=>{const area=currentArea();return area?(n.facets?.[area.facet]||[]):[];};
const passesAreaFilters=n=>{
  if(!hasAreaFacets)return true;
  const values=nodeAreaValues(n), area=currentArea();
  if(!values.length)return roleFocus!=='delivery';
  if(areaFocus)return values.includes(areaFocus);
  return values.some(value=>area.values.includes(value));
};
const passesSharedFilters = n => filt[n.g] && rfilt[relKey(n)]
  && (roleFocus==='all'||(n.role||'delivery')===roleFocus)
  && passesAreaFilters(n)
  && (!questionOnly || nodeHasOwnerQuestions(n));
const passesHierarchyFocus=n=>groupFocus?nodeBelongsToGroup(n,groupFocus):(!capFocus||n.c===capFocus);
function visible(n){ return passesSharedFilters(n) && passesHierarchyFocus(n); }
function retarget(){
  let sx=0, sy=0, sz=0, k=0;
  for (const n of DATA.nodes) if (visible(n)){ sx+=n.x; sy+=n.y; sz+=n.z; k++; }
  const all = k===0 || (!questionOnly && !capFocus && !hasAreaFacets && roleFocus==='all' && Object.values(filt).every(v=>v) && Object.values(rfilt).every(v=>v));
  ct = all ? {x:0,y:0,z:0} : {x:sx/k, y:sy/k, z:sz/k};
}
const nbr = DATA.nodes.map(()=>({up:[],dn:[]}));
DATA.edges.forEach(([a,b])=>{ nbr[b].up.push(a); nbr[a].dn.push(b); });
// Accepted owner course is an overlay on dependency truth. A punt propagates
// only through real hard-dependency edges; it never fabricates causal links.
const nodeById=new Map(DATA.nodes.map((n,i)=>[n.id,i]));
const ownerPromoted=new Set((ACCEPTED_PLAN.promote||[]).map(id=>nodeById.get(id)).filter(i=>i!==undefined));
const ownerDeferred=new Set((ACCEPTED_PLAN.defer||[]).map(id=>nodeById.get(id)).filter(i=>i!==undefined));
const ownerOrdered=new Map((ACCEPTED_PLAN.order||[]).map((id,rank)=>[nodeById.get(id),rank+1]).filter(([i])=>i!==undefined));
const puntedBy=DATA.nodes.map(()=>[]), puntImpactLinks=[];
for(const source of ownerDeferred){
  const seen=new Set([source]), stack=[source];
  while(stack.length){
    const parent=stack.pop();
    for(const child of nbr[parent].dn){
      puntImpactLinks.push([parent,child,source]);
      if(!puntedBy[child].includes(source))puntedBy[child].push(source);
      if(!seen.has(child)){seen.add(child);stack.push(child);}
    }
  }
}
const ownerCourse=i=>ownerDeferred.has(i)?'punted':ownerPromoted.has(i)?'promoted':ownerOrdered.has(i)?'prioritized':'';
const ownerCourseText=i=>{
  const labels=[];
  if(ownerPromoted.has(i))labels.push('promoted');
  if(ownerDeferred.has(i))labels.push('punted');
  if(ownerOrdered.has(i))labels.push(`course #${ownerOrdered.get(i)}`);
  return labels.join(' · ');
};
const ownerImpactText=i=>{
  if(ownerDeferred.has(i)){
    const affected=puntedBy.reduce((out,sources,j)=>{if(sources.includes(i))out.push(DATA.nodes[j].t);return out;},[]);
    return affected.length?`downstream effects: ${affected.length} · ${affected.join(', ')}`:'downstream effects: none in the hard-dependency graph';
  }
  if(puntedBy[i].length){
    return `affected by owner punt: ${puntedBy[i].map(source=>DATA.nodes[source].t).join(', ')}`;
  }
  return '';
};
// Typed lineage is navigable independently of prerequisite readiness.
const relNbr = DATA.nodes.map(()=>({out:[],inc:[]}));
(DATA.relations||[]).forEach(([a,b,k])=>{
  relNbr[a].out.push([b,k]); relNbr[b].inc.push([a,k]);
});
const freshWork = w => w && w.state==='active' && Date.now()<Date.parse(w.staleAt);
const activeNode = i => lens.activity && (DATA.nodes[i].aw||[]).some(wi=>freshWork(DATA.work[wi]));
// Owner questions are explicit researched records. Never infer them from a
// blocked activity row, checkpoint prose, punctuation, or a stalled timer.
// They are governance gates,
// not optional Activity-lens decoration, so their blocker state never vanishes
// when another lens is switched off.
const ownerQuestions = i =>
  (DATA.nodes[i].oq||[]).map(qi=>(DATA.questions||[])[qi]).filter(Boolean);
const questionStopsWork = i => (DATA.nodes[i].aw||[]).some(wi=>DATA.work[wi]?.state==='blocked');
// A pulse is an interrupt, not decoration: reserve it for an unresolved owner
// decision that is stopping current work or sits on the recommended next item.
const actionableQuestion = i => ownerQuestions(i).length>0
  && (questionStopsWork(i)||Boolean(DATA.nodes[i].rec));
const ownerDecisions = i =>
  (DATA.nodes[i].od||[]).map(di=>(DATA.decisions||[])[di]).filter(Boolean);
const nodeProgress = i => (DATA.nodes[i].aw||[]).reduce((p,wi)=>{
  const w=DATA.work[wi]; p.done+=w.done; p.total+=w.total; return p;
},{done:0,total:0});
// Progress and version are independent evidence. Fill opacity carries lifecycle
// progress; the outer ring carries release horizon. Both remain in the owner's
// requested 50–100% range before temporary search/selection dimming.
const LIFECYCLE_PROGRESS={idea:0,backlog:.1,specced:.28,ready:.42,building:.6,
  'in-flight':.78,'bug-gap':.72,shipped:1,verified:1,parked:.16,unknown:0};
const VERSION_OPACITY={R0:1,R1:.83,R2:.67,R3:.5,'R?':.5};
const progressOpacity = n => .5+.5*(LIFECYCLE_PROGRESS[n.st]??0);
const versionOpacity = n => VERSION_OPACITY[relKey(n)]??.5;
const ageDays = at => Math.max(0,(Date.now()-Date.parse(at))/86400000);
const progressEvents = i => lens.progress ? (DATA.nodes[i].pg||{}).events||[] : [];
const stall = i => {
  if(!lens.progress) return null;
  const candidate=(DATA.nodes[i].pg||{}).stall;
  if(!candidate) return null;
  const days=ageDays(candidate.since);
  return days>=candidate.afterDays ? {...candidate,days} : null;
};
const progressText = n => {
  const events=(n.pg||{}).events||[], blocked=(n.pg||{}).stall;
  const trail=events.map(e=>`${e.kind}: ${e.detail} · ${ageDays(e.at).toFixed(1)}d ago · ${e.source}`).join(' | ');
  const blockedDays=blocked?ageDays(blocked.since):0;
  const stuck=blocked&&blockedDays>=blocked.afterDays?`stalled ${blockedDays.toFixed(1)}d since verified/eligible evidence · ${blocked.source}`:'';
  return [trail,stuck].filter(Boolean).join(' | ');
};
