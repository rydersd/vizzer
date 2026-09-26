const DATA=__DATA__;
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = (name,fill=false) => `<svg class="symbol${fill?' fill':''}" aria-hidden="true"><use href="#sym-${name}"/></svg>`;

const REPO = DATA.repo || '';
const RENDER_ID=DATA.renderId||'';
// codex-sequence-2026-08-08: the local app opener exists only behind loopback HTTP.
const SERVED = location.protocol === 'http:';
const ACCEPTED_PLAN=DATA.planning||{};
// codex-sequence-2026-08-08: node groups are derived from configured roles in Python.
const GLAB = {shipped:'done', active:'active', ready:'ready', buggap:'regression', specced:'specced', faint:'backlog/idea', parked:'parked', foundation:'foundation'};
const css = k => getComputedStyle(document.documentElement).getPropertyValue('--'+k).trim();
let C = {}, RGB = {};
const contrastColors=new Map();
function rgbOf(col){ col=col.trim(); const m=col.match(/^#([0-9a-f]{6})\b/i);
  if (m){ const v=parseInt(m[1],16); return [v>>16&255,(v>>8)&255,v&255]; }
  const mm=col.match(/(\d+)[, ]+(\d+)[, ]+(\d+)/); return mm?[+mm[1],+mm[2],+mm[3]]:[128,128,128]; }
const mixA = (a,b,t)=> a.map((v,i)=>Math.round(v+(b[i]-v)*t));
const rgbCss = a => 'rgb('+a.join(',')+')';
function recolor(){ contrastColors.clear(); for (const g of ['shipped','active','ready','buggap','specced','faint','parked','foundation']){ C[g]=css(g); RGB[g]=rgbOf(C[g]); }
  C.owner=css('owner-override'); RGB.owner=rgbOf(C.owner);
  C.trails=Array.from({length:6},(_,i)=>css(`agent-trail-${i+1}`));
  RGB.fade = rgbOf(css('faint'));
  RGB.ink=rgbOf(css('ink'));
  RGB.sky=['sky-top','sky-mid','sky-bottom'].map(key=>rgbOf(css(key))); }
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

// ---- layout: capability clusters on a fibonacci sphere, then epics within them ----
// codex-sequence-2026-08-08: layout includes synthetic relation targets such as
// foundations even though product completion counts intentionally exclude them.
const caps = Object.keys(DATA.caps);
const layoutTotals = {};
DATA.nodes.forEach(n=>{ layoutTotals[n.c]=(layoutTotals[n.c]||0)+1; });
const layoutCaps = Object.keys(layoutTotals);
const CAP_SPHERE_MIN_R = 340;
let R = CAP_SPHERE_MIN_R;
const capDir = {};                 // capability -> unit direction on the sphere
const capPos = {};                 // capability -> anchor, capDir scaled by R
layoutCaps.forEach((c,i)=>{
  const k = i + .5, phi = Math.acos(1 - 2*k/layoutCaps.length), th = Math.PI*(1+Math.sqrt(5))*k;
  capDir[c] = [Math.cos(th)*Math.sin(phi), Math.sin(th)*Math.sin(phi), Math.cos(phi)];
});
function placeCapabilities(radius){
  R=radius;
  for (const c of layoutCaps) capPos[c]=capDir[c].map(v=>v*radius);
}
placeCapabilities(R);
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
const epicKey = n => n.c+'/'+(n.e||'');
const layoutEpics = {};            // capability -> ordered epic names (non-empty only)
const layoutEpicTotals = {};       // epicKey -> story count
for (const n of DATA.nodes){
  if(!n.e) continue;
  const key=epicKey(n);
  if(!layoutEpicTotals[key]){ layoutEpicTotals[key]=0; (layoutEpics[n.c]=layoutEpics[n.c]||[]).push(n.e); }
  layoutEpicTotals[key]++;
}
for (const c in layoutEpics) layoutEpics[c].sort();
const fibonacciPoint = (i,count,radius) => {
  const k=i+.5, phi=Math.acos(1-2*k/count), th=Math.PI*(1+Math.sqrt(5))*k;
  return [radius*Math.cos(th)*Math.sin(phi), radius*Math.sin(th)*Math.sin(phi), radius*Math.cos(phi)];
};
const epicAnchor = {};             // epicKey -> [x,y,z], rebuilt by layout()
const epicRadius = {};             // capability -> radius of its epic sphere, sized by layout()
const capExtent = {};              // capability -> MEDIAN member distance from its anchor (a robust radius: a few dependency-pulled or epic-less outliers must not dictate the cluster-focus frame)
const capReach = {};               // capability -> epic radius + 2 sigma story spread: the room it claims on the capability sphere
// World-space node radius: nodeRadius() is p.s*weight where p.s ~ 4.6 at the
// viewport centre, so 4.6*weight approximates the drawn size in layout units.
const layoutRadius = n => 4.6*(sizeMode==='time' ? (n.tw||1) : (n.w||1));
// Edge pull is applied to each node's MEAN vector toward its cross-epic
// dependency neighbours (not summed per edge), so a well-connected story is
// pulled no harder than a single link would. Links that cross a capability
// count at a tenth of the weight: they nudge related work closer without
// dragging a small epic out of its own capability. The mean is taken over the
// LINK COUNT, so a story whose only link crosses a capability moves a tenth
// as far as one linked inside it (iteration 2: dividing by the summed weight
// let the weight cancel, and single-link stories were dragged 200+ units
// into the next capability; at a quarter weight a one-story epic still moved
// ~50 units, more than the epic spacing it was meant to keep).
const RELAX_ITERATIONS=40, EDGE_PULL=.06, EPIC_PULL=.10, REPEL_GAP=2.2, CROSS_CAP_WEIGHT=.1;
// Epic anchors must sit EPIC_GAP mean-spreads apart (owner 2026-09-16 iteration
// 2: Drawing's eleven epics overlapped on a radius that scaled only with story
// count). The test holds the measured separation to 1.5x the measured spread.
const EPIC_GAP=2.2;
// Cheapest packing an epic of k stories can reach under the within-epic
// repulsion: half the minimum gap times the cube root of the count. It is the
// floor for an epic's spread estimate, and the ceiling is a multiple of it, so
// an epic stretched by dependency pulls cannot claim room it does not fill.
const packingRadius = (list,mul) => Math.max(10*mul,
  REPEL_GAP*list.reduce((sum,i)=>sum+layoutRadius(DATA.nodes[i]),0)/list.length/2*Math.cbrt(list.length));
// Two epics joined by a dependency drift toward each other under the
// magnetism: the edge pull and the epic pull settle where a linked story has
// closed EDGE_PULL/(EDGE_PULL+EPIC_PULL) of the gap, so linked anchors get
// that much more room to keep the measured separation.
const LINKED_EPIC_ROOM=1/(1-EDGE_PULL/(EDGE_PULL+EPIC_PULL));
const linkedEpicPairs=new Set();
for (const [a,b] of DATA.edges){
  const na=DATA.nodes[a], nb=DATA.nodes[b];
  if(na.c!==nb.c||!na.e||!nb.e||na.e===nb.e) continue;
  linkedEpicPairs.add(epicKey(na)+'|'+epicKey(nb)); linkedEpicPairs.add(epicKey(nb)+'|'+epicKey(na));
}
// Slot each capability's epics on its fibonacci sphere largest-first, each
// into the free slot that maximises the smallest (chord / spread pair) ratio
// to the epics already placed, then take the smallest radius at which every
// pair is EPIC_GAP mean-spreads apart. Deterministic: ties break on name.
function sizeEpicSphere(c,spread,sigma){
  const epics=(layoutEpics[c]||[]).slice().sort((a,b)=>spread[c+'/'+b]-spread[c+'/'+a]||a.localeCompare(b));
  const count=epics.length, slotOf=new Map(), used=new Set();
  if(count<2){ epics.forEach((e,i)=>slotOf.set(e,i)); return {radius:0,slotOf}; }
  const unit=epics.map((_,i)=>fibonacciPoint(i,count,1));
  const chord=(p,q)=>Math.hypot(p[0]-q[0],p[1]-q[1],p[2]-q[2]);
  for (const e of epics){
    let best=-1,bestScore=-1;
    for (let slot=0; slot<count; slot++){ if(used.has(slot)) continue;
      let score=Infinity;
      for (const [other,otherSlot] of slotOf){ const ratio=chord(unit[slot],unit[otherSlot])/(spread[c+'/'+e]+spread[c+'/'+other]); if(ratio<score) score=ratio; }
      if(score>bestScore){ bestScore=score; best=slot; }
    }
    slotOf.set(e,best); used.add(best);
  }
  let radius=0;
  for (let a=0; a<count; a++) for (let b=a+1; b<count; b++){
    const linked=linkedEpicPairs.has(c+'/'+epics[a]+'|'+c+'/'+epics[b]);
    // A pair of tiny epics still gets the capability's typical spread of
    // room, so breathing space inside one capability reads as uniform.
    const need=EPIC_GAP*Math.max(sigma,(spread[c+'/'+epics[a]]+spread[c+'/'+epics[b]])/2)*(linked?LINKED_EPIC_ROOM:1);
    radius=Math.max(radius, need/chord(unit[slotOf.get(epics[a])],unit[slotOf.get(epics[b])]));
  }
  return {radius,slotOf};
}
function layout(){
  const mul = sizeMode==='time' ? 1.6 : 1;
  const members={};
  DATA.nodes.forEach((n,i)=>{ (members[epicKey(n)]=members[epicKey(n)]||[]).push(i); });
  // Pass 1: provisional anchors from story counts; the relaxation then shows
  // how much room each epic really takes (repulsion + dependency pulls).
  const packing={};
  for (const key in members) packing[key]=packingRadius(members[key],mul);
  const provisional={};
  for (const c of layoutCaps){
    const radius=(18+9*Math.sqrt(layoutTotals[c]))*mul, epics=layoutEpics[c]||[];
    provisional[c]={radius,slotOf:new Map(epics.map((e,i)=>[e,i]))};
  }
  placeCapabilities(CAP_SPHERE_MIN_R);
  placeEpicAnchors(provisional);
  scatterAndRelax(members,mul);
  // Measured spread: the median member distance from the epic centroid,
  // floored at the packing radius and capped at three times it plus a node.
  const spread={};
  for (const key in members){
    const list=members[key];
    let cx=0,cy=0,cz=0;
    for (const i of list){ cx+=DATA.nodes[i].x; cy+=DATA.nodes[i].y; cz+=DATA.nodes[i].z; }
    cx/=list.length; cy/=list.length; cz/=list.length;
    const radial=list.map(i=>Math.hypot(DATA.nodes[i].x-cx,DATA.nodes[i].y-cy,DATA.nodes[i].z-cz)).sort((a,b)=>a-b);
    const median=radial[radial.length>>1];
    spread[key]=Math.min(Math.max(packing[key],median),3*packing[key]+10*mul);
  }
  // Pass 2: epic spheres sized so their epics stay apart, capability sphere
  // sized so no two capabilities' reaches overlap, then the final relaxation.
  const sized={};
  for (const c of layoutCaps){
    let weighted=0,count=0;
    for (const key in members){ if(key.startsWith(c+'/')){ weighted+=spread[key]*members[key].length; count+=members[key].length; } }
    const sigma=count?weighted/count:0;   // story-weighted mean spread of the capability
    sized[c]=sizeEpicSphere(c,spread,sigma);
    epicRadius[c]=sized[c].radius;
    capReach[c]=Math.max(epicRadius[c]+2*sigma, 2*(spread[c+'/']||0));
  }
  let sphere=CAP_SPHERE_MIN_R;
  for (let a=0; a<layoutCaps.length; a++) for (let b=a+1; b<layoutCaps.length; b++){
    const da=capDir[layoutCaps[a]], db=capDir[layoutCaps[b]];
    const chord=Math.hypot(da[0]-db[0],da[1]-db[1],da[2]-db[2]);
    if(chord>1e-9) sphere=Math.max(sphere,(capReach[layoutCaps[a]]+capReach[layoutCaps[b]])/chord);
  }
  placeCapabilities(sphere);
  placeEpicAnchors(sized);
  scatterAndRelax(members,mul);
  // Cluster-focus radius per capability: the median member distance. The max
  // was tried first and let one or two flung stories (epic-less scatter, a
  // cross-capability pull) push six small capabilities to the 1.25 zoom floor.
  const distances={};
  for (const c of layoutCaps) distances[c]=[];
  for (const n of DATA.nodes){ const cp=capPos[n.c];
    distances[n.c].push(Math.hypot(n.x-cp[0],n.y-cp[1],n.z-cp[2])); }
  for (const c of layoutCaps){
    const sorted=distances[c].sort((a,b)=>a-b);
    capExtent[c]=sorted.length?sorted[sorted.length>>1]:0;
  }
}
// 1. epic anchors on a sphere around the capability anchor
function placeEpicAnchors(sized){
  for (const c of layoutCaps){
    const epics=layoutEpics[c]||[], {radius,slotOf}=sized[c];
    for (const e of epics){
      const q=fibonacciPoint(slotOf.get(e),epics.length,radius), cp=capPos[c];
      epicAnchor[c+'/'+e]=[cp[0]+q[0],cp[1]+q[1],cp[2]+q[2]];
    }
  }
}
function scatterAndRelax(members,mul){
  // 2. stories gaussian around their epic anchor; epic-less nodes around the capability
  const home = new Array(DATA.nodes.length);
  DATA.nodes.forEach((n,i)=>{
    const key=epicKey(n), anchor=n.e?epicAnchor[key]:capPos[n.c];
    const spread=n.e ? (8+6*Math.sqrt(layoutEpicTotals[key]))*mul
                     : (26+13*Math.sqrt(layoutTotals[n.c]))*mul;
    home[i]=anchor;
    n.x=anchor[0]+n.ox*spread; n.y=anchor[1]+n.oy*spread; n.z=anchor[2]+n.oz*spread;
  });
  // 3. deterministic relaxation (no randomness: same input, same coordinates).
  // Positions are staged in typed arrays: DATA.nodes carry differing shapes,
  // so per-pair property access on them is dictionary-slow (measured ~280 ns
  // per pair, 100+ ms for the graph); flat arrays bring the whole pass under
  // the 50 ms budget.
  const count=DATA.nodes.length, xs=new Float64Array(count), ys=new Float64Array(count), zs=new Float64Array(count);
  const hx=new Float64Array(count), hy=new Float64Array(count), hz=new Float64Array(count);
  DATA.nodes.forEach((n,i)=>{ xs[i]=n.x; ys[i]=n.y; zs[i]=n.z; hx[i]=home[i][0]; hy[i]=home[i][1]; hz[i]=home[i][2]; });
  const crossEpicEdges=DATA.edges.filter(([a,b])=>epicKey(DATA.nodes[a])!==epicKey(DATA.nodes[b]))
    .map(([a,b])=>[a,b,DATA.nodes[a].c===DATA.nodes[b].c?1:CROSS_CAP_WEIGHT]);
  const px=new Float64Array(count), py=new Float64Array(count), pz=new Float64Array(count), pc=new Int32Array(count);
  const sqrt=Math.sqrt, cos=Math.cos, sin=Math.sin, PI=Math.PI;
  // Per-node radii for the repulsion: the gap a pair must keep is REPEL_GAP
  // times the MEAN of that pair's radii (iteration 3: one gap per epic, from
  // the epic's mean radius, left every pair of larger-than-mean glyphs
  // overlapping — 628 of the 629 overlapping pairs were within an epic).
  const rs=new Float64Array(count);
  DATA.nodes.forEach((n,i)=>{ rs[i]=layoutRadius(n); });
  const groups=Object.values(members).map(list=>Int32Array.from(list));
  for (let iter=0; iter<RELAX_ITERATIONS; iter++){
    // 3a. magnetism: each node moves 6% along its mean weighted vector to cross-epic neighbours
    px.fill(0); py.fill(0); pz.fill(0); pc.fill(0);
    for (const [a,b,w] of crossEpicEdges){
      const dx=(xs[b]-xs[a])*w, dy=(ys[b]-ys[a])*w, dz=(zs[b]-zs[a])*w;
      px[a]+=dx; py[a]+=dy; pz[a]+=dz; pc[a]++; px[b]-=dx; py[b]-=dy; pz[b]-=dz; pc[b]++;
    }
    for (let i=0; i<count; i++){ if(!pc[i]) continue;
      const f=EDGE_PULL/pc[i]; xs[i]+=px[i]*f; ys[i]+=py[i]*f; zs[i]+=pz[i]*f; }
    // 3b. every story eases 10% back toward its epic (or capability) anchor
    for (let i=0; i<count; i++){
      // Without named epics, preserve the generic capability scatter rather
      // than contracting the entire project into one tiny pseudo-epic.
      if(!DATA.nodes[i].e)continue;
      xs[i]+=(hx[i]-xs[i])*EPIC_PULL; ys[i]+=(hy[i]-ys[i])*EPIC_PULL; zs[i]+=(hz[i]-zs[i])*EPIC_PULL; }
    // 3c. within-epic repulsion: separate any pair closer than 2.2x the pair's mean radius
    // (sqrt/cos/sin are bound locally: the hot loop must not resolve globals per pair)
    for (const list of groups){
      for (let p=0; p<list.length; p++){ const a=list[p], ra=rs[a];
        for (let q=p+1; q<list.length; q++){ const b=list[q];
          const minGap=REPEL_GAP*(ra+rs[b])/2;
          let dx=xs[b]-xs[a], dy=ys[b]-ys[a], dz=zs[b]-zs[a], d=sqrt(dx*dx+dy*dy+dz*dz);
          if(d>=minGap) continue;
          if(d<1e-6){ // coincident: push apart along a fixed, index-derived direction
            const th=(a*7+b*13)%360*PI/180; dx=cos(th); dy=sin(th); dz=.3; d=sqrt(dx*dx+dy*dy+dz*dz); }
          const push=(minGap-d)/2/d;
          xs[a]-=dx*push; ys[a]-=dy*push; zs[a]-=dz*push; xs[b]+=dx*push; ys[b]+=dy*push; zs[b]+=dz*push;
        }
      }
    }
  }
  DATA.nodes.forEach((n,i)=>{ n.x=xs[i]; n.y=ys[i]; n.z=zs[i]; });
}
// Activity weights feed layoutRadius, so they are computed before the first layout.
recomputeActivityWeights();
layout();
function recomputeActivityWeights(){
  // Activity weight (time mode), same units as the delivery weight n.w.
  const amax = Math.max(1, ...DATA.nodes.map(n=>n.ac+n.am));
  // steeper curve + wider range so scale differences read at a glance (~4x radius min→max)
  DATA.nodes.forEach(n=>{ n.tw = 0.6 + 2.8*Math.pow((n.ac+n.am)/amax, .75); });
}
// ---- state ----
const filt = Object.fromEntries(Object.keys(GLAB).map(g=>[g,true]));
const RELS = ['R0','R1','R2','R3','R?'];
const rfilt = Object.fromEntries(RELS.map(r=>[r,true]));
const relKey = n => RELS.includes(n.r) ? n.r : 'R?';
const drawsHollowCircle = n => n.g!=='buggap' && n.g!=='shipped';
const versionChannelName = n => drawsHollowCircle(n)?'circle stroke width':'ring';
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
// The owner question the Previous | N of M | Next control counts from
// (question_navigation.js). Declared here because openNode reads it, and a let
// in a later fragment is in its dead zone until that fragment runs.
let questionNavFocusId = '';
let clusterFocus = null, clusterFocusReturnZoom = null;
const lensButtons = {};
const lifecycleButtons = {};
const ROUTE_VIEWS=new Set(['constellation','dashboard','velocity','roadmap','structure','features','completion','workstreams','reviews','ledgers']);
const requestedView=()=>{
  const candidate=location.hash.replace(/^#/,'').split('?')[0];
  return ROUTE_VIEWS.has(candidate)?candidate:'constellation';
};
const requestedViewParams=()=>{
  const raw=location.hash.replace(/^#/,'');
  const query=raw.includes('?')?raw.slice(raw.indexOf('?')+1):'';
  const values={};
  for(const pair of query.split('&')){
    if(!pair)continue;
    const [key,value='']=pair.split('=',2);
    try{values[decodeURIComponent(key)]=decodeURIComponent(value.replace(/\+/g,' '));}
    catch(_){/* malformed route values do not abort page boot */}
  }
  return {get:key=>values[key]||null};
};
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
const clusterTier=capability=>clusterFocus===null||capability===clusterFocus?1:.18;
const focusBackground=index=>clusterFocus!==null&&DATA.nodes[index]?.c!==clusterFocus;
function clusterCentroid(capability){
  const nodes=DATA.nodes.filter(node=>node.c===capability);
  if(!nodes.length)return null;
  return nodes.reduce((sum,node)=>({x:sum.x+node.x/nodes.length,y:sum.y+node.y/nodes.length,z:sum.z+node.z/nodes.length}),{x:0,y:0,z:0});
}
function enterClusterFocus(capability){
  const centroid=clusterCentroid(capability);if(!centroid)return false;
  if(clusterFocus===null)clusterFocusReturnZoom=zoom;
  clusterFocus=capability;ct=centroid;
  zoom=Math.min(3.4,Math.max(1.25,190/Math.max(48,capExtent[capability]||48)));
  if(reducedMotion)cc={...ct};
  if(typeof clearPointerState==='function')clearPointerState();
  if(typeof syncFocusExitControl==='function')syncFocusExitControl();return true;
}
function exitClusterFocus(){
  if(clusterFocus===null)return false;
  clusterFocus=null;
  if(clusterFocusReturnZoom!==null){zoom=clusterFocusReturnZoom;clusterFocusReturnZoom=null;}
  retarget();if(reducedMotion)cc={...ct};
  if(typeof clearPointerState==='function')clearPointerState();
  if(typeof syncFocusExitControl==='function')syncFocusExitControl();return true;
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

// Optional tag identity colors; lifecycle remains explicit in the dossier.
function nodeColor(n){
  for(const tag of n.tags||[]){const color=(DATA.tagColors||{})[tag];if(typeof color==='string'&&/^#[0-9a-f]{6}$/i.test(color))return [1,3,5].map(i=>parseInt(color.slice(i,i+2),16));}
  return RGB[n.g];
}

// Contrast is checked against every gradient stop, including the magenta edge.
// Cache by semantic color/state so orbiting does not recalculate the palette.
function relativeLuminance(rgb){return rgb.reduce((sum,c,i)=>{
  c/=255;return sum+[.2126,.7152,.0722][i]*(c<=.04045?c/12.92:((c+.055)/1.055)**2.4);
},0);}
function contrastRatio(a,b){const x=relativeLuminance(a),y=relativeLuminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
function contrastNodeColor(rgb,target=4.5){
  const key=rgb.join(',')+':'+target;if(contrastColors.has(key))return contrastColors.get(key);
  const enough=color=>RGB.sky.every(bg=>contrastRatio(color,bg)>=target);
  let result=rgb;
  if(!enough(result)){
    const end=relativeLuminance(RGB.ink)>.5?[255,255,255]:[0,0,0];
    for(let step=1;step<=100;step++){result=mixA(rgb,end,step/100);if(enough(result))break;}
  }
  contrastColors.set(key,result);return result;
}
const canvasVisible=n=>passesSharedFilters(n);
const outsideCluster=n=>Boolean(capFocus||groupFocus)&&!passesHierarchyFocus(n);
