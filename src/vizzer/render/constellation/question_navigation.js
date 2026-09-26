// ---- Previous | "N of M" | Next across open owner questions ----
// Owner directive 2026-09-26: "when i start answering
// questions, and there are more than one. at the top of the panel i should
// just have a segmented control at the top to jump between next and prev, so i
// can get to the next one without closing the panel." The order is the owner
// question order: graph order of delivery items, then question order within an
// item. Other roles (a reference dossier has no answer footer) are left out.
// Served-only: the file:// build cannot record answers.
function openOwnerQuestionOrder(){
  return DATA.nodes.flatMap((node,n)=>node.foundation||(node.role||'delivery')!=='delivery'?[]
    :ownerQuestions(n).map(q=>({n,id:q.id})));
}
// Pure: where the dossier's story sits in the open-question order, or null
// when there is nothing to step to (static build, fewer than two open
// questions, or a story with no open question).
function questionNavigatorState(storyIndex=sel,focusId=questionNavFocusId){
  if(!SERVED||!Number.isInteger(storyIndex)||storyIndex<0)return null;
  const order=openOwnerQuestionOrder();
  if(order.length<2)return null;
  const here=order.filter(entry=>entry.n===storyIndex);
  if(!here.length)return null;
  const current=here.find(entry=>entry.id===focusId)||here[0];
  const position=order.indexOf(current);
  return {order,position,total:order.length,current,
    previous:order[position-1]||null,next:order[position+1]||null};
}
function questionNavigatorMarkup(state){
  if(!state)return '';
  return `<nav class="questionnav" aria-label="Owner questions" aria-keyshortcuts="ArrowLeft ArrowRight" data-question-nav>`
    +`<button type="button" data-question-nav-previous aria-label="Previous owner question" ${state.previous?'':'disabled'}>Previous</button>`
    +`<span role="status" aria-live="polite" data-question-nav-position>${state.position+1} of ${state.total}</span>`
    +`<button type="button" data-question-nav-next aria-label="Next owner question" ${state.next?'':'disabled'}>Next</button></nav>`;
}
const questionNavKeyStep=key=>key==='ArrowLeft'?-1:key==='ArrowRight'?1:0;
function navigateOwnerQuestion(step){
  const state=questionNavigatorState();
  const target=state&&(step<0?state.previous:state.next);
  if(!target)return false;
  showOwnerQuestion(target);
  // The header was rebuilt under the pressed button: keep keyboard focus on
  // the same segment, or its neighbour once this end is reached.
  const nav=dossierIdentity.querySelector('[data-question-nav]');
  const same=nav?.querySelector(step<0?'[data-question-nav-previous]':'[data-question-nav-next]');
  const other=nav?.querySelector(step<0?'[data-question-nav-next]':'[data-question-nav-previous]');
  (same&&!same.disabled?same:other)?.focus?.();
  return true;
}
// Drafts live in questionDrafts, which openNode never clears, so a chosen
// option is still selected when a step comes back to its card.
function showOwnerQuestion(target){
  questionNavFocusId=target.id;
  if(target.n!==sel)openNode(target.n);else refreshDossier();
  [...dbody.querySelectorAll('form[data-question-id]')].find(form=>form.dataset.questionId===target.id)
    ?.scrollIntoView?.({block:'start'});
}
// After the shown question is answered, move on to the next open question after it (or the nearest earlier one when it was the last).
function nextOpenQuestionAfter(before){
  if(!before)return null;
  const order=openOwnerQuestionOrder(), open=new Map(order.map(entry=>[entry.id,entry]));
  const later=before.order.slice(before.position+1).find(entry=>open.has(entry.id));
  const earlier=before.order.slice(0,before.position).reverse().find(entry=>open.has(entry.id));
  const pick=later||earlier;
  return pick?open.get(pick.id):null;
}
function syncQuestionNavigator(){
  const nav=dossierIdentity.querySelector('[data-question-nav]'), state=questionNavigatorState();
  if(!nav||!state)return;
  const position=nav.querySelector('[data-question-nav-position]');
  if(position)position.textContent=`${state.position+1} of ${state.total}`;
  const previous=nav.querySelector('[data-question-nav-previous]'), next=nav.querySelector('[data-question-nav-next]');
  if(previous)previous.disabled=!state.previous;
  if(next)next.disabled=!state.next;
}
function bindQuestionNavigator(){
  const nav=dossierIdentity.querySelector('[data-question-nav]');
  if(!nav)return;
  nav.querySelector('[data-question-nav-previous]')?.addEventListener('click',()=>navigateOwnerQuestion(-1));
  nav.querySelector('[data-question-nav-next]')?.addEventListener('click',()=>navigateOwnerQuestion(1));
  // Arrows on the focused control step questions; preventDefault keeps the
  // window-level work navigation from also firing.
  nav.addEventListener('keydown',event=>{
    const step=questionNavKeyStep(event.key);
    if(!step||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey)return;
    event.preventDefault();navigateOwnerQuestion(step);
  });
  // Working on a card makes it the shown question, so "N of M" stays true.
  (dbody.querySelectorAll?.('form[data-question-id]')||[]).forEach(form=>form.addEventListener('focusin',()=>{
    if(questionNavFocusId===form.dataset.questionId)return;
    questionNavFocusId=form.dataset.questionId;syncQuestionNavigator();
  }));
}
