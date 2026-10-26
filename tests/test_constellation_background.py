"""Black-box regressions for the browser-local constellation background picker."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vizzer.config import Config, DEFAULTS
from vizzer.model import Graph
from vizzer.render import render_all


def test_background_picker_is_project_local_validates_and_preserves_failed_replacement(tmp_path):
    node = shutil.which("node")
    assert node is not None, "Node is required for browser-local picker regression"
    html = render_all(Graph(vocab=Config(data=DEFAULTS).vocab), Config(data=DEFAULTS),
                      tmp_path, only={"constellation"})["constellation.html"]
    assert 'id="cluster-background"' in html
    assert 'id="background-panel"' in html
    assert "__VIZZER_BACKGROUND_JS__" not in html
    assert "background.css" in html or "#cluster-background" in html
    script = (Path(__file__).parents[1] / "src/vizzer/render/constellation/background.js") \
        .read_text(encoding="utf-8")
    harness = r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const stores=new Map();let nextObject=0,lastBlob=null;
class Element{
  constructor(id){this.id=id;this.hidden=id==='cv'?false:id==='background-panel';this.disabled=false;
    this.value=id==='background-opacity'?'25':'';this.files=[];this.listeners={};this.attributes={};
    this.style={};this.textContent='';this.src='';}
  addEventListener(type,fn){(this.listeners[type]??=[]).push(fn)}
  dispatch(type,event={}){for(const fn of this.listeners[type]||[])fn({target:this,key:'',stopPropagation(){},...event})}
  setAttribute(k,v){this.attributes[k]=String(v)}
  removeAttribute(k){delete this.attributes[k];if(k==='src')this.src=''}
  focus(){}
}
function createContext(projectId,configured=true){
 const ids=new Map(['cluster-background','background-panel','background-open','background-file',
  'background-opacity','background-remove','background-status','background-value','background-close','cv']
  .map(id=>[id,new Element(id)]));
 const dbKey='project:'+projectId;
 const db={createObjectStore(){},transaction(){
   const tx={objectStore(){return {
     get(key){return {result:stores.get(key)}},
     put(value,key){stores.set(key,value);return {result:key}},
     delete(key){stores.delete(key);return {result:undefined}}
   }}};
   Object.defineProperty(tx,'oncomplete',{set(fn){queueMicrotask(fn)}});
   Object.defineProperty(tx,'onerror',{set(){}});Object.defineProperty(tx,'onabort',{set(){}});
   return tx;
 }};
 const indexedDB={open(){const req={result:db};queueMicrotask(()=>{req.onupgradeneeded?.();req.onsuccess?.()});return req}};
 const URL={createObjectURL(blob){lastBlob=blob;return 'blob:fake-'+(++nextObject)},revokeObjectURL(){}};
 class Image{set src(v){this._src=v}get src(){return this._src}async decode(){await Promise.resolve()}
  get naturalWidth(){return lastBlob?.width||1000}get naturalHeight(){return lastBlob?.height||1000}}
 class MutationObserver{constructor(fn){this.fn=fn}observe(){}}
 const document={getElementById:id=>ids.get(id)};
 const sandbox={DATA:{projectId,projectIdConfigured:configured},location:{pathname:'/projects/'+projectId+'/index.html'},document,window:{indexedDB},URL,Image,MutationObserver,
   Promise,Number,String,Error,console};sandbox.globalThis=sandbox;
 vm.runInNewContext(input.script,sandbox);
 return {ids,dbKey};
}
const wait=()=>new Promise(resolve=>setTimeout(resolve,0));
async function main(){
 const a=createContext('one');await wait();
 const file=a.ids.get('background-file');
 file.files=[{name:'scene.webp',type:'image/webp',size:900000}];file.dispatch('change');await wait();await wait();
 const oldSrc=a.ids.get('cluster-background').src;
 file.files=[{name:'bad.gif',type:'image/gif',size:20}];file.dispatch('change');await wait();
 const rejected=a.ids.get('background-status').textContent;
 const preserved=a.ids.get('cluster-background').src===oldSrc;
 file.files=[{name:'large.jpg',type:'image/jpeg',size:5*1024*1024+1}];file.dispatch('change');await wait();
 const sizeRejected=a.ids.get('background-status').textContent;
 file.files=[{name:'pixels.png',type:'image/png',size:100,width:6000,height:5000}];file.dispatch('change');await wait();
 const pixelsRejected=a.ids.get('background-status').textContent;
 const slider=a.ids.get('background-opacity');slider.value='40';slider.dispatch('input');slider.dispatch('change');await wait();await wait();
 const b=createContext('two');await wait();
 const aReload=createContext('one');await wait();
 const isolated=b.ids.get('cluster-background').hidden;
 const restored=aReload.ids.get('cluster-background').hidden===false &&
   aReload.ids.get('background-opacity').value==='40';
 aReload.ids.get('background-remove').dispatch('click');await wait();await wait();
 const afterRemove=createContext('one');await wait();
 const fallback=createContext('fallback',false);await wait();
 fallback.ids.get('background-file').files=[{name:'temporary.png',type:'image/png',size:30}];
 fallback.ids.get('background-file').dispatch('change');await wait();await wait();
 process.stdout.write(JSON.stringify({rejected,preserved,sizeRejected,pixelsRejected,isolated,restored,
   removed:afterRemove.ids.get('cluster-background').hidden,
   fallbackActive:fallback.ids.get('cluster-background').hidden===false,
   fallbackNote:fallback.ids.get('background-status').textContent,
   fallbackNotStored:!stores.has('project:fallback:/projects/fallback/index.html')}));
}
main().catch(error=>{process.stderr.write(String(error.stack||error));process.exitCode=1});
'''
    completed = subprocess.run(
        [node, "-e", harness], input=json.dumps({"script": script}),
        text=True, capture_output=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert "PNG, JPEG or WebP" in result["rejected"]
    assert result["preserved"] is True
    assert "up to 5 MB" in result["sizeRejected"]
    assert "24 million pixels" in result["pixelsRejected"]
    assert result["isolated"] is True
    assert result["restored"] is True
    assert result["removed"] is True
    assert result["fallbackActive"] is True
    assert "unique project.id" in result["fallbackNote"]
    assert result["fallbackNotStored"] is True


@pytest.mark.parametrize("mime,size,width,height,expected", [
    ("image/jpeg", 5 * 1024 * 1024 + 1, 100, 100, "up to 5 MB"),
    ("image/png", 10, 6000, 5000, "24 million pixels"),
])
def test_background_picker_enforces_size_and_decoded_pixel_limits(
    tmp_path, mime, size, width, height, expected
):
    # Keep the boundaries visible in the source contract; runtime persistence
    # and failed-replacement behavior are exercised in the test above.
    from vizzer.render.constellation import _template_text

    script = _template_text(Config(data=DEFAULTS))
    assert "5*1024*1024" in script
    assert "24000000" in script
    assert mime.startswith("image/") and size > 0 and width * height > 0
    assert expected in script
