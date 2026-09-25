// ---- served-only runner fleet indicators ----
// Owner 2026-08-26: "in vizzer it should show the runners connected and i
// should be able to hover over and see status." Fed by /api/runners at request
// time (opt-in [runners] enabled): nothing here is baked into the committed
// file, and on file:// none of it runs, so exports stay byte-reproducible.
// No animation: the indicators repaint only when a payload arrives, and only
// when what they show has changed.
let runnerContext=null;
let runnerMarkupShown=null; // the markup currently in #runners, to skip no-op repaints
let runnerCardName='';      // the runner whose card is showing, '' when hidden
let runnerHideTimer=null, runnerLoadingTimer=null;
const RUNNER_LOADING_REPOLL_MS=3000;
const RUNNER_CARD_HIDE_DELAY_MS=150;
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
// "offline" comes FIRST, so a narrow window can only ever clip the lane.
function runnerIndicatorText(runner){
  if(runner.state==='out-of-pool')return '';
  const lane=runner.lane||runner.name||'runner';
  return runner.state==='offline'?`offline · ${lane}`:lane;
}
function runnerAccessibleLabel(runner){
  return `Runner ${runner.name}${runner.lane?`, lane ${runner.lane}`:''}, `
    +`${RUNNER_STATE_TEXT[runner.state]||runner.state}`;
}
// Pure seam: header markup for a payload. Four distinct states, never
// confused: loading (a serve that has not asked GitHub yet), live view only (a
// file:// page), unavailable (GitHub could not be reached; never a
// last-known-green indicator), and the fleet itself.
function runnerIndicatorsMarkup(payload){
  if(!payload)return '';
  if(payload.static)return '<span class="runnersnote">runners · live view only</span>';
  if(payload.loading)return '<span class="runnersnote" role="status">runners…</span>';
  if(!payload.available){
    return `<span class="runnersunavailable" title="${esc(payload.error||'Runner status unavailable')}">`
      +'runners unavailable</span>';
  }
  return (payload.runners||[]).map(runner=>
    `<button type="button" class="runner ${esc(runner.state)}" data-runner-name="${esc(runner.name)}"`
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
// Pure seam: keep the card inside the viewport (8px margin on each side).
function runnerCardLeft(anchorLeft,cardWidth,viewportWidth){
  return Math.max(8,Math.min(Math.round(anchorLeft),Math.round(viewportWidth-cardWidth-8)));
}
function runnerNamed(name){
  return runnerContext&&runnerContext.available
    ?(runnerContext.runners||[]).find(runner=>runner.name===name)||null:null;
}
function cancelRunnerCardHide(){
  if(runnerHideTimer!==null&&typeof clearTimeout==='function')clearTimeout(runnerHideTimer);
  runnerHideTimer=null;
}
function hideRunnerCard(){
  cancelRunnerCardHide();
  runnerCardName='';
  const card=document.getElementById('runnercard');
  if(card)card.hidden=true;
}
// The pointer may travel from the indicator into the card (WCAG 1.4.13:
// hoverable), so leaving either one hides after a short grace period that
// entering either one cancels.
function scheduleRunnerCardHide(){
  cancelRunnerCardHide();
  if(typeof setTimeout!=='function'){hideRunnerCard();return;}
  runnerHideTimer=setTimeout(hideRunnerCard,RUNNER_CARD_HIDE_DELAY_MS);
}
function showRunnerCard(button){
  const card=document.getElementById('runnercard');
  const runner=runnerNamed(button.dataset.runnerName);
  if(!card||!runner)return;
  cancelRunnerCardHide();
  card.innerHTML=runnerCardMarkup(runner,runnerContext,Date.now());
  card.hidden=false;
  runnerCardName=runner.name;
  const rect=button.getBoundingClientRect();
  const viewportWidth=typeof innerWidth==='number'?innerWidth:1280;
  card.style.left=`${runnerCardLeft(rect.left,card.offsetWidth||0,viewportWidth)}px`;
  card.style.top=`${Math.round(rect.bottom+6)}px`;
}
let runnerHoverBound=false;
function bindRunnerHover(container){
  if(runnerHoverBound||!container.addEventListener)return;
  runnerHoverBound=true;
  const target=event=>event.target&&event.target.closest?event.target.closest('.runner'):null;
  container.addEventListener('pointerover',event=>{const b=target(event);if(b)showRunnerCard(b);});
  container.addEventListener('pointerout',event=>{if(target(event))scheduleRunnerCardHide();});
  container.addEventListener('focusin',event=>{const b=target(event);if(b)showRunnerCard(b);});
  container.addEventListener('focusout',hideRunnerCard);
  const card=document.getElementById('runnercard');
  if(card&&card.addEventListener){
    card.addEventListener('pointerenter',cancelRunnerCardHide);
    card.addEventListener('pointerleave',scheduleRunnerCardHide);
  }
  if(typeof addEventListener==='function')addEventListener('keydown',dismissRunnerCardOnEscape);
}
// WCAG 1.4.13: the card can be dismissed without moving the pointer or focus.
function dismissRunnerCardOnEscape(event){
  if(event.key==='Escape'&&runnerCardName)hideRunnerCard();
}
function focusedRunnerName(container){
  const active=document.activeElement;
  return active&&container.contains&&container.contains(active)&&active.dataset
    ?active.dataset.runnerName||'':'';
}
function applyRunnerStatus(payload){
  runnerContext=payload||null;
  const container=document.getElementById('runners');
  if(!container)return;
  bindRunnerHover(container);
  const markup=runnerIndicatorsMarkup(runnerContext);
  const openCard=runnerCardName;
  if(markup!==runnerMarkupShown){
    // Rebuild only when what the header shows changed, and put keyboard
    // focus and an open card back on the same runner afterwards.
    const focused=focusedRunnerName(container);
    container.innerHTML=markup;
    container.hidden=markup==='';
    runnerMarkupShown=markup;
    // The runners row changes #top's height; the search box and rail are
    // placed from that measurement.
    if(typeof syncChromeMetrics==='function')syncChromeMetrics();
    const again=name=>name&&container.querySelectorAll
      ?[...container.querySelectorAll('.runner')].find(button=>button.dataset.runnerName===name)||null:null;
    const focusButton=again(focused);
    if(focusButton&&focusButton.focus)focusButton.focus();
    const cardButton=again(openCard);
    if(cardButton)showRunnerCard(cardButton);else if(openCard)hideRunnerCard();
  }else if(openCard){
    // Same indicators, newer details (elapsed time, data age): refresh the
    // open card's text in place.
    const runner=runnerNamed(openCard), card=document.getElementById('runnercard');
    if(runner&&card)card.innerHTML=runnerCardMarkup(runner,runnerContext,Date.now());
    else hideRunnerCard();
  }
}
// Pure seam: a cold serve answers "loading" at once while it asks GitHub, so
// ask again shortly instead of waiting for the next 90 s tick.
function runnerRepollDelay(body){
  return body&&body.loading?RUNNER_LOADING_REPOLL_MS:null;
}
async function refreshRunnerStatus(){
  if(!SERVED||typeof fetch!=='function')return false;
  try{
    const response=await fetch('/api/runners',{headers:{accept:'application/json'}});
    if(response.status===404){applyRunnerStatus(null);return false;} // disabled: no chrome
    const body=await response.json();
    applyRunnerStatus(response.ok?body:{available:false,
      error:body.error||'Runner status unavailable'});
    const delay=response.ok?runnerRepollDelay(body):null;
    if(delay!==null&&runnerLoadingTimer===null&&typeof setTimeout==='function'){
      runnerLoadingTimer=setTimeout(()=>{runnerLoadingTimer=null;refreshRunnerStatus();},delay);
    }
    return true;
  }catch(_error){
    applyRunnerStatus({available:false,error:'Runner status unavailable'});
    return false;
  }
}
