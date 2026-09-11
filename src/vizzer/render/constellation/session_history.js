// Rolling session history is fetched separately; it never enlarges DATA or
// participates in Story, answer, or lifecycle writes.
const sessionHistory={payload:null,provider:'',session:'',hours:72,segments:[],points:[],busy:false,drawer:null,offset:null,events:[],hour:null,kind:'progress',generation:0,clickTimer:null,lastClick:null};
const historyDock=document.getElementById('historydock');
const historyLogFilter={kind:'',tool:'',q:''};
let historyLogSession='',historyLogOffset=0;
const historyDate=t=>new Date(t*1000).toLocaleString();
const historySetTimeout=typeof globalThis.setTimeout==='function'?globalThis.setTimeout.bind(globalThis):null;
const historyClearTimeout=typeof globalThis.clearTimeout==='function'?globalThis.clearTimeout.bind(globalThis):()=>{};
const historyShortId=id=>id.includes(':agent:')?id.split(':agent:')[1].slice(-12):(id.split(':')[1]||id).slice(0,8)+'…'+id.slice(-4);
function historySession(id){return sessionHistory.payload?.sessions.find(s=>s.id===id)}
function historyVisibleSessions(){return (sessionHistory.payload?.sessions||[]).filter(s=>!sessionHistory.provider||s.provider===sessionHistory.provider)}
function historyModel(s){return !s?.model||s.model.startsWith('<')?'Model unrecorded':s.model;}
function historyColor(id){
 const model=historyModel(historySession(id)),known={'gpt-6-astra':'#5ad4ff','gpt-5.6-sol':'#ffc857','gpt-5.6-terra':'#65dd9c','gpt-5.6-luna':'#bb9aff','claude-opus-5':'#ff8c78','claude-fable-5-1':'#f381cf','Model unrecorded':'#a0a8b6'};
 if(known[model])return known[model];let hash=0;for(const char of model)hash=(hash*31+char.charCodeAt(0))|0;return `hsl(${Math.abs(hash)%360} 72% 68%)`;
}
function historyOpacity(timestamp,now=Date.now()/1000){return Math.max(0,1-Math.max(0,now-timestamp)/(sessionHistory.hours*3600));}
function historyIsolate(id){if(!historySession(id))return;sessionHistory.session=id;historyRenderDock();}
function historyExitIsolation(){if(!sessionHistory.session)return false;sessionHistory.session='';historyRenderDock();return true;}
function historyQueueClick(target,x,y){
 historyClearTimeout(sessionHistory.clickTimer);sessionHistory.lastClick={target,x,y,time:Date.now()};
 if(historySetTimeout)sessionHistory.clickTimer=historySetTimeout(()=>historyOpenEvent(target.event,target.session),350);
}
function historyDoubleClick(x,y,node=-1){
 const last=sessionHistory.lastClick;
 const target=last&&Date.now()-last.time<650&&Math.hypot(x-last.x,y-last.y)<12?last.target:historyTrailAtPointer(x,y,node);
 if(!target)return false;historyClearTimeout(sessionHistory.clickTimer);sessionHistory.generation++;historyIsolate(target.session);sessionHistory.lastClick=null;return true;
}
function historyRenderDock(){
 const p=sessionHistory.payload;if(!p)return;
 const sessions=historyVisibleSessions(), select=document.getElementById('historysession');
 select.innerHTML='<option value="">All sessions</option>'+sessions.map(s=>`<option value="${esc(s.id)}">${esc(s.title)} · ${esc(historyShortId(s.id))}</option>`).join('');select.value=sessionHistory.session;
 const shown=sessionHistory.session?sessions.filter(s=>s.id===sessionHistory.session):sessions;
 const allowed=new Set(shown.map(s=>s.id)), bySession=new Map();
 for(const ref of p.references||[]){if(!allowed.has(ref.session)||!historyOpacity(ref.timestamp))continue;const n=nodeById.get(ref.storyId);if(n===undefined)continue;if(!bySession.has(ref.session))bySession.set(ref.session,[]);bySession.get(ref.session).push({...ref,n});}
 sessionHistory.segments=[];sessionHistory.points=[];
 for(const [sid,points] of bySession){
  points.forEach((p,i)=>{p.step=i;p.head=i===points.length-1;sessionHistory.points.push(p);
   // A multi-Story handoff is not an ordered trip through those Stories.
   // Keep its markers but break the path on both sides of ambiguous batches.
   if(i&&p.eventStoryCount===1&&points[i-1].eventStoryCount===1&&p.timestamp>points[i-1].timestamp)sessionHistory.segments.push({session:sid,a:points[i-1],b:p,event:p.event,timestamp:p.timestamp});
  });
 }
 document.getElementById('historylengthvalue').textContent=sessionHistory.hours===72?'3 days':sessionHistory.hours+' h';
 document.getElementById('historyall').disabled=!sessionHistory.session;
 const isolated=historySession(sessionHistory.session),banner=document.getElementById('historyisolation');
 banner.hidden=!isolated;document.getElementById('historyisolatedlabel').textContent=isolated?`Path isolated · ${isolated.provider} · ${historyShortId(isolated.id)}`:'';
 banner.title=isolated?isolated.title+' — click Show all paths to exit isolation':'';
 const models=new Map(shown.map(s=>[historyModel(s),s.id]));
 document.getElementById('historylegend').innerHTML=[...models].sort((a,b)=>a[0].localeCompare(b[0])).map(([model,id])=>`<span><i style="background:${historyColor(id)}"></i>${esc(model)}</span>`).join('');
 document.getElementById('historystatus').textContent=`${shown.length} sessions · ${bySession.size} with Story touches in last ${sessionHistory.hours} h · ${p.refreshing?'updating':p.lastScan?'checked '+new Date(p.lastScan).toLocaleTimeString():'indexing'}${p.error?' · '+p.error:''} · old trails fade out · ${sessionHistory.session?'Path isolated · use top banner to exit':'double-click path to isolate'}`;
}
async function historyRefresh(){
 if(!SERVED||sessionHistory.busy)return;sessionHistory.busy=true;
 try{const r=await fetch('/api/work-history?summary=1',{cache:'no-store'});if(!r.ok)throw Error('history unavailable '+r.status);sessionHistory.payload=await r.json();historyRenderDock();}
 catch(e){document.getElementById('historystatus').textContent=e.message+' · original records remain preserved';}
 finally{sessionHistory.busy=false;}
}
function historyPoint(p){
 const n=P[p.n];if(!n)return null;
 // Historical touches remain locatable even when today's lifecycle filters
 // hide the Story. These small hollow ghosts do not change Story visibility.
 const angle=-1.5+p.step*.85,r=18+(p.step%5)*2;
 return {x:n.x+Math.cos(angle)*r,y:n.y+Math.sin(angle)*r};
}
function historyCurve(s){
 const a=historyPoint(s.a),b=historyPoint(s.b);if(!a||!b)return null;
 const dx=b.x-a.x,dy=b.y-a.y,bend=s.a.n===s.b.n?.6:.12;
 return {a,b,c:{x:(a.x+b.x)/2-dy*bend,y:(a.y+b.y)/2+dx*bend}};
}
function historyCurveAt(curve,t){const u=1-t;return{x:u*u*curve.a.x+2*u*t*curve.c.x+t*t*curve.b.x,y:u*u*curve.a.y+2*u*t*curve.c.y+t*t*curve.b.y}}
function drawSessionHistory(){
 if(!lens.activity||!sessionHistory.payload)return;
 const now=Date.now()/1000;ctx.save();ctx.setLineDash([]);
 for(const s of sessionHistory.segments){const q=historyCurve(s);if(!q||!historyOpacity(s.a.timestamp,now))continue;
  ctx.strokeStyle=historyColor(s.session);ctx.globalAlpha=(sessionHistory.session?.95:.65)*historyOpacity(s.timestamp,now);ctx.lineWidth=sessionHistory.session?2.5:1.5;ctx.beginPath();ctx.moveTo(q.a.x,q.a.y);ctx.quadraticCurveTo(q.c.x,q.c.y,q.b.x,q.b.y);ctx.stroke();
 }
 for(const p of sessionHistory.points){const q=historyPoint(p);if(!q||!historyOpacity(p.timestamp,now))continue;
  ctx.globalAlpha=(sessionHistory.session?1:.8)*historyOpacity(p.timestamp,now);ctx.fillStyle=historyColor(p.session);ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=p.head?2:1;
  ctx.beginPath();ctx.arc(q.x,q.y,p.head?5:2.6,0,Math.PI*2);p.head?ctx.stroke():ctx.fill();
  if(p.head&&sessionHistory.session){ctx.font='11px sans-serif';ctx.fillText(historySession(p.session)?.provider+' · latest mapped',q.x+9,q.y-7);}
 }
 ctx.restore();
}
function hitSessionHistory(x,y){
 if(!lens.activity)return null;let found=null,best=6;
 for(const s of sessionHistory.segments){const q=historyCurve(s);if(!q||!historyOpacity(s.a.timestamp))continue;for(let t=0;t<=1;t+=.05){const p=historyCurveAt(q,t),d=Math.hypot(x-p.x,y-p.y);if(d<best){best=d;found=s;}}}
 for(const p of sessionHistory.points){const q=historyPoint(p);if(!q||!historyOpacity(p.timestamp))continue;const d=Math.hypot(x-q.x,y-q.y);if(d<best+2){best=d;found=p;}}
 return found;
}
function historyTrailAtPointer(x,y,node=-1){
 // Actual Story paint keeps priority; a large invisible node halo must not
 // swallow a trail dot beside it.
 if(node>=0&&Math.hypot(x-P[node].x,y-P[node].y)<=nodeRadius(node)+3)return null;
 return hitSessionHistory(x,y);
}
function historySidebar(title,body){
 if(sel>=0&&typeof storyDraftDirty==='function'&&storyDraftDirty(sel)){
  if(!guardNavigationAway(()=>{dismissDossier({focusCanvas:false,skipGuard:true});historySidebar(title,body)}))return false;
 }
 if(sel>=0&&!dismissDossier({focusCanvas:false}))return false;
 document.getElementById('dossieridentity').innerHTML=`<h2>${esc(title)}</h2><p class="historymeta">Session history · previous 3 days</p>`;
 dbody.innerHTML=body;document.getElementById('dossierfooter').innerHTML='';dossier.classList.add('open');dossier.setAttribute('aria-hidden','false');document.documentElement.classList.add('dossier-open');return true;
}
function historySessionMarkup(s){
 const span=s.observedSpanSeconds<3600?Math.round(s.observedSpanSeconds/60)+' min':(s.observedSpanSeconds/3600).toFixed(1)+' h';
 return `<p class="historymeta">${esc(s.provider)} · ${esc(s.model||'model unrecorded')}<br>${esc(s.id)}</p><p><b>Recorded worktree</b><br>${esc(s.cwd||'Unrecorded')}</p><p><b>Recorded branch</b><br>${esc(s.branch||'Unrecorded')}</p><p>${s.updates} public updates · ${s.actions} tool invocations<br>${span} observed span, including gaps.</p><p class="historymeta">Last record ${historyDate(s.last)}. This is not measured working time.</p><div id="historydrawercontrols"><button data-hlog="${esc(s.id)}">Open work log</button><button data-hsession="${esc(s.id)}">Recent progress</button></div>`;
}
async function historyOpenSession(id,hour=null,append=false){
 const s=historySession(id);if(!s)return;
 const gen=++sessionHistory.generation;
 if(!append){if(!historySidebar(s.title,historySessionMarkup(s)+'<p>Loading recorded progress…</p>'))return;sessionHistory.events=[];sessionHistory.hour=hour;sessionHistory.session=id;sessionHistory.drawer='session';historyRenderDock();}
 const query=new URLSearchParams({session:id,kind:sessionHistory.kind,hour:hour===null?'':String(hour),offset:append?String(sessionHistory.offset):'0'});
 try{const r=await fetch('/api/work-history?'+query);if(!r.ok)throw Error('Could not load session');const p=await r.json();if(gen!==sessionHistory.generation||sel>=0)return;sessionHistory.events=append?sessionHistory.events.concat(p.events):p.events;sessionHistory.offset=p.nextOffset;
 historySidebar(s.title,`<div class="historyfilterbar" role="region" aria-label="Work progress filters"><h3>${hour===null?'Recent progress':`${72-hour} hours ago`}</h3><label>Activity <select id="historykind"><option value="progress">Progress and explanations</option><option value="guidance">User / team guidance</option><option value="action">Tool invocations</option><option value="">All activity</option></select></label></div>`+historySessionMarkup(s)+`<p class="historymeta">${p.total} matching records · agent reports, not independently verified results.</p>`+sessionHistory.events.map(e=>`<button class="historyevent" data-hevent="${e.id}"><small>${historyDate(e.timestamp)} · ${esc(e.kind)}</small><span class="excerpt">${esc(e.text.slice(0,380))}</span></button>`).join('')+(p.nextOffset!==null?'<button id="historyolder">Load older records</button>':''));
 document.getElementById('historykind').value=sessionHistory.kind;
 }catch(e){if(gen===sessionHistory.generation)historySidebar(s.title,historySessionMarkup(s)+'<p>'+esc(e.message)+'</p>');}
}
function historyInsights(text){
 // An extractive reading aid, not an autonomous review or a finding generator.
 // Keep requested checks separate from reported outcomes; preserve the source.
 const sentences=String(text).split(/(?<=[.!?])\s+|\n+/).map(s=>s.replace(/^\s*[-*#]+\s*/,'').trim()).filter(Boolean);
 const out={risks:[],checks:[],challenges:[],rationale:[],opportunities:[],suggestions:[],evidence:[]};
 const clip=s=>s.length>650?s.slice(0,647)+'…':s;
 for(const sentence of sentences){
  if(/^(?:Evidence(?: directory)?|Receipts?|Result bundles?)\b/i.test(sentence)){out.evidence.push(clip(sentence));continue;}
  if(/^(?:Main )?risks?:/i.test(sentence)){out.risks.push(clip(sentence.replace(/^(?:Main )?risks?:\s*/i,'')));continue;}
  if(/^(?:Attack|Review targets?|Check for)\b/i.test(sentence)){
   out.checks.push(...sentence.replace(/^(?:Attack|Review targets?:?|Check for)\s*/i,'').replace(/[.]$/,'').split(/,\s+(?![^()]*\))/).map(s=>clip(s.replace(/^and\s+/i,''))));continue;
  }
  if(/^(?:(?:Please|Independently)\s+)?(?:perform|conduct|return|inspect|verify|distinguish|run|review|do not|check|test|ensure|confirm)\b/i.test(sentence))continue;
  if(/\b(?:opportunit(?:y|ies)|could improve|next step|follow-up|recommend(?:ed)?|suggest(?:ed)?|we should)\b/i.test(sentence))out.opportunities.push(clip(sentence));
  if(/\b(?:because|reason|chose|decided|so that|therefore|instead)\b|, so\b/i.test(sentence))out.rationale.push(clip(sentence));
  // Match reported states, not "attack stale IDs", "no failures", or the
  // word "repair" in a task title. Heuristics remain attributed excerpts.
  if(/\b(?:failed|failure|blocked|blocking|missing|stale|conflict|slow|quota|overloaded|timed out|remaining|cannot|can't|disappeared|vanished)\b/i.test(sentence)&&!/\b(?:no|zero|without)\s+(?:\w+\s+)?(?:failures?|blockers?|conflicts?|missing|stale)\b/i.test(sentence))out.challenges.push(clip(sentence));
 }
 const requested=out.checks.join(' '),reported=out.challenges.join(' ');
 if(/\b(?:IDs?|selection|channel|filtering|locked|lifetime)\b/i.test(requested))out.suggestions.push('**Coverage:** turn the requested membership, filtering, and lifetime edge cases into a small regression matrix, with the expected outcome for each case.');
 if(/tautolog|negative control|mutation/i.test(requested))out.suggestions.push('**Test strength:** add a negative control or targeted mutation that must fail; a green test alone does not prove it detects the defect.');
 if(/evidence|attribution|source ordering/i.test(requested))out.suggestions.push('**Evidence clarity:** bind each claim to its exact source snapshot and result record; keep failed methods, assertion occurrences, and deduplicated issues distinct.');
 if(/\b(?:slow|latency|stall|timed out)\b/i.test(reported))out.suggestions.push('**Performance follow-up:** investigate the remaining slow stage separately, retaining its measured baseline and a clear boundary between this repair and later optimization.');
 if(/\b(?:worktree|checkout)\b/i.test(reported)&&/\b(?:disappeared|vanished|missing)\b/i.test(reported))out.suggestions.push('**Continuity:** verify the branch, commit, and recovery path before recreating or cleaning the missing checkout; record the result in the handoff.');
 if(/\b(?:quota|overloaded)\b/i.test(reported))out.suggestions.push('**Review availability:** record provider failures as no verdict, then seek an authorized independent fallback rather than repeatedly retrying an unavailable reviewer.');
 const section=(heading,items,empty)=>`### ${heading}\n\n`+(items.length?[...new Set(items)].slice(0,12).map(s=>'- '+s).join('\n'):empty)+'\n\n';
 out.markdown='### Challenges and context\n\nExtracted from this public record; these are attributed statements, not independently verified findings.\n\n';
 out.markdown+=section('Reported challenges / remaining gaps',out.challenges,'No explicit obstacle was identified in this record. A review request is not itself a finding.');
 if(out.risks.length)out.markdown+=section('Stated risks — not confirmed defects',out.risks,'');
 if(out.checks.length)out.markdown+=section('Requested review checks — not findings',out.checks,'');
 out.markdown+=section('Recorded rationale',out.rationale,'No explicit rationale was identified. See the original record and surrounding work log.');
 out.markdown+=section('Opportunities to improve — recorded',out.opportunities,'No explicit improvement proposal was identified in this record.');
 out.markdown+=section('Opportunities to improve — suggested follow-ups',out.suggestions,'No additional suggestion derived from this record.');
 if(out.suggestions.length)out.markdown+='These are UI-generated suggestions based on the topics above, not agent commitments, approved work, or completed actions.\n\n';
 if(out.evidence.length)out.markdown+=section('Evidence referenced — not a current finding',out.evidence,'');
 return out;
}
async function historyOpenEvent(id,sid){
 const s=historySession(sid);if(!s)return;const gen=++sessionHistory.generation;
 try{const r=await fetch('/api/work-history/event?id='+encodeURIComponent(id));if(!r.ok)throw Error('Event unavailable');const e=await r.json();if(gen!==sessionHistory.generation)return;
 const insights=historyInsights(e.text);
 sessionHistory.drawer='event';historySidebar(s.title,`<h3>${historyDate(e.timestamp)} · ${esc(e.kind)}</h3><div class="storymd historyinsights">${renderStoryMarkdown(insights.markdown)}</div><details class="historyoriginal"><summary>Original recorded message</summary><div class="storymd">${renderStoryMarkdown(e.text)}</div></details><p class="historymeta">Extractive grouping may miss nuance; the original record is preserved. No private reasoning is inferred.<br>Event ${esc(e.id)}<br>${esc(s.sourceName)} · record ${e.line}</p>`+historySessionMarkup(s));
 }catch(e){document.getElementById('historystatus').textContent=e.message;}
}
async function historyOpenLog(sid,offset=0){
 const s=historySession(sid);if(!s)return;const gen=++sessionHistory.generation;
 try{const query=new URLSearchParams({session:sid,...historyLogFilter,offset:String(offset)});const r=await fetch('/api/work-history/log?'+query);if(!r.ok)throw Error('Log unavailable');const p=await r.json();if(gen!==sessionHistory.generation)return;
 const controls=`<form id="historylogfilters" class="historyfilterbar" aria-label="Work log filters"><label>Activity <select id="historylogkind"><option value="">All activity</option><option value="progress">Progress</option><option value="guidance">User / team guidance</option><option value="action">Tool invocations</option></select></label><label>Tool <select id="historylogtool"><option value="">All tools</option><option value="@exec">Invoked exec (all variants)</option>${p.tools.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join('')}</select></label><label>Search public log <input id="historylogsearch" type="search" maxlength="200" value="${esc(historyLogFilter.q)}"></label><button type="submit">Apply filters</button><button id="historylogclear" type="button">Clear filters</button></form>`;
 sessionHistory.drawer='log';if(!historySidebar(s.title,`<button data-hsession="${esc(sid)}">Back to session</button><h3>Work log</h3>${controls}<p class="historymeta">${p.matchingEvents} matching of ${p.totalEvents} records in the last 3 days · showing ${p.eventCount?offset+1:0}–${offset+p.eventCount}, newest page first (chronological within page). Filters do not alter the archive.<br>${esc(p.path)}<br>Tool names only; command arguments and output are not collected.</p><div class="storymd historylog">${renderStoryMarkdown(p.markdown)}</div>${offset?'<button id="historylognewer">Newer records</button>':''}${p.nextOffset!==null?'<button id="historylogolder">Older records</button>':''}`))return;
 historyLogSession=sid;historyLogOffset=offset;
 document.getElementById('historylogkind').value=historyLogFilter.kind;document.getElementById('historylogtool').value=historyLogFilter.tool;
 document.getElementById('historylogfilters').onsubmit=e=>{e.preventDefault();historyLogFilter.kind=document.getElementById('historylogkind').value;historyLogFilter.tool=document.getElementById('historylogtool').value;historyLogFilter.q=document.getElementById('historylogsearch').value;historyOpenLog(sid)};
 document.getElementById('historylogclear').onclick=()=>{Object.assign(historyLogFilter,{kind:'',tool:'',q:''});historyOpenLog(sid)};
 document.getElementById('historylogkind').onchange=document.getElementById('historylogtool').onchange=()=>document.getElementById('historylogfilters').requestSubmit();
 if(offset)document.getElementById('historylognewer').onclick=()=>historyOpenLog(sid,Math.max(0,offset-300));
 if(p.nextOffset!==null)document.getElementById('historylogolder').onclick=()=>historyOpenLog(sid,p.nextOffset);
 }catch(e){document.getElementById('historystatus').textContent=e.message;}
}
function historyHandleClick(e){
 const s=e.target.closest('[data-hsession]');if(s){historyOpenSession(s.dataset.hsession,s.dataset.hhour===undefined?null:Number(s.dataset.hhour));return;}
 const event=e.target.closest('[data-hevent]');if(event){historyOpenEvent(event.dataset.hevent,sessionHistory.session);return;}
 const log=e.target.closest('[data-hlog]');if(log){historyOpenLog(log.dataset.hlog);return;}
 if(e.target.id==='historyolder')historyOpenSession(sessionHistory.session,sessionHistory.hour,true);
}
if(historyDock){
 historyDock.addEventListener('click',historyHandleClick);
 dbody.addEventListener('click',historyHandleClick);
 dbody.addEventListener('change',e=>{if(e.target.id==='historykind'){sessionHistory.kind=e.target.value;historyOpenSession(sessionHistory.session,sessionHistory.hour)}});
 document.getElementById('historyprovider').onchange=e=>{sessionHistory.provider=e.target.value;sessionHistory.session='';historyRenderDock()};
 document.getElementById('historysession').onchange=e=>{sessionHistory.session=e.target.value;historyRenderDock()};
 document.getElementById('historylength').oninput=e=>{sessionHistory.hours=Math.max(1,Math.min(72,Number(e.target.value)||72));historyRenderDock()};
 document.getElementById('historyall').onclick=historyExitIsolation;
 document.getElementById('historydetails').onclick=()=>{if(sessionHistory.session)historyOpenLog(sessionHistory.session);else historySidebar('Session work logs','<p>Select a session to isolate its snail trail, or open its log below. A session without an explicit Story reference has a log but no invented map position.</p>'+historyVisibleSessions().map(s=>`<button class="historyevent" data-hsession="${esc(s.id)}">${esc(s.provider+' · '+s.title)}<small>${esc(s.id)}</small></button>`).join(''))};
 document.getElementById('historyrefresh').onclick=historyRefresh;
 if(SERVED){
  if(historySetTimeout)historySetTimeout(historyRefresh,0);else historyRefresh();
  if(typeof globalThis.setInterval==='function')globalThis.setInterval(()=>{if(!document.hidden)historyRefresh()},30000);
 }else{document.getElementById('historystatus').textContent='Open the locally served Vizzer to see session history.'}
}
