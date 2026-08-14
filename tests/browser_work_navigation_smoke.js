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
  const devtoolsActive=path.join(profile,'DevToolsActivePort');
  const port=await waitFor(()=>fs.existsSync(devtoolsActive)&&fs.readFileSync(devtoolsActive,'utf8').split('\n')[0],
    'DevTools port');
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
  if(browser){const exited=new Promise(resolve=>browser.once('exit',resolve));browser.kill('SIGTERM');
    await Promise.race([exited,delay(1500)]);if(browser.exitCode==null)browser.kill('SIGKILL');}
  fs.rmSync(root,{recursive:true,force:true,maxRetries:5,retryDelay:50});
}
})().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
