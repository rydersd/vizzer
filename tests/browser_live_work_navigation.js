const fs=require('fs'),os=require('os'),path=require('path');
const {spawn}=require('child_process');

(async()=>{
const chrome=process.argv[2],url=process.argv[3];
if(!chrome||!url)throw new Error('usage: browser_live_work_navigation.js <chrome> <url>');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'vizzer-live-work-navigation-'));
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const waitFor=async(fn,label,timeout=10000)=>{const deadline=Date.now()+timeout;
  while(Date.now()<deadline){try{const value=await fn();if(value)return value;}catch(_){}await delay(40);}
  throw new Error(`timed out waiting for ${label}`);};
let browser,socket;
try{
  browser=spawn(chrome,['--headless=new','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,url],{stdio:'ignore'});
  const activeFile=path.join(profile,'DevToolsActivePort');
  const port=await waitFor(()=>fs.existsSync(activeFile)&&fs.readFileSync(activeFile,'utf8').split('\n')[0],'DevTools port');
  const target=await waitFor(async()=>{const targets=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    return targets.find(candidate=>candidate.type==='page'&&candidate.url.startsWith(url));},'live Vizzer page');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let nextId=0;const pending=new Map();
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(!message.id)return;const slot=pending.get(message.id);if(!slot)return;
    pending.delete(message.id);message.error?slot.reject(new Error(message.error.message)):slot.resolve(message.result);});
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++nextId;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value;};
  const keyCode={ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40};
  const key=async value=>{const code=keyCode[value];
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:value,code:value,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:value,code:value,windowsVirtualKeyCode:code,nativeVirtualKeyCode:code});};
  await send('Runtime.enable');await send('Page.enable');
  await waitFor(()=>evaluate(`document.readyState==='complete'&&typeof workNavigationIndexes==='function'&&document.getElementById('boot').hidden`),'Vizzer boot');
  const lanes=await evaluate(`({version:ENGINE_VERSION,active:workNavigationIndexes('active'),recent:workNavigationIndexes('recent')})`);
  if(!lanes.active.length||lanes.recent.length<2)throw new Error(`insufficient live lanes ${JSON.stringify(lanes)}`);
  const selected=()=>evaluate(`sel`),outside=await evaluate(`DATA.nodes.findIndex((_,index)=>!workNavigationIndexes('active').includes(index))`);
  await evaluate(`openNode(${outside});cv.focus()`);await key('ArrowRight');const activeFirst=await selected();
  await key('ArrowRight');const activeSecond=await selected();await key('ArrowLeft');const activeBack=await selected();
  await evaluate(`openNode(${lanes.recent[0]});cv.focus()`);await key('ArrowDown');const recentDown=await selected();await key('ArrowUp');const recentBack=await selected();
  await evaluate(`openNode(${lanes.recent[0]});const input=document.createElement('input');input.id='live-nav-input';input.value='draft';dbody.appendChild(input);input.focus()`);
  await key('ArrowDown');const inputSelection=await selected(),inputValue=await evaluate(`document.getElementById('live-nav-input').value`);
  await evaluate(`for(const key of Object.keys(filt))filt[key]=false;for(const key of Object.keys(rfilt))rfilt[key]=false;searchMatches=DATA.nodes.map(()=>false);openNode(${outside});cv.focus()`);
  await key('ArrowRight');const filterIndependent=await selected();
  const receipt={version:lanes.version,activeCount:lanes.active.length,recentCount:lanes.recent.length,
    expected:{activeFirst:lanes.active[0],activeSecond:lanes.active[1]??lanes.active[0],activeBack:lanes.active[0],recentDown:lanes.recent[1],recentBack:lanes.recent[0],inputSelection:lanes.recent[0],filterIndependent:lanes.active[0]},
    actual:{activeFirst,activeSecond,activeBack,recentDown,recentBack,inputSelection,filterIndependent},inputValue};
  if(JSON.stringify(receipt.expected)!==JSON.stringify(receipt.actual)||inputValue!=='draft')throw new Error(`live navigation mismatch ${JSON.stringify(receipt)}`);
  process.stdout.write(JSON.stringify(receipt));
}finally{
  if(socket)socket.close();if(browser){const exited=new Promise(resolve=>browser.once('exit',resolve));browser.kill('SIGTERM');
    await Promise.race([exited,delay(1500)]);if(browser.exitCode==null)browser.kill('SIGKILL');}
  fs.rmSync(profile,{recursive:true,force:true,maxRetries:5,retryDelay:50});
}
})().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
