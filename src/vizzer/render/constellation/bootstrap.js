if(SERVED){
  fetch('/api/plan').then(async response=>{
    if(!response.ok){
      if(response.status===404){planError='Planning controls are disabled for this project.';refreshDossier();return;}
      throw new Error((await response.json()).error||'planning unavailable');
    }
    planContext=await response.json();
    if(planContext.engineVersion!==ENGINE_VERSION)throw new Error(`Vizzer server is out of date (${planContext.engineVersion||'unknown'} vs ${ENGINE_VERSION}). Restart vizzer serve.`);
    planDraft=JSON.parse(JSON.stringify(planContext.overlay.state));
    refreshDossier();
  }).catch(error=>{ planError=error.message||String(error); refreshDossier(); });
  fetch('/api/questions').then(async response=>{
    const body=await response.json();
    if(!response.ok)throw new Error(body.error||'question answers unavailable');
    if(body.engineVersion!==ENGINE_VERSION)throw new Error(`Vizzer server is out of date (${body.engineVersion||'unknown'} vs ${ENGINE_VERSION}). Restart vizzer serve before answering.`);
    questionContext=body;
    refreshDossier();
  }).catch(error=>{questionError=error.message||String(error);refreshDossier();});
  fetch('/api/discussions').then(async response=>{
    const body=await response.json();
    if(!response.ok)throw new Error(body.error||'discussion queue unavailable');
    if(body.engineVersion!==ENGINE_VERSION)throw new Error(`Vizzer server is out of date (${body.engineVersion||'unknown'} vs ${ENGINE_VERSION}). Restart vizzer serve before queuing discussion.`);
    discussionContext=body;discussionError='';refreshDossier();
  }).catch(error=>{discussionError=error.message||String(error);refreshDossier();});
  fetch('/api/workstreams').then(async response=>{
    if(response.status===404)return null;
    const body=await response.json();
    if(!response.ok)throw new Error(body.error||'workstreams unavailable');
    if(body.engineVersion!==ENGINE_VERSION)throw new Error(`Vizzer server is out of date (${body.engineVersion||'unknown'} vs ${ENGINE_VERSION}). Restart vizzer serve.`);
    DATA.workstreams=body.workstreams||{};
    if(currentView==='workstreams')renderCurrentView();
    return body;
  }).catch(error=>{console.warn('Vizzer workstreams:',error.message||String(error));});
}
frame();
window.__vizzerBoot.ready();
