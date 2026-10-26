const fs=require('fs'),os=require('os'),path=require('path');
const http=require('http');
const {spawn}=require('child_process');

(async()=>{
const chrome=process.argv[2];
if(!chrome)throw new Error('usage: browser_question_navigation_smoke.js <chrome>');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'vizzer-question-navigation-'));
const profile=path.join(root,'profile');fs.mkdirSync(profile);
// The control is served-only, so the page is served from loopback; every API
// request is refused, which leaves navigation (not answering) to test.
const html=fs.readFileSync(0,'utf8');
const server=http.createServer((request,response)=>{
  if(request.url==='/'){response.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});response.end(html);return;}
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
let browser,socket;
try{
  browser=spawn(chrome,['--headless=new','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--disable-dev-shm-usage','--remote-debugging-port=0',
    `--user-data-dir=${profile}`,url],
    {stdio:'ignore',detached:useProcessGroup});
  const devtoolsActive=path.join(profile,'DevToolsActivePort');
  const port=await waitFor(()=>fs.existsSync(devtoolsActive)&&fs.readFileSync(devtoolsActive,'utf8').split('\n')[0],
    'DevTools port',20000);
  const target=await waitFor(async()=>{
    const targets=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    return targets.find(candidate=>candidate.type==='page'&&candidate.url===url);
  },'Vizzer page');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let nextId=0;const pending=new Map();
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(!message.id)return;
    const slot=pending.get(message.id);if(!slot)return;pending.delete(message.id);
    message.error?slot.reject(new Error(message.error.message)):slot.resolve(message.result);});
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++nextId;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
    return result.result.value;};
  const keyCodes={ArrowLeft:37,ArrowRight:39,Tab:9};
  const key=async(value,modifiers=0)=>{const code=keyCodes[value];
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:value,code:value,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code,modifiers});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:value,code:value,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code,modifiers});};
  await send('Runtime.enable');await send('Page.enable');
  await waitFor(()=>evaluate(`document.readyState==='complete'&&document.getElementById('boot').hidden`),'Vizzer boot');
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
  process.stdout.write(JSON.stringify({opened,tabbed,box:{visible:box.visible,hit:box.hit},clicked,right,left}));
}finally{
  if(socket)socket.close();
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
