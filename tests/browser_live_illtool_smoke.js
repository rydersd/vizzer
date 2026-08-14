const fs=require('fs'),os=require('os'),path=require('path');
const {spawn}=require('child_process');

(async()=>{
const chrome=process.argv[2],url=process.argv[3];
if(!chrome||!url)throw new Error('usage: browser_live_illtool_smoke.js <chrome> <url>');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'vizzer-live-browser-'));
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const waitFor=async(fn,label,timeout=10000)=>{
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){try{const value=await fn();if(value)return value;}catch(_){}await delay(50);}
  throw new Error(`timed out waiting for ${label}`);
};
let browser,socket;
try{
  browser=spawn(chrome,['--headless=new','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,url],
    {stdio:'ignore'});
  const active=path.join(profile,'DevToolsActivePort');
  const debugPort=await waitFor(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0],'DevTools port');
  const target=await waitFor(async()=>{
    const targets=await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
    return targets.find(candidate=>candidate.type==='page'&&candidate.url.startsWith(url.split('#')[0]));
  },'live IllTool page');
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
    await send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});
  };
  const rectCenter=expression=>evaluate(`(()=>{const element=${expression};if(!element)throw new Error('target missing');
    element.scrollIntoView({block:'center',inline:'center'});const r=element.getBoundingClientRect();
    return{x:r.left+r.width/2,y:r.top+r.height/2};})()`);

  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});
  await waitFor(()=>evaluate(`document.readyState==='complete'&&typeof switchView==='function'&&document.getElementById('boot').hidden`),'Vizzer boot');
  await waitFor(()=>evaluate(`questionContext&&questionContext.engineVersion===ENGINE_VERSION`),'live question authority');

  const activeHoldPoint=await rectCenter(`lifecycleButtons.active`);
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',...activeHoldPoint});
  await send('Input.dispatchMouseEvent',{type:'mousePressed',...activeHoldPoint,button:'left',clickCount:1});
  await delay(760);
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',...activeHoldPoint,button:'left',clickCount:1});
  const lifecycleHold=await evaluate(`({active:filt.active,ready:filt.ready,
    activePressed:lifecycleButtons.active.getAttribute('aria-pressed'),
    readyPressed:lifecycleButtons.ready.getAttribute('aria-pressed')})`);
  if(!lifecycleHold.active||lifecycleHold.ready||lifecycleHold.activePressed!=='true'||lifecycleHold.readyPressed!=='false')
    throw new Error(`live lifecycle hold failed ${JSON.stringify(lifecycleHold)}`);
  await evaluate(`for(const key of Object.keys(filt))filt[key]=true;syncLifecycle();applyViewState()`);
  const releaseHoldPoint=await rectCenter(`segBtns.R1`);
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',...releaseHoldPoint});
  await send('Input.dispatchMouseEvent',{type:'mousePressed',...releaseHoldPoint,button:'left',clickCount:1});
  await delay(760);
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',...releaseHoldPoint,button:'left',clickCount:1});
  const releaseHold=await evaluate(`({r0:rfilt.R0,r1:rfilt.R1,
    r0Pressed:segBtns.R0.getAttribute('aria-pressed'),r1Pressed:segBtns.R1.getAttribute('aria-pressed')})`);
  if(releaseHold.r0||!releaseHold.r1||releaseHold.r0Pressed!=='false'||releaseHold.r1Pressed!=='true')
    throw new Error(`live release hold failed ${JSON.stringify(releaseHold)}`);
  await evaluate(`for(const key of Object.keys(rfilt))rfilt[key]=true;syncSeg();applyViewState()`);
  const filterHolds={lifecycle:lifecycleHold,release:releaseHold};

  await evaluate(`switchView('dashboard');viewPanel.scrollTop=0`);
  const card=await evaluate(`(()=>{const element=document.querySelector('[data-view-node]');const r=element.getBoundingClientRect();
    return{x:r.left+r.width/2,y:r.top+r.height/2,index:Number(element.dataset.viewNode),title:element.querySelector('b').textContent};})()`);
  await clickPoint(card);
  const wide=await evaluate(`({viewport:[innerWidth,innerHeight],route:currentView,
    dossierOpen:dossier.classList.contains('open'),selected:sel,title:dossierIdentity.querySelector('h2')?.textContent,
    expected:${card.index},expectedTitle:${JSON.stringify(card.title)},version:ENGINE_VERSION,
    headerVersion:document.querySelector('#title small').textContent})`);
  const liveResizeStart=await evaluate(`(()=>{const handle=dossierResize.getBoundingClientRect(),drawer=dossier.getBoundingClientRect();
    return{x:handle.left+handle.width/2,y:handle.top+handle.height/2,width:drawer.width};})()`);
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:liveResizeStart.x,y:liveResizeStart.y});
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:liveResizeStart.x,y:liveResizeStart.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:liveResizeStart.x-96,y:liveResizeStart.y,button:'left',buttons:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:liveResizeStart.x-96,y:liveResizeStart.y,button:'left',clickCount:1});
  const drawerResize=await evaluate(`(()=>{const drawer=dossier.getBoundingClientRect(),panel=viewPanel.getBoundingClientRect();return{
    initial:Math.round(${JSON.stringify(liveResizeStart)}.width),current:Math.round(drawer.width),
    stored:Number(sessionStorage.getItem(dossierStorageKey)),aria:Number(dossierResize.getAttribute('aria-valuenow')),
    panelMeetsDrawer:Math.abs(panel.right-drawer.left)<1,bodyFits:dbody.scrollWidth<=dbody.clientWidth};})()`);
  if(drawerResize.current<=drawerResize.initial||drawerResize.current!==drawerResize.stored||
      drawerResize.current!==drawerResize.aria||!drawerResize.panelMeetsDrawer||!drawerResize.bodyFits)
    throw new Error(`live drawer resize failed ${JSON.stringify(drawerResize)}`);
  await evaluate(`dismissDossier({focusCanvas:false});switchView('dashboard');viewPanel.scrollTop=0`);
  await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:640,y:650,deltaX:0,deltaY:320});
  await waitFor(()=>evaluate(`viewPanel.scrollTop>0`),'wide Dashboard scroll');

  await send('Emulation.setDeviceMetricsOverride',{width:360,height:320,deviceScaleFactor:1,mobile:false});
  await waitFor(()=>evaluate(`innerWidth===360&&innerHeight===320`),'contracted viewport');
  await evaluate(`switchView('dashboard');viewPanel.scrollTop=0`);
  await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:180,y:220,deltaX:0,deltaY:220});
  await waitFor(()=>evaluate(`viewPanel.scrollTop>0`),'contracted Dashboard scroll');
  const contracted=await evaluate(`(()=>{const top=document.getElementById('top').getBoundingClientRect();
    const nav=[document.getElementById('title'),viewMenu,exportMenu].map(e=>e.getBoundingClientRect());
    const counts=document.getElementById('meter').getBoundingClientRect(),chips=document.getElementById('chips').getBoundingClientRect();
    return{viewport:[innerWidth,innerHeight],pageFits:document.documentElement.scrollWidth<=innerWidth,
      headerFits:top.left>=0&&top.right<=innerWidth&&top.top>=0,
      navOneRow:Math.max(...nav.map(r=>r.top))-Math.min(...nav.map(r=>r.top))<2,
      countsSecond:counts.top>Math.max(...nav.map(r=>r.top)),chipsAfterCounts:chips.top>counts.top,
      panelScroll:viewPanel.scrollTop,panelScrollable:viewPanel.scrollHeight>viewPanel.clientHeight,
      canvasHidden:cv.hidden&&bgcv.hidden,panelVisible:!viewPanel.hidden};})()`);
  const responsiveDrawer=await evaluate(`(()=>{document.querySelector('[data-view-node]').click();const drawer=dossier.getBoundingClientRect();return{
    viewport:[innerWidth,innerHeight],left:Math.round(drawer.left),right:Math.round(drawer.right),width:Math.round(drawer.width),
    fullWidth:Math.abs(drawer.width-innerWidth)<1,handleHidden:getComputedStyle(dossierResize).display==='none',
    bodyFits:dbody.scrollWidth<=dbody.clientWidth,pageFits:document.documentElement.scrollWidth<=innerWidth};})()`);
  if(!responsiveDrawer.fullWidth||!responsiveDrawer.handleHidden||!responsiveDrawer.bodyFits||!responsiveDrawer.pageFits)
    throw new Error(`responsive drawer failure ${JSON.stringify(responsiveDrawer)}`);
  await evaluate(`dismissDossier({focusCanvas:false})`);

  const narrowLayouts=[];
  for(const [width,height] of [[320,260],[280,240]]){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:2,mobile:false});
    await waitFor(()=>evaluate(`innerWidth===${width}&&innerHeight===${height}`),`${width}px responsive viewport`);
    await evaluate(`switchView('dashboard');viewPanel.scrollTop=0`);
    await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:Math.floor(width/2),y:Math.max(120,height-30),deltaX:0,deltaY:180});
    const layout=await waitFor(()=>evaluate(`(()=>{const top=document.getElementById('top').getBoundingClientRect();
      const title=document.getElementById('title').getBoundingClientRect(),view=viewMenu.getBoundingClientRect(),
        exp=exportMenu.getBoundingClientRect(),counts=document.getElementById('meter').getBoundingClientRect(),
        chips=document.getElementById('chips').getBoundingClientRect();
      const result={viewport:[innerWidth,innerHeight],pageFits:document.documentElement.scrollWidth<=innerWidth,
        topFits:top.left>=0&&top.right<=innerWidth,titleFits:title.left>=top.left&&title.right<=view.left,
        menusFit:view.right<=exp.left&&exp.right<=top.right,
        navOneRow:Math.max(title.top,view.top,exp.top)-Math.min(title.top,view.top,exp.top)<2,
        countsSecond:counts.top>Math.max(title.top,view.top,exp.top),chipsAfterCounts:chips.top>counts.top,
        panelScroll:viewPanel.scrollTop,panelScrollable:viewPanel.scrollHeight>viewPanel.clientHeight,
        canvasHidden:cv.hidden&&bgcv.hidden};return result.panelScroll>0&&result;})()`),`${width}px routed scroll`);
    if(!layout.pageFits||!layout.topFits||!layout.titleFits||!layout.menusFit||!layout.navOneRow||
        !layout.countsSecond||!layout.chipsAfterCounts||!layout.panelScrollable||!layout.canvasHidden)
      throw new Error(`responsive header failure ${JSON.stringify(layout)}`);
    narrowLayouts.push(layout);
  }

  await send('Page.reload',{ignoreCache:true});
  await waitFor(()=>evaluate(`document.readyState==='complete'&&typeof switchView==='function'&&document.getElementById('boot').hidden`),'compact live reload');
  await waitFor(()=>evaluate(`questionContext&&questionContext.engineVersion===ENGINE_VERSION`),'reloaded live authority');
  drawerResize.reloadedCompact=true;
  await send('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});
  await waitFor(()=>evaluate(`innerWidth===1280&&innerHeight===800`),'wide Constellation viewport');
  await waitFor(()=>evaluate(`Math.round(dossier.getBoundingClientRect().width)===Number(sessionStorage.getItem(dossierStorageKey))`),'restored live drawer width');
  drawerResize.restored=await evaluate(`Math.round(dossier.getBoundingClientRect().width)`);
  if(drawerResize.restored!==drawerResize.current)throw new Error(`drawer width was not preserved ${JSON.stringify(drawerResize)}`);
  const centerHitAudit=await evaluate(`(()=>{switchView('constellation');if(questionOnly)setQuestionFilter(false);
    rx=-.35;ry=.6;zoom=1;panX=0;panY=0;cc={...ct};vx=0;vy=0;project();
    const failures=[],occlusions=[];let cases=0;
    DATA.nodes.forEach((node,index)=>{if(!P[index].on||!(node.oq||[]).length)return;cases++;
      updatePointerState(P[index].x,P[index].y);
      if(hover!==index)failures.push({index,hover,distance:hover<0?null:Math.hypot(P[hover].x-P[index].x,P[hover].y-P[index].y),title:node.t});
      const owner=document.elementFromPoint(P[index].x,P[index].y);
      if(owner!==cv)occlusions.push({index,owner:owner?.id||owner?.className||owner?.tagName||null,title:node.t});});
    return{cases,failures,occlusions};})()`);
  const physicalCenterAudit={cases:0,failures:[]};
  const physicalTargets=await evaluate(`(()=>{if(!questionOnly)setQuestionFilter(true);
    rx=-.35;ry=.6;zoom=1;panX=0;panY=0;cc={...ct};vx=0;vy=0;project();
    return DATA.nodes.map((node,index)=>({index,title:node.t,on:P[index].on,questions:(node.oq||[]).length}))
      .filter(value=>value.on&&value.questions);})()`);
  for(const candidate of physicalTargets){
    const point=await evaluate(`(()=>{dismissDossier({focusCanvas:false});rx=-.35;ry=.6;zoom=1;panX=0;panY=0;
      cc={...ct};vx=0;vy=0;project();const p=P[${candidate.index}],owner=document.elementFromPoint(p.x,p.y);
      return{x:p.x,y:p.y,on:p.on,owner:owner===cv?'cv':owner?.id||owner?.className||owner?.tagName||null};})()`);
    physicalCenterAudit.cases++;
    if(!point.on||point.owner!=='cv'){
      physicalCenterAudit.failures.push({...candidate,point,selected:null});continue;
    }
    await clickPoint(point);
    const drawer=await evaluate(`({selected:sel,open:dossier.classList.contains('open'),
      title:dossierIdentity.querySelector('h2')?.textContent||'',bodyLength:dbody.innerHTML.length})`);
    if(drawer.selected!==candidate.index||!drawer.open||drawer.title!==candidate.title||drawer.bodyLength<100)
      physicalCenterAudit.failures.push({...candidate,point,drawer});
  }
  const questionGlyphHitAudit=await evaluate(`(()=>{
    if(!questionOnly)setQuestionFilter(true);
    rx=-.35;ry=.6;zoom=1;panX=0;panY=0;cc={...ct};vx=0;vy=0;project();
    const failures=[],order=DATA.nodes.map((_,index)=>index).filter(index=>P[index].on)
      .sort((a,b)=>P[b].d-P[a].d),paintPosition=new Map(order.map((index,position)=>[index,position]));
    let cases=0,covered=0;
    for(const index of order){
      if(!ownerQuestions(index).length)continue;
      const xRadius=Math.max(4,nodeRadius(index)*.72);
      const points=[];
      for(const fraction of [-1,-.75,-.5,-.25,0,.25,.5,.75,1]){
        points.push([P[index].x+xRadius*fraction,P[index].y+xRadius*fraction]);
        points.push([P[index].x+xRadius*fraction,P[index].y-xRadius*fraction]);
      }
      for(const [x,y] of points){
        if(!insideCanvasInteractionBounds(x,y)||document.elementFromPoint(x,y)!==cv)continue;
        const occluder=order.find(candidate=>candidate!==index&&ownerQuestions(candidate).length&&
          paintPosition.get(candidate)>paintPosition.get(index)&&questionGlyphPaintDistance(candidate,x,y)<=2.5);
        if(occluder!=null){covered++;continue;}
        updatePointerState(x,y);cases++;
        if(hover!==index)failures.push({index,hover,x,y,title:DATA.nodes[index].t,
          hoverTitle:hover<0?null:DATA.nodes[hover].t,distance:Math.hypot(P[index].x-x,P[index].y-y)});
      }
    }
    return{cases,covered,failures:failures.slice(0,24)};
  })()`);
  if(questionGlyphHitAudit.failures.length)
    throw new Error(`question X ownership mismatch ${JSON.stringify(questionGlyphHitAudit)}`);
  const decorativeRingAudit=await evaluate(`(()=>{
    const order=DATA.nodes.map((_,index)=>index).filter(index=>P[index].on).sort((a,b)=>P[a].d-P[b].d);
    for(const index of order){if(!actionableQuestion(index))continue;
      const radii=questionRingRadii(index);
      for(const radius of radii)for(let step=0;step<36;step++){
        const angle=step*Math.PI/18,x=P[index].x+Math.cos(angle)*radius,y=P[index].y+Math.sin(angle)*radius;
        if(!insideCanvasInteractionBounds(x,y)||document.elementFromPoint(x,y)!==cv)continue;
        if(order.some(candidate=>ownerQuestions(candidate).length&&questionGlyphPaintDistance(candidate,x,y)<=2.5))continue;
        const story=order.find(candidate=>candidate!==index&&Math.hypot(P[candidate].x-x,P[candidate].y-y)<=nodePaintRadius(candidate));
        if(story==null)continue;updatePointerState(x,y);
        return{index,story,x,y,title:DATA.nodes[index].t,storyTitle:DATA.nodes[story].t,hover};
      }
    }
    return null;
  })()`);
  let physicalDecorativeRing=null;
  if(decorativeRingAudit){
    const target=decorativeRingAudit;
    await evaluate(`dismissDossier({focusCanvas:false});rx=-.35;ry=.6;zoom=1;panX=0;panY=0;
      cc={...ct};vx=0;vy=0;project();clearPointerState()`);
    await clickPoint({x:target.x,y:target.y});
    await waitFor(()=>evaluate(`sel===${target.story}&&dossier.classList.contains('open')`),'decorative ring does not capture Story click');
    physicalDecorativeRing=await evaluate(`({expected:${target.story},selected:sel,
      expectedTitle:DATA.nodes[${target.story}].t,selectedTitle:DATA.nodes[sel].t,
      decorativeOwner:${target.index},decorativeTitle:DATA.nodes[${target.index}].t,
      dossierOpen:dossier.classList.contains('open')})`);
  }
  await evaluate(`dismissDossier({focusCanvas:false})`);
  await evaluate(`if(!questionOnly)setQuestionFilter(true);
    rx=.18;ry=.82;zoom=1.25;panX=40;panY=-10;cc={...ct};vx=0;vy=0;project()`);
  const targetNode=await evaluate(`(()=>{let index=-1,count=0;
    DATA.nodes.forEach((node,i)=>{if(P[i].on&&(node.oq||[]).length>count){index=i;count=node.oq.length;}});
    if(index<0||count<2)throw new Error('live graph needs a story with multiple open questions');
    panX+=innerWidth*.55-P[index].x;panY+=innerHeight*.58-P[index].y;project();
    return{index,count,x:P[index].x,y:P[index].y,title:DATA.nodes[index].t};})()`);
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:targetNode.x,y:targetNode.y});
  await delay(200);
  const hoverDiagnostic=await evaluate(`(()=>({hover,expected:${targetNode.index},pointer:[pointerX,pointerY],
    target:[P[${targetNode.index}].x,P[${targetNode.index}].y,P[${targetNode.index}].on],
    targetDistance:Math.hypot(P[${targetNode.index}].x-pointerX,P[${targetNode.index}].y-pointerY),
    element:document.elementFromPoint(pointerX,pointerY)?.id||document.elementFromPoint(pointerX,pointerY)?.className||'',
    nearby:P.map((p,index)=>({index,distance:Math.hypot(p.x-pointerX,p.y-pointerY),on:p.on,questions:(DATA.nodes[index].oq||[]).length}))
      .filter(value=>value.on&&value.distance<30).sort((a,b)=>a.distance-b.distance).slice(0,8)}))()`);
  if(hoverDiagnostic.hover!==targetNode.index||!await evaluate(`cv.classList.contains('hover-target')`))
    throw new Error(`exact question hover mismatch ${JSON.stringify(hoverDiagnostic)}`);
  const cameraBefore=await evaluate(`[rx,ry,zoom,panX,panY]`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:targetNode.x,y:targetNode.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:targetNode.x+3,y:targetNode.y+2,button:'left',buttons:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:targetNode.x+3,y:targetNode.y+2,button:'left',clickCount:1});
  await waitFor(()=>evaluate(`sel===${targetNode.index}&&dossier.classList.contains('open')`),'exact question selection');
  await waitFor(()=>evaluate(`document.querySelectorAll('form[data-question-id]').length===${targetNode.count}&&
    !document.querySelector('form[data-question-id] [data-question-option]').disabled`),'live question controls');

  const optionSnapshots=[];
  for(let index=0;index<targetNode.count;index++){
    if(index===1){
      await clickPoint(await rectCenter(`document.querySelectorAll('form[data-question-id]')[${index}].querySelector('[data-question-custom]+label')`));
      await clickPoint(await rectCenter(`document.querySelectorAll('form[data-question-id]')[${index}].querySelector('[data-question-text]')`));
      await send('Input.insertText',{text:'Live smoke alternative'});
    }else{
      await clickPoint(await rectCenter(`document.querySelectorAll('form[data-question-id]')[${index}].querySelector('[data-question-option]+label')`));
    }
    const snapshot=await evaluate(`({step:${index},dossierOpen:dossier.classList.contains('open'),selected:sel,
      bodyLength:dbody.innerHTML.length,formCount:document.querySelectorAll('form[data-question-id]').length,
      status:document.querySelectorAll('form[data-question-id]')[${index}].querySelector('.questionstatus').textContent,
      outerScroll:dossier.scrollTop,dossierTop:dossier.getBoundingClientRect().top,
      identityTop:dossierIdentity.getBoundingClientRect().top,bodyTop:dbody.getBoundingClientRect().top})`);
    if(!snapshot.dossierOpen||snapshot.selected!==targetNode.index||snapshot.bodyLength<100||
        snapshot.formCount!==targetNode.count||snapshot.outerScroll!==0||
        snapshot.identityTop<snapshot.dossierTop||snapshot.bodyTop<snapshot.dossierTop)
      throw new Error(`drawer cleared after answer selection ${JSON.stringify(snapshot)}`);
    optionSnapshots.push(snapshot);
  }
  await waitFor(()=>evaluate(`!document.querySelector('[data-question-queue] button').disabled`),'complete live answer queue');
  const drawerActionLayout=await evaluate(`(()=>{const footer=document.querySelector('[data-question-queue]'),status=footer.querySelector('.actionstatus'),actions=footer.querySelector('.dossieractions');
    const f=footer.getBoundingClientRect(),s=status.getBoundingClientRect(),a=actions.getBoundingClientRect(),d=dossier.getBoundingClientRect();
    return{pinned:Math.abs(f.bottom-d.bottom)<1,below:a.top>s.bottom,leftAligned:Math.abs(a.left-s.left)<1,
      footer:[f.left,f.top,f.right,f.bottom],drawer:[d.left,d.top,d.right,d.bottom]};})()`);
  if(!drawerActionLayout.pinned||!drawerActionLayout.below||!drawerActionLayout.leftAligned)
    throw new Error(`drawer action layout drifted ${JSON.stringify(drawerActionLayout)}`);
  await evaluate(`dbody.scrollTop=Math.min(120,dbody.scrollHeight-dbody.clientHeight);
    globalThis.__liveAnswerCalls=0;globalThis.__livePreflightCalls=0;globalThis.__liveNativeFetch=fetch;
    globalThis.__queueEvents=[];const queue=document.querySelector('[data-question-queue]');globalThis.__observedQueue=queue;
    new MutationObserver(()=>globalThis.__queueEvents.push({at:performance.now(),kind:'mutation',
      status:queue.querySelector('span').textContent,button:queue.querySelector('button').textContent,
      disabled:queue.querySelector('button').disabled,busy:queue.getAttribute('aria-busy')}))
      .observe(queue,{subtree:true,childList:true,characterData:true,attributes:true});
    new MutationObserver(()=>{const live=document.querySelector('[data-question-queue]');
      globalThis.__queueEvents.push({at:performance.now(),kind:'dossier-mutation',same:live===globalThis.__observedQueue,
        status:live?.querySelector('span')?.textContent||null,submissionError:questionSubmissionError});})
      .observe(dbody,{subtree:true,childList:true});
    for(const kind of ['click','change','input','focusin'])document.addEventListener(kind,event=>{
      if(event.target.closest?.('[data-question-queue],form[data-question-id]'))globalThis.__queueEvents.push({
        at:performance.now(),kind:'document-'+kind,target:event.target.tagName,id:event.target.id||'',
        sameQueue:document.querySelector('[data-question-queue]')===globalThis.__observedQueue,
        status:document.querySelector('[data-question-queue] span')?.textContent||null,
        submissionError:questionSubmissionError});},true);
    for(const element of document.querySelectorAll('form[data-question-id] input,form[data-question-id] textarea,[data-question-queue] button'))
      for(const kind of ['change','input','focus','blur','click'])element.addEventListener(kind,event=>
        globalThis.__queueEvents.push({at:performance.now(),kind,target:event.target.tagName,
          id:event.target.id||'',status:queue.querySelector('span').textContent}),true);
    globalThis.fetch=async(url,options)=>{if(url==='/api/questions')globalThis.__livePreflightCalls++;
    if(url==='/api/questions/answers'){
      globalThis.__liveAnswerCalls++;globalThis.__livePayload=JSON.parse(options.body);
      return new Response(JSON.stringify({error:'live-smoke forced refresh failure'}),{status:500,headers:{'Content-Type':'application/json'}});
    }return globalThis.__liveNativeFetch(url,options);};`);
  const queuePoint=await rectCenter(`document.querySelector('[data-question-queue] button')`);
  await evaluate(`globalThis.__liveBefore={selected:sel,scroll:dbody.scrollTop,route:currentView,questionOnly,
    camera:[rx,ry,zoom,panX,panY],drafts:[...document.querySelectorAll('form[data-question-id]')].map(form=>questionDrafts.get(form.dataset.questionId))}`);
  await clickPoint(queuePoint);
  try{
    await waitFor(()=>evaluate(`document.querySelector('[data-question-queue] span').textContent==='live-smoke forced refresh failure'`),'live failed submission');
  }catch(error){
    const diagnostic=await evaluate(`(()=>{const queue=document.querySelector('[data-question-queue]');return{
      queue:Boolean(queue),status:queue?.querySelector('span')?.textContent||null,
      button:queue?.querySelector('button')?.textContent||null,disabled:queue?.querySelector('button')?.disabled??null,
      busy:queue?.getAttribute('aria-busy')||null,preflightCalls:globalThis.__livePreflightCalls,
      answerCalls:globalThis.__liveAnswerCalls,payload:Boolean(globalThis.__livePayload),
      contextVersion:questionContext?.engineVersion||null,contextRevision:questionContext?.revision??null,
      submissionError:questionSubmissionError,sameQueue:queue===globalThis.__observedQueue,
      forms:[...document.querySelectorAll('form[data-question-id]')].map(form=>form.dataset.questionId),
      events:globalThis.__queueEvents};})()`);
    throw new Error(`${error.message}: ${JSON.stringify(diagnostic)}`);
  }
  const failure=await evaluate(`(()=>{const button=document.querySelector('[data-question-queue] button');return{
    error:document.querySelector('[data-question-queue] span').textContent,retryAvailable:!button.disabled,calls:globalThis.__liveAnswerCalls,
    preflightCalls:globalThis.__livePreflightCalls,
    payloadCount:globalThis.__livePayload.answers.length,selected:sel,scroll:dbody.scrollTop,route:currentView,questionOnly,
    camera:[rx,ry,zoom,panX,panY],dossierOpen:dossier.classList.contains('open'),before:globalThis.__liveBefore};})()`);

  await evaluate(`globalThis.fetch=async(url,options)=>{if(url==='/api/questions')globalThis.__livePreflightCalls++;
  if(url==='/api/questions/answers'){
    globalThis.__liveAnswerCalls++;const payload=JSON.parse(options.body);
    const decisions=payload.answers.map((entry,index)=>{const q=DATA.questions.find(value=>value.id===entry.questionId);return{
      question:{...q},fingerprint:q.fingerprint,revision:index+1,answeredAt:'2026-08-11T12:00:00Z',answeredBy:'live-smoke',
      kind:entry.answer.kind,optionId:entry.answer.optionId||null,text:entry.answer.text||null};});
    return new Response(JSON.stringify({decisions,revision:questionContext.revision+decisions.length}),{status:200,headers:{'Content-Type':'application/json'}});
  }return globalThis.__liveNativeFetch(url,options);};`);
  const retryPoint=await rectCenter(`document.querySelector('[data-question-queue] button')`);
  const retryScrollBefore=await evaluate(`dbody.scrollTop`);
  await clickPoint(retryPoint);
  await waitFor(()=>evaluate(`document.querySelectorAll('.questioncard.answered').length>=${targetNode.count}`),'live retry reconciliation');
  const retryScrollTrace=[];
  for(const wait of [0,16,32,64,128,256]){
    if(wait)await delay(wait);
    retryScrollTrace.push(await evaluate(`({after:${wait},scroll:dbody.scrollTop,
      height:dbody.scrollHeight,client:dbody.clientHeight,active:document.activeElement?.tagName||null,
      activeClass:document.activeElement?.className||''})`));
  }
  const retry=await evaluate(`({calls:globalThis.__liveAnswerCalls,preflightCalls:globalThis.__livePreflightCalls,dossierOpen:dossier.classList.contains('open'),
    selected:sel,scroll:dbody.scrollTop,route:currentView,questionOnly,camera:[rx,ry,zoom,panX,panY],
    drafts:globalThis.__liveBefore.drafts,openQuestions:(DATA.nodes[sel].oq||[]).length,
    answeredCards:document.querySelectorAll('.questioncard.answered').length,queueGone:!document.querySelector('[data-question-queue]'),
    metadataVisible:Boolean(document.querySelector('.kv')),spacerGone:!document.querySelector('[data-scroll-preserver]')})`);
  if(retry.scroll!==0||!retry.metadataVisible||!retry.spacerGone||retryScrollTrace.some(sample=>sample.scroll!==0))
    throw new Error(`successful Story reload did not restore complete top-level content from ${retryScrollBefore}: ${JSON.stringify({retry,retryScrollTrace})}`);
  const chatPoint=await evaluate(`(()=>{
    globalThis.__liveDiscussionCalls=[];
    globalThis.fetch=async(url,options)=>{
      if(url==='/api/discussions/queue'){
        const payload=JSON.parse(options.body);globalThis.__liveDiscussionCalls.push(payload);
        const queues={codex:[],claude:[]};queues[payload.provider]=[payload.storyId];
        return new Response(JSON.stringify({changed:true,reloadRequired:false,queue:{schema:1,revision:1,
          updatedAt:'2026-08-11T21:00:00Z',queues,history:[]}}),{status:200,headers:{'Content-Type':'application/json'}});
      }
      return globalThis.__liveNativeFetch(url,options);
    };
    const button=document.querySelector('[data-chat-primary]'),r=button.getBoundingClientRect();
    globalThis.__liveChatLabel=button.textContent;return{x:r.left+r.width/2,y:r.top+r.height/2};
  })()`);
  await clickPoint(chatPoint);
  await waitFor(()=>evaluate(`globalThis.__liveDiscussionCalls.length===1&&document.querySelector('[data-discussion-status]').textContent.startsWith('Queued first')`),'live discussion queue');
  const discussionQueue=await evaluate(`(()=>{const call=globalThis.__liveDiscussionCalls[0];return{
    label:globalThis.__liveChatLabel,provider:call.provider,storyId:call.storyId,
    questionCount:call.questions.length,position:discussionContext.queue.queues[call.provider].indexOf(call.storyId),
    dossierOpen:dossier.classList.contains('open'),selected:sel,route:currentView,questionOnly,
    camera:[rx,ry,zoom,panX,panY],status:document.querySelector('[data-discussion-status]').textContent};})()`);
  if(!discussionQueue.dossierOpen||discussionQueue.selected!==targetNode.index||discussionQueue.position!==0||
      discussionQueue.questionCount!==targetNode.count||!discussionQueue.label.toLowerCase().includes(discussionQueue.provider))
    throw new Error(`live discussion queue lost context ${JSON.stringify(discussionQueue)}`);
  await clickPoint(await rectCenter(`document.getElementById('close')`));
  const secondNode=await evaluate(`(()=>{
    project();let index=-1,count=0;
    DATA.nodes.forEach((node,i)=>{const open=ownerQuestions(i).length;if(P[i].on&&open>count){index=i;count=open;}});
    if(index<0)throw new Error('post-answer smoke needs a second question Story');
    panX+=innerWidth*.55-P[index].x;panY+=innerHeight*.58-P[index].y;project();
    return{index,count,x:P[index].x,y:P[index].y,title:DATA.nodes[index].t};})()`);
  await clickPoint(secondNode);
  await waitFor(()=>evaluate(`sel===${secondNode.index}&&dossier.classList.contains('open')`),
    'second question Story selection');
  const secondTransition=await evaluate(`(()=>{
    const questions=ownerQuestions(${secondNode.index});
    const decisions=questions.map((q,index)=>({question:{...q},fingerprint:q.fingerprint,
      revision:questionContext.revision+index+1,answeredAt:'2026-08-11T12:01:00Z',answeredBy:'live-smoke',
      kind:'option',optionId:q.recommendation.optionId,text:null}));
    reconcileAcceptedDecisions(decisions,questionContext.revision+decisions.length);
    return{selected:sel,dossierOpen:dossier.classList.contains('open'),answered:decisions.length,
      remainingOnStory:ownerQuestions(${secondNode.index}).length,outerScroll:dossier.scrollTop};
  })()`);
  if(secondTransition.selected!==secondNode.index||!secondTransition.dossierOpen||
      secondTransition.answered!==secondNode.count||secondTransition.remainingOnStory!==0||secondTransition.outerScroll!==0)
    throw new Error(`second answer reconciliation lost state ${JSON.stringify(secondTransition)}`);
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape'});
  const explicitClose=await evaluate(`({dossierOpen:dossier.classList.contains('open'),hidden:dossier.getAttribute('aria-hidden'),selected:sel})`);
  const remainingTargets=await evaluate(`(()=>{project();return DATA.nodes.map((node,index)=>({index,
    x:P[index].x,y:P[index].y,on:P[index].on,title:node.t,questions:ownerQuestions(index).length,
    element:document.elementFromPoint(P[index].x,P[index].y)===cv?'cv':'other'}))
    .filter(value=>value.on&&value.questions&&value.element==='cv');})()`);
  const postAnswerHitAudit={cases:0,failures:[]};
  for(const target of remainingTargets){
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:target.x,y:target.y});
    const state=await evaluate(`({hover,pointer:cv.classList.contains('hover-target'),cursor:getComputedStyle(cv).cursor})`);
    postAnswerHitAudit.cases++;
    if(state.hover!==target.index||!state.pointer||state.cursor!=='pointer')
      postAnswerHitAudit.failures.push({...target,state});
  }
  if(postAnswerHitAudit.failures.length)
    throw new Error(`post-answer question hover mismatch ${JSON.stringify(postAnswerHitAudit)}`);
  const orbitPoint=remainingTargets[0];if(!orbitPoint)throw new Error('post-answer orbit smoke needs a remaining question');
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:orbitPoint.x,y:orbitPoint.y});
  await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:orbitPoint.x,y:orbitPoint.y,deltaX:140,deltaY:70});
  await delay(180);
  const wheelPointer=await evaluate(`({hover,pointerActive,pointer:cv.classList.contains('hover-target'),
    cursor:getComputedStyle(cv).cursor,consistent:(hover>=0)===cv.classList.contains('hover-target')})`);
  const panBefore=await evaluate(`({panX,panY})`);
  await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:orbitPoint.x,y:orbitPoint.y,
    deltaX:36,deltaY:24,modifiers:4});
  await delay(120);
  const panPointer=await evaluate(`({panX,panY,hover,pointerActive,
    pointer:cv.classList.contains('hover-target'),cursor:getComputedStyle(cv).cursor,
    consistent:(hover>=0)===cv.classList.contains('hover-target')})`);
  const zoomBefore=await evaluate(`zoom`);
  await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:orbitPoint.x,y:orbitPoint.y,
    deltaX:0,deltaY:-50,modifiers:2});
  await delay(120);
  const pinchPointer=await evaluate(`({zoom,hover,pointerActive,
    pointer:cv.classList.contains('hover-target'),cursor:getComputedStyle(cv).cursor,
    consistent:(hover>=0)===cv.classList.contains('hover-target')})`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:orbitPoint.x,y:orbitPoint.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:orbitPoint.x+30,y:orbitPoint.y+12,button:'left',buttons:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:orbitPoint.x+30,y:orbitPoint.y+12,button:'left',clickCount:1});
  await delay(120);
  const dragPointer=await evaluate(`({hover,pointerActive,pointer:cv.classList.contains('hover-target'),
    cursor:getComputedStyle(cv).cursor,consistent:(hover>=0)===cv.classList.contains('hover-target'),
    pointerDown,orbiting})`);
  if(!wheelPointer.pointerActive||!wheelPointer.consistent||!panPointer.pointerActive||
      !panPointer.consistent||panPointer.panX!==panBefore.panX-36||panPointer.panY!==panBefore.panY-24||
      !pinchPointer.pointerActive||!pinchPointer.consistent||pinchPointer.zoom<=zoomBefore||
      !dragPointer.pointerActive||
      !dragPointer.consistent||dragPointer.pointerDown||dragPointer.orbiting)
    throw new Error(`camera input pointer presentation stale ${JSON.stringify({wheelPointer,panBefore,panPointer,zoomBefore,pinchPointer,dragPointer})}`);

  process.stdout.write(JSON.stringify({filterHolds,wide,drawerResize,contracted,responsiveDrawer,narrowLayouts,constellation:{centerHitAudit,physicalCenterAudit,questionGlyphHitAudit,decorativeRingAudit,physicalDecorativeRing,target:targetNode,cameraBefore,
    pointerCursor:await evaluate(`getComputedStyle(cv).cursor`),optionSnapshots,drawerActionLayout,failure,retry,retryScrollBefore,retryScrollTrace,discussionQueue,secondNode,
    secondTransition,postAnswerHitAudit,wheelPointer,panBefore,panPointer,zoomBefore,pinchPointer,dragPointer,explicitClose}}));
}finally{
  if(socket)socket.close();
  if(browser){const exited=new Promise(resolve=>browser.once('exit',resolve));browser.kill('SIGTERM');
    await Promise.race([exited,delay(1500)]);if(browser.exitCode==null)browser.kill('SIGKILL');}
  fs.rmSync(profile,{recursive:true,force:true,maxRetries:5,retryDelay:50});
}
})().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
