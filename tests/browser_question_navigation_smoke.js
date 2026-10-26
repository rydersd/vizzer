const fs=require('fs'),os=require('os'),path=require('path');
const http=require('http');
const {spawn}=require('child_process');

(async()=>{
const chrome=process.argv[2];
const assetDir=process.argv[3];
const chromeRecord=process.argv[4];
if(!chrome||!assetDir||!chromeRecord)throw new Error('usage: browser_question_navigation_smoke.js <chrome> <renderer-assets-dir> <chrome-record>');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'vizzer-question-navigation-'));
const profile=path.join(root,'profile');fs.mkdirSync(profile);
// The control is served-only, so the page is served from loopback; every API
// request is refused, which leaves navigation (not answering) to test. The
// renderer's local editor assets are served from its own output bundle.
const html=fs.readFileSync(0,'utf8');
const assets=new Map([
  ['/milkdown.js',{body:fs.readFileSync(path.join(assetDir,'milkdown.js')),type:'text/javascript; charset=utf-8'}],
  ['/milkdown.css',{body:fs.readFileSync(path.join(assetDir,'milkdown.css')),type:'text/css; charset=utf-8'}],
]);
const requests=[];
const eventProbe=`<script>
window.__vizzerSmokeEvents=[];
(function(){
  function clip(value){try{return String(value??'').slice(0,512)}catch(_){return '[unprintable]'}}
  addEventListener('error',function(event){
    if(window.__vizzerSmokeEvents.length>=20)return;
    const target=event&&event.target,error=event&&event.error;
    window.__vizzerSmokeEvents.push({type:'error',message:clip(event&&event.message),filename:clip(event&&event.filename),
      line:event&&event.lineno||0,column:event&&event.colno||0,
      target:target?{tag:clip(target.tagName),src:clip(target.currentSrc||target.src),href:clip(target.href),rel:clip(target.rel)}:null,
      error:error?{name:clip(error.name),message:clip(error.message),stack:clip(error.stack)}:null});
  },true);
  addEventListener('unhandledrejection',function(event){
    if(window.__vizzerSmokeEvents.length>=20)return;
    const reason=event&&event.reason;
    window.__vizzerSmokeEvents.push({type:'unhandledrejection',reason:clip(reason&& (reason.stack||reason.message)||reason)});
  });
})();
</script>`;
const server=http.createServer((request,response)=>{
  const pathname=new URL(request.url,'http://127.0.0.1').pathname;
  if(pathname==='/'&&request.method==='GET'){
    response.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});response.end(eventProbe+html);
    if(requests.length<40)requests.push({path:pathname,status:200});
    return;
  }
  if(request.method==='GET'&&assets.has(pathname)){
    const asset=assets.get(pathname);response.writeHead(200,{'Content-Type':asset.type});response.end(asset.body);
    if(requests.length<40)requests.push({path:pathname,status:200});
    return;
  }
  if(requests.length<40)requests.push({path:pathname.slice(0,512),status:404});
  response.writeHead(404,{'Content-Type':'application/json'});response.end('{"error":"not served in this test"}');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url=`http://127.0.0.1:${server.address().port}/`,delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const useProcessGroup=process.platform!=='win32';
const signalBrowser=(child,signal)=>{
  if(!useProcessGroup&&(child.exitCode!==null||child.signalCode!==null))return false;
  try{
    if(useProcessGroup&&Number.isInteger(child.pid)){process.kill(-child.pid,signal);return true;}
    return child.kill(signal);
  }catch(error){if(error.code==='ESRCH'||error.code==='EPERM')return false;throw error;}
};
const browserRunning=child=>{
  if(useProcessGroup&&Number.isInteger(child.pid)){
    try{process.kill(-child.pid,0);return true;}
    catch(error){if(error.code==='ESRCH'||error.code==='EPERM')return false;throw error;}
  }
  return child.exitCode===null&&child.signalCode===null;
};
const waitForExit=async(child,timeout)=>{
  const deadline=Date.now()+timeout;
  while(browserRunning(child)&&Date.now()<deadline)await delay(25);
  return !browserRunning(child);
};
const removeRoot=async()=>{
  const deadline=Date.now()+5000;
  while(true){
    try{fs.rmSync(root,{recursive:true,force:true});return;}
    catch(error){
      if(!['EBUSY','EMFILE','ENFILE','ENOTEMPTY','EPERM'].includes(error.code)||Date.now()>=deadline)throw error;
      await delay(100);
    }
  }
};
const waitFor=async(fn,label,timeout=10000)=>{
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){try{const value=await fn();if(value)return value;}catch(_){}await delay(40);}
  throw new Error(`timed out waiting for ${label}`);
};
let browser,socket,chromeStderr='';
const pageErrors=[];
try{
  browser=spawn(chrome,['--headless=new','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--disable-dev-shm-usage','--remote-debugging-port=0',
    `--user-data-dir=${profile}`,url],
    {stdio:['ignore','ignore','pipe'],detached:useProcessGroup});
  fs.writeFileSync(chromeRecord,JSON.stringify({pid:browser.pid,profile}));
  browser.stderr?.on('data',chunk=>{
    if(chromeStderr.length<65536)chromeStderr+=chunk.toString('utf8').slice(0,65536-chromeStderr.length);
  });
  const devtoolsActive=path.join(profile,'DevToolsActivePort');
  const port=await waitFor(()=>fs.existsSync(devtoolsActive)&&fs.readFileSync(devtoolsActive,'utf8').split('\n')[0],
    'DevTools port',20000);
  const target=await waitFor(async()=>{
    const targets=await (await fetch(`http://127.0.0.1:${port}/json/list`,{signal:AbortSignal.timeout(1000)})).json();
    return targets.find(candidate=>candidate.type==='page'&&candidate.url===url);
  },'Vizzer page');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('DevTools WebSocket open timed out after 5000ms')),5000);
    socket.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
    socket.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('DevTools WebSocket failed to open'));},{once:true});
  });
  let nextId=0;const pending=new Map();
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);
    if(message.method){
      if(pageErrors.length<40&&['Runtime.exceptionThrown','Runtime.consoleAPICalled','Log.entryAdded'].includes(message.method)){
        const params=message.params||{};let detail='';
        if(message.method==='Runtime.exceptionThrown')detail=params.exceptionDetails?.text||params.exceptionDetails?.exception?.description||'';
        if(message.method==='Runtime.consoleAPICalled')detail=(params.args||[]).map(arg=>arg.value??arg.description??'').join(' ');
        if(message.method==='Log.entryAdded')detail=params.entry?.text||'';
        const entry=params.entry||{};
        pageErrors.push({method:message.method,detail:String(detail).slice(0,2000),
          url:String(entry.url||'').slice(0,512),source:String(entry.source||'').slice(0,128),lineNumber:entry.lineNumber||0});
      }
      return;
    }
    if(!message.id)return;
    const slot=pending.get(message.id);if(!slot)return;pending.delete(message.id);
    message.error?slot.reject(new Error(message.error.message)):slot.resolve(message.result);});
  const send=(method,params={},timeoutMs=2000)=>new Promise((resolve,reject)=>{
    const id=++nextId;const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP ${method} timed out after ${timeoutMs}ms`));},timeoutMs);
    pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});
    try{socket.send(JSON.stringify({id,method,params}));}
    catch(error){pending.delete(id);clearTimeout(timer);reject(error);}
  });
  const evaluate=async(expression,timeoutMs=2000)=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},timeoutMs);
    if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
    return result.result.value;};
  const keyCodes={ArrowLeft:37,ArrowRight:39,Tab:9};
  const key=async(value,modifiers=0)=>{const code=keyCodes[value];
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:value,code:value,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code,modifiers});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:value,code:value,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code,modifiers});};
  await send('Runtime.enable');await send('Log.enable');await send('Page.enable');
  const bootDeadline=Date.now()+10000;let bootState=null,bootEvaluationError=null,bootFailure=null;
  while(Date.now()<bootDeadline){
    try{
      const remaining=bootDeadline-Date.now();
      bootState=await evaluate(`(()=>{const e=document.getElementById('boot');return {readyState:document.readyState,
        hidden:e?.hidden??null,className:e?.className??null,text:e?.textContent??null,bootHook:typeof window.__vizzerBoot?.ready,
        smokeEvents:(window.__vizzerSmokeEvents||[]).slice(0,20)}})()`,Math.min(2000,remaining));
      if(bootState.className==='error'){
        bootFailure=`Vizzer boot failed: ${bootState.text||'no error detail'}`;
        break;
      }
      if(Date.now()>bootDeadline){bootEvaluationError='Boot readiness evaluation completed after 10s deadline';break;}
      if(bootState.readyState==='complete'&&bootState.hidden)break;
    }catch(error){bootEvaluationError=error.message||String(error);break;}
    await delay(40);
  }
  if(bootFailure||bootEvaluationError||!bootState||bootState.readyState!=='complete'||!bootState.hidden){
    const diagnostics={state:bootState,evaluationError:bootEvaluationError,pageErrors,requests,chromeStderr:chromeStderr.slice(0,65536)};
    throw new Error(`${bootFailure||'Vizzer boot did not become ready within 10s'}: ${JSON.stringify(diagnostics)}`);
  }
  const ids=await evaluate(`Object.fromEntries(DATA.nodes.map((node,index)=>[node.id,index]))`);
  const state=()=>evaluate(`({story:sel>=0?DATA.nodes[sel].id:null,
    position:document.querySelector('[data-question-nav-position]')?.textContent||null,
    focus:[...(document.activeElement?.attributes||[])].map(a=>a.name).find(name=>name.startsWith('data-question-nav-'))||document.activeElement?.id||document.activeElement?.tagName})`);
  await evaluate(`openNode(${ids['story:a']})`);
  await waitFor(()=>evaluate(`document.querySelector('[data-question-nav]')&&getComputedStyle(document.getElementById('dossier')).visibility!=='hidden'`),'question control');
  const opened=await state();
  // Keyboard reach: Shift+Tab back from the panel's close button lands on the
  // control (Previous is disabled at 1 of M, so Next).
  await evaluate(`document.getElementById('close').focus()`);
  await key('Tab',8);const tabbed=await state();
  // A real pointer click at Next's centre: the button must be the element hit there.
  const box=await evaluate(`(()=>{const r=document.querySelector('[data-question-nav-next]').getBoundingClientRect();
    const x=r.left+r.width/2,y=r.top+r.height/2,hit=document.elementFromPoint(x,y);
    return {x,y,visible:r.width>0&&r.height>0,hit:Boolean(hit&&hit.closest('[data-question-nav-next]'))};})()`);
  for(const type of ['mousePressed','mouseReleased'])
    await send('Input.dispatchMouseEvent',{type,x:box.x,y:box.y,button:'left',clickCount:1});
  const clicked=await state();
  // Arrow keys on the focused control.
  await key('ArrowRight');const right=await state();
  await key('ArrowLeft');const left=await state();
  const assetStatus=Object.fromEntries(['/milkdown.js','/milkdown.css'].map(path=>[
    path,requests.find(request=>request.path===path)?.status??null]));
  process.stdout.write(JSON.stringify({opened,tabbed,box:{visible:box.visible,hit:box.hit},clicked,right,left,assetStatus}));
}finally{
  if(socket){try{socket.close();}catch(_){}}
  if(browser){
    signalBrowser(browser,'SIGTERM');
    if(!await waitForExit(browser,1500)){
      signalBrowser(browser,'SIGKILL');
      if(!await waitForExit(browser,5000))throw new Error('Chrome did not exit after SIGKILL');
    }
  }
  await new Promise(resolve=>server.close(resolve));
  await removeRoot();
}
})().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
