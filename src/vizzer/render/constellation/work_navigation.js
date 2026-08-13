// ---- keyboard traversal over authoritative activity records ----
// DATA.work is serialized for deterministic artifacts, not presentation order.
// Derive both lanes from timestamps and deduplicate by Story before navigating.
function workNavigationIndexes(lane){
  const latestByNode=new Map();
  for(const work of DATA.work||[]){
    if(!work||!Number.isInteger(work.n)||work.n<0||work.n>=DATA.nodes.length)continue;
    if(lane==='active'&&!freshWork(work))continue;
    const stamp=Date.parse(work.updatedAt);
    if(!Number.isFinite(stamp))continue;
    const previous=latestByNode.get(work.n);
    if(previous==null||stamp>previous)latestByNode.set(work.n,stamp);
  }
  return [...latestByNode.entries()]
    .sort((a,b)=>b[1]-a[1]||DATA.nodes[a[0]].id.localeCompare(DATA.nodes[b[0]].id))
    .map(([index])=>index);
}
function workNavigationHint(){
  const active=workNavigationIndexes('active').length,recent=workNavigationIndexes('recent').length;
  const lanes=[];
  if(active)lanes.push(`<span><kbd>←</kbd><kbd>→</kbd> active ${active}</span>`);
  if(recent)lanes.push(`<span><kbd>↑</kbd><kbd>↓</kbd> recent ${recent}</span>`);
  dossier.setAttribute('aria-keyshortcuts',lanes.length?'ArrowLeft ArrowRight ArrowUp ArrowDown':'');
  return lanes.length?`<p class="dossierkeyboard" aria-label="Keyboard Story navigation">${lanes.join('')}</p>`:'';
}
function navigateWorkLane(lane,step){
  const indexes=workNavigationIndexes(lane);
  if(!indexes.length)return false;
  const position=indexes.indexOf(sel);
  const target=position<0?indexes[0]:indexes[(position+step+indexes.length)%indexes.length];
  openNode(target);
  return true;
}
function arrowKeyOwnedByControl(target){
  if(!target)return false;
  const tag=String(target.tagName||'').toUpperCase();
  const role=target.getAttribute?.('role')||'';
  return target.isContentEditable||['INPUT','TEXTAREA','SELECT'].includes(tag)||
    ['separator','slider','spinbutton','listbox','menu','menubar','tree','grid'].includes(role);
}
addEventListener('keydown',event=>{
  const route={ArrowLeft:['active',-1],ArrowRight:['active',1],ArrowUp:['recent',-1],ArrowDown:['recent',1]}[event.key];
  if(!route||event.defaultPrevented||event.isComposing||event.altKey||event.ctrlKey||
      event.metaKey||event.shiftKey||!dossier.classList.contains('open')||
      arrowKeyOwnedByControl(event.target))return;
  if(navigateWorkLane(route[0],route[1]))event.preventDefault();
});
