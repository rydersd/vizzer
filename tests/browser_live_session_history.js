const fs=require('fs'),os=require('os'),path=require('path');
const {spawn}=require('child_process');

(async()=>{
const chrome=process.argv[2],url=process.argv[3];
if(!chrome||!url)throw new Error('usage: browser_live_session_history.js <chrome> <url>');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'vizzer-session-history-'));
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const useProcessGroup=process.platform!=='win32';
const signalBrowser=(child,signal)=>{try{return useProcessGroup?process.kill(-child.pid,signal):child.kill(signal)}catch(error){if(error.code==='ESRCH'||error.code==='EPERM')return false;throw error}};
const browserRunning=child=>{try{if(useProcessGroup){process.kill(-child.pid,0);return true}return child.exitCode===null}catch(error){if(error.code==='ESRCH'||error.code==='EPERM')return false;throw error}};
const waitFor=async(fn,label,timeout=12000)=>{const deadline=Date.now()+timeout;
  while(Date.now()<deadline){try{const value=await fn();if(value)return value;}catch(_){}await delay(40);}
  throw new Error(`timed out waiting for ${label}`);
};
let browser,socket;
try{
  browser=spawn(chrome,['--headless=new','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,url],
    {stdio:'ignore',detached:useProcessGroup});
  const active=path.join(profile,'DevToolsActivePort');
  const debugPort=await waitFor(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0],'DevTools port',20000);
  const target=await waitFor(async()=>{const targets=await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
    return targets.find(candidate=>candidate.type==='page'&&candidate.url.startsWith(url));},'Vizzer page');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let nextId=0;const pending=new Map();
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(!message.id)return;const slot=pending.get(message.id);if(!slot)return;pending.delete(message.id);message.error?slot.reject(new Error(message.error.message)):slot.resolve(message.result);});
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++nextId;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value;};
  const mouse=async(type,x,y,clickCount=1)=>send('Input.dispatchMouseEvent',{type,x,y,button:'left',clickCount});
  await send('Runtime.enable');await send('Page.enable');
  await waitFor(()=>evaluate(`document.readyState==='complete'&&typeof historyTrailAtPointer==='function'&&document.getElementById('boot').hidden`),'Vizzer boot');
  await waitFor(()=>evaluate(`sessionHistory.payload&&sessionHistory.points.length>0`),'history payload');

  await evaluate(`globalThis.__historyDraws=0;const original=drawSessionHistory;drawSessionHistory=()=>{globalThis.__historyDraws++;return original();};project();`);
  await waitFor(()=>evaluate(`globalThis.__historyDraws>0`),'assembled canvas draw hook');
  const paint=await evaluate(`(()=>{let arcs=0,strokes=0,fills=0;
    const arc=ctx.arc.bind(ctx),stroke=ctx.stroke.bind(ctx),fill=ctx.fill.bind(ctx);
    ctx.arc=(...args)=>{arcs++;return arc(...args)};ctx.stroke=(...args)=>{strokes++;return stroke(...args)};ctx.fill=(...args)=>{fills++;return fill(...args)};
    try{drawSessionHistory()}finally{ctx.arc=arc;ctx.stroke=stroke;ctx.fill=fill}
    return{arcs,strokes,fills,points:sessionHistory.points.length,segments:sessionHistory.segments.length,
      heads:sessionHistory.points.filter(point=>point.head).length};})()`);
  if(paint.points!==2||paint.segments!==1||paint.arcs!==paint.points||
     paint.strokes!==paint.segments+paint.heads||paint.fills!==paint.points-paint.heads)
    throw new Error('trail paint counts mismatch: '+JSON.stringify(paint));
  const point=await evaluate(`historyPoint(sessionHistory.points[0])`);
  await evaluate(`(()=>{const init={clientX:${point.x},clientY:${point.y},pointerId:7,bubbles:true};
    cv.dispatchEvent(new PointerEvent('pointerdown',init));cv.dispatchEvent(new PointerEvent('pointerup',init));})()`);
  await waitFor(()=>evaluate(`dossier.classList.contains('open')&&sessionHistory.drawer==='event'`),'trail event dossier');
  await evaluate(`dismissDossier({focusCanvas:false})`);
  await evaluate(`cv.dispatchEvent(new MouseEvent('dblclick',{clientX:${point.x},clientY:${point.y},bubbles:true,detail:2}))`);
  await waitFor(()=>evaluate(`Boolean(sessionHistory.session)&&!document.getElementById('historyisolation').hidden`),'path isolation');
  await evaluate(`document.getElementById('historyall').click()`);
  await waitFor(()=>evaluate(`!sessionHistory.session&&document.getElementById('historyisolation').hidden`),'isolation dismissal');

  await send('Emulation.setDeviceMetricsOverride',{width:760,height:640,deviceScaleFactor:1,mobile:false});
  await waitFor(()=>evaluate(`innerWidth===760`),'760px viewport');
  const compactDock=await evaluate(`(()=>{const dock=document.getElementById('historydock');return{
    visible:getComputedStyle(dock).display!=='none',
    controlsVisible:[...dock.querySelectorAll('select,input,button')].every(el=>el.getBoundingClientRect().width>0),
    noOverflow:document.documentElement.scrollWidth<=innerWidth};})()`);
  await evaluate(`historyOpenLog(sessionHistory.payload.sessions[0].id)`);
  await waitFor(()=>evaluate(`document.getElementById('historylogfilters')`),'work log filters');
  const state=await evaluate(`(()=>{const dock=document.getElementById('historydock'),filters=document.getElementById('historylogfilters');
    return{draws:globalThis.__historyDraws,dockHiddenWithSidebar:getComputedStyle(dock).display==='none',
      noOverflow:document.documentElement.scrollWidth<=innerWidth,
      filtersSticky:getComputedStyle(filters).position==='sticky',
      filtersVisible:filters.getBoundingClientRect().top>=document.getElementById('dbody').getBoundingClientRect().top-1,
      keyboardFocusable:[...dock.querySelectorAll('select,input,button')].every(el=>el.tabIndex>=0)};})()`);
  if(!state.draws)throw new Error('history was not invoked by assembled canvas renderer');
  if(!compactDock.visible||!compactDock.controlsVisible||!compactDock.noOverflow||!state.dockHiddenWithSidebar||!state.noOverflow||!state.filtersSticky||!state.filtersVisible||!state.keyboardFocusable)
    throw new Error('responsive session-history controls failed: '+JSON.stringify({compactDock,state}));
  process.stdout.write(JSON.stringify({paint,state}));
}finally{
  if(socket)socket.close();
  if(browser){signalBrowser(browser,'SIGTERM');for(let i=0;i<80&&browserRunning(browser);i++)await delay(25);
    if(browserRunning(browser)){signalBrowser(browser,'SIGKILL');for(let i=0;i<80&&browserRunning(browser);i++)await delay(25);}}
  for(let i=0;i<30;i++){try{fs.rmSync(profile,{recursive:true,force:true});break}
    catch(error){if(i===29)throw error;await delay(100);}}
}
})().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
