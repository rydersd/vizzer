const fs=require('fs'),http=require('http'),os=require('os'),path=require('path');
const {spawn}=require('child_process');
(async()=>{

const html=fs.readFileSync(0,'utf8');
const chrome=process.argv[2];
if(!chrome)throw new Error('Chrome executable path is required');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'vizzer-browser-'));
const server=http.createServer((request,response)=>{
  if(request.url==='/constellation.html'){
    response.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});
    response.end(html);return;
  }
  response.writeHead(404,{'Content-Type':'application/json'});response.end('{}');
});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const termGraceMs=+(process.env.VIZZER_BROWSER_TERM_GRACE_MS||1500);
const useProcessGroup=process.platform!=='win32';
const signalBrowser=(child,signal)=>{
  if(!useProcessGroup&&(child.exitCode!==null||child.signalCode!==null))return false;
  try{
    if(useProcessGroup&&Number.isInteger(child.pid)){process.kill(-child.pid,signal);return true;}
    return child.kill(signal);
  }catch(error){if(error.code==='ESRCH')return false;throw error;}
};
const browserRunning=child=>{
  if(useProcessGroup&&Number.isInteger(child.pid)){
    try{process.kill(-child.pid,0);return true;}
    catch(error){if(error.code==='ESRCH')return false;throw error;}
  }
  return child.exitCode===null&&child.signalCode===null;
};
const waitForExit=async(child,timeout)=>{
  const deadline=Date.now()+timeout;
  while(browserRunning(child)&&Date.now()<deadline)await delay(25);
  return !browserRunning(child);
};
const removeProfile=async()=>{
  const deadline=Date.now()+5000;
  while(true){
    try{fs.rmSync(profile,{recursive:true,force:true});return;}
    catch(error){
      if(!['EBUSY','EMFILE','ENFILE','ENOTEMPTY','EPERM'].includes(error.code)||Date.now()>=deadline)throw error;
      await delay(100);
    }
  }
};
const waitFor=async(fn,label,timeout=8000)=>{
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){try{const value=await fn();if(value)return value;}catch(_){}await delay(50);}
  throw new Error(`timed out waiting for ${label}`);
};
let browser;
try{
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const url=`http://127.0.0.1:${server.address().port}/constellation.html`;
  browser=spawn(chrome,['--headless=new','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,url],
    {stdio:'ignore',detached:useProcessGroup});
  const active=path.join(profile,'DevToolsActivePort');
  const debugPort=await waitFor(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0],'DevTools port');
  const target=await waitFor(async()=>{
    const targets=await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
    return targets.find(candidate=>candidate.type==='page'&&candidate.url===url);
  },'constellation page');
  const socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let nextId=0;const pending=new Map();
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(!message.id)return;const slot=pending.get(message.id);if(!slot)return;pending.delete(message.id);message.error?slot.reject(new Error(message.error.message)):slot.resolve(message.result);});
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++nextId;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>(await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})).result.value;
  await send('Runtime.enable');await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});
  await waitFor(()=>evaluate(`document.readyState==='complete'&&typeof openNode==='function'`),'Vizzer boot');
  await waitFor(()=>evaluate(`innerWidth===1280&&innerHeight===800`),'wide viewport');
  const wideCardRect=await evaluate(`(()=>{switchView('dashboard');const card=document.querySelector('[data-view-node]');
    const r=card.getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2};})()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:wideCardRect.x,y:wideCardRect.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:wideCardRect.x,y:wideCardRect.y,button:'left',clickCount:1});
  const wideCard=await evaluate(`({route:currentView,dossierOpen:dossier.classList.contains('open'),selected:sel})`);
  const resizeStart=await evaluate(`(()=>{const handle=dossierResize.getBoundingClientRect(),drawer=dossier.getBoundingClientRect();
    return{x:handle.left+handle.width/2,y:handle.top+handle.height/2,width:drawer.width};})()`);
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:resizeStart.x,y:resizeStart.y});
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:resizeStart.x,y:resizeStart.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:resizeStart.x-120,y:resizeStart.y,button:'left',buttons:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:resizeStart.x-120,y:resizeStart.y,button:'left',clickCount:1});
  const dragWidth=await evaluate(`Math.round(dossier.getBoundingClientRect().width)`);
  await evaluate(`dossierResize.focus()`);
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight'});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight'});
  const drawerResize=await evaluate(`(()=>{const drawer=dossier.getBoundingClientRect(),panel=viewPanel.getBoundingClientRect();return{
    grew:${dragWidth}>Math.round(${JSON.stringify(resizeStart)}.width)+90,
    keyboardShrank:Math.round(drawer.width)===${dragWidth}-16,
    ariaMatches:Math.round(drawer.width)===Number(dossierResize.getAttribute('aria-valuenow')),
    stored:Math.round(drawer.width)===Number(sessionStorage.getItem(dossierStorageKey)),
    panelMeetsDrawer:Math.abs(panel.right-drawer.left)<1,bodyFits:dbody.scrollWidth<=dbody.clientWidth};})()`);
  await evaluate(`dismissDossier({focusCanvas:false});switchView('dashboard')`);
  await send('Emulation.setDeviceMetricsOverride',{width:360,height:320,deviceScaleFactor:1,mobile:false});
  await waitFor(()=>evaluate(`innerWidth===360&&innerHeight===320`),'contracted viewport');
  const narrowDrawer=await evaluate(`(()=>{document.querySelector('[data-view-node]').click();const drawer=dossier.getBoundingClientRect();
    return{left:Math.round(drawer.left),right:Math.round(drawer.right),width:Math.round(drawer.width),
      fullWidth:Math.abs(drawer.width-innerWidth)<1,handleHidden:getComputedStyle(dossierResize).display==='none',
      bodyFits:dbody.scrollWidth<=dbody.clientWidth,pageFits:document.documentElement.scrollWidth<=innerWidth};})()`);
  await evaluate(`dismissDossier({focusCanvas:false});switchView('dashboard')`);
  await evaluate(`viewPanel.scrollTop=0`);
  await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:180,y:220,deltaX:0,deltaY:180});
  const responsive=await waitFor(async()=>{
    const value=await evaluate(`(()=>{const top=document.getElementById('top').getBoundingClientRect();
      const nav=[document.getElementById('title'),viewMenu,exportMenu].map(e=>e.getBoundingClientRect());
      const counts=document.getElementById('meter').getBoundingClientRect(),chips=document.getElementById('chips').getBoundingClientRect();
      return{viewport:[innerWidth,innerHeight],pageFits:document.documentElement.scrollWidth<=innerWidth,
        headerFits:top.left>=0&&top.right<=innerWidth&&top.top>=0,
        navOneRow:Math.max(...nav.map(r=>r.top))-Math.min(...nav.map(r=>r.top))<2,
        countsSecond:counts.top>Math.max(...nav.map(r=>r.top)),chipsAfterCounts:chips.top>counts.top,
        panelScroll:viewPanel.scrollTop,panelScrollable:viewPanel.scrollHeight>viewPanel.clientHeight,
        canvasHidden:cv.hidden&&bgcv.hidden,panelVisible:!viewPanel.hidden,wideCard:${JSON.stringify(wideCard)}}})()`);
    return value.panelScroll>0&&value;
  },'contracted dashboard scroll');
  responsive.narrowDrawer=narrowDrawer;
  await send('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});
  await waitFor(()=>evaluate(`innerWidth===1280&&innerHeight===800`),'restored wide viewport');
  const rect=await evaluate(`(()=>{
    switchView('constellation');
    questionContext={schema:1,revision:0,csrfToken:'test',questions:DATA.questions,decisions:[]};
    questionError='';openNode(DATA.questions[0].n);
    const label=document.querySelector('[data-question-option]+label');
    label.scrollIntoView({block:'center'});const r=label.getBoundingClientRect();
    return{x:r.left+r.width/2,y:r.top+r.height/2,right:r.right,width:innerWidth};
  })()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:rect.x,y:rect.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:rect.x,y:rect.y,button:'left',clickCount:1});
  const customRect=await evaluate(`(()=>{const form=document.querySelectorAll('form[data-question-id]')[1];
    const label=form.querySelector('[data-question-custom]+label');label.scrollIntoView({block:'center'});
    const r=label.getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2};})()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:customRect.x,y:customRect.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:customRect.x,y:customRect.y,button:'left',clickCount:1});
  const textRect=await evaluate(`(()=>{const text=document.querySelectorAll('[data-question-text]')[1];
    text.scrollIntoView({block:'center'});const r=text.getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2};})()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:textRect.x,y:textRect.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:textRect.x,y:textRect.y,button:'left',clickCount:1});
  await send('Input.insertText',{text:'Keep it exact.'});
  await waitFor(()=>evaluate(`!document.querySelector('[data-question-queue] button').disabled`),'complete answer queue');
  const state=await evaluate(`(()=>{const forms=[...document.querySelectorAll('form[data-question-id]')],button=document.querySelector('[data-question-queue] button');return{
    checked:forms[0].querySelector('[data-question-option]').checked,
    customChecked:forms[1].querySelector('[data-question-custom]').checked,
    freeform:forms[1].querySelector('[data-question-text]').value,
    dossierOpen:dossier.classList.contains('open'),hidden:dossier.getAttribute('aria-hidden'),
    selected:sel,expected:DATA.questions[0].n,buttonDisabled:button.disabled,
    buttonText:button.textContent,statuses:forms.map(form=>form.querySelector('.questionstatus').textContent),
    queue:document.querySelector('[data-question-queue] span').textContent,
    drafts:DATA.questions.map(q=>questionDrafts.get(q.id)),queueButtons:document.querySelectorAll('[data-question-queue] button').length,
    outerScroll:dossier.scrollTop,
    headerVisible:dossierIdentity.getBoundingClientRect().top>=dossier.getBoundingClientRect().top,
    bodyVisible:dbody.getBoundingClientRect().top>=dossier.getBoundingClientRect().top,
    rectInside:(${JSON.stringify(rect)}).right<=(${JSON.stringify(rect)}).width,
    backgroundPointerEvents:getComputedStyle(bgcv).pointerEvents,
    backgroundOwnsHit:document.elementFromPoint(innerWidth/2,innerHeight-20)===bgcv,
    actionLayout:(()=>{const footer=document.querySelector('[data-question-queue]'),status=footer.querySelector('.actionstatus'),actions=footer.querySelector('.dossieractions');
      const f=footer.getBoundingClientRect(),s=status.getBoundingClientRect(),a=actions.getBoundingClientRect(),d=dossier.getBoundingClientRect();
      return{pinned:Math.abs(f.bottom-d.bottom)<1,below:a.top>s.bottom,leftAligned:Math.abs(a.left-s.left)<1};})()
  }})()`);
  const staleRect=await evaluate(`(()=>{
    dbody.scrollTop=80;
    globalThis.__stalePostCalls=0;
    globalThis.__staleBefore={selected:sel,scroll:dbody.scrollTop,route:currentView,
      drafts:DATA.questions.map(q=>questionDrafts.get(q.id))};
    globalThis.fetch=async(url,options)=>{
      if(url==='/api/questions')return new Response(JSON.stringify({engineVersion:'0.0.0',
        schema:1,revision:0,csrfToken:'stale',questions:DATA.questions,decisions:[]}),
        {status:200,headers:{'Content-Type':'application/json'}});
      if(url==='/api/questions/answers')globalThis.__stalePostCalls++;
      throw new Error('mutation must not run after a stale preflight');
    };
    const button=document.querySelector('[data-question-queue] button');const r=button.getBoundingClientRect();
    return{x:r.left+r.width/2,y:r.top+r.height/2};
  })()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:staleRect.x,y:staleRect.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:staleRect.x,y:staleRect.y,button:'left',clickCount:1});
  await waitFor(()=>evaluate(`document.querySelector('[data-question-queue] span').textContent.includes('Vizzer version mismatch')`),'stale page preflight');
  state.stalePreflight=await evaluate(`(()=>{const button=document.querySelector('[data-question-queue] button');return{
    error:document.querySelector('[data-question-queue] span').textContent,postCalls:globalThis.__stalePostCalls,
    retryAvailable:!button.disabled,dossierOpen:dossier.classList.contains('open'),selected:sel,
    scroll:dbody.scrollTop,route:currentView,drafts:DATA.questions.map(q=>questionDrafts.get(q.id)),
    before:globalThis.__staleBefore};})()`);
  const submitRect=await evaluate(`(()=>{
    rx=.125;ry=.75;zoom=1.4;panX=31;panY=-19;searchInput.value='A';updateSearch();rfilt.R1=false;
    dbody.scrollTop=80;
    globalThis.__failureBefore={selected:sel,scroll:dbody.scrollTop,route:currentView,
      search:searchInput.value,r1:rfilt.R1,camera:[rx,ry,zoom,panX,panY],
      drafts:DATA.questions.map(q=>questionDrafts.get(q.id))};
    globalThis.__answerFetchCalls=0;
    globalThis.fetch=async(url,options)=>{
      if(url==='/api/questions')return new Response(JSON.stringify({engineVersion:ENGINE_VERSION,
        schema:1,revision:0,csrfToken:'restart-token',questions:DATA.questions,decisions:[]}),
        {status:200,headers:{'Content-Type':'application/json'}});
      globalThis.__answerFetchCalls++;
      globalThis.__submittedAnswers=JSON.parse(options.body);
      return new Response(JSON.stringify({error:'refresh exploded'}),
        {status:500,headers:{'Content-Type':'application/json'}});
    };
    const button=document.querySelector('[data-question-queue] button');const r=button.getBoundingClientRect();
    return{x:r.left+r.width/2,y:r.top+r.height/2};
  })()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:submitRect.x,y:submitRect.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:submitRect.x,y:submitRect.y,button:'left',clickCount:1});
  await waitFor(()=>evaluate(`document.querySelector('[data-question-queue]')?.getAttribute('aria-busy')!=='true'`),'failed answer response');
  await evaluate(`refreshDossier()`);
  await waitFor(()=>evaluate(`document.querySelector('[data-question-queue] span').textContent==='refresh exploded'`),'failed answer survives dossier refresh');
  state.failedSubmit=await evaluate(`(()=>{const button=document.querySelector('[data-question-queue] button');return{
    error:document.querySelector('[data-question-queue] span').textContent,
    retryAvailable:!button.disabled,buttonText:button.textContent,
    dossierOpen:dossier.classList.contains('open'),selected:sel,scroll:dbody.scrollTop,route:currentView,
    search:searchInput.value,r1:rfilt.R1,camera:[rx,ry,zoom,panX,panY],
    drafts:DATA.questions.map(q=>questionDrafts.get(q.id)),before:globalThis.__failureBefore,
    submitted:{calls:globalThis.__answerFetchCalls,revision:globalThis.__submittedAnswers.expectedRevision,
      ids:globalThis.__submittedAnswers.answers.map(a=>a.questionId),
      kinds:globalThis.__submittedAnswers.answers.map(a=>a.answer.kind),
      freeform:globalThis.__submittedAnswers.answers[1].answer.text}
  }})()`);
  const retryRect=await evaluate(`(()=>{
    globalThis.fetch=async(url,options)=>{
      if(url==='/api/questions')return new Response(JSON.stringify({engineVersion:ENGINE_VERSION,
        schema:1,revision:0,csrfToken:'retry-token',questions:DATA.questions,decisions:[]}),
        {status:200,headers:{'Content-Type':'application/json'}});
      globalThis.__answerFetchCalls++;globalThis.__submittedAnswers=JSON.parse(options.body);
      const decisions=DATA.questions.map((q,index)=>{const draft=questionDrafts.get(q.id);return{
        question:{...q},fingerprint:q.fingerprint,revision:index+1,answeredAt:'2026-08-11T12:00:00Z',answeredBy:'Ryder',
        kind:draft.kind,optionId:draft.optionId||null,text:draft.kind==='freeform'?draft.text.trim():null};});
      return new Response(JSON.stringify({decisions,revision:decisions.length}),
        {status:200,headers:{'Content-Type':'application/json'}});
    };
    const button=document.querySelector('[data-question-queue] button');const r=button.getBoundingClientRect();
    return{x:r.left+r.width/2,y:r.top+r.height/2};
  })()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:retryRect.x,y:retryRect.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:retryRect.x,y:retryRect.y,button:'left',clickCount:1});
  await waitFor(()=>evaluate(`document.querySelectorAll('.questioncard.answered').length===2`),'successful answer retry');
  state.successfulRetry=await evaluate(`({calls:globalThis.__answerFetchCalls,
    dossierOpen:dossier.classList.contains('open'),selected:sel,scroll:dbody.scrollTop,route:currentView,
    search:searchInput.value,r1:rfilt.R1,camera:[rx,ry,zoom,panX,panY],
    drafts:DATA.questions.map(q=>questionDrafts.get(q.id)),openQuestions:(DATA.nodes[sel].oq||[]).length,
    decisions:(DATA.nodes[sel].od||[]).length,answeredCards:document.querySelectorAll('.questioncard.answered').length,
    queueGone:!document.querySelector('[data-question-queue]'),metadataVisible:Boolean(document.querySelector('.kv')),
    spacerGone:!document.querySelector('[data-scroll-preserver]')})`);
  const chatRect=await evaluate(`(()=>{
    const workIndex=DATA.work.push({agent:'Claude',updatedAt:'2026-08-11T21:00:00Z'})-1;
    DATA.nodes[sel].aw=[workIndex];
    discussionContext={engineVersion:ENGINE_VERSION,csrfToken:'discussion-token',queue:{revision:0,queues:{codex:[],claude:[]}}};
    discussionError='';globalThis.__discussionCalls=[];
    globalThis.fetch=async(url,options)=>{
      if(url==='/api/questions')return new Response(JSON.stringify({engineVersion:ENGINE_VERSION,
        schema:1,revision:2,csrfToken:'question-token',questions:[],decisions:questionContext.decisions}),
        {status:200,headers:{'Content-Type':'application/json'}});
      if(url==='/api/discussions')return new Response(JSON.stringify({engineVersion:ENGINE_VERSION,
        schema:1,csrfToken:'discussion-token',queue:discussionContext.queue}),
        {status:200,headers:{'Content-Type':'application/json'}});
      const payload=JSON.parse(options.body);globalThis.__discussionCalls.push(payload);
      const queue={schema:1,revision:1,updatedAt:'2026-08-11T21:01:00Z',queues:{codex:[],claude:[payload.storyId]},history:[]};
      return new Response(JSON.stringify({queue,changed:true,reloadRequired:false}),
        {status:200,headers:{'Content-Type':'application/json'}});
    };
    refreshDossier();const button=document.querySelector('[data-chat-primary]'),r=button.getBoundingClientRect();
    globalThis.__chatLabel=button.textContent;return{x:r.left+r.width/2,y:r.top+r.height/2};
  })()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:chatRect.x,y:chatRect.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:chatRect.x,y:chatRect.y,button:'left',clickCount:1});
  await waitFor(()=>evaluate(`discussionMessages.get(DATA.nodes[sel].id)==='Queued first · claude'`),'general Story discussion queue');
  state.generalDiscussion=await evaluate(`(()=>{const call=globalThis.__discussionCalls[0];return{
    label:globalThis.__chatLabel,provider:call.provider,storyId:call.storyId,questions:call.questions,
    revision:discussionContext.queue.revision,position:discussionContext.queue.queues.claude.indexOf(call.storyId),
    dossierOpen:dossier.classList.contains('open'),selected:sel,answerQueueAbsent:!document.querySelector('[data-question-queue]'),
    chatPresent:Boolean(document.querySelector('[data-chat-primary]')),
    status:document.querySelector('[data-discussion-status]').textContent};})()`);
  await send('Emulation.setDeviceMetricsOverride',{width:360,height:320,deviceScaleFactor:1,mobile:false});
  await waitFor(()=>evaluate(`innerWidth===360&&innerHeight===320`),'compact persistence viewport');
  await send('Page.reload',{ignoreCache:true});
  await waitFor(()=>evaluate(`document.readyState==='complete'&&typeof openNode==='function'&&innerWidth===360`),'compact reload');
  drawerResize.reloadedCompact=true;
  await send('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});
  await waitFor(()=>evaluate(`innerWidth===1280&&innerHeight===800`),'persistence restore viewport');
  await waitFor(()=>evaluate(`Math.round(dossier.getBoundingClientRect().width)===Number(sessionStorage.getItem(dossierStorageKey))`),'restored drawer width');
  drawerResize.restored=true;
  state.responsive=responsive;
  state.drawerResize=drawerResize;
  process.stdout.write(JSON.stringify(state));socket.close();
}finally{
  if(browser){
    signalBrowser(browser,'SIGTERM');
    if(!await waitForExit(browser,termGraceMs)){
      signalBrowser(browser,'SIGKILL');
      if(!await waitForExit(browser,5000))throw new Error('Chrome did not exit after SIGKILL');
    }
  }
  if(server.closeAllConnections)server.closeAllConnections();
  server.close();
  await removeProfile();
}
})().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
