const fs=require('fs'),os=require('os'),path=require('path');
const {spawn}=require('child_process');

(async()=>{
const chrome=process.argv[2],url=process.argv[3];
if(!chrome||!url)throw new Error('usage: browser_live_constellation_matrix.js <chrome> <url>');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'vizzer-constellation-matrix-'));
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const waitFor=async(fn,label,timeout=10000)=>{
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){try{const value=await fn();if(value)return value;}catch(_){}await delay(40);}
  throw new Error(`timed out waiting for ${label}`);
};
let browser,socket;
try{
  browser=spawn(chrome,['--headless=new','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,url],
    {stdio:'ignore'});
  const active=path.join(profile,'DevToolsActivePort');
  const debugPort=await waitFor(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0],
    'DevTools port');
  const target=await waitFor(async()=>{
    const targets=await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
    return targets.find(candidate=>candidate.type==='page'&&candidate.url.startsWith(url.split('#')[0]));
  },'live Vizzer page');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let nextId=0;const pending=new Map();
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(!message.id)return;
    const slot=pending.get(message.id);if(!slot)return;pending.delete(message.id);
    message.error?slot.reject(new Error(message.error.message)):slot.resolve(message.result);});
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++nextId;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{
    const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
    return result.result.value;
  };
  const clickPoint=async({x,y})=>{
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});
    await send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});
  };
  await send('Runtime.enable');await send('Page.enable');
  await waitFor(()=>evaluate(`document.readyState==='complete'&&typeof switchView==='function'&&
    document.getElementById('boot').hidden`),'Vizzer boot');
  await waitFor(()=>evaluate(`questionContext&&questionContext.engineVersion===ENGINE_VERSION`),
    'question authority');

  const structure=await evaluate(`(()=>{
    switchView('structure');
    const roots=[...document.querySelectorAll('.structuregroup.depth-0>summary b')]
      .map(element=>element.textContent.trim());
    const foundationGroups=(DATA.groups||[]).filter(group=>group.kind==='foundation');
    const sourceBacked=(DATA.groups||[]).filter(group=>group.p);
    const contractControls=[...document.querySelectorAll('[data-open-group],.structurecontract a')];
    const sourceById=new Map((DATA.groups||[]).map(group=>[group.id,group.p||'']));
    const sourceByHref=new Map((DATA.groups||[]).map(group=>[group.h||'',group.p||'']));
    const sourceDocs=new Set(sourceBacked.map(group=>group.p));
    const visibleSourceDocs=new Set(contractControls.map(element=>
      sourceById.get(element.dataset.openGroup)||sourceByHref.get(element.getAttribute('href'))||''
    ).filter(Boolean));
    const foundationControls=[...document.querySelectorAll('[data-open-group^="foundation:"],.structurecontract a')]
      .filter(element=>foundationGroups.some(group=>
        element.dataset.openGroup===group.id||element.getAttribute('href')===group.h));
    return{roots,foundationGroups:foundationGroups.length,sourceBacked:sourceBacked.length,
      sourceDocs:sourceDocs.size,visibleSourceDocs:visibleSourceDocs.size,
      contractControls:contractControls.length,foundationControls:foundationControls.length,
      headingVisible:viewPanel.textContent.includes('Project hierarchy')};
  })()`);
  if(!structure.roots.length)throw new Error('Hierarchy view rendered no root groups');
  if(structure.sourceBacked&&!structure.contractControls)
    throw new Error('Hierarchy view hid all source-backed contracts');
  if(structure.visibleSourceDocs!==structure.sourceDocs)
    throw new Error(`Hierarchy view exposed ${structure.visibleSourceDocs}/${structure.sourceDocs} source documents`);
  if(structure.foundationControls!==structure.foundationGroups)
    throw new Error(`Hierarchy view exposed ${structure.foundationControls}/${structure.foundationGroups} foundation contracts`);
  if(!structure.headingVisible)
    throw new Error('Hierarchy view lost its visible heading');
  await evaluate(`switchView('constellation')`);

  const poses=[
    {name:'wide-all-time',width:1280,height:800,dpr:1,rx:-.35,ry:.6,zoom:1,size:'time',filter:'all'},
    {name:'wide-retina-rotated',width:1280,height:800,dpr:2,rx:.58,ry:1.12,zoom:1.2,size:'delivery',filter:'question'},
    {name:'wide-fractional-scale',width:1280,height:800,dpr:1.5,rx:-.61,ry:-.28,zoom:.9,size:'time',filter:'question'},
    {name:'wide-page-scale-up',width:1280,height:800,dpr:2,pageScale:1.25,rx:.31,ry:-.92,zoom:1.15,size:'delivery',filter:'question'},
    {name:'wide-page-scale-down',width:1280,height:800,dpr:2,pageScale:.8,rx:-.22,ry:1.48,zoom:1.35,size:'time',filter:'question'},
    {name:'wide-min-graph-zoom',width:1280,height:800,dpr:1,rx:.73,ry:-.56,zoom:.45,size:'time',filter:'question'},
    {name:'wide-max-graph-zoom',width:1280,height:800,dpr:1,rx:-.19,ry:1.73,zoom:3.4,size:'delivery',filter:'all'},
    {name:'wide-all-roles',width:1280,height:800,rx:.47,ry:.67,zoom:1.05,size:'delivery',filter:'all-roles'},
    {name:'wide-support-role',width:1280,height:800,rx:-.38,ry:1.31,zoom:.95,size:'time',filter:'support-role'},
    {name:'wide-capability',width:1280,height:800,rx:.15,ry:-.72,zoom:1.3,size:'delivery',filter:'capability'},
    {name:'wide-area',width:1280,height:800,rx:-.66,ry:.91,zoom:1.1,size:'time',filter:'area'},
    {name:'wide-status-release',width:1280,height:800,rx:.52,ry:-.19,zoom:1.25,size:'delivery',filter:'status-release'},
    {name:'wide-question-capability',width:1280,height:800,rx:-.41,ry:1.04,zoom:1.4,size:'time',filter:'question-capability'},
    {name:'wide-question-delivery',width:1280,height:800,rx:.18,ry:.82,zoom:1.45,size:'delivery',filter:'question'},
    {name:'wide-release-rotated',width:1280,height:800,rx:-.72,ry:.15,zoom:.72,size:'time',filter:'release'},
    {name:'medium-all-close',width:900,height:600,rx:.44,ry:1.18,zoom:1.7,size:'delivery',filter:'all'},
    {name:'medium-active',width:900,height:600,rx:-.1,ry:-.45,zoom:1.1,size:'time',filter:'active'},
    {name:'tablet-question',width:760,height:520,rx:.62,ry:.25,zoom:1.3,size:'delivery',filter:'question'},
    {name:'tablet-ready',width:760,height:520,rx:-.55,ry:1.4,zoom:.82,size:'time',filter:'ready'},
    {name:'compact-all',width:420,height:520,rx:.25,ry:.95,zoom:1,size:'delivery',filter:'all'},
    {name:'compact-question',width:360,height:320,rx:-.48,ry:.38,zoom:.78,size:'time',filter:'question'},
    {name:'compact-question-close',width:360,height:320,rx:.7,ry:1.25,zoom:1.5,size:'delivery',filter:'question'},
  ];
  const audit={engineVersion:await evaluate('ENGINE_VERSION'),structure,poses:[],centerCases:0,
    advertisedTargetCases:0,decorativeRingStoryCases:0,failures:[]};
  for(const pose of poses){
    await send('Emulation.setDeviceMetricsOverride',{width:pose.width,height:pose.height,
      deviceScaleFactor:pose.dpr||1,mobile:false});
    await send('Emulation.setPageScaleFactor',{pageScaleFactor:pose.pageScale||1});
    await waitFor(()=>evaluate(`innerWidth===${pose.width}&&innerHeight===${pose.height}`),`${pose.name} viewport`);
    const setup=await evaluate(`(()=>{
      dismissDossier({focusCanvas:false});switchView('constellation');
      for(const key of Object.keys(filt))filt[key]=true;
      for(const key of Object.keys(rfilt))rfilt[key]=true;
      questionOnly=false;roleFocus=availableRoles.includes('delivery')?'delivery':'all';
      capFocus=null;areaFocus=null;areaMode=areaDefinitions[0]?.id||null;
      searchTerms=[];searchMatches=DATA.nodes.map(()=>true);
      const mode=${JSON.stringify(pose.filter)};
      if(mode==='question')questionOnly=true;
      if(mode==='active'||mode==='ready')for(const key of Object.keys(filt))filt[key]=key===mode;
      if(mode==='release'){
        const release=Object.keys(rfilt).find(key=>key!=='unversioned')||Object.keys(rfilt)[0];
        for(const key of Object.keys(rfilt))rfilt[key]=key===release;
      }
      if(mode==='all-roles')roleFocus='all';
      if(mode==='support-role')roleFocus=availableRoles.find(role=>role!=='delivery')||roleFocus;
      if(mode==='capability'||mode==='question-capability'){
        if(mode==='question-capability')questionOnly=true;
        const counts=new Map();for(const node of DATA.nodes)if(!node.foundation&&passesSharedFilters(node))
          counts.set(node.c,(counts.get(node.c)||0)+1);
        capFocus=[...counts].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0]?.[0]||null;
      }
      if(mode==='area'&&hasAreaFacets){
        const area=currentArea(),counts=new Map(area.values.map(value=>[value,0]));
        for(const node of DATA.nodes)for(const value of (node.facets?.[area.facet]||[]))
          if(counts.has(value))counts.set(value,counts.get(value)+1);
        areaFocus=[...counts].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0]?.[0]||null;
      }
      if(mode==='status-release'){
        let winner=null;
        for(const group of Object.keys(filt))for(const release of RELS){
          const count=DATA.nodes.filter(node=>!node.foundation&&node.g===group&&relKey(node)===release&&
            (node.role||'delivery')===roleFocus&&passesAreaFilters(node)).length;
          if(!winner||count>winner.count)winner={group,release,count};
        }
        if(winner){for(const key of Object.keys(filt))filt[key]=key===winner.group;
          for(const key of Object.keys(rfilt))rfilt[key]=key===winner.release;}
      }
      size();sizeMode=${JSON.stringify(pose.size)};rx=${pose.rx};ry=${pose.ry};zoom=${pose.zoom};panX=0;panY=0;
      cc={...ct};vx=0;vy=0;project();draw();
      const order=DATA.nodes.map((_,index)=>index).filter(index=>P[index].on).sort((a,b)=>P[a].d-P[b].d);
      const semanticOwner=(x,y)=>{
        const glyphs=order.map(index=>({index,miss:ownerQuestions(index).length?
          questionGlyphPaintDistance(index,x,y):Infinity,depth:P[index].d}))
          .filter(value=>value.miss<=2.5).sort((a,b)=>a.miss-b.miss||a.depth-b.depth);
        return glyphs.length?glyphs[0].index:-1;
      };
      const eligible=[];
      for(const index of order){
        const p=P[index],semantic=semanticOwner(p.x,p.y);
        if(semantic>=0&&semantic!==index)continue;
        if(semantic<0){
          const paint=order.filter(candidate=>Math.hypot(P[candidate].x-p.x,P[candidate].y-p.y)<=nodePaintRadius(candidate))[0];
          if(paint!==index)continue;
        }
        if(document.elementFromPoint(p.x,p.y)!==cv)continue;
        eligible.push({index,x:p.x,y:p.y,title:DATA.nodes[index].t,question:ownerQuestions(index).length>0});
      }
      const questions=eligible.filter(value=>value.question),ordinary=eligible.filter(value=>!value.question);
      const room=Math.max(0,100-questions.length),stride=Math.max(1,Math.floor(ordinary.length/Math.max(1,room)));
      const sampled=[...questions,...ordinary.filter((_,position)=>position%stride===0).slice(0,room)];
      const canvasRect=cv.getBoundingClientRect();
      return{visible:order.length,eligible:eligible.length,targets:sampled,
        bounds:canvasInteractionBounds(),filter:mode,sizeMode,
        canvasRect:[canvasRect.left,canvasRect.top,canvasRect.width,canvasRect.height],
        canvasBacking:[cv.width,cv.height],viewport:[innerWidth,innerHeight],devicePixelRatio};
    })()`);
    const receipt={name:pose.name,viewport:[pose.width,pose.height],dpr:pose.dpr||1,
      pageScale:pose.pageScale||1,visible:setup.visible,
      eligible:setup.eligible,centerCases:0,advertisedTargetCases:0,
      decorativeRingStoryCases:0,canvasRect:setup.canvasRect,
      canvasBacking:setup.canvasBacking,cssViewport:setup.viewport,
      actualDpr:setup.devicePixelRatio,failures:[]};
    if(Math.abs(setup.canvasRect[0])>.01||Math.abs(setup.canvasRect[1])>.01||
        Math.abs(setup.canvasRect[2]-setup.viewport[0])>.01||
        Math.abs(setup.canvasRect[3]-setup.viewport[1])>.01){
      const failure={pose:pose.name,kind:'canvas-css-geometry',canvasRect:setup.canvasRect,
        backing:setup.canvasBacking,viewport:setup.viewport,dpr:setup.devicePixelRatio};
      receipt.failures.push(failure);audit.failures.push(failure);
    }
    for(const target of setup.targets){
      await evaluate(`dismissDossier({focusCanvas:false});project()`);
      const point=await evaluate(`(()=>{const p=P[${target.index}],element=document.elementFromPoint(p.x,p.y);
        return{x:p.x,y:p.y,on:p.on,element:element===cv?'cv':element?.id||element?.className||element?.tagName||null};})()`);
      receipt.centerCases++;audit.centerCases++;
      if(!point.on||point.element!=='cv'){
        const failure={pose:pose.name,kind:'center-routing',...target,point};receipt.failures.push(failure);audit.failures.push(failure);continue;
      }
      await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:point.x,y:point.y});
      const hoverState=await evaluate(`({hover,cursor:getComputedStyle(cv).cursor})`);
      if(hoverState.hover!==target.index||hoverState.cursor!=='pointer'){
        const nearby=await evaluate(`P.map((p,index)=>({index,title:DATA.nodes[index].t,on:p.on,
          distance:Math.hypot(p.x-${point.x},p.y-${point.y}),depth:p.d,
          questions:ownerQuestions(index).length,glyphMiss:ownerQuestions(index).length?
            questionGlyphPaintDistance(index,${point.x},${point.y}):null,paintRadius:nodePaintRadius(index)}))
          .filter(value=>value.on&&value.distance<20).sort((a,b)=>a.distance-b.distance)`);
        const failure={pose:pose.name,kind:'center-hover',...target,point,hoverState,nearby};receipt.failures.push(failure);audit.failures.push(failure);continue;
      }
      await clickPoint(point);
      const selected=await evaluate(`({selected:sel,open:dossier.classList.contains('open'),
        title:sel<0?'':DATA.nodes[sel].t})`);
      if(selected.selected!==target.index||!selected.open||selected.title!==target.title){
        const failure={pose:pose.name,kind:'center-selection',...target,point,selected};receipt.failures.push(failure);audit.failures.push(failure);
      }
    }
    const switchPair=await evaluate(`(()=>{
      dismissDossier({focusCanvas:false});project();draw();
      const deltas=[[5,0],[-5,0],[0,5],[0,-5],[4,3],[4,-3],[-4,3],[-4,-3]];
      const offsets=[[0,0],[3,0],[-3,0],[0,3],[0,-3]];
      for(let index=0;index<P.length;index++){
        if(!P[index].on)continue;
        for(const [ox,oy] of offsets){
          const ax=P[index].x+ox,ay=P[index].y+oy;
          if(document.elementFromPoint(ax,ay)!==cv)continue;
          updatePointerState(ax,ay);const advertised=hover;
          if(advertised<0)continue;
          for(const [dx,dy] of deltas){
            const bx=ax+dx,by=ay+dy;
            if(document.elementFromPoint(bx,by)!==cv)continue;
            updatePointerState(bx,by);const reranked=hover;
            if(reranked>=0&&reranked!==advertised){clearPointerState();return{
              ax,ay,bx,by,advertised,reranked,advertisedTitle:DATA.nodes[advertised].t,
              rerankedTitle:DATA.nodes[reranked].t};}
          }
        }
      }
      clearPointerState();return null;
    })()`);
    if(switchPair){
      receipt.advertisedTargetCases++;audit.advertisedTargetCases++;
      await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:switchPair.ax,y:switchPair.ay});
      const advertisedState=await evaluate(`({hover,presentedHover,title:presentedHover<0?'':DATA.nodes[presentedHover].t})`);
      await send('Input.dispatchMouseEvent',{type:'mousePressed',x:switchPair.bx,y:switchPair.by,button:'left',clickCount:1});
      await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:switchPair.bx,y:switchPair.by,button:'left',clickCount:1});
      const selected=await evaluate(`({selected:sel,open:dossier.classList.contains('open'),title:sel<0?'':DATA.nodes[sel].t})`);
      if(advertisedState.presentedHover!==switchPair.advertised||selected.selected!==switchPair.advertised||
          !selected.open||selected.title!==switchPair.advertisedTitle){
        const failure={pose:pose.name,kind:'advertised-target-switch',...switchPair,advertisedState,selected};
        receipt.failures.push(failure);audit.failures.push(failure);
      }
    }
    const used=[];
    for(let attempt=0;attempt<6;attempt++){
      const ring=await evaluate(`(()=>{
        dismissDossier({focusCanvas:false});project();draw();const used=new Set(${JSON.stringify(used)});
        const order=DATA.nodes.map((_,index)=>index).filter(index=>P[index].on).sort((a,b)=>P[a].d-P[b].d);
        for(const index of order){if(!actionableQuestion(index))continue;
          const radii=questionRingRadii(index);
          for(let ringIndex=0;ringIndex<radii.length;ringIndex++)for(let step=0;step<36;step++){
            const key=index+':'+ringIndex+':'+step;if(used.has(key))continue;
            const angle=step*Math.PI/18,x=P[index].x+Math.cos(angle)*radii[ringIndex],
              y=P[index].y+Math.sin(angle)*radii[ringIndex];
            if(!insideCanvasInteractionBounds(x,y)||document.elementFromPoint(x,y)!==cv)continue;
            const competingX=order.some(candidate=>candidate!==index&&ownerQuestions(candidate).length&&
              questionGlyphPaintDistance(candidate,x,y)<=2.5);if(competingX)continue;
            const oldWinner=order.find(candidate=>candidate!==index&&
              Math.hypot(P[candidate].x-x,P[candidate].y-y)<=nodePaintRadius(candidate));
            if(oldWinner==null)continue;
            return{key,index,oldWinner,x,y,title:DATA.nodes[index].t,oldTitle:DATA.nodes[oldWinner].t};
          }
        }
        return null;
      })()`);
      if(!ring)break;used.push(ring.key);receipt.decorativeRingStoryCases++;audit.decorativeRingStoryCases++;
      await clickPoint(ring);
      const selected=await evaluate(`({selected:sel,open:dossier.classList.contains('open'),title:sel<0?'':DATA.nodes[sel].t})`);
      if(selected.selected!==ring.oldWinner||!selected.open||selected.title!==ring.oldTitle){
        const failure={pose:pose.name,kind:'decorative-ring-captured-input',...ring,selected};receipt.failures.push(failure);audit.failures.push(failure);
      }
    }
    audit.poses.push(receipt);
  }
  if(audit.failures.length)throw new Error(`constellation matrix failures ${JSON.stringify(audit)}`);
  process.stdout.write(JSON.stringify(audit));
}finally{
  if(socket)socket.close();
  if(browser){const exited=new Promise(resolve=>browser.once('exit',resolve));browser.kill('SIGTERM');
    await Promise.race([exited,delay(1500)]);if(browser.exitCode==null)browser.kill('SIGKILL');}
  fs.rmSync(profile,{recursive:true,force:true,maxRetries:5,retryDelay:50});
}
})().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
