// ---- question -> story reader ----
// Owner directive 2026-11-21: "when a question is about a new story, allow it to
// open that md file and display it inline with a back to the question view" /
// "don't make me hunt down the story." The server reads the story from disk
// (/api/question-story/<id>), so new untracked stories open like committed ones.
// The reader is an overlay: the question view underneath is never re-rendered,
// so drafts, selections and scroll survive Back to question.

const storyReaderCache = new Map();
function fetchQuestionStory(storyId){
  if(!storyReaderCache.has(storyId)){
    storyReaderCache.set(storyId,fetch('/api/question-story/'+encodeURIComponent(storyId))
      .then(async response=>{
        let body=null;try{body=await response.json();}catch(_){}
        if(!response.ok)return{ok:false,error:(body&&body.error)||'The story could not be loaded.'};
        return{ok:true,path:body.path,markdown:body.markdown};
      }).catch(()=>({ok:false,error:'The Vizzer server could not be reached.'})));
  }
  return storyReaderCache.get(storyId);
}
function questionStoryLinkMarkup(q){
  const id=q&&q.storyId;
  if(!id)return '<p class="questionstory missing" role="status">This question names no story.</p>';
  const slug=String(id).replace(/^story:/,'');
  if(!SERVED)return `<p class="questionstory"><span>Story <code>${esc(slug)}</code> · open the served view (vizzer serve) to read it inline.</span></p>`;
  return `<p class="questionstory" data-question-story-row="${esc(id)}"><button type="button" class="questionstorybtn" data-open-question-story="${esc(id)}">Read story: ${esc(slug)}</button>`
    +` <span class="questionstorystatus" aria-live="polite"></span></p>`;
}
// Resolve every story row inside a container up front, so an unresolvable story
// is stated on the question itself rather than discovered on click.
function hydrateQuestionStoryLinks(container){
  if(!SERVED||!container)return;
  container.querySelectorAll('[data-question-story-row]').forEach(async row=>{
    const id=row.dataset.questionStoryRow,status=row.querySelector('.questionstorystatus');
    const result=await fetchQuestionStory(id);
    if(!status)return;
    if(result.ok){status.textContent=result.path;status.title=result.path;}
    else{
      row.classList.add('missing');status.textContent='Story file not found. '+result.error;
      const button=row.querySelector('button');if(button)button.disabled=true;
    }
  });
}

function splitStoryFrontMatter(text){
  const normalized=String(text).replace(/\r\n?/g,'\n');
  const match=normalized.match(/^---\n([\s\S]*?)\n---\n?/);
  if(!match)return{fields:[],body:normalized};
  const fields=[];
  for(const line of match[1].split('\n')){
    const field=line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if(field)fields.push([field[1],field[2]]);
    else if(fields.length&&/^\s+\S/.test(line))fields[fields.length-1][1]+=' '+line.trim();
  }
  return{fields,body:normalized.slice(match[0].length)};
}
function storyFrontMatterMarkup(fields){
  if(!fields.length)return '';
  return '<dl class="storyfm">'+fields.map(([key,value])=>
    `<dt>${esc(key)}</dt><dd>${mdInline(value)}</dd>`).join('')+'</dl>';
}
function storyTitle(body,fallback){
  const heading=body.match(/^#\s+(.+?)\s*$/m);
  return heading?heading[1]:fallback;
}
function storyReaderBodyMarkup(markdown,fallbackTitle){
  const{fields,body}=splitStoryFrontMatter(markdown);
  const previous=mdLinkResolver;
  // Relative links to sibling stories open in this reader; others stay inert.
  mdLinkResolver=url=>{
    const target=url.split('#')[0];
    const m=target.match(/(?:^|\/)([A-Za-z0-9][A-Za-z0-9._-]*)\.md$/);
    return m&&!/^[a-z]+:/i.test(target)?'story:'+m[1]:null;
  };
  try{
    return `<h2 class="storyreadertitle">${esc(storyTitle(body,fallbackTitle))}</h2>`
      +storyFrontMatterMarkup(fields)+`<div class="storymd storyfull">${renderStoryMarkdown(body)}</div>`;
  }finally{mdLinkResolver=previous;}
}


// ---- owner comments on story text ----
// Owner directive 2026-11-21: select text in the story, comment on it, and the
// comments reach the orchestrator for a grill session (vizzer/story-comments.json,
// surfaced as views/story-comments.md). Everything is text: the quote and the
// comment only ever reach the DOM through esc() or textContent.
const STORY_QUOTE_MAX=2000,STORY_COMMENT_MAX=4000;

// Pure. Find `quote` across an array of text-node strings, tolerating
// whitespace differences. Returns [{node,start,end}] per node touched, or null.
// A selection that crosses blocks reads with a newline the DOM text lacks, so a
// second pass treats node boundaries as whitespace.
function findQuoteSegments(texts,quote){
  const want=String(quote).replace(/\s+/g,' ').trim();
  if(!want)return null;
  for(const separated of [false,true]){
    let flat='';const map=[];
    texts.forEach((text,node)=>{
      if(separated&&flat&&!flat.endsWith(' ')){flat+=' ';map.push(null);}
      for(let i=0;i<text.length;i++){
        const space=/\s/.test(text[i]);
        if(space&&(flat.endsWith(' ')||!flat))continue;
        flat+=space?' ':text[i];map.push({node,offset:i});
      }
    });
    const at=flat.indexOf(want);
    if(at<0)continue;
    const segments=[];
    for(let i=at;i<at+want.length;i++){
      const hit=map[i];if(!hit)continue;
      const last=segments[segments.length-1];
      if(last&&last.node===hit.node)last.end=hit.offset+1;
      else segments.push({node:hit.node,start:hit.offset,end:hit.offset+1});
    }
    return segments.length?segments:null;
  }
  return null;
}
function storyCommentPayload({storyId,path,questionId,quote,heading,comment}){
  const payload={storyId,path,quote:String(quote).slice(0,STORY_QUOTE_MAX),
    heading:String(heading||''),comment:String(comment).trim(),clientTime:new Date().toISOString()};
  if(questionId)payload.questionId=questionId;
  return payload;
}
function storyCommentsListMarkup(comments,anchoredIds){
  if(!comments.length)return '<p class="storysectionmissing">No comments yet. Select text in the story to add one.</p>';
  return comments.map(comment=>{
    const anchored=anchoredIds.has(comment.id);
    return `<article class="storycommentitem" data-story-comment="${esc(comment.id)}">`
      +`<header><span class="storycommentstatus">${esc(comment.status)}</span>`
      +(anchored?'':' <span class="storycommentloose">unanchored</span>')+'</header>'
      +`<blockquote>${esc(comment.quote)}</blockquote>`
      +(comment.heading?`<small>${esc(comment.heading)}</small>`:'')
      +`<p>${esc(comment.comment)}</p>`
      +(comment.status==='open'?`<button type="button" data-delete-story-comment="${esc(comment.id)}">Delete</button>`:'')
      +'</article>';
  }).join('');
}

function storyTextNodes(root){
  const nodes=[],walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  for(let node=walker.nextNode();node;node=walker.nextNode())nodes.push(node);
  return nodes;
}
// Wrap the quote in <mark> where it can still be found; returns whether it was.
function highlightStoryQuote(root,comment){
  const nodes=storyTextNodes(root);
  const segments=findQuoteSegments(nodes.map(node=>node.data),comment.quote);
  if(!segments)return false;
  for(const{node,start,end}of segments.reverse()){
    const range=document.createRange();range.setStart(nodes[node],start);range.setEnd(nodes[node],end);
    const mark=document.createElement('mark');mark.className='storycommentmark';
    mark.dataset.commentId=comment.id;mark.title=comment.comment;
    range.surroundContents(mark);
  }
  return true;
}
function renderStoryComments(state){
  state.body.querySelectorAll('mark.storycommentmark').forEach(mark=>mark.replaceWith(...mark.childNodes));
  state.body.normalize();
  const anchored=new Set();
  if(state.story)state.comments.forEach(comment=>{
    if(highlightStoryQuote(state.body,comment))anchored.add(comment.id);
  });
  state.side.innerHTML=state.story?storyCommentsListMarkup(state.comments,anchored):'';
  state.side.querySelectorAll('[data-story-comment]').forEach(item=>item.addEventListener('click',event=>{
    if(event.target.closest('button'))return;
    state.body.querySelector(`mark[data-comment-id="${CSS.escape(item.dataset.storyComment)}"]`)
      ?.scrollIntoView({block:'center'});
  }));
  state.side.querySelectorAll('[data-delete-story-comment]').forEach(button=>
    button.addEventListener('click',()=>deleteStoryComment(state,button.dataset.deleteStoryComment)));
}
async function refreshStoryComments(state){
  const storyId=state.storyId;
  try{
    const response=await fetch('/api/story-comments?storyId='+encodeURIComponent(storyId),{cache:'no-store'});
    const body=await response.json();
    if(!response.ok)throw new Error(body.error||'comments could not be loaded');
    if(storyReaderState!==state||state.storyId!==storyId)return;
    state.comments=body.comments;state.csrf=body.csrfToken;renderStoryComments(state);
  }catch(error){
    if(storyReaderState===state)state.side.insertAdjacentHTML('afterbegin',
      `<p class="storyreadererror" role="alert">Comments could not be loaded. ${esc(error.message)}</p>`);
  }
}
async function storyCommentRequest(state,method,url,body){
  const response=await fetch(url,{method,headers:{'Content-Type':'application/json','X-Vizzer-CSRF':state.csrf},
    body:body?JSON.stringify(body):undefined});
  let result={};try{result=await response.json();}catch(_){}
  if(!response.ok)throw new Error(result.error||'The server refused the comment.');
  return result;
}
async function deleteStoryComment(state,id){
  try{
    await storyCommentRequest(state,'DELETE','/api/story-comments/'+encodeURIComponent(id));
    state.comments=state.comments.filter(comment=>comment.id!==id);renderStoryComments(state);
  }catch(error){state.side.insertAdjacentHTML('afterbegin',
    `<p class="storyreadererror" role="alert">${esc(error.message)}</p>`);}
}
function closeCommentCompose(state){
  if(state.compose){state.compose.remove();state.compose=null;}
  if(state.affordance){state.affordance.remove();state.affordance=null;}
}
function nearestHeadingAbove(body,range){
  let found='';
  for(const heading of body.querySelectorAll('.mdh,.storyreadertitle')){
    if(heading.compareDocumentPosition(range.startContainer)&Node.DOCUMENT_POSITION_FOLLOWING
        ||heading.contains(range.startContainer))found=heading.textContent;
  }
  return found.trim();
}
function bindCommentSelection(state){
  state.body.addEventListener('mouseup',()=>setTimeout(()=>{
    if(storyReaderState!==state||state.compose||!state.story||!state.csrf)return;
    const selection=window.getSelection();
    if(!selection||selection.isCollapsed||!selection.rangeCount)return;
    const range=selection.getRangeAt(0);
    if(!state.body.contains(range.commonAncestorContainer))return;
    const quote=selection.toString().trim();
    if(!quote)return;
    closeCommentCompose(state);
    const rect=range.getBoundingClientRect();
    const button=document.createElement('button');
    button.type='button';button.className='storycommentadd';button.textContent='Comment';
    button.style.left=Math.max(8,Math.min(rect.right,window.innerWidth-100))+'px';
    button.style.top=Math.max(8,rect.bottom+6)+'px';
    // mousedown must not collapse the selection before we read it.
    button.addEventListener('mousedown',event=>event.preventDefault());
    const context={quote,heading:nearestHeadingAbove(state.body,range),rect};
    button.addEventListener('click',()=>openCommentCompose(state,context));
    state.overlay.appendChild(button);state.affordance=button;
  },0));
  state.body.addEventListener('mousedown',()=>{if(!state.compose&&state.affordance)closeCommentCompose(state);});
}
function openCommentCompose(state,{quote,heading,rect}){
  closeCommentCompose(state);
  const form=document.createElement('form');form.className='storycommentform';
  form.innerHTML='<blockquote></blockquote><textarea maxlength="'+STORY_COMMENT_MAX+'" aria-label="Your comment" required></textarea>'
    +'<div class="storycommentactions"><button type="submit">Save</button><button type="button" data-cancel>Cancel</button></div>'
    +'<p class="storyreadererror" role="alert" hidden></p>';
  form.querySelector('blockquote').textContent=quote.length>240?quote.slice(0,240)+'…':quote;
  form.style.left=Math.max(8,Math.min(rect.left,window.innerWidth-340))+'px';
  form.style.top=Math.max(8,Math.min(rect.bottom+6,window.innerHeight-230))+'px';
  state.overlay.appendChild(form);state.compose=form;
  const area=form.querySelector('textarea'),error=form.querySelector('.storyreadererror');
  area.focus();
  form.querySelector('[data-cancel]').addEventListener('click',()=>closeCommentCompose(state));
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(!area.value.trim())return;
    const save=form.querySelector('[type=submit]');save.disabled=true;
    try{
      const result=await storyCommentRequest(state,'POST','/api/story-comments',
        storyCommentPayload({storyId:state.storyId,path:state.story.path,questionId:state.questionId,
          quote,heading,comment:area.value}));
      window.getSelection()?.removeAllRanges();
      closeCommentCompose(state);
      state.comments.push(result.comment);renderStoryComments(state);
    }catch(failure){error.textContent=failure.message;error.hidden=false;save.disabled=false;}
  });
}

let storyReaderState=null;
function scrollSnapshot(from){
  const saved=[];
  for(let el=from;el&&el!==document.body;el=el.parentElement){
    if(el.scrollTop>0)saved.push([el,el.scrollTop]);
  }
  return{saved,windowY:window.scrollY||0};
}
function closeStoryReader(){
  const state=storyReaderState;if(!state)return;
  storyReaderState=null;
  document.removeEventListener('keydown',state.onKey,true);
  closeCommentCompose(state);
  state.overlay.remove();
  state.snapshot.saved.forEach(([el,top])=>{el.scrollTop=top;});
  window.scrollTo(0,state.snapshot.windowY);
  if(state.opener&&state.opener.isConnected)state.opener.focus({preventScroll:true});
}
async function showStoryInReader(storyId){
  const state=storyReaderState;if(!state)return;
  const slug=storyId.replace(/^story:/,'');
  state.body.innerHTML=`<p class="storysectionmissing">Loading ${esc(slug)}…</p>`;
  const result=await fetchQuestionStory(storyId);
  if(storyReaderState!==state)return;
  state.path.textContent=result.ok?result.path:'';
  state.body.innerHTML=result.ok?storyReaderBodyMarkup(result.markdown,slug)
    :`<p class="storyreadererror" role="alert"><b>${esc(slug)}</b> could not be opened. ${esc(result.error)}</p>`;
  state.body.scrollTop=0;
  state.storyId=storyId;state.story=result.ok?result:null;state.comments=[];
  closeCommentCompose(state);
  renderStoryComments(state);
  if(result.ok)refreshStoryComments(state);
  state.body.querySelectorAll('[data-md-story]').forEach(link=>link.addEventListener('click',event=>{
    event.preventDefault();state.trail.push(storyId);showStoryInReader(link.dataset.mdStory);
    state.previous.hidden=false;
  }));
}
function openStoryReader(storyId,opener){
  if(storyReaderState)closeStoryReader();
  const overlay=document.createElement('div');
  overlay.className='storyreader';overlay.setAttribute('role','dialog');
  overlay.setAttribute('aria-modal','true');overlay.setAttribute('aria-label','Story');
  overlay.innerHTML='<header class="storyreaderbar"><button type="button" class="storyreaderback" data-story-reader-back>&larr; Back to question</button>'
    +'<button type="button" class="storyreaderprev" data-story-reader-prev hidden>&larr; Previous story</button>'
    +'<code class="storyreaderpath"></code></header><div class="storyreaderlayout"><div class="storyreaderbody"></div>'
    +'<aside class="storycomments" aria-label="Your comments on this story"></aside></div>';
  document.body.appendChild(overlay);
  const state={overlay,opener,snapshot:scrollSnapshot(opener),trail:[],
    body:overlay.querySelector('.storyreaderbody'),side:overlay.querySelector('.storycomments'),
    questionId:opener?.closest?.('[data-question-id]')?.dataset.questionId||'',
    storyId:'',story:null,comments:[],csrf:'',path:overlay.querySelector('.storyreaderpath'),
    previous:overlay.querySelector('[data-story-reader-prev]')};
  state.onKey=event=>{if(event.key!=='Escape')return;event.preventDefault();
    if(state.compose)closeCommentCompose(state);else closeStoryReader();};
  document.addEventListener('keydown',state.onKey,true);
  storyReaderState=state;
  overlay.querySelector('[data-story-reader-back]').addEventListener('click',closeStoryReader);
  state.previous.addEventListener('click',()=>{
    const back=state.trail.pop();if(back)showStoryInReader(back);
    state.previous.hidden=!state.trail.length;
  });
  bindCommentSelection(state);
  overlay.querySelector('[data-story-reader-back]').focus({preventScroll:true});
  showStoryInReader(storyId);
}
// Delegated: question cards re-render freely without rebinding.
if(typeof document?.addEventListener==='function'){
  document.addEventListener('click',event=>{
    const button=event.target?.closest?.('[data-open-question-story]');
    if(button&&!button.disabled){event.preventDefault();openStoryReader(button.dataset.openQuestionStory,button);}
  });
}
// Resolve story rows as cards appear, whichever view rendered them.
if(typeof MutationObserver==='function'&&typeof document!=='undefined'&&document.body){
  const observer=new MutationObserver(()=>{
    document.querySelectorAll('[data-question-story-row]:not([data-story-checked])').forEach(row=>{
      row.dataset.storyChecked='1';hydrateQuestionStoryLinks(row.parentElement||row);
    });
  });
  observer.observe(document.body,{childList:true,subtree:true});
}
