// ---- 3d render ----
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
let W,H,DPR; function size(){ DPR=Math.min(devicePixelRatio,2); W=innerWidth; H=innerHeight;
  cv.width=W*DPR; cv.height=H*DPR; ctx.setTransform(DPR,0,0,DPR,0,0);} size(); addEventListener('resize',size);
let rx=-.35, ry=.6, zoom=1, panX=0, panY=0, vx=0, vy=0;
const P = DATA.nodes.map(()=>({x:0,y:0,s:0,d:0,on:true,near:0}));
const nodeRadius = i => P[i].s*(sizeMode==='time' ? DATA.nodes[i].tw : (DATA.nodes[i].w||1));
// Canvas nodes are intentionally tiny, but their pointer target must not be.
// Fourteen screen pixels keeps adjacent nodes distinguishable while making a
// normal mouse click survive sub-pixel projection and hand jitter.
const nodeHitRadius = i => Math.max(14,nodeRadius(i)+4);
function trianglePath(x,y,radius){
  ctx.beginPath();ctx.moveTo(x,y-radius);ctx.lineTo(x+radius*.88,y+radius*.68);ctx.lineTo(x-radius*.88,y+radius*.68);ctx.closePath();
}
function xPath(x,y,radius){
  ctx.beginPath();ctx.moveTo(x-radius,y-radius);ctx.lineTo(x+radius,y+radius);ctx.moveTo(x+radius,y-radius);ctx.lineTo(x-radius,y+radius);
}
function agentTrailColor(agent){
  let hash=2166136261;
  for(const char of agent)hash=Math.imul(hash^char.codePointAt(0),16777619);
  return C.trails[Math.abs(hash)%C.trails.length]||C.active;
}
function trailArrow(a,b,color,alpha){
  const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy);
  if(length<8)return;
  const ux=dx/length,uy=dy/length,size=3.5;
  ctx.strokeStyle=color;ctx.globalAlpha=alpha;ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(b.x,b.y);
  ctx.lineTo(b.x-ux*size-uy*size*.62,b.y-uy*size+ux*size*.62);
  ctx.moveTo(b.x,b.y);
  ctx.lineTo(b.x-ux*size+uy*size*.62,b.y-uy*size-ux*size*.62);ctx.stroke();
}
const nodeBadgeRadius = rr => Math.max(1.5,Math.min(8,rr*.42));
const nodeBadgePoint = (p,rr,radius,side=1,slot=0) => {
  // Keep every badge on the node envelope. Older progress fans around that
  // envelope instead of walking outward far enough to impersonate a peer node.
  const fan=slot===0?0:(slot%2?-1:1)*Math.ceil(slot/2)*.82;
  const angle=(side>0?-.67:-Math.PI+.67)+fan;
  const distance=rr+radius*.12;
  return {x:p.x+Math.cos(angle)*distance,y:p.y+Math.sin(angle)*distance};
};
const questionWavePhase = (i,offset=0) => reducedMotion
  ? offset
  : (performance.now()/1900+i*.173+offset)%1;
function project(){
  const cy=Math.cos(ry), sy=Math.sin(ry), cx=Math.cos(rx), sx=Math.sin(rx);
  const F = 900*zoom, cxp=W/2+40+panX, cyp=H/2+panY;
  DATA.nodes.forEach((n,i)=>{
    const nx = n.x-cc.x, ny = n.y-cc.y, nz = n.z-cc.z;
    const x1 = nx*cy + nz*sy, z1 = -nx*sy + nz*cy;
    const y2 = ny*cx - z1*sx, z2 = ny*sx + z1*cx;
    const w = F/(F+z2+520);
    const p = P[i]; p.x = cxp + x1*w*zoom; p.y = cyp + y2*w*zoom; p.d = z2;
    p.s = Math.max(1.6, 4.6*w*zoom);
    p.on = visible(n);
  });
}
function draw(){
  ctx.clearRect(0,0,W,H);
  const activeWave=reducedMotion?.5:.5+.5*Math.sin(performance.now()/300);
  const pulse=reducedMotion?.78:.55+.45*activeWave;
  const xWave=reducedMotion?.5:.5+.5*Math.sin(performance.now()/620);
  const selSet = new Set();
  if (sel>=0){ selSet.add(sel); nbr[sel].up.forEach(j=>selSet.add(j)); nbr[sel].dn.forEach(j=>selSet.add(j)); }
  if (sel>=0){ relNbr[sel].out.forEach(([j])=>selSet.add(j)); relNbr[sel].inc.forEach(([j])=>selSet.add(j)); }
  // Hard dependencies are solid. Active endpoints add steady context only;
  // an explicit relatedStoryIds overlay below is what actually pulses.
  for (const [a,b] of DATA.edges){
    if (!P[a].on || !P[b].on) continue;
    const lit = selSet.has(a) && selSet.has(b) && (a===sel||b===sel);
    const activeCount=Number(activeNode(a))+Number(activeNode(b));
    if (!(lens.structure&&lit) && !activeCount) continue;
    ctx.setLineDash([]); ctx.lineWidth=lit?1.5:(activeCount===2?2:1);
    ctx.strokeStyle = lit ? C.shipped : C.active;
    const searchEdgeDim=searchTerms.length>0&&!searchMatches[a]&&!searchMatches[b];
    ctx.globalAlpha = (lit ? .9 : (activeCount===2?.62:.27))*(searchEdgeDim?.16:1);
    ctx.beginPath(); ctx.moveTo(P[a].x,P[a].y); ctx.lineTo(P[b].x,P[b].y); ctx.stroke();
  }
  // Nonblocking relations remain dashed, including their active endpoint context.
  ctx.setLineDash([4,4]);
  for (const [a,b] of (DATA.relations||[])){
    if (!P[a].on || !P[b].on) continue;
    const lit=lens.structure&&sel>=0&&(a===sel||b===sel);
    const activeCount=Number(activeNode(a))+Number(activeNode(b));
    if (!lit&&!activeCount) continue;
    ctx.lineWidth=lit?1.5:(activeCount===2?2:1);
    const searchEdgeDim=searchTerms.length>0&&!searchMatches[a]&&!searchMatches[b];
    ctx.strokeStyle = C.active; ctx.globalAlpha = (lit?.75:(activeCount===2?.55:.22))*(searchEdgeDim?.16:1);
    ctx.beginPath(); ctx.moveTo(P[a].x,P[a].y); ctx.lineTo(P[b].x,P[b].y); ctx.stroke();
  }
  // Straight agent trails connect only explicit chronological checkpoints.
  // They are not dependency edges and never bridge across a filtered point.
  if(lens.activity){
    ctx.setLineDash([]);
    for(const trail of (DATA.agentTrails||[])){
      const color=agentTrailColor(trail.agent),points=trail.points||[];
      for(let step=1;step<points.length;step++){
        const a=points[step-1].n,b=points[step].n;
        if(a==null||b==null||!P[a].on||!P[b].on)continue;
        const recency=step/Math.max(1,points.length-1);
        const searchEdgeDim=searchTerms.length>0&&!searchMatches[a]&&!searchMatches[b];
        const alpha=(.14+.5*recency)*(searchEdgeDim?.16:1);
        ctx.strokeStyle=color;ctx.lineWidth=1.15;ctx.globalAlpha=alpha;
        ctx.beginPath();ctx.moveTo(P[a].x,P[a].y);ctx.lineTo(P[b].x,P[b].y);ctx.stroke();
        trailArrow(P[a],P[b],color,alpha);
      }
    }
  }
  // Explicit agent-work linkage pulses. It is not silently inferred from a hard
  // dependency or typed relation, so the overlay never claims evidence it lacks.
  if (lens.activity){
    ctx.setLineDash([2,6]); ctx.lineDashOffset=reducedMotion?0:-performance.now()/90;
    for (const [wi,b] of (DATA.workLinks||[])){
      const w=DATA.work[wi], a=w&&w.n;
      if (!freshWork(w)||a==null||!P[a].on||!P[b].on) continue;
      const searchEdgeDim=searchTerms.length>0&&!searchMatches[a]&&!searchMatches[b];
      ctx.strokeStyle=C.active; ctx.lineWidth=2.6; ctx.globalAlpha=pulse*(searchEdgeDim?.16:1);
      ctx.beginPath(); ctx.moveTo(P[a].x,P[a].y); ctx.lineTo(P[b].x,P[b].y); ctx.stroke();
    }
  }
  // Owner punts are light-magenta dashed pathways over the real dependency
  // graph. They stay quiet globally and brighten when either the punt or an
  // affected story is inspected, so impact is visible without becoming soup.
  ctx.setLineDash([3,5]);
  for(const [a,b,source] of puntImpactLinks){
    if(!P[a].on||!P[b].on)continue;
    const lit=sel===source||sel===a||sel===b||hover===source||hover===a||hover===b;
    const searchEdgeDim=searchTerms.length>0&&!searchMatches[a]&&!searchMatches[b];
    ctx.strokeStyle=C.owner;ctx.lineWidth=lit?2:1.2;ctx.globalAlpha=(lit?.7:.13)*(searchEdgeDim?.16:1);
    ctx.beginPath();ctx.moveTo(P[a].x,P[a].y);ctx.lineTo(P[b].x,P[b].y);ctx.stroke();
  }
  ctx.lineDashOffset=0;
  ctx.setLineDash([]);
  ctx.globalAlpha = 1;
  // nodes, painter-sorted
  const order = DATA.nodes.map((_,i)=>i).filter(i=>P[i].on).sort((a,b)=>P[b].d-P[a].d);
  // One shallow blur bucket creates depth without a blur filter per node. The
  // farthest third changes the canvas filter once, then the focal field stays
  // sharp. Very large graphs keep the cheaper opacity/scale depth cues only.
  const depthBlur=(!reducedMotion&&DATA.nodes.length<=800&&typeof ctx.filter==='string')?'blur(.7px)':'none';
  const farCount=depthBlur==='none'?0:Math.floor(order.length/3);
  let appliedFilter='none';ctx.filter='none';
  for (let position=0;position<order.length;position++){
    const i=order[position],p=P[i];
    const nextFilter=position<farCount?depthBlur:'none';
    if(nextFilter!==appliedFilter){ctx.filter=nextFilter;appliedFilter=nextFilter;}
    const n = DATA.nodes[i];
    const searchDim = searchTerms.length>0 && !searchMatches[i];
    const dim = (sel>=0 && !selSet.has(i)) || searchDim;
    let rgb = RGB[n.g];
    const rec = lens.delivery && n.rec && !dim;
    if (rec) rgb = mixA(rgb, [255,255,255], .55); // ★ next: brighter lightness
    const col = rgbCss(rgb);
    const focusAlpha=dim?.18:1;
    ctx.globalAlpha = progressOpacity(n)*focusAlpha;
    const rr = nodeRadius(i);
    if (n.g==='specced'){ // unbuilt-but-specced: an empty vessel, outline only
      ctx.strokeStyle = col; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*.85,0,7); ctx.stroke();
    } else if(n.g==='shipped'){
      ctx.strokeStyle=col;ctx.lineWidth=1.5;trianglePath(p.x,p.y,rr);ctx.stroke();
    } else if(n.g==='buggap'){
      ctx.globalAlpha*=.9+.1*xWave;ctx.strokeStyle=col;ctx.lineWidth=1.5;
      xPath(p.x,p.y,rr*(.7+.035*xWave));ctx.stroke();
    } else {
      ctx.fillStyle = col;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr,0,7); ctx.fill();
    }
    // Release/version is a separate outer-ring channel; blending it into fill
    // would make progress versus horizon impossible to decode.
    ctx.globalAlpha=versionOpacity(n)*focusAlpha; ctx.strokeStyle=col;
    ctx.lineWidth=1;
    ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.16,0,7); ctx.stroke();
    // Unknown assessed size gets a neutral dashed ring. It must not look like
    // XS merely because both are visually compact.
    if(sizeMode==='delivery'&&n.assess&&n.assess.band==null&&!dim){
      ctx.globalAlpha=.72;ctx.strokeStyle=C.faint;ctx.lineWidth=1;ctx.setLineDash([2,2]);
      ctx.beginPath();ctx.arc(p.x,p.y,rr*1.42,0,7);ctx.stroke();ctx.setLineDash([]);
    }
    // Accepted owner override: solid halo = promoted, dashed halo + slash =
    // punted. Downstream-affected nodes get a quieter dotted halo.
    const course=ownerCourse(i);
    if(course&&!dim){
      ctx.globalAlpha=course==='promoted'?.88:.72;ctx.strokeStyle=C.owner;ctx.lineWidth=1;
      ctx.setLineDash(course==='punted'?[4,3]:[]);
      ctx.beginPath();ctx.arc(p.x,p.y,rr*1.82,0,7);ctx.stroke();ctx.setLineDash([]);
      if(course==='promoted'){
        ctx.globalAlpha=.09;ctx.fillStyle=C.owner;ctx.beginPath();ctx.arc(p.x,p.y,rr*2.25,0,7);ctx.fill();
      }else{
        ctx.globalAlpha=.82;ctx.beginPath();ctx.moveTo(p.x-rr*1.18,p.y+rr*1.18);ctx.lineTo(p.x+rr*1.18,p.y-rr*1.18);ctx.stroke();
      }
    }else if(puntedBy[i].length&&!dim){
      ctx.globalAlpha=.3;ctx.strokeStyle=C.owner;ctx.lineWidth=1;ctx.setLineDash([1.5,3]);
      ctx.beginPath();ctx.arc(p.x,p.y,rr*1.42,0,7);ctx.stroke();ctx.setLineDash([]);
    }
    // Continuous proximity precedes the exact hit state, making small circles
    // discoverable without the old 1.7x hover-size jump.
    if(p.near>0&&!dim){
      ctx.globalAlpha=.035+.1*p.near; ctx.fillStyle=rgbCss(mixA(rgb,[255,255,255],.55));
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*(1.45+.7*p.near),0,7); ctx.fill();
    }
    if(i===hover&&!dim){
      ctx.globalAlpha=.9; ctx.strokeStyle=rgbCss(mixA(rgb,[255,255,255],.8)); ctx.lineWidth=1.25;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.38,0,7); ctx.stroke();
    }
    if(i===sel){
      ctx.globalAlpha=1; ctx.strokeStyle=C.shipped; ctx.lineWidth=1.5;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.58,0,7); ctx.stroke();
    }
    if (rec){ // recommended-next: soft glow + bright ring so it pops off the muted field
      ctx.globalAlpha = .16;
      ctx.fillStyle = rgbCss(mixA(rgb,[255,255,255],.5));
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*2.6,0,7); ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = rgbCss(mixA(rgb,[255,255,255],.7)); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.5,0,7); ctx.stroke();
    }
    if (n.g==='shipped' && !dim){ ctx.globalAlpha=.12; ctx.strokeStyle=col;ctx.lineWidth=1.5;
      trianglePath(p.x,p.y,p.s*2.45);ctx.stroke(); }
    if (activeNode(i) && !dim){
      // Motion is optional; the steady ring and checkpoint arc preserve meaning
      // under prefers-reduced-motion.
      ctx.globalAlpha=pulse; ctx.strokeStyle=C.active; ctx.lineWidth=1;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*(reducedMotion?1.9:1.72+.58*activeWave),0,7); ctx.stroke();
      ctx.globalAlpha=reducedMotion?.12:.1+.22*activeWave;
      ctx.beginPath();ctx.arc(p.x,p.y,rr*(reducedMotion?2.45:2.35+.42*activeWave),0,7);ctx.stroke();
      const progress=nodeProgress(i);
      if(progress.total>0){ ctx.globalAlpha=.95; ctx.lineWidth=1;
        ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.28,-Math.PI/2,
          -Math.PI/2+2*Math.PI*(progress.done/progress.total)); ctx.stroke(); }
    }
    // Explicit researched decisions use an X as the steady blocker signal.
    // Faint shockwaves attract attention without making another circular cue
    // look like a neighboring clickable story.
    const unresolved=ownerQuestions(i);
    if(unresolved.length&&!dim){
      const questionPulse=reducedMotion?.16:.1+.08*(.5+.5*Math.sin(performance.now()/430+i*1.618));
      ctx.globalAlpha=questionPulse;ctx.fillStyle=C.owner;
      ctx.beginPath();ctx.arc(p.x,p.y,rr*2.15,0,7);ctx.fill();
      for(const offset of [0,.5]){
        const phase=questionWavePhase(i,offset);
        ctx.globalAlpha=reducedMotion?(offset===0?.13:.07):.2*Math.pow(1-phase,1.7);
        ctx.strokeStyle=C.owner;ctx.lineWidth=1;
        ctx.beginPath();ctx.arc(p.x,p.y,rr*(1.65+phase*3.1),0,7);ctx.stroke();
      }
      const radius=nodeBadgeRadius(rr);
      const {x,y}=nodeBadgePoint(p,rr,radius,-1,0);
      ctx.globalAlpha=.86+.14*xWave;ctx.strokeStyle=C.owner;ctx.lineWidth=1.5;
      xPath(x,y,Math.max(2.5,radius*.82)*(1+.05*xWave));ctx.stroke();
      if(unresolved.length>1){ctx.fillStyle=C.owner;ctx.font=`${Math.max(5,radius*1.25)}px ui-monospace,monospace`;ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(String(unresolved.length),x+radius,y);}
    }
    // Circle-check marks are a static history trail: the newest overlaps the
    // story envelope and older verified progress fans along that same envelope.
    // Motion never carries it, and none of the badges can read as a peer node.
    if (lens.progress && !dim){
      const events=progressEvents(i);
      const markerBase=nodeBadgeRadius(rr);
      events.forEach((event,order)=>{
        const age=ageDays(event.at), hotWindow=Math.max(.01,(n.pg||{}).hotWindowDays||7);
        const brightness=Math.max(.18,1-age/hotWindow);
        const {x,y}=nodeBadgePoint(p,rr,markerBase,1,order);
        ctx.globalAlpha=brightness*.95; ctx.strokeStyle=C.active; ctx.lineWidth=1;
        ctx.beginPath(); ctx.arc(x,y,markerBase,0,7); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(x-markerBase*.42,y);
        ctx.lineTo(x-markerBase*.08,y+markerBase*.32);
        ctx.lineTo(x+markerBase*.5,y-markerBase*.34); ctx.stroke();
      });
      const blocked=stall(i);
      if (blocked){
        // Staleness is evidence age, not an owner question. Keep it as a quiet
        // dashed ring in the next badge slot so the two concepts do not lie
        // with the same glyph.
        const ageRatio=Math.min(1,blocked.days/Math.max(1,blocked.maxDays));
        const radius=Math.min(10,markerBase*(1+.25*ageRatio));
        const {x,y}=nodeBadgePoint(p,rr,radius,-1,unresolved.length?1:0);
        ctx.globalAlpha=.9; ctx.strokeStyle=C.buggap; ctx.lineWidth=1;
        ctx.setLineDash([Math.max(1,radius*.38),Math.max(1,radius*.34)]);
        ctx.beginPath(); ctx.arc(x,y,radius,0,7); ctx.stroke();
        ctx.setLineDash([]);
      }
    }
  }
  ctx.filter='none';
  ctx.globalAlpha = 1;
}
const snapCam = reducedMotion;
function frame(){ ry+=vy; rx+=vx; vx*=.9; vy*=.9;
  const e = snapCam ? 1 : .07; // ease the camera centre toward the visible centroid
  cc.x += (ct.x-cc.x)*e; cc.y += (ct.y-cc.y)*e; cc.z += (ct.z-cc.z)*e;
  project(); if(pointerActive&&!orbiting)updatePointerState(pointerX,pointerY); draw(); requestAnimationFrame(frame); }
// ---- input ----
let pointerDown=false, orbiting=false, downTarget=-1, lx=0, ly=0, downX=0, downY=0,
  pointerActive=false, pointerX=0, pointerY=0;
const orbitThreshold=6;
function capturePointer(e){
  if(e.pointerId==null||!cv.setPointerCapture)return;
  try{cv.setPointerCapture(e.pointerId);}catch(_error){}
}
function releasePointer(e){
  if(e.pointerId==null||!cv.releasePointerCapture)return;
  try{
    if(!cv.hasPointerCapture||cv.hasPointerCapture(e.pointerId))cv.releasePointerCapture(e.pointerId);
  }catch(_error){}
}
function updatePointerState(x,y){
  pointerActive=true; pointerX=x; pointerY=y;
  let best=-1,bestDistance=Infinity,bestDepth=Infinity;
  for(let i=0;i<P.length;i++){
    const p=P[i];
    if(!p.on){p.near=0;continue;}
    const distance=Math.hypot(p.x-x,p.y-y), hitRadius=nodeHitRadius(i);
    p.near=Math.max(0,1-Math.max(0,distance-hitRadius)/32);
    if(distance<=hitRadius&&(distance<bestDistance-.25||(Math.abs(distance-bestDistance)<=.25&&p.d<bestDepth))){best=i;bestDistance=distance;bestDepth=p.d;}
  }
  hover=best;
}
function clearPointerState(){
  pointerActive=false;hover=-1;P.forEach(p=>{p.near=0;});
  const tip=document.getElementById('tip');if(tip)tip.style.display='none';
  cv.style.cursor='grab';
}
cv.addEventListener('pointerdown',e=>{
  updatePointerState(e.clientX,e.clientY);
  pointerDown=true;orbiting=false;downTarget=hover;downX=lx=e.clientX;downY=ly=e.clientY;
  capturePointer(e);
});
cv.addEventListener('pointermove',e=>{
  if(pointerDown){
    if(!orbiting&&Math.hypot(e.clientX-downX,e.clientY-downY)>orbitThreshold){
      orbiting=true;downTarget=-1;cv.classList.add('drag');clearPointerState();
      document.getElementById('tip').style.display='none';
    }
    if(orbiting){ry+=(e.clientX-lx)*.005;rx+=(e.clientY-ly)*.005;vy=0;}
    lx=e.clientX;ly=e.clientY;
  }
  else {
    updatePointerState(e.clientX,e.clientY);
    const best=hover;
    const tip = document.getElementById('tip');
    if (best>=0){ const n=DATA.nodes[best];
      const live=(n.aw||[]).map(wi=>DATA.work[wi]).filter(freshWork);
      const liveText=live.length?` · ${live.map(w=>w.total?w.done+'/'+w.total:'0/0').join(', ')} checkpoints`:'';
      const trailText=lens.progress&&progressText(n)?` · ${progressText(n)}`:'';
      const opacityText=` · ${Math.round(progressOpacity(n)*100)}% progress fill · ${Math.round(versionOpacity(n)*100)}% version ring`;
      tip.style.display='block'; tip.style.left=(e.clientX+14)+'px'; tip.style.top=(e.clientY+10)+'px';
      const courseText=ownerCourseText(hover)?` · owner ${ownerCourseText(hover)}`:(puntedBy[hover].length?` · affected by ${puntedBy[hover].length} punt${puntedBy[hover].length===1?'':'s'}`:'');
      tip.innerHTML = `${lens.delivery&&n.rec?icon('star-fill',true)+' ':''}${esc(n.t)}<small>${esc(n.st)} · ${esc(n.c.replace(/-/g,' '))}${esc(opacityText)}${esc(courseText)}${esc(liveText)}${esc(trailText)}</small>`;
      cv.style.cursor='pointer';
    } else { tip.style.display='none'; cv.style.cursor='grab'; }
  }
});
cv.addEventListener('pointerleave',()=>{if(!pointerDown){clearPointerState();document.getElementById('tip').style.display='none';cv.style.cursor='grab';}});
cv.addEventListener('pointerup',e=>{
  const wasOrbiting=orbiting;
  pointerDown=false;orbiting=false;cv.classList.remove('drag');
  releasePointer(e);
  if(!wasOrbiting){
    // Lock the nearest pointer-down target through harmless jitter and camera
    // easing. Re-hit-testing at release could select a neighboring front-most
    // node after the projection moved under the pointer.
    const target=downTarget;
    project();updatePointerState(e.clientX,e.clientY);
    if(target>=0&&P[target].on)openNode(target);
    else if(sel>=0){sel=-1;dossier.classList.remove('open');dossier.setAttribute('aria-hidden','true');}
  }
  downTarget=-1;
});
cv.addEventListener('pointercancel',e=>{
  pointerDown=false;orbiting=false;downTarget=-1;cv.classList.remove('drag');clearPointerState();
  releasePointer(e);
});
cv.addEventListener('wheel',e=>{ e.preventDefault();
  if (e.ctrlKey){ // trackpad pinch arrives as ctrl+wheel
    zoom = Math.min(3.4, Math.max(.45, zoom * (e.deltaY<0?1.06:.94)));
  } else if (e.metaKey){ // Command + two-finger scroll pans in screen space
    panX -= e.deltaX; panY -= e.deltaY;
  } else { // two-finger scroll orbits
    ry += e.deltaX*.0035; rx += e.deltaY*.0035;
  }
},{passive:false});
