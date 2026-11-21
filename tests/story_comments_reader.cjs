// Pure comment logic from story_reader.js: quote anchoring, payload shape, safe list markup.
const fs=require('fs'),path=require('path'),vm=require('vm');
const dir=path.join(__dirname,'..','src','vizzer','render','constellation');
const read=n=>fs.readFileSync(path.join(dir,n),'utf8');
const sandbox={SERVED:true,console};sandbox.window=sandbox;sandbox.document={};
vm.createContext(sandbox);
const esc="const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));";
vm.runInContext(esc+read('markdown.js')+read('story_reader.js')+
  ';this.api={findQuoteSegments,storyCommentPayload,storyCommentsListMarkup};',sandbox);
const {findQuoteSegments,storyCommentPayload,storyCommentsListMarkup}=sandbox.api;
const fail=m=>{console.error('FAIL '+m);process.exit(1);};
const eq=(a,b,m)=>{if(JSON.stringify(a)!==JSON.stringify(b))fail(m+' '+JSON.stringify(a));};
// anchoring inside one text node
eq(findQuoteSegments(['Water moves on the page.'],'moves on'),[{node:0,start:6,end:14}],'single node');
// across inline elements, no separator
eq(findQuoteSegments(['Water ','moves',' on'],'Water moves on'),[{node:0,start:0,end:6},{node:1,start:0,end:5},{node:2,start:0,end:3}],'across nodes');
// across blocks: selection text has a newline where the DOM has none
eq(findQuoteSegments(['First para','Second para'],'First para\nSecond para').length,2,'across blocks');
// whitespace differences are tolerated; absence is null
eq(findQuoteSegments(['a   b\n c'],'a b c'),[{node:0,start:0,end:8}],'whitespace');
eq(findQuoteSegments(['nothing here'],'missing passage'),null,'unanchored');
eq(findQuoteSegments(['abc'],'  '),null,'blank quote');
// payload
const p=storyCommentPayload({storyId:'story:a',path:'p.md',questionId:'question:q',quote:'q'.repeat(2500),heading:'H',comment:'  hi  '});
eq([p.storyId,p.path,p.questionId,p.heading,p.comment],['story:a','p.md','question:q','H','hi'],'payload fields');
if(p.quote.length!==2000)fail('quote capped at 2000');
if(!/^\d{4}-\d\d-\d\dT/.test(p.clientTime))fail('client time ISO');
if('questionId' in storyCommentPayload({storyId:'s',path:'p',quote:'q',heading:'',comment:'c'}))fail('no question id omitted');
// list markup: text only, status shown, unanchored named, delete only for open
const html=storyCommentsListMarkup([
  {id:'1',status:'open',quote:'<img src=x onerror=alert(1)>',heading:'<b>H</b>',comment:'</aside><script>x</script>'},
  {id:'2',status:'resolved',quote:'gone',heading:'',comment:'old'}],new Set(['1']));
if(/<img|<script|<b>/.test(html))fail('markup injected: '+html);
if(!html.includes('&lt;img'))fail('escaped quote');
if(!html.includes('data-delete-story-comment="1"'))fail('delete for open');
if(html.includes('data-delete-story-comment="2"'))fail('no delete for resolved');
if(!html.includes('unanchored'))fail('unanchored label');
if(!html.includes('resolved')||!html.includes('open'))fail('status text');
console.log('comments ok');
