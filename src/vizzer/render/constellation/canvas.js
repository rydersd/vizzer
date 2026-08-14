// ---- 3d render ----
const bgcv=document.getElementById('bgcv'), bgctx=bgcv.getContext('2d');
const cv=document.getElementById('cv'), nodeCtx=cv.getContext('2d');
let ctx=nodeCtx;
let W,H,DPR; function size(){ DPR=Math.min(devicePixelRatio,2); W=innerWidth; H=innerHeight;
  for(const canvas of [bgcv,cv]){canvas.width=W*DPR;canvas.height=H*DPR;}
  for(const context of [bgctx,nodeCtx])context.setTransform(DPR,0,0,DPR,0,0);
  ctx=nodeCtx;} size(); addEventListener('resize',size);
let rx=-.35, ry=.6, zoom=1, panX=0, panY=0, vx=0, vy=0;
const P = DATA.nodes.map(()=>({x:0,y:0,s:0,d:0,on:true,near:0}));
const nodeRadius = i => P[i].s*(sizeMode==='time' ? DATA.nodes[i].tw : (DATA.nodes[i].w||1));
// Canvas nodes are intentionally tiny, but their pointer target must not be.
// Fourteen screen pixels keeps adjacent nodes distinguishable while making a
// normal mouse click survive sub-pixel projection and hand jitter.
const nodeHitRadius = i => Math.max(14,nodeRadius(i)+4);
// Distinguish pixels occupied by a Story glyph from its generous pointer halo.
// Visible paint wins dense overlaps; an invisible halo must not steal a nearby
// Story or its centered question X.
const nodePaintRadius = i => Math.max(2.5,nodeRadius(i)*1.6);
const questionGlyphRadius = i => Math.max(4,nodeRadius(i)*.72);
function questionGlyphPaintDistance(i,x,y){
  const dx=x-P[i].x,dy=y-P[i].y,radius=questionGlyphRadius(i);
  if(Math.max(Math.abs(dx),Math.abs(dy))>radius+2)return Infinity;
  return Math.min(Math.abs(dy-dx),Math.abs(dy+dx))/Math.SQRT2;
}
const questionAttentionRadius = i => actionableQuestion(i)
  ?Math.max(28,nodeRadius(i)*3.25):Math.max(22,nodeRadius(i)*2.5);
let questionRingFractions=reducedMotion?[.72,.9]:[.68,.9];
const questionRingRadii = i => {
  const radius=questionAttentionRadius(i);
  return questionRingFractions.map(fraction=>radius*fraction);
};
function canvasInteractionBounds(){
  const compact=W<=760,drawerOpen=dossier.classList.contains('open');
  return {left:compact?0:236,top:106,
    right:drawerOpen?(compact?0:Math.max(236,dossier.getBoundingClientRect().left)):W,bottom:H};
}
const insideCanvasInteractionBounds=(x,y,bounds=canvasInteractionBounds())=>
  x>=bounds.left&&x<=bounds.right&&y>=bounds.top&&y<=bounds.bottom;
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
function project(){
  // Resize delivery and pointer input are separate browser tasks. A click can
  // arrive after innerWidth changes but before the resize listener runs; using
  // stale W/H then shifts every projected target by half the viewport delta.
  if(W!==innerWidth||H!==innerHeight)size();
  const cy=Math.cos(ry), sy=Math.sin(ry), cx=Math.cos(rx), sx=Math.sin(rx);
  const F = 900*zoom, cxp=W/2+40+panX, cyp=H/2+panY;
  const bounds=canvasInteractionBounds();
  DATA.nodes.forEach((n,i)=>{
    const nx = n.x-cc.x, ny = n.y-cc.y, nz = n.z-cc.z;
    const x1 = nx*cy + nz*sy, z1 = -nx*sy + nz*cy;
    const y2 = ny*cx - z1*sx, z2 = ny*sx + z1*cx;
    const w = F/(F+z2+520);
    const p = P[i]; p.x = cxp + x1*w*zoom; p.y = cyp + y2*w*zoom; p.d = z2;
    p.s = Math.max(1.6, 4.6*w*zoom);
    // Never advertise a canvas target underneath interactive HTML chrome. A
    // visible-but-unclickable node is worse than a clipped node: it lies.
    p.on = visible(n)&&insideCanvasInteractionBounds(p.x,p.y,bounds);
  });
}
function draw(){
  bgctx.clearRect(0,0,W,H);nodeCtx.clearRect(0,0,W,H);ctx=bgctx;
  const bounds=canvasInteractionBounds();
  for(const context of [bgctx,nodeCtx]){
    context.save();context.beginPath();context.rect(bounds.left,bounds.top,
      Math.max(0,bounds.right-bounds.left),Math.max(0,bounds.bottom-bounds.top));context.clip();
  }
  const activeWave=reducedMotion?.5:.5+.5*Math.sin(performance.now()/300);
  const pulse=reducedMotion?.78:.55+.45*activeWave;
  const xWave=reducedMotion?.5:.5+.5*Math.sin(performance.now()/620);
  questionRingFractions=reducedMotion?[.72,.9]:[.62+.12*activeWave,.82+.16*activeWave];
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
  // Animated pulses and ambient echoes are paint only. Keeping them on the
  // pointer-transparent backdrop makes that architectural fact inspectable,
  // instead of relying on every future hit-test author to remember it.
  for(const i of order){
    const p=P[i],n=DATA.nodes[i],rr=nodeRadius(i);
    const searchDim=searchTerms.length>0&&!searchMatches[i];
    const dim=(sel>=0&&!selSet.has(i))||searchDim;
    const rgb=RGB[n.g],rec=lens.delivery&&n.rec&&!dim;
    if(rec){
      ctx.globalAlpha=.16;ctx.fillStyle=rgbCss(mixA(rgb,[255,255,255],.5));
      ctx.beginPath();ctx.arc(p.x,p.y,rr*2.6,0,7);ctx.fill();
    }
    if(n.g==='shipped'&&!dim){
      ctx.globalAlpha=.12;ctx.strokeStyle=rgbCss(rgb);ctx.lineWidth=1.5;
      trianglePath(p.x,p.y,p.s*2.45);ctx.stroke();
    }
    if(activeNode(i)&&!dim){
      ctx.globalAlpha=pulse;ctx.strokeStyle=C.active;ctx.lineWidth=1;
      ctx.beginPath();ctx.arc(p.x,p.y,rr*(reducedMotion?1.9:1.72+.58*activeWave),0,7);ctx.stroke();
      ctx.globalAlpha=reducedMotion?.12:.1+.22*activeWave;
      ctx.beginPath();ctx.arc(p.x,p.y,rr*(reducedMotion?2.45:2.35+.42*activeWave),0,7);ctx.stroke();
    }
    if(actionableQuestion(i)&&!dim){
      const [innerRadius,outerRadius]=questionRingRadii(i);
      ctx.globalAlpha=reducedMotion?.72:.42+.48*activeWave;ctx.strokeStyle=C.owner;ctx.lineWidth=1.5;
      ctx.beginPath();ctx.arc(p.x,p.y,innerRadius,0,7);ctx.stroke();
      ctx.globalAlpha=reducedMotion?.1:.07+.18*activeWave;
      ctx.beginPath();ctx.arc(p.x,p.y,outerRadius,0,7);ctx.stroke();
    }
  }
  ctx=nodeCtx;
  for (let position=0;position<order.length;position++){
    const i=order[position],p=P[i];
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
    if (rec){ // recommended-next: bright ring over its background glow
      ctx.globalAlpha = 1;
      ctx.strokeStyle = rgbCss(mixA(rgb,[255,255,255],.7)); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.5,0,7); ctx.stroke();
    }
    if (activeNode(i) && !dim){
      // The static checkpoint arc is node information; the moving pulse is on bgcv.
      const progress=nodeProgress(i);
      if(progress.total>0){ ctx.globalAlpha=.95;ctx.strokeStyle=C.active;ctx.lineWidth=1;
        ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.28,-Math.PI/2,
          -Math.PI/2+2*Math.PI*(progress.done/progress.total)); ctx.stroke(); }
    }
    const unresolved=ownerQuestions(i);
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
  // Owner decisions use one centered, static X on a dedicated top layer.
  // Pulses and offset badges made the signal look like a neighboring Story;
  // letting ordinary nodes paint over the X made its advertised target lie.
  for(const i of order){
    const p=P[i],rr=nodeRadius(i),unresolved=ownerQuestions(i);
    const searchDim=searchTerms.length>0&&!searchMatches[i];
    const dim=(sel>=0&&!selSet.has(i))||searchDim;
    if(!unresolved.length||dim)continue;
    ctx.globalAlpha=.95;ctx.strokeStyle=C.owner;ctx.lineWidth=1.5;
    xPath(p.x,p.y,Math.max(4,rr*.72));ctx.stroke();
    if(unresolved.length>1){ctx.fillStyle=C.owner;ctx.font=`${Math.max(6,rr*.52)}px ui-monospace,monospace`;ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(String(unresolved.length),p.x+rr*.82,p.y);}
  }
  ctx.globalAlpha = 1;ctx=nodeCtx;
  for(const context of [bgctx,nodeCtx])context.restore();
}
const snapCam = reducedMotion;
function frame(){ ry+=vy; rx+=vx; vx*=.9; vy*=.9;
  const e = snapCam ? 1 : .07; // ease the camera centre toward the visible centroid
  cc.x += (ct.x-cc.x)*e; cc.y += (ct.y-cc.y)*e; cc.z += (ct.z-cc.z)*e;
  project(); if(pointerActive&&!orbiting)updatePointerAt(pointerX,pointerY); draw(); requestAnimationFrame(frame); }
// ---- input ----
let pointerDown=false, orbiting=false, downTarget=-1, lx=0, ly=0, downX=0, downY=0,
  pointerActive=false, pointerX=0, pointerY=0;
const orbitThreshold=6;
const hitDebugEnabled=/(?:^|[?&])hitdebug(?:=1|=true|&|$)/.test(location.search||'');
let hitDebugPanel=null,hitDebugLine=null;
const debugNodeLabel=index=>index>=0&&DATA.nodes[index]
  ?`${index}:${DATA.nodes[index].t}`:String(index);
function publishHitDebug(stage,event,extra={}){
  if(!hitDebugEnabled)return;
  if(!hitDebugPanel){
    hitDebugPanel=document.createElement('pre');hitDebugPanel.id='hitdebug';
    Object.assign(hitDebugPanel.style,{position:'fixed',left:'8px',bottom:'8px',zIndex:'99',
      maxWidth:'min(720px,calc(100vw - 16px))',maxHeight:'42vh',overflow:'auto',margin:'0',
      padding:'8px',border:'1px solid #ff5cff',borderRadius:'6px',background:'#090b10ee',
      color:'#f6d8ff',font:'11px/1.35 ui-monospace,monospace',pointerEvents:'none'});
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    Object.assign(svg.style,{position:'fixed',inset:'0',width:'100vw',height:'100vh',
      zIndex:'98',pointerEvents:'none'});
    hitDebugLine=document.createElementNS('http://www.w3.org/2000/svg','line');
    hitDebugLine.setAttribute('stroke','#00ffff');hitDebugLine.setAttribute('stroke-width','2');
    svg.appendChild(hitDebugLine);document.body.append(svg,hitDebugPanel);
  }
  const rect=cv.getBoundingClientRect(),target=extra.chosen??extra.opened??hover;
  const point=target>=0&&P[target]?P[target]:null;
  const receipt={stage,pointer:[event.clientX,event.clientY],offset:[event.offsetX,event.offsetY],
    canvas:[rect.left,rect.top,rect.width,rect.height],backing:[cv.width,cv.height],
    viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,
    visualViewport:visualViewport?[visualViewport.offsetLeft,visualViewport.offsetTop,
      visualViewport.width,visualViewport.height,visualViewport.scale]:null,
    hover:debugNodeLabel(hover),presented:debugNodeLabel(presentedHover),
    down:debugNodeLabel(downTarget),selected:debugNodeLabel(sel),
    target:point?[point.x,point.y]:null,
    delta:point?[point.x-event.clientX,point.y-event.clientY]:null,...extra};
  hitDebugPanel.textContent=JSON.stringify(receipt,null,2);window.__vizzerHitDebug=receipt;
  if(point){hitDebugLine.setAttribute('x1',event.clientX);hitDebugLine.setAttribute('y1',event.clientY);
    hitDebugLine.setAttribute('x2',point.x);hitDebugLine.setAttribute('y2',point.y);}
  document.title=`HIT ${stage} adv=${extra.advertised??presentedHover} geo=${extra.geometric??hover} open=${extra.opened??'-'} sel=${sel} p=${Math.round(event.clientX)},${Math.round(event.clientY)}`;
}
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
  let questionGlyphBest=-1,questionGlyphPaintDistanceBest=Infinity,
    questionGlyphDepth=Infinity;
  let questionCenterBest=-1,questionCenterDistanceBest=Infinity,
    questionCenterPaintDistanceBest=Infinity,questionCenterDepth=Infinity;
  let paintBest=-1,paintDepth=Infinity;
  for(let i=0;i<P.length;i++){
    const p=P[i];
    if(!p.on){p.near=0;continue;}
    const distance=Math.hypot(p.x-x,p.y-y), hitRadius=nodeHitRadius(i);
    p.near=Math.max(0,1-Math.max(0,distance-hitRadius)/32);
    if(distance<=hitRadius&&(distance<bestDistance-.25||(Math.abs(distance-bestDistance)<=.25&&p.d<bestDepth))){best=i;bestDistance=distance;bestDepth=p.d;}
    if(distance<=nodePaintRadius(i)&&p.d<paintDepth){
      paintBest=i;paintDepth=p.d;
    }
    if(ownerQuestions(i).length){
      const glyphPaintDistance=questionGlyphPaintDistance(i,x,y);
      if(glyphPaintDistance<=2.5){
        // A deliberate center click owns its X even when another glyph crosses
        // there. Outside that small core, mirror the canvas: materially closer
        // stroke first, then front-most/later paint order. Center proximity is
        // not visible ownership at an overlapping endpoint.
        // Keep this genuinely central. A broader exception lets a nearby X's
        // center steal an exact endpoint that was painted in front of it.
        const centerCore=Math.min(.75,questionGlyphRadius(i)*.15);
        if(distance<=centerCore){
          const sameCenter=Math.abs(distance-questionCenterDistanceBest)<=.05;
          const samePaint=Math.abs(glyphPaintDistance-questionCenterPaintDistanceBest)<=.05;
          const sameDepth=Math.abs(p.d-questionCenterDepth)<=.05;
          if(distance<questionCenterDistanceBest-.05||(sameCenter&&
              (glyphPaintDistance<questionCenterPaintDistanceBest-.05||(samePaint&&
                (p.d<questionCenterDepth-.05||(sameDepth&&i>questionCenterBest)))))){
            questionCenterBest=i;questionCenterDistanceBest=distance;
            questionCenterPaintDistanceBest=glyphPaintDistance;questionCenterDepth=p.d;
          }
        }else{
          const sameStroke=Math.abs(glyphPaintDistance-questionGlyphPaintDistanceBest)<=.05;
          const sameDepth=Math.abs(p.d-questionGlyphDepth)<=.05;
          if(glyphPaintDistance<questionGlyphPaintDistanceBest-.05||(sameStroke&&
              (p.d<questionGlyphDepth-.05||(sameDepth&&i>questionGlyphBest)))){
            questionGlyphBest=i;questionGlyphPaintDistanceBest=glyphPaintDistance;
            questionGlyphDepth=p.d;
          }
        }
      }
    }
  }
  // The static X and node paint are interaction. Animated rings are attention
  // only on pointer-transparent bgcv and must never steal a nearby Story.
  // Generous invisible halos remain the final fallback for tiny nodes.
  hover=questionCenterBest>=0?questionCenterBest:
    (questionGlyphBest>=0?questionGlyphBest:(paintBest>=0?paintBest:best));
}
let presentedHover=-1;
function presentPointerState(x,y){
  const best=hover,tip=document.getElementById('tip');
  if(best>=0){
    if(presentedHover!==best){
      const n=DATA.nodes[best];
      const live=(n.aw||[]).map(wi=>DATA.work[wi]).filter(freshWork);
      const liveText=live.length?` · ${live.map(w=>w.total?w.done+'/'+w.total:'0/0').join(', ')} checkpoints`:'';
      const trailText=lens.progress&&progressText(n)?` · ${progressText(n)}`:'';
      const opacityText=` · ${Math.round(progressOpacity(n)*100)}% progress fill · ${Math.round(versionOpacity(n)*100)}% version ring`;
      const courseText=ownerCourseText(best)?` · owner ${ownerCourseText(best)}`:(puntedBy[best].length?` · affected by ${puntedBy[best].length} punt${puntedBy[best].length===1?'':'s'}`:'');
      tip.innerHTML=`${lens.delivery&&n.rec?icon('star-fill',true)+' ':''}${esc(n.t)}<small>${esc(n.st)} · ${esc(n.c.replace(/-/g,' '))}${esc(opacityText)}${esc(courseText)}${esc(liveText)}${esc(trailText)}</small>`;
    }
    tip.style.display='block';tip.style.left=(x+14)+'px';tip.style.top=(y+10)+'px';
    cv.classList.add('hover-target');
  }else{
    tip.style.display='none';cv.classList.remove('hover-target');
  }
  presentedHover=best;
}
function updatePointerAt(x,y){updatePointerState(x,y);presentPointerState(x,y);}
function clearPointerState(){
  pointerActive=false;hover=-1;presentedHover=-1;P.forEach(p=>{p.near=0;});
  const tip=document.getElementById('tip');if(tip)tip.style.display='none';
  cv.classList.remove('hover-target');
}
cv.addEventListener('pointerdown',e=>{
  // A press within ordinary hand jitter belongs to the Story whose tooltip
  // the UI is already advertising. Re-running dense-scene ranking first can
  // silently replace that Story with a neighbor between hover and press.
  const advertisedTarget=pointerActive&&presentedHover>=0&&P[presentedHover]?.on&&
    Math.hypot(e.clientX-pointerX,e.clientY-pointerY)<=orbitThreshold
    ?presentedHover:-1;
  updatePointerState(e.clientX,e.clientY);const geometricTarget=hover;
  if(advertisedTarget>=0)hover=advertisedTarget;
  presentPointerState(e.clientX,e.clientY);
  pointerDown=true;orbiting=false;downTarget=advertisedTarget>=0?advertisedTarget:hover;
  downX=lx=e.clientX;downY=ly=e.clientY;
  publishHitDebug('down',e,{advertised:advertisedTarget,geometric:geometricTarget,chosen:downTarget,
    pointerType:e.pointerType||'unknown'});
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
    updatePointerAt(e.clientX,e.clientY);
    publishHitDebug('move',e,{chosen:hover,pointerType:e.pointerType||'unknown'});
  }
});
cv.addEventListener('pointerleave',()=>{if(!pointerDown){clearPointerState();document.getElementById('tip').style.display='none';}});
cv.addEventListener('pointerup',e=>{
  const wasOrbiting=orbiting;
  pointerDown=false;orbiting=false;cv.classList.remove('drag');
  releasePointer(e);
  if(!wasOrbiting){
    // Lock the nearest pointer-down target through harmless jitter and camera
    // easing. Re-hit-testing at release could select a neighboring front-most
    // node after the projection moved under the pointer.
    const target=downTarget;
    project();updatePointerAt(e.clientX,e.clientY);
    // Visibility was already proven when downTarget was captured. Requiring it
    // again after projection lets easing or a chrome boundary cancel a valid
    // press between pointer-down and pointer-up.
    if(target>=0)openNode(target);
    publishHitDebug('up',e,{opened:target,pointerType:e.pointerType||'unknown'});
  }else{
    project();updatePointerAt(e.clientX,e.clientY);
    publishHitDebug('orbit-up',e,{opened:-1,pointerType:e.pointerType||'unknown'});
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
  project();updatePointerAt(e.clientX,e.clientY);
},{passive:false});
