let restartCsrfToken='';
const restartServiceButton=document.getElementById('restart-service');
const restartServiceStatus=document.getElementById('restart-service-status');
function offerServerRestart(body){
  if(body?.csrfToken&&body?.renderId&&body.renderId!==RENDER_ID){
    restartCsrfToken=body.csrfToken;
    if(restartServiceButton)restartServiceButton.hidden=false;
    if(restartServiceStatus)restartServiceStatus.textContent='This page and server use different Vizzer builds.';
  }
}
restartServiceButton?.addEventListener('click',async()=>{
  if(!restartCsrfToken)return;
  restartServiceButton.disabled=true;
  if(restartServiceStatus)restartServiceStatus.textContent='Checking the project service…';
  try{
    const response=await fetch('/api/server/restart',{method:'POST',headers:{'X-Vizzer-CSRF':restartCsrfToken}});
    const body=await response.json();
    if(!response.ok)throw new Error(body.error||'Could not restart Vizzer.');
    if(restartServiceStatus)restartServiceStatus.textContent=`Restarting ${body.service||'this project service'}…`;
    setTimeout(()=>location.reload(),1500);
  }catch(error){
    if(restartServiceStatus)restartServiceStatus.textContent=error.message||String(error);
    restartServiceButton.disabled=false;
  }
});
if(SERVED){
  fetch('/api/plan').then(async response=>{
    const body=await response.json();offerServerRestart(body);
    if(!response.ok){
      if(response.status===404){planError='Planning controls are disabled for this project.';refreshDossier();return;}
      throw new Error(body.error||'planning unavailable');
    }
    planContext=body;
    if(planContext.renderId!==RENDER_ID)throw new Error(`Vizzer server is out of date (${planContext.renderId||'unknown'} vs ${RENDER_ID}). Restart vizzer serve.`);
    planDraft=JSON.parse(JSON.stringify(planContext.overlay.state));
    refreshDossier();
  }).catch(error=>{ planError=error.message||String(error); refreshDossier(); });
  fetch('/api/questions').then(async response=>{
    const body=await response.json();
    offerServerRestart(body);
    if(!response.ok)throw new Error(body.error||'question answers unavailable');
    if(body.renderId!==RENDER_ID)throw new Error(`Vizzer server is out of date (${body.renderId||'unknown'} vs ${RENDER_ID}). Restart vizzer serve before answering.`);
    adoptQuestionAuthority(body);
  }).catch(error=>{questionError=error.message||String(error);refreshDossier();});
  fetch('/api/discussions').then(async response=>{
    const body=await response.json();
    offerServerRestart(body);
    if(!response.ok)throw new Error(body.error||'discussion queue unavailable');
    if(body.renderId!==RENDER_ID)throw new Error(`Vizzer server is out of date (${body.renderId||'unknown'} vs ${RENDER_ID}). Restart vizzer serve before queuing discussion.`);
    discussionContext=body;discussionError='';refreshDossier();
  }).catch(error=>{discussionError=error.message||String(error);refreshDossier();});
  fetch('/api/workstreams').then(async response=>{
    if(response.status===404)return null;
    const body=await response.json();
    offerServerRestart(body);
    if(!response.ok)throw new Error(body.error||'workstreams unavailable');
    if(body.renderId!==RENDER_ID)throw new Error(`Vizzer server is out of date (${body.renderId||'unknown'} vs ${RENDER_ID}). Restart vizzer serve.`);
    DATA.workstreams=body.workstreams||{};
    if(currentView==='workstreams')renderCurrentView();
    return body;
  }).catch(error=>{console.warn('Vizzer workstreams:',error.message||String(error));});
  loadReviewContext();
  // Runner fleet indicators (opt-in [runners]); the server caches ~60s.
  refreshRunnerStatus();
  setInterval(refreshRunnerStatus,90000);
}
syncChromeMetrics();
addEventListener('resize',syncChromeMetrics);
if(typeof ResizeObserver==='function'){
  const chromeObserver=new ResizeObserver(syncChromeMetrics);
  chromeObserver.observe(document.getElementById('top'));
  chromeObserver.observe(document.getElementById('search'));
}
// Fit once before deep-link navigation; never override a later owner zoom.
zoom=restZoom();
openRequestedStory();
frame();
window.__vizzerBoot.ready();
