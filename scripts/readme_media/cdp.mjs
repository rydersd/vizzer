// Minimal Chrome DevTools Protocol client for recording the README GIFs.
// Node's built-in WebSocket and fetch are enough, so recording adds no npm
// dependency. Chrome is launched with a private profile and closed by the
// exact PID this module spawned.
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const CHROME_CANDIDATES = [
  process.env.CHROME,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
].filter(Boolean);

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function launch({width, height}) {
  const chrome = CHROME_CANDIDATES.find(candidate => fs.existsSync(candidate));
  if (!chrome) throw new Error('Chrome not found; set CHROME=/path/to/chrome');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'vizzer-readme-chrome-'));
  const port = 9300 + Math.floor(Math.random() * 500);
  const proc = spawn(chrome, [
    '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
    `--window-size=${width},${height}`, '--hide-scrollbars', '--force-device-scale-factor=1',
    '--no-first-run', '--no-default-browser-check', '--use-angle=swiftshader', 'about:blank',
  ], {stdio: 'ignore'});
  let target;
  for (let attempt = 0; attempt < 100 && !target; attempt++) {
    await sleep(100);
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      target = list.find(entry => entry.type === 'page');
    } catch { /* Chrome is still starting. */ }
  }
  if (!target) { proc.kill('SIGKILL'); throw new Error('Chrome did not expose a page target'); }
  const page = await connect(target.webSocketDebuggerUrl);
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  await page.send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: false});
  page.close = async () => {
    page.socket.close();
    proc.kill('SIGTERM');
    await new Promise(resolve => proc.exitCode !== null ? resolve() : proc.once('exit', resolve));
    fs.rmSync(profile, {recursive: true, force: true});
  };
  return page;
}

async function connect(url) {
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let nextId = 1;
  const pending = new Map();
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const {resolve, reject} = pending.get(message.id);
      pending.delete(message.id);
      message.error ? reject(new Error(message.error.message)) : resolve(message.result);
    }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || expression);
    return result.result.value;
  };
  return {socket, send, evaluate};
}

export {sleep};
