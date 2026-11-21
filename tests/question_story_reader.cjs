// Runs the real markdown.js + story_reader.js against a stub DOM-free harness.
const fs=require('fs'),path=require('path'),vm=require('vm');
const dir=path.join(__dirname,'..','src','vizzer','render','constellation');
const read=n=>fs.readFileSync(path.join(dir,n),'utf8');
const sandbox={SERVED:true,console};
sandbox.window=sandbox;sandbox.document={};
vm.createContext(sandbox);
const stateJsEsc="const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));";
vm.runInContext(stateJsEsc+read('markdown.js')+read('story_reader.js')+
  ';this.api={storyReaderBodyMarkup,questionStoryLinkMarkup,splitStoryFrontMatter};',sandbox);
const {storyReaderBodyMarkup,questionStoryLinkMarkup}=sandbox.api;
const fail=m=>{console.error('FAIL '+m);process.exit(1);};
const md='---\nstatus: proposed\nsummary: Water moves.\n---\n# Live wet page\n\nSee [Goal](wet-media-gpu-goal.md) and [web](https://example.com).\n\n## Acceptance criteria\n- one\n- two\n';
const html=storyReaderBodyMarkup(md,'fallback');
if(!html.includes('Live wet page'))fail('title');
if(!html.includes('<dt>status</dt><dd>proposed</dd>'))fail('front matter');
if(!html.includes('Acceptance criteria')||!html.includes('<li>one</li>'))fail('headings/lists');
if(!html.includes('data-md-story="story:wet-media-gpu-goal"'))fail('relative story link');
if(!html.includes('href="https://example.com"'))fail('external link');
const link=questionStoryLinkMarkup({storyId:'story:live-wet-page-fluid-and-chemistry'});
if(!link.includes('data-open-question-story="story:live-wet-page-fluid-and-chemistry"'))fail('question link');
if(!questionStoryLinkMarkup({}).includes('names no story'))fail('missing story id stated');
console.log('reader ok');
