// ---- served-only runner fleet indicators ----
// Owner 2026-08-26: "in vizzer it should show the runners connected and i
// should be able to hover over and see status." Fed by /api/runners at request
// time (opt-in [runners] enabled): nothing here is baked into the committed
// file, and on file:// none of it runs, so exports stay byte-reproducible.
// No animation: the indicators repaint only when a payload arrives.
let runnerContext=null;
const RUNNER_STATE_TEXT={
  'idle':'online · idle',
  'busy':'online · busy',
  'offline':'offline',
  'out-of-pool':'not in pool',
};
// Pure seam: "3m 07s" / "1h 04m" for a whole number of seconds.
function runnerElapsedText(seconds){
  const total=Math.max(0,Math.floor(Number(seconds)||0));
  const hours=Math.floor(total/3600),minutes=Math.floor(total%3600/60),rest=total%60;
  if(hours)return `${hours}h ${String(minutes).padStart(2,'0')}m`;
  if(minutes)return `${minutes}m ${String(rest).padStart(2,'0')}s`;
  return `${rest}s`;
}
function runnerSecondsSince(iso,nowMs){
  const at=Date.parse(iso||'');
  return Number.isFinite(at)?Math.max(0,(nowMs-at)/1000):null;
}
// Pure seam: the compact text an indicator shows without hovering. The lane
// comes from the runner's labels (server-built); a runner with no routing
// labels falls back to its name so two such runners stay distinguishable.
// An idle/offline runner with no routing labels is a dashed dot with no text:
// it is out of the build pool, so it should not compete for attention.
function runnerIndicatorText(runner){
  if(runner.state==='out-of-pool')return '';
  const lane=runner.lane||runner.name||'runner';
  return runner.state==='offline'?`${lane} offline`:lane;
}
function runnerAccessibleLabel(runner){
  return `Runner ${runner.name}${runner.lane?`, lane ${runner.lane}`:''}, `
    +`${RUNNER_STATE_TEXT[runner.state]||runner.state}`;
}
// Pure seam: header markup for a payload. Unavailable is said out loud —
// never a last-known-green indicator (the server drops the last good payload
// when a refresh fails).
function runnerIndicatorsMarkup(payload){
  if(!payload)return '';
  if(!payload.available){
    return `<span class="runnersunavailable" title="${esc(payload.error||'Runner status unavailable')}">`
      +'runners unavailable</span>';
  }
  return (payload.runners||[]).map((runner,index)=>
    `<button type="button" class="runner ${esc(runner.state)}" data-runner-index="${index}"`
    +` aria-describedby="runnercard" aria-label="${esc(runnerAccessibleLabel(runner))}">`
    +'<span class="runnerdot" aria-hidden="true"></span>'
    +(runnerIndicatorText(runner)?`<span class="runnerlane">${esc(runnerIndicatorText(runner))}</span>`:'')
    +'</button>'
  ).join('');
}
// Pure seam: the hover card for one runner at a given wall-clock time.
function runnerCardMarkup(runner,payload,nowMs){
  const lines=[`<b>${esc(runner.name)}</b>`];
  lines.push(`<span class="runnerstate ${esc(runner.state)}">${esc(RUNNER_STATE_TEXT[runner.state]||runner.state)}</span>`);
  if(!runner.inPool)lines.push('<small>No custom routing labels — out of the labelled build pool.</small>');
  lines.push(`<small>Labels: ${esc((runner.labels||[]).join(', ')||'none')}</small>`);
  if(runner.state==='busy'){
    const job=runner.job;
    if(job){
      const elapsed=runnerSecondsSince(job.startedAt,nowMs);
      lines.push(`<span>${esc(job.workflow)}${job.workflow&&job.name?' · ':''}${esc(job.name)}</span>`);
      lines.push(`<small>${job.pr?`PR #${esc(job.pr)}`:esc(job.branch||'no PR')}`
        +`${elapsed===null?'':` · running ${esc(runnerElapsedText(elapsed))}`}</small>`);
    }else{
      lines.push(`<small>${esc(runner.jobError||'current job unknown')}</small>`);
    }
  }
  if(!runner.online){
    const since=runnerSecondsSince(runner.lastSeenOnline,nowMs);
    lines.push(`<small>${since===null
      ?`Not seen online since this serve started${payload&&payload.observingSince?` (${esc(payload.observingSince)})`:''}`
      :`Last seen online ${esc(runnerElapsedText(since))} ago`}</small>`);
  }
  const age=Number(payload&&payload.ageSeconds);
  if(payload&&payload.stale&&Number.isFinite(age))
    lines.push(`<small>Runner data ${Math.max(0,Math.floor(age))}s old</small>`);
  return lines.join('');
}
function hideRunnerCard(){
  const card=document.getElementById('runnercard');
  if(card)card.hidden=true;
}
function showRunnerCard(button){
  const card=document.getElementById('runnercard');
  const runner=runnerContext&&runnerContext.available
    ?(runnerContext.runners||[])[Number(button.dataset.runnerIndex)]:null;
  if(!card||!runner)return;
  card.innerHTML=runnerCardMarkup(runner,runnerContext,Date.now());
  const rect=button.getBoundingClientRect();
  card.style.left=`${Math.max(8,Math.round(rect.left))}px`;
  card.style.top=`${Math.round(rect.bottom+6)}px`;
  card.hidden=false;
}
let runnerHoverBound=false;
function bindRunnerHover(container){
  if(runnerHoverBound||!container.addEventListener)return;
  runnerHoverBound=true;
  const target=event=>event.target&&event.target.closest?event.target.closest('.runner'):null;
  container.addEventListener('pointerover',event=>{const b=target(event);if(b)showRunnerCard(b);});
  container.addEventListener('pointerout',event=>{if(target(event))hideRunnerCard();});
  container.addEventListener('focusin',event=>{const b=target(event);if(b)showRunnerCard(b);});
  container.addEventListener('focusout',hideRunnerCard);
}
function applyRunnerStatus(payload){
  runnerContext=payload||null;
  const container=document.getElementById('runners');
  if(!container)return;
  bindRunnerHover(container);
  const markup=runnerIndicatorsMarkup(runnerContext);
  container.innerHTML=markup;
  container.hidden=markup==='';
  hideRunnerCard();
}
async function refreshRunnerStatus(){
  if(!SERVED||typeof fetch!=='function')return false;
  try{
    const response=await fetch('/api/runners',{headers:{accept:'application/json'}});
    if(response.status===404){applyRunnerStatus(null);return false;} // disabled: no chrome
    const body=await response.json();
    applyRunnerStatus(response.ok?body:{available:false,
      error:body.error||'Runner status unavailable'});
    return true;
  }catch(_error){
    applyRunnerStatus({available:false,error:'Runner status unavailable'});
    return false;
  }
}
