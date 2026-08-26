const fs=require('fs'),os=require('os'),path=require('path');
const {pathToFileURL}=require('url');
const {spawn}=require('child_process');

(async()=>{
const chrome=process.argv[2];
if(!chrome)throw new Error('usage: browser_work_navigation_smoke.js <chrome>');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'vizzer-work-navigation-'));
const profile=path.join(root,'profile'),page=path.join(root,'constellation.html');
fs.mkdirSync(profile);fs.writeFileSync(page,fs.readFileSync(0,'utf8'));
const url=pathToFileURL(page).href,delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
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
  const keyCodes={ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40};
  const key=async value=>{const code=keyCodes[value];
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:value,code:value,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:value,code:value,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code});};
  await send('Runtime.enable');await send('Page.enable');
  await waitFor(()=>evaluate(`document.readyState==='complete'&&typeof workNavigationIndexes==='function'&&document.getElementById('boot').hidden`),'Vizzer boot');
  const ids=await evaluate(`Object.fromEntries(DATA.nodes.map((node,index)=>[node.id,index]))`);
  const selected=()=>evaluate(`DATA.nodes[sel].id`);

  await evaluate(`openNode(${ids['story:c']});cv.focus()`);
  await key('ArrowRight');const activeSequence=[await selected()];
  await key('ArrowRight');activeSequence.push(await selected());
  await key('ArrowRight');activeSequence.push(await selected());

  await evaluate(`openNode(${ids['story:c']});cv.focus()`);
  const recent=[await selected()];await key('ArrowUp');recent.push(await selected());

  await evaluate(`openNode(${ids['story:c']});const input=document.createElement('input');input.id='navigation-draft';input.value='draft';dbody.appendChild(input);input.focus()`);
  await key('ArrowDown');const inputPreserved=await selected();
  const inputValue=await evaluate(`document.getElementById('navigation-draft').value`);

  await evaluate(`for(const key of Object.keys(filt))filt[key]=false;for(const key of Object.keys(rfilt))rfilt[key]=false;searchMatches=DATA.nodes.map(()=>false);openNode(${ids['story:c']});cv.focus()`);
  await key('ArrowRight');const filterIndependent=await selected();
  const hint=await evaluate(`({active:dossierIdentity.textContent.includes('active 2'),recent:dossierIdentity.textContent.includes('recent 4')})`);
  process.stdout.write(JSON.stringify({active:activeSequence,recent,inputPreserved,inputValue,filterIndependent,hint}));
}finally{
  if(socket)socket.close();
  if(browser){
    signalBrowser(browser,'SIGTERM');
    if(!await waitForExit(browser,1500)){
      signalBrowser(browser,'SIGKILL');
      if(!await waitForExit(browser,5000))throw new Error('Chrome did not exit after SIGKILL');
    }
  }
  await removeRoot();
}
})().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
