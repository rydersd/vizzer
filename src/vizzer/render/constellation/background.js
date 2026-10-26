// Browser-local images are keyed by project identity and never enter the graph.
// IndexedDB keeps binary images out of localStorage and out of project files.
(function(){
  const layer=document.getElementById('cluster-background');
  const panel=document.getElementById('background-panel');
  const open=document.getElementById('background-open');
  const file=document.getElementById('background-file');
  const slider=document.getElementById('background-opacity');
  const remove=document.getElementById('background-remove');
  const status=document.getElementById('background-status');
  const canPersist=Boolean(DATA.projectIdConfigured);
  const key='project:'+DATA.projectId+':'+location.pathname;
  let current=null,objectURL='',revision=0,queue=Promise.resolve();
  const database=new Promise((resolve,reject)=>{
    if(!canPersist){resolve(null);return;}
    if(!window.indexedDB){reject(new Error('Image storage is unavailable in this browser.'));return;}
    const request=window.indexedDB.open('vizzer-cluster-backgrounds',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('projects');
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(new Error('Cannot open browser image storage.'));
    request.onblocked=()=>reject(new Error('Close older Vizzer tabs and try again.'));
  });
  // Attach a rejection handler immediately, before the first storage use.
  database.catch(()=>{});
  async function storage(mode,record){
    if(!canPersist)throw new Error('Set a unique project.id to save this image between visits.');
    const db=await database;
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('projects',mode),store=tx.objectStore('projects');
      const request=mode==='readonly'?store.get(key):record?store.put(record,key):store.delete(key);
      tx.oncomplete=()=>resolve(request.result);
      tx.onerror=tx.onabort=()=>reject(new Error('Could not save the image. Browser storage may be full or disabled.'));
    });
  }
  function enqueue(operation){
    queue=queue.catch(()=>{}).then(operation);
    queue.catch(error=>{status.textContent=error.message;});
    return queue;
  }
  function syncVisibility(){layer.hidden=!current||document.getElementById('cv').hidden;}
  function apply(record){
    if(objectURL)URL.revokeObjectURL(objectURL);
    current=record;objectURL=record?URL.createObjectURL(record.blob):'';
    if(record)layer.src=objectURL;else layer.removeAttribute('src');
    slider.value=String(record?.opacity??25);
    layer.style.opacity=String(Number(slider.value)/100);
    document.getElementById('background-value').value=slider.value+'%';
    remove.disabled=!record;slider.disabled=!record;
    syncVisibility();
  }
  function toggle(show){panel.hidden=!show;open.setAttribute('aria-expanded',String(show));if(show)file.focus();else open.focus();}
  open.addEventListener('click',()=>toggle(panel.hidden));
  document.getElementById('background-close').addEventListener('click',()=>toggle(false));
  panel.addEventListener('keydown',event=>{if(event.key==='Escape'){toggle(false);event.stopPropagation();}});
  new MutationObserver(syncVisibility).observe(document.getElementById('cv'),{attributes:true,attributeFilter:['hidden']});
  file.addEventListener('change',async()=>{
    const selected=file.files[0];file.value='';if(!selected)return;
    const attempt=++revision;
    try{
      if(!['image/png','image/jpeg','image/webp'].includes(selected.type))throw new Error('Choose a PNG, JPEG or WebP image.');
      if(selected.size>5*1024*1024)throw new Error('Choose an image up to 5 MB.');
      const url=URL.createObjectURL(selected),image=new Image();
      try{image.src=url;await image.decode();if(image.naturalWidth*image.naturalHeight>24000000)throw new Error('Choose an image with at most 24 million pixels.');}
      finally{URL.revokeObjectURL(url);}
      if(attempt!==revision)return;
      const record={blob:selected,opacity:Number(slider.value),name:selected.name};
      await enqueue(async()=>{if(attempt!==revision)return;if(canPersist)await storage('readwrite',record);if(attempt===revision){apply(record);status.textContent=canPersist?'Saved for this project: '+record.name:'Image active for this page. Set a unique project.id to save it between visits.';}});
    }catch(error){if(attempt===revision)status.textContent=error.message||'Could not read this image.';}
  });
  slider.addEventListener('input',()=>{
    if(!current)return;
    current={...current,opacity:Number(slider.value)};
    layer.style.opacity=String(current.opacity/100);
    document.getElementById('background-value').value=slider.value+'%';
  });
  slider.addEventListener('change',()=>{
    const record=current,attempt=revision;if(!record)return;
    enqueue(async()=>{if(canPersist&&attempt===revision)await storage('readwrite',record);});
  });
  remove.addEventListener('click',()=>{
    const attempt=++revision;
    enqueue(async()=>{if(canPersist)await storage('readwrite',null);if(attempt===revision){apply(null);status.textContent='Background removed.';}});
  });
  const initial=revision;
  enqueue(async()=>{const record=canPersist?await storage('readonly'):null;if(initial!==revision)return;if(record){apply(record);status.textContent='Saved for this project: '+record.name;}else{apply(null);if(!canPersist)status.textContent='Set a unique project.id to save images between visits.';}});
})();
