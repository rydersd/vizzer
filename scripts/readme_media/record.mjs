// Drive the served demo project through each README scene and save numbered
// PNG frames per scene. A visible pointer glides to every control before it is
// clicked so the GIFs read as a person using the tool, not a page flipping.
//
// usage: node record.mjs <base-url> <frames-dir> <scene>... | evidence <png>
import fs from 'node:fs';
import path from 'node:path';
import {launch, sleep} from './cdp.mjs';

const WIDTH = 1280, HEIGHT = 760, FPS = 12;

const POINTER = `(()=>{if(document.getElementById('readme-pointer'))return;
  const p=document.createElement('div');p.id='readme-pointer';
  p.style.cssText='position:fixed;left:640px;top:420px;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;'+
    'background:rgba(255,255,255,.92);box-shadow:0 0 0 3px rgba(120,160,255,.55),0 2px 8px rgba(0,0,0,.5);'+
    'z-index:2147483647;pointer-events:none;transition:left .7s cubic-bezier(.4,0,.2,1),top .7s cubic-bezier(.4,0,.2,1),transform .15s';
  document.documentElement.appendChild(p);})()`;

// Screenshots of a busy canvas take longer than 1/FPS, so each frame records
// how long it was on screen and frames.ffconcat replays them in real time.
function recorder(page, dir) {
  fs.mkdirSync(dir, {recursive: true});
  const frames = [];
  let running = true;
  const loop = (async () => {
    while (running) {
      const started = Date.now();
      const shot = await page.send('Page.captureScreenshot', {format: 'jpeg', quality: 92});
      const name = `f-${String(frames.length).padStart(4, '0')}.jpg`;
      fs.writeFileSync(path.join(dir, name), Buffer.from(shot.data, 'base64'));
      frames.push({name, at: started});
      await sleep(Math.max(0, 1000 / FPS - (Date.now() - started)));
    }
  })();
  return async () => {
    running = false;
    await loop;
    const end = Date.now();
    const lines = ['ffconcat version 1.0'];
    frames.forEach((frame, i) => lines.push(`file '${frame.name}'`,
      `duration ${(((frames[i + 1]?.at ?? end) - frame.at) / 1000).toFixed(3)}`));
    // The concat demuxer ignores the last duration unless the file repeats.
    if (frames.length) lines.push(`file '${frames.at(-1).name}'`);
    fs.writeFileSync(path.join(dir, 'frames.ffconcat'), lines.join('\n') + '\n');
    return frames.length;
  };
}

// Find a rendered element by CSS selector, optionally narrowed by its text.
// checkVisibility rejects content inside a closed <details>, which still has
// client rects but cannot be clicked.
const find = (selector, text) => `[...document.querySelectorAll(${JSON.stringify(selector)})]
  .find(e=>e.checkVisibility()&&${text ? `((e.getAttribute('aria-label')||'')+' '+e.textContent).includes(${JSON.stringify(text)})` : 'true'})`;

async function point(page, selector, text) {
  const box = await page.evaluate(`(()=>{const e=${find(selector, text)};if(!e)return null;
    e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();
    const p=document.getElementById('readme-pointer');p.style.left=(r.left+Math.min(r.width/2,60))+'px';p.style.top=(r.top+r.height/2)+'px';
    return {x:r.left+Math.min(r.width/2,60),y:r.top+r.height/2}})()`);
  if (!box) throw new Error(`no visible ${selector}${text ? ` containing "${text}"` : ''}`);
  await sleep(850);
  return box;
}

async function click(page, selector, text, pause = 1200) {
  const {x, y} = await point(page, selector, text);
  await page.evaluate(`document.getElementById('readme-pointer').style.transform='scale(.7)'`);
  for (const type of ['mousePressed', 'mouseReleased'])
    await page.send('Input.dispatchMouseEvent', {type, x, y, button: 'left', clickCount: 1});
  await sleep(150);
  await page.evaluate(`document.getElementById('readme-pointer').style.transform=''`);
  await sleep(pause);
}

// Orbit the 3D canvas with a real drag so the camera motion is the app's own.
async function orbit(page, dx, steps = 40) {
  const x0 = 700, y = 430;
  await page.evaluate(`(()=>{const p=document.getElementById('readme-pointer');p.style.transition='none';p.style.left='${x0}px';p.style.top='${y}px'})()`);
  await page.send('Input.dispatchMouseEvent', {type: 'mousePressed', x: x0, y, button: 'left', clickCount: 1});
  for (let i = 1; i <= steps; i++) {
    const x = x0 + dx * i / steps;
    await page.send('Input.dispatchMouseEvent', {type: 'mouseMoved', x, y, button: 'left', buttons: 1});
    await page.evaluate(`document.getElementById('readme-pointer').style.left='${x}px'`);
    await sleep(40);
  }
  await page.send('Input.dispatchMouseEvent', {type: 'mouseReleased', x: x0 + dx, y, button: 'left', clickCount: 1});
  await page.evaluate(`document.getElementById('readme-pointer').style.transition=''`);
}

// Error capture is registered before navigation so startup exceptions count.
const ERROR_CAPTURE = `window.__readmeErrors=[];addEventListener('error',e=>__readmeErrors.push(e.error&&e.error.stack||e.message))`;
let errorCaptureInstalled = false;

async function open(page, url, settle = 3500) {
  if (!errorCaptureInstalled) {
    await page.send('Page.addScriptToEvaluateOnNewDocument', {source: ERROR_CAPTURE});
    errorCaptureInstalled = true;
  }
  await page.send('Page.navigate', {url});
  await sleep(settle);
  await page.evaluate(POINTER);
}

// Switch route through the header's Views menu, never a same-named rail item.
async function view(page, name, pause) {
  await click(page, '#viewmenu summary', '', 700);
  await click(page, '#viewmenu a', name, pause);
}

// Developer Flow frame buttons are unlabeled; the frame's header names them.
async function expandFrame(page, title, pause) {
  const tagged = await page.evaluate(`(()=>{const b=[...document.querySelectorAll('header button')]
    .find(e=>e.textContent.trim()==='Expand'&&e.parentElement.textContent.startsWith(${JSON.stringify(title)}));
    if(b)b.dataset.readmeTarget='';return Boolean(b)})()`);
  if (!tagged) throw new Error(`no Expand button on the ${title} frame`);
  await click(page, '[data-readme-target]', '', pause);
}

// A GIF of the app failing is worse than no GIF: any page error fails the scene.
async function assertNoPageErrors(page, name) {
  const errors = await page.evaluate('window.__readmeErrors||[]');
  if (errors.length) throw new Error(`${name} raised page errors:\n${errors.join('\n')}`);
}

const SCENES = {
  // Capability clusters: orbit, focus one capability so its stories spread
  // apart, then open a story to see its dossier and dependency edges.
  constellation: {url: '/constellation.html#constellation', async run(page) {
    await sleep(600);
    await orbit(page, 260);
    await sleep(900);
    await click(page, '.railgroup summary, [data-rail-id], button', 'Sync', 2600);
    await click(page, '.railgroup summary', 'Devices', 900);
    await click(page, 'button', 'Open story: Offline queue', 2600);
    await click(page, 'button', 'Open story: Conflict merge', 2400);
  }},
  // Owner questions: a blocked story's decision card, stepping through the
  // queue, choosing the recommended option, and recording the answer.
  questions: {url: '/constellation.html#dashboard', async run(page) {
    await sleep(500);
    await click(page, 'button, a, [role=button], .card, article', 'Conflict merge', 2200);
    await click(page, '[data-question-nav-next]', '', 1600);
    await click(page, '[data-question-nav-next]', '', 1600);
    await click(page, '[data-question-nav-previous]', '', 1400);
    await click(page, '[data-question-nav-previous]', '', 1400);
    await click(page, 'label', 'Keep both versions inline', 1000);
    await click(page, '[data-question-submit]', '', 2600);
  }},
  // One graph, many routes: the Views menu walks the same graph as a
  // dashboard, roadmap, hierarchy, feature index, and completion sheet.
  views: {url: '/constellation.html#dashboard', async run(page) {
    await sleep(900);
    for (const name of ['Roadmap', 'Hierarchy', 'Features', 'Completion']) await view(page, name, 2000);
  }},
  // Concurrent agents: workstreams split by lane, coordination warnings on
  // shared paths, and the leased Claude and Codex sessions in each lane.
  workstreams: {url: '/constellation.html#workstreams', async run(page) {
    await sleep(1800);
    await page.evaluate(`viewpanel.scrollBy({top:300,behavior:'smooth'})`);
    await sleep(1500);
    await click(page, 'summary', 'Sessions', 2200);
    await page.evaluate(`viewpanel.scrollBy({top:200,behavior:'smooth'})`);
    await sleep(2400);
  }},
  // Reviews: the agent's recorded run and evidence beside a separate owner
  // verdict. The row opens expanded; scrolling reveals the run and evidence.
  reviews: {url: '/constellation.html#reviews', async run(page) {
    await sleep(1800);
    await page.evaluate(`viewpanel.scrollBy({top:340,behavior:'smooth'})`);
    await sleep(2600);
    await page.evaluate(`viewpanel.scrollBy({top:340,behavior:'smooth'})`);
    await sleep(2600);
  }},
  // Developer Flow: the 2D object graph, expanding one capability frame to
  // its epics and stories, then back to the overview.
  developer_flow: {url: '/developer-flow.html', settle: 5000, async run(page) {
    await sleep(900);
    await expandFrame(page, 'Sync', 3000);
    await click(page, 'button', 'Overview', 2200);
  }},
};

// Review evidence: a plain mock of the fictional app's filtered search, so the
// recorded agent run carries a real screenshot.
const EVIDENCE = `<!doctype html><body style="margin:0;font:15px system-ui;background:#f6f7fb;color:#1d2433">
<div style="padding:18px 22px;background:#fff;border-bottom:1px solid #e3e6ef;font-weight:600">Sample Notes</div>
<div style="padding:22px"><div style="padding:10px 14px;border:1px solid #cfd5e4;border-radius:8px;background:#fff">roadmap</div>
<div style="margin:12px 0"><span style="padding:4px 10px;border-radius:12px;background:#3b5bdb;color:#fff">#planning &times;</span></div>
${['Q3 roadmap draft', 'Planning offsite notes', 'Roadmap review checklist'].map(t => `<div style="padding:12px 14px;margin:8px 0;background:#fff;border-radius:8px;border:1px solid #e3e6ef">${t}<div style="color:#6b7488;font-size:13px">#planning</div></div>`).join('')}
</div></body>`;

const [base, out, ...scenes] = process.argv.slice(2);
const page = await launch({width: WIDTH, height: HEIGHT});
try {
  if (base === 'evidence') {
    await page.send('Page.navigate', {url: 'data:text/html,' + encodeURIComponent(EVIDENCE)});
    await sleep(800);
    const shot = await page.send('Page.captureScreenshot', {format: 'png', clip: {x: 0, y: 0, width: 640, height: 400, scale: 1}});
    fs.writeFileSync(out, Buffer.from(shot.data, 'base64'));
  } else {
    for (const name of scenes) {
      if (!SCENES[name]) throw new Error(`unknown scene ${name}`);
      const scene = SCENES[name];
      await open(page, base + scene.url, scene.settle);
      const stop = recorder(page, path.join(out, name));
      try { await scene.run(page); } finally { console.log(`${name}: ${await stop()} frames`); }
      await assertNoPageErrors(page, name);
    }
  }
} finally {
  await page.close();
}
