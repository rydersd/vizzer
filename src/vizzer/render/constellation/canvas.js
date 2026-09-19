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
const FOCUS_BACKGROUND_TIER=.3, FOCUS_BACKGROUND_SCALE=.6, FOCUS_DESATURATE=.8;
const desaturate=(rgb,amount)=>{const grey=Math.round(.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]);return mixA(rgb,[grey,grey,grey],amount);};
function nodePaintColor(rgb,focusAlpha,tier){
  if(tier<FOCUS_BACKGROUND_TIER)return mixA(desaturate(rgb,FOCUS_DESATURATE),RGB.bg,1-focusAlpha);
  return contrastNodeColor(mixA(rgb,RGB.fade,1-focusAlpha),focusAlpha<.5?3.2:4.5);
}
const nodeRadius = i => Math.max(3,P[i].s*(sizeMode==='time' ? DATA.nodes[i].tw : (DATA.nodes[i].w||1)))
  *(focusBackground(i)?FOCUS_BACKGROUND_SCALE:1);
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
function latestTestReview(i){
  const refs=DATA.nodes[i].tr||[];
  return refs.length?(DATA.testReviews||[])[refs[refs.length-1]]:null;
}
function testReviewVisualState(testReview,{active=.5,slow=.5,reduced=false}={}){
  const snag=Boolean(testReview.snag)||['snagged','unauthorized-execution'].includes(testReview.state)||testReview.outcome==='infrastructure-failure';
  const preparing=testReview.state==='preparing',reviewing=testReview.state==='under-review',running=testReview.state==='running',moving=preparing||reviewing||running||snag;
  const outcomeBadge={pass:'✓','expected-red':'R','unexpected-fail':'!','infrastructure-failure':'⚠',partial:'½',inconclusive:'?',cancelled:'×',invalidated:'!'};
  return {snag,preparing,reviewing,running,moving,wave:running?active:slow,
    dash:snag?[2,2]:(reviewing?[7,3]:(preparing?[2,4]:[])),
    stateLabel:reduced&&moving?({preparing:'P','under-review':'U',running:'R',snagged:'S','unauthorized-execution':'!'}[testReview.state]||'•'):'',
    outcomeBadge:outcomeBadge[testReview.outcome]||(testReview.outcome==='pending'?'':'•')};
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
    p.on = canvasVisible(n)&&insideCanvasInteractionBounds(p.x,p.y,bounds);
  });
}
// Derived, cached, concave capability regions. This is the generic extraction
// of the downstream constellation algorithm: only projected nodes, the
// canvas bounds, and optional hierarchy titles are inputs.
const HULL_ALPHA=.07, HULL_LABEL_ALPHA=.55, HULL_MIN_NODES=4, HULL_MIN_WIDTH=60, HULL_DIM_TIER=.25;
const HULL_LABEL_FONT='11px ui-monospace,monospace', HULL_LABEL_LINE=16;
// A hull edge longer than this many mean member spacings (sqrt of the bounding
// area per member) is dug inward toward the members; shorter edges already hug them.
const HULL_DIG_SPACINGS=3.5;
// Ring search for a name that found no slot: step outward this many px per
// ring, this many directions per ring, until the canvas is exhausted.
const HULL_LABEL_RING_STEP=12, HULL_LABEL_RING_DIRECTIONS=16, HULL_LABEL_GRID=8;
let hullCache={key:'',hulls:[]}, hullComputeMs=0;
const capColorIndex=new Map([...caps].sort().map((capability,index)=>[capability,index]));
function hslRgb(h,s=.62,l=.57){
  const c=(1-Math.abs(2*l-1))*s,x=c*(1-Math.abs((h/60)%2-1)),m=l-c/2;
  let rgb=h<60?[c,x,0]:h<120?[x,c,0]:h<180?[0,c,x]:h<240?[0,x,c]:h<300?[x,0,c]:[c,0,x];
  return rgb.map(value=>Math.round((value+m)*255));
}

const capabilityColor = c => hslRgb(((capColorIndex.get(c)??0)*137.508)%360);
function capabilityTitle(c){
  const root=(DATA.groups||[]).find(group=>!group.parent&&group.id.split(':').pop()===c);
  return root?.title||String(c).replace(/-/g,' ');
}
// Andrew's monotone chain; returns the hull counter-clockwise in canvas
// coordinates (interior on the left of each edge), collinear points dropped.
function convexHull(points){
  if(points.length<3)return points.slice();
  const sorted=points.slice().sort((a,b)=>a.x-b.x||a.y-b.y);
  const cross=(o,a,b)=>(a.x-o.x)*(b.y-o.y)-(a.y-o.y)*(b.x-o.x);
  const lower=[];
  for(const point of sorted){
    while(lower.length>=2&&cross(lower[lower.length-2],lower[lower.length-1],point)<=0)lower.pop();
    lower.push(point);
  }
  const upper=[];
  for(let index=sorted.length-1;index>=0;index--){
    const point=sorted[index];
    while(upper.length>=2&&cross(upper[upper.length-2],upper[upper.length-1],point)<=0)upper.pop();
    upper.push(point);
  }
  lower.pop();upper.pop();
  return lower.concat(upper);
}
// Do segments ab and cd properly cross (sharing an endpoint does not count)?
const orient=(p,q,r)=>(q.x-p.x)*(r.y-p.y)-(q.y-p.y)*(r.x-p.x);
function segmentsCross(a,b,c,d){
  const o1=orient(a,b,c),o2=orient(a,b,d);
  if(!((o1>0&&o2<0)||(o1<0&&o2>0)))return false;
  const o3=orient(c,d,a),o4=orient(c,d,b);
  return (o3>0&&o4<0)||(o3<0&&o4>0);
}
// Concave hull: Park & Oh edge digging on the convex hull. Every edge longer
// than maxEdge is replaced by two edges through the interior member nearest
// that edge's LINE whose foot lies within the segment. Any member inside the
// removed triangle would be nearer the edge than the chosen one, so digging
// to the nearest never drops a member outside; a dig whose new edges would
// cross the outline is skipped, so the polygon stays simple. Deterministic:
// the seed hull is ordered, edges are visited in order and re-visited after a
// dig, ties break on the members' order. Orientation matches convexHull
// (interior on the left of each edge, cross > 0). Interior coordinates are
// staged in flat arrays: the candidate scan is the hot loop.
function concaveHull(points,maxEdge){
  const hull=convexHull(points);
  if(hull.length<3||!(maxEdge>0))return hull;
  const onHull=new Set(hull);
  const inside=points.filter(point=>!onHull.has(point));
  const count=inside.length,ix=new Float64Array(count),iy=new Float64Array(count),free=new Uint8Array(count);
  for(let k=0;k<count;k++){ix[k]=inside[k].x;iy[k]=inside[k].y;free[k]=1;}
  let remaining=count;
  const maxEdge2=maxEdge*maxEdge,cross=segmentsCross;  // bound once: a global lookup per pair is the vm's slow path
  for(let index=0;index<hull.length&&remaining;){
    const a=hull[index],b=hull[(index+1)%hull.length];
    const ax=a.x,ay=a.y,ex=b.x-ax,ey=b.y-ay,length2=ex*ex+ey*ey;
    if(length2<=maxEdge2){index++;continue;}
    let best=-1,bestDistance=1e300;
    for(let k=0;k<count;k++){
      if(!free[k])continue;
      const px=ix[k]-ax,py=iy[k]-ay;
      const along=px*ex+py*ey;
      if(along<=0||along>=length2)continue;
      // >= 0: on the interior side, or ON the edge. A member lying on a hull
      // edge is not a hull vertex (convexHull drops collinear points) and has
      // distance 0, so it must be the first dig on that edge — skipping it
      // and digging past it would leave it outside the polygon (review of
      // #1336: six of fifteen grid-aligned members fell outside their hull).
      const cross=ex*py-ey*px;
      if(cross<-1e-6)continue;
      const distance=cross*cross;         // squared perpendicular distance times length2
      if(distance<bestDistance){bestDistance=distance;best=k;}
    }
    if(best<0){index++;continue;}
    const c=inside[best];
    let crosses=false;
    for(let e=0;e<hull.length&&!crosses;e++){
      if(e===index)continue;
      const p=hull[e],q=hull[(e+1)%hull.length];
      if(cross(a,c,p,q)||cross(c,b,p,q))crosses=true;
    }
    if(crosses){index++;continue;}
    hull.splice(index+1,0,c);free[best]=0;remaining--;
  }
  return hull;
}
// Label text width. The node vm's recording context cannot measure text
// (width 0); 11px ui-monospace runs ~6.6px per glyph, so that estimate stands
// in wherever a measurement is unavailable and the placement stays testable.
function hullLabelWidth(text){
  const measured=bgctx.measureText(text).width;
  return measured>0?measured:text.length*6.6;
}
const rectsOverlap=(a,b)=>a.x0<b.x1&&b.x0<a.x1&&a.y0<b.y1&&b.y0<a.y1;
// Where a capability's name may sit: above the hull (centred, then hugging
// either corner), below it likewise, then left, then right. The first slot
// whose text box is inside the canvas, clear of every label already placed
// and clear of every on-screen node's painted glyph wins;
// a name with no free slot is hidden rather than printed over something.
// The focused capability chooses first, then bigger regions, so the map's
// main areas keep their names.
function placeHullLabels(hulls,nodeBoxes,bounds){
  const gap=4,half=HULL_LABEL_LINE/2;
  const placed=[];
  hulls.sort((a,b)=>(b.c===clusterFocus)-(a.c===clusterFocus)||b.members-a.members||a.c.localeCompare(b.c));
  for(const entry of hulls){
    const w=hullLabelWidth(entry.title)/2+gap,{minX,maxX,minY,maxY,pad,reach}=entry;
    const cx=(minX+maxX)/2,cy=(minY+maxY)/2;
    // The hull runs through node CENTRES; the widest painted glyph on its rim
    // reaches `reach` past it, so the name clears that, not just the pad.
    const clear=Math.max(pad,reach)+gap;
    const above=minY-clear-half,below=maxY+clear+half;
    // Every slot lies within this margin of the hull's box, so only the nodes
    // inside it can collide; one pass over the nodes per hull, not per slot.
    const margin={x0:minX-clear-2*w,x1:maxX+clear+2*w,y0:above-half,y1:below+half};
    const nearby=nodeBoxes.filter(node=>rectsOverlap(margin,node));
    const slots=[
      {x:cx,y:above},{x:minX+w,y:above},{x:maxX-w,y:above},
      {x:cx,y:below},{x:minX+w,y:below},{x:maxX-w,y:below},
      {x:minX-clear-w,y:cy},{x:maxX+clear+w,y:cy},
    ];
    entry.label=null;
    for(const slot of slots){
      const box={x0:slot.x-w,x1:slot.x+w,y0:slot.y-half,y1:slot.y+half};
      if(box.x0<bounds.left||box.x1>bounds.right||box.y0<bounds.top||box.y1>bounds.bottom)continue;
      if(placed.some(other=>rectsOverlap(box,other)))continue;
      if(nearby.some(node=>rectsOverlap(box,node)))continue;
      entry.label={x:slot.x,y:slot.y,box,leader:null};break;
    }
    if(!entry.label)entry.label=placeHullLabelOnRing(entry,w,half,placed,nodeBoxes,bounds);
    placed.push(entry.label.box);
  }
}
// A name with no free slot beside its hull (iteration 3: "Automation" hid at
// rest in the crowded centre) walks outward on rings around the hull until a
// spot is clear of every node and every placed name, and draws a leader back
// to the hull. The node boxes are rasterised into a coarse occupancy grid
// once per pass, so each candidate costs a handful of cell reads. Should the
// whole canvas be occupied, the name still prints at its first slot clamped
// inside the canvas: a name is never dropped.
let hullLabelGrid=null;
function hullLabelOccupancy(nodeBoxes,bounds){
  if(hullLabelGrid)return hullLabelGrid;
  const cell=HULL_LABEL_GRID,cols=Math.ceil(W/cell)+1,rows=Math.ceil(H/cell)+1;
  const cells=new Uint8Array(cols*rows);
  const clampCol=v=>{ const c=(v/cell)|0; return c<0?0:(c>cols-1?cols-1:c); };
  const clampRow=v=>{ const r=(v/cell)|0; return r<0?0:(r>rows-1?rows-1:r); };
  for(const box of nodeBoxes){
    const c0=clampCol(box.x0),c1=clampCol(box.x1),r0=clampRow(box.y0),r1=clampRow(box.y1);
    for(let r=r0;r<=r1;r++)for(let c=c0;c<=c1;c++)cells[r*cols+c]=1;
  }
  const occupied=box=>{
    const c0=clampCol(box.x0),c1=clampCol(box.x1),r0=clampRow(box.y0),r1=clampRow(box.y1);
    for(let r=r0;r<=r1;r++)for(let c=c0;c<=c1;c++)if(cells[r*cols+c])return true;
    return false;
  };
  return hullLabelGrid={occupied};
}
// The ring directions, top first then alternating sides, so a name prefers
// to sit above its hull; computed once.
const HULL_LABEL_RING_ANGLES=Array.from({length:HULL_LABEL_RING_DIRECTIONS},(_,d)=>{
  const angle=-Math.PI/2+(d%2?1:-1)*Math.ceil(d/2)*2*Math.PI/HULL_LABEL_RING_DIRECTIONS;
  return [Math.cos(angle),Math.sin(angle)];
});
function placeHullLabelOnRing(entry,w,half,placed,nodeBoxes,bounds){
  const {minX,maxX,minY,maxY,pad,reach}=entry;
  const cx=(minX+maxX)/2,cy=(minY+maxY)/2,halfW=(maxX-minX)/2,halfH=(maxY-minY)/2;
  const clear=(pad>reach?pad:reach)+4;
  const grid=hullLabelOccupancy(nodeBoxes,bounds);
  const maxRing=Math.ceil(Math.max(W,H)/HULL_LABEL_RING_STEP);
  for(let ring=1;ring<=maxRing;ring++){
    const offset=clear+ring*HULL_LABEL_RING_STEP;
    for(const [cos,sin] of HULL_LABEL_RING_ANGLES){
      const x=cx+(halfW+w+offset)*cos,y=cy+(halfH+half+offset)*sin;
      const box={x0:x-w,x1:x+w,y0:y-half,y1:y+half};
      if(box.x0<bounds.left||box.x1>bounds.right||box.y0<bounds.top||box.y1>bounds.bottom)continue;
      if(placed.some(other=>rectsOverlap(box,other)))continue;
      if(grid.occupied(box))continue;
      return {x,y,box,leader:hullLeader(entry,box)};
    }
  }
  const x=Math.min(bounds.right-w,Math.max(bounds.left+w,cx));
  const y=Math.min(bounds.bottom-half,Math.max(bounds.top+half,minY-clear-half));
  return {x,y,box:{x0:x-w,x1:x+w,y0:y-half,y1:y+half},leader:null};
}
// Leader from the label box edge nearest the hull to the hull vertex nearest
// the label; null when the label already touches the hull's box.
function hullLeader(entry,box){
  const cx=(box.x0+box.x1)/2,cy=(box.y0+box.y1)/2;
  let vertex=null,best=Infinity;
  for(const point of entry.hull){
    const d=Math.hypot(point.x-cx,point.y-cy);
    if(d<best){best=d;vertex=point;}
  }
  if(!vertex)return null;
  const gap=Math.max(entry.pad,entry.reach)+4;
  if(vertex.x>=box.x0-gap&&vertex.x<=box.x1+gap&&vertex.y>=box.y0-gap&&vertex.y<=box.y1+gap)return null;
  // Exit the box where the line to the vertex leaves it.
  const dx=vertex.x-cx,dy=vertex.y-cy;
  const sx=dx!==0?Math.abs((box.x1-box.x0)/2/dx):Infinity,sy=dy!==0?Math.abs((box.y1-box.y0)/2/dy):Infinity;
  const t=Math.min(sx,sy)*1.15;
  return {x0:cx+dx*t,y0:cy+dy*t,x1:vertex.x,y1:vertex.y};
}
// Where a capability name may be printed: the canvas interaction bounds less
// the snail-trails dock (#historydock), which is fixed over the bottom of the
// canvas — a name placed under it is as good as dropped (review of #1336: at
// 1000x700 "Platform Shell" sat under the dock). The vm's DOM stub reports a
// whole-viewport rect for every element (top 0), which cannot be a dock, so
// only a rect that starts below the interaction top counts.
function hullLabelBounds(){
  const bounds=canvasInteractionBounds();
  const dock=document.getElementById('historydock');
  const rect=dock&&typeof dock.getBoundingClientRect==='function'?dock.getBoundingClientRect():null;
  if(rect&&rect.height>0&&rect.top>bounds.top&&rect.top<bounds.bottom)bounds.bottom=rect.top-4;
  return bounds;
}
function computeCapabilityHulls(){
  const started=performance.now();
  const members=new Map(),radii=new Map(),reach=new Map(),nodeBoxes=[];
  DATA.nodes.forEach((n,i)=>{
    const p=P[i];if(!p.on)return;
    let list=members.get(n.c);if(!list){list=[];members.set(n.c,list);radii.set(n.c,0);reach.set(n.c,0);}
    const r=nodeRadius(i),painted=nodePaintRadius(i);
    list.push({x:p.x,y:p.y});radii.set(n.c,radii.get(n.c)+r);
    if(painted>reach.get(n.c))reach.set(n.c,painted);
    // A node blended into the sky by cluster focus is background; a name may
    // sit over it, but never over a node that is actually legible.
    if(clusterTier(n.c)>=FOCUS_BACKGROUND_TIER)
      nodeBoxes.push({x0:p.x-painted,x1:p.x+painted,y0:p.y-painted,y1:p.y+painted});
  });
  const hulls=[];
  for(const [c,list] of members){
    if(list.length<HULL_MIN_NODES)continue;
    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    for(const point of list){
      if(point.x<minX)minX=point.x;if(point.x>maxX)maxX=point.x;
      if(point.y<minY)minY=point.y;if(point.y>maxY)maxY=point.y;
    }
    const pad=1.5*radii.get(c)/list.length;
    if(maxX-minX+2*pad<HULL_MIN_WIDTH)continue;
    // Mean member spacing from the bounding area; the dig length follows it,
    // so the outline hugs the epic clumps at any zoom.
    const spacing=Math.sqrt(Math.max(1,(maxX-minX)*(maxY-minY))/list.length);
    const hull=concaveHull(list,Math.max(HULL_DIG_SPACINGS*spacing,2*pad));
    if(hull.length<3)continue;
    hulls.push({c,title:capabilityTitle(c),members:list.length,hull,pad,reach:reach.get(c),minX,maxX,minY,maxY});
  }
  bgctx.font=HULL_LABEL_FONT;
  hullLabelGrid=null;
  placeHullLabels(hulls,nodeBoxes,hullLabelBounds());
  hullComputeMs=performance.now()-started;
  return hulls;
}
function capabilityHulls(){
  let onCount=0,onSum=0;
  for(let i=0;i<P.length;i++)if(P[i].on){onCount++;onSum+=i;}
  const key=[rx,ry,zoom,panX,panY,cc.x,cc.y,cc.z,W,H,sizeMode,clusterFocus,onCount,onSum].join(',');
  if(key!==hullCache.key)hullCache={key,hulls:computeCapabilityHulls()};
  return hullCache.hulls;
}
// Trace the hull offset outward by pad: each edge shifted along its outward
// normal, each convex vertex rounded with an arc, each reflex vertex (a
// concave notch) joined at the mitre of its two offset edges, so the region
// hugs the members without the doubled seam a fill-plus-wide-stroke would paint.
function traceExpandedHull(hull,pad){
  const count=hull.length;
  ctx.beginPath();
  for(let index=0;index<count;index++){
    const previous=hull[(index+count-1)%count],vertex=hull[index],next=hull[(index+1)%count];
    const turn=(vertex.x-previous.x)*(next.y-vertex.y)-(vertex.y-previous.y)*(next.x-vertex.x);
    const inAngle=Math.atan2(-(vertex.x-previous.x),vertex.y-previous.y);
    const outAngle=Math.atan2(-(next.x-vertex.x),next.y-vertex.y);
    if(turn>=0){ctx.arc(vertex.x,vertex.y,pad,inAngle,outAngle,true);continue;}
    const n1x=Math.cos(inAngle),n1y=Math.sin(inAngle),n2x=Math.cos(outAngle),n2y=Math.sin(outAngle);
    const dot=1+n1x*n2x+n1y*n2y;
    if(dot<.2){ctx.lineTo(vertex.x+n1x*pad,vertex.y+n1y*pad);ctx.lineTo(vertex.x+n2x*pad,vertex.y+n2y*pad);continue;}
    ctx.lineTo(vertex.x+(n1x+n2x)*pad/dot,vertex.y+(n1y+n2y)*pad/dot);
  }
  ctx.closePath();
}
// In cluster focus only the focused capability's region reads at full
// strength; the others recede with their nodes.
const hullTier = c => clusterFocus&&c!==clusterFocus?HULL_DIM_TIER:1;
function drawCapabilityRegions(){
  const hulls=capabilityHulls();
  if(!hulls.length)return;
  ctx.font=HULL_LABEL_FONT;ctx.textAlign='center';ctx.textBaseline='middle';
  for(const {c,title,hull,pad,label} of hulls){
    const tier=hullTier(c);
    // A third toward the ink so the fill reads on the sky in either theme.
    const color=rgbCss(mixA(capabilityColor(c),RGB.ink,.3));
    ctx.globalAlpha=HULL_ALPHA*tier;ctx.fillStyle=color;
    traceExpandedHull(hull,pad);ctx.fill();
    if(!label)continue;
    ctx.globalAlpha=HULL_LABEL_ALPHA*tier;
    ctx.fillText(title,label.x,label.y);
    if(!label.leader)continue;
    ctx.globalAlpha=HULL_LABEL_ALPHA*tier*.6;ctx.strokeStyle=color;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(label.leader.x0,label.leader.y0);ctx.lineTo(label.leader.x1,label.leader.y1);ctx.stroke();
  }
  ctx.globalAlpha=1;
}
function draw(){
  bgctx.clearRect(0,0,W,H);nodeCtx.clearRect(0,0,W,H);ctx=bgctx;
  const bounds=canvasInteractionBounds();
  for(const context of [bgctx,nodeCtx]){
    context.save();context.beginPath();context.rect(bounds.left,bounds.top,
      Math.max(0,bounds.right-bounds.left),Math.max(0,bounds.bottom-bounds.top));context.clip();
  }
  drawCapabilityRegions(bounds);
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
    ctx.globalAlpha = (lit ? .9 : (activeCount===2?.62:.27))*(searchEdgeDim?.16:1)*Math.min(clusterTier(DATA.nodes[a].c),clusterTier(DATA.nodes[b].c));
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
    ctx.strokeStyle = C.active; ctx.globalAlpha = (lit?.75:(activeCount===2?.55:.22))*(searchEdgeDim?.16:1)*Math.min(clusterTier(DATA.nodes[a].c),clusterTier(DATA.nodes[b].c));
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
        // Offscreen endpoints are not filtered endpoints. The canvas clip keeps
        // crossing segments visible as orbiting moves their nodes behind chrome.
        if(a==null||b==null||!P[a]||!P[b]||!visible(DATA.nodes[a])||!visible(DATA.nodes[b]))continue;
        if(![P[a].x,P[a].y,P[b].x,P[b].y].every(Number.isFinite))continue;
        const recency=step/Math.max(1,points.length-1);
        const previous=(step-1)/Math.max(1,points.length-1);
        const searchEdgeDim=searchTerms.length>0&&!searchMatches[a]&&!searchMatches[b];
        const alpha=.12+.76*recency*recency;
        const startAlpha=.12+.76*previous*previous;
        const gradient=ctx.createLinearGradient(P[a].x,P[a].y,P[b].x,P[b].y);
        const rgb=rgbOf(color).join(',');
        gradient.addColorStop(0,`rgba(${rgb},${startAlpha})`);
        gradient.addColorStop(1,`rgba(${rgb},${alpha})`);
        ctx.strokeStyle=gradient;ctx.lineWidth=1.4;ctx.globalAlpha=searchEdgeDim?.16:1;
        ctx.beginPath();ctx.moveTo(P[a].x,P[a].y);ctx.lineTo(P[b].x,P[b].y);ctx.stroke();
        trailArrow(P[a],P[b],color,alpha*(searchEdgeDim?.16:1));
      }
    }
  }
  // Rolling session history is a separate, time-bounded overlay. It never
  // changes graph topology or Story lifecycle state.
  if(typeof drawSessionHistory==='function')drawSessionHistory();
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
    const dim=(sel>=0&&!selSet.has(i))||searchDim||outsideCluster(DATA.nodes[i])||focusBackground(i);
    const rgb=nodeColor(n),rec=lens.delivery&&n.rec&&!dim;
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
    const dim = (sel>=0 && !selSet.has(i)) || searchDim || outsideCluster(n) || focusBackground(i);
    let rgb = nodeColor(n);
    const rec = lens.delivery && n.rec && !dim;
    if (rec) rgb = mixA(rgb, [255,255,255], .55); // ★ next: brighter lightness
    const clusterActive=Boolean(capFocus||groupFocus)&&!outsideCluster(n);
    rgb=contrastNodeColor(dim?RGB.fade:rgb,dim?3.1:(clusterActive?7:4.5));
    if(focusBackground(i))rgb=nodePaintColor(rgb,clusterTier(n.c),clusterTier(n.c));
    const col = rgbCss(rgb);
    const focusAlpha=(dim?.18:1)*clusterTier(n.c);
    ctx.globalAlpha = progressOpacity(n)*focusAlpha;
    const rr = nodeRadius(i);
    // Build one lifecycle path. Hollow/round nodes carry version in this same
    // stroke instead of acquiring a second concentric version circle.
    if(n.g==='shipped')trianglePath(p.x,p.y,rr);
    else if(n.g==='buggap')xPath(p.x,p.y,rr*.7);
    else {ctx.beginPath();ctx.arc(p.x,p.y,n.g==='specced'?rr*.85:rr,0,7);}
    if(n.g!=='specced'&&drawsHollowCircle(n)){ctx.fillStyle=col;ctx.fill();}
    ctx.globalAlpha=1;ctx.strokeStyle=col;
    const outlineWidth=clusterActive&&!dim?3:2.5;
    // Width, rather than opacity, preserves upstream's essential outline
    // contrast while conveying the release horizon on the shared circle.
    ctx.lineWidth=outlineWidth*(drawsHollowCircle(n)?Math.max(.35,versionOpacity(n)):1);
    ctx.stroke();
    // Non-circular glyphs retain a separate version ring.
    if(!drawsHollowCircle(n)){
      ctx.globalAlpha=versionOpacity(n)*focusAlpha; ctx.strokeStyle=col;ctx.lineWidth=1;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.16,0,7); ctx.stroke();
    }
    const testReview=latestTestReview(i);
    if(testReview&&!dim){
      const isC=testReview.risk==='C',visual=testReviewVisualState(testReview,{active:activeWave,slow:xWave,reduced:reducedMotion});
      const outcomeColor={pass:C.shipped,'expected-red':C.ready,'unexpected-fail':C.buggap,partial:C.active,inconclusive:C.specced,'infrastructure-failure':C.conflict,invalidated:C.buggap,cancelled:C.faint};
      ctx.globalAlpha=(visual.moving?(reducedMotion?.92:.42+.58*visual.wave):.86)*fog;
      ctx.strokeStyle=visual.snag?C.buggap:(visual.reviewing?C.owner:(outcomeColor[testReview.outcome]||C.active));ctx.lineWidth=visual.snag?4:(isC?3:1.7);ctx.setLineDash(visual.dash);
      const radius=rr*((isC?2.12:1.82)+(visual.preparing?.16:visual.reviewing?.08:visual.running?.24:0)*visual.wave);
      ctx.beginPath();ctx.arc(p.x,p.y,radius,0,7);ctx.stroke();ctx.setLineDash([]);
      if(testReview.outcome!=='pending'){ctx.globalAlpha=.96*fog;ctx.fillStyle=outcomeColor[testReview.outcome]||C.owner;ctx.font=`700 ${Math.max(8,rr*.72)}px ui-monospace`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(visual.outcomeBadge,p.x+rr*1.7,p.y-rr*1.7);}
      if(reducedMotion&&visual.moving){ctx.globalAlpha=.98*fog;ctx.fillStyle=visual.snag?C.buggap:C.owner;ctx.font=`700 ${Math.max(8,rr*.68)}px ui-monospace`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(visual.stateLabel,p.x-rr*1.7,p.y-rr*1.7);}
    }
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
      ctx.globalAlpha=.9; ctx.strokeStyle=rgbCss(mixA(rgb,RGB.ink,.8)); ctx.lineWidth=1.25;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.38,0,7); ctx.stroke();
    }
    if(i===sel){
      ctx.globalAlpha=1; ctx.strokeStyle=C.shipped; ctx.lineWidth=1.5;
      ctx.beginPath(); ctx.arc(p.x,p.y,rr*1.58,0,7); ctx.stroke();
    }
    if (rec){ // recommended-next: bright ring over its background glow
      ctx.globalAlpha = 1;
      ctx.strokeStyle = rgbCss(mixA(rgb,RGB.ink,.7)); ctx.lineWidth = 1;
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
    const dim=(sel>=0&&!selSet.has(i))||searchDim||outsideCluster(DATA.nodes[i])||focusBackground(i);
    if(!unresolved.length||dim)continue;
    ctx.globalAlpha=.95;ctx.strokeStyle=C.owner;ctx.lineWidth=1.5;
    xPath(p.x,p.y,Math.max(4,rr*.72));ctx.stroke();
    if(unresolved.length>1){ctx.fillStyle=C.owner;ctx.font=`${Math.max(6,rr*.52)}px ui-monospace,monospace`;ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(String(unresolved.length),p.x+rr*.82,p.y);}
  }
  ctx.globalAlpha = 1;ctx=nodeCtx;
  for(const context of [bgctx,nodeCtx])context.restore();
}
const snapCam = reducedMotion;
function restZoom(){
  const reach=Math.max(0,...Object.values(capReach));
  const radius=R+reach,bounds=hullLabelBounds();
  const target=.4*Math.min(bounds.right-bounds.left,bounds.bottom-bounds.top);
  if(!(radius>0)||!(target>0))return 1;
  let z=1;
  for(let step=0;step<8;step++){const F=900*z;z=target/(radius*F/(F+520));}
  return Math.min(3.4,Math.max(1,z));
}
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
    // In capability focus the rest of the constellation is scenery. It stays
    // visibly contextual but cannot steal a hover or a click through the
    // selected capability.
    if(!p.on||focusBackground(i)){p.near=0;continue;}
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
let downHistoryTarget=null,presentedHover=-1;
function presentPointerState(x,y){
  const best=hover,tip=document.getElementById('tip');
  const workTrail=typeof historyTrailAtPointer==='function'
    ?historyTrailAtPointer(x,y,best):null;
  if(workTrail){
    const s=historySession(workTrail.session);
    tip.innerHTML=esc(s?.provider+' · '+s?.title)+
      `<small>${esc(historyDate(workTrail.timestamp))} · click for work, rationale and challenges</small>`;
    tip.style.display='block';tip.style.left=(x+14)+'px';tip.style.top=(y+10)+'px';
    cv.classList.add('hover-target');presentedHover=-1;return;
  }
  if(best>=0){
    if(presentedHover!==best){
      const n=DATA.nodes[best];
      const live=(n.aw||[]).map(wi=>DATA.work[wi]).filter(freshWork);
      const liveText=live.length?` · ${live.map(w=>w.total?w.done+'/'+w.total:'0/0').join(', ')} checkpoints`:'';
      const trailText=lens.progress&&progressText(n)?` · ${progressText(n)}`:'';
      const opacityText=` · ${Math.round(progressOpacity(n)*100)}% progress fill · ${Math.round(versionOpacity(n)*100)}% version ${versionChannelName(n)}`;
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
  downHistoryTarget=typeof historyTrailAtPointer==='function'
    ?historyTrailAtPointer(e.clientX,e.clientY,downTarget):null;
  if(downHistoryTarget)downTarget=-1;
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
    if(downHistoryTarget){
      historyQueueClick(downHistoryTarget,e.clientX,e.clientY);downHistoryTarget=null;
    }else if(target>=0)openNode(target);
    else if(typeof hitSessionHistory==='function'){
      const segment=hitSessionHistory(e.clientX,e.clientY);
      if(segment)historyQueueClick(segment,e.clientX,e.clientY);
    }
    publishHitDebug('up',e,{opened:target,pointerType:e.pointerType||'unknown'});
  }else{
    project();updatePointerAt(e.clientX,e.clientY);
    publishHitDebug('orbit-up',e,{opened:-1,pointerType:e.pointerType||'unknown'});
  }
  downTarget=-1;
});
cv.addEventListener('pointercancel',e=>{
  pointerDown=false;orbiting=false;downTarget=-1;downHistoryTarget=null;cv.classList.remove('drag');clearPointerState();
  releasePointer(e);
});
cv.addEventListener('dblclick',e=>{
  updatePointerState(e.clientX,e.clientY);
  if(typeof historyDoubleClick==='function'&&historyDoubleClick(e.clientX,e.clientY,hover)){
    e.preventDefault();
  }
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
