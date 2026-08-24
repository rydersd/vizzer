import { build } from 'esbuild';
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here=dirname(fileURLToPath(import.meta.url));
const output=resolve(here,'../../src/vizzer/render/developer_flow_assets');
await mkdir(resolve(output,'third-party'),{recursive:true});
await build({
  entryPoints:[resolve(here,'src/main.jsx')],
  outfile:resolve(output,'app.js'),
  bundle:true,
  minify:true,
  sourcemap:false,
  format:'iife',
  target:['safari16','chrome110','firefox115'],
  legalComments:'none',
  jsx:'automatic',
});
const reactFlowCss=await readFile(resolve(here,'node_modules/@xyflow/react/dist/style.css'),'utf8');
const appCss=await readFile(resolve(here,'src/app.css'),'utf8');
await writeFile(resolve(output,'app.css'),`${reactFlowCss}\n${appCss}`,'utf8');

const packages={
  react:JSON.parse(await readFile(resolve(here,'node_modules/react/package.json'),'utf8')),
  reactDom:JSON.parse(await readFile(resolve(here,'node_modules/react-dom/package.json'),'utf8')),
  reactFlow:JSON.parse(await readFile(resolve(here,'node_modules/@xyflow/react/package.json'),'utf8')),
  elk:JSON.parse(await readFile(resolve(here,'node_modules/elkjs/package.json'),'utf8')),
};
const notice=`# Vizzer Developer Flow third-party notices\n\n`
  +`- React ${packages.react.version} — MIT — Facebook, Inc. and contributors\n`
  +`- React DOM ${packages.reactDom.version} — MIT — Facebook, Inc. and contributors\n`
  +`- React Flow ${packages.reactFlow.version} — MIT — webkid GmbH and contributors\n`
  +`- elkjs ${packages.elk.version} — Eclipse Public License 2.0 — Kiel University and contributors\n\n`
  +`The bundled page retains React Flow's visible attribution. Exact license texts accompany this notice.\n`;
await writeFile(resolve(output,'THIRD_PARTY_NOTICES.md'),notice,'utf8');
await copyFile(resolve(here,'node_modules/@xyflow/react/LICENSE'),resolve(output,'third-party/REACT_FLOW_LICENSE.txt'));
await copyFile(resolve(here,'node_modules/react/LICENSE'),resolve(output,'third-party/REACT_LICENSE.txt'));
await copyFile(resolve(here,'node_modules/react-dom/LICENSE'),resolve(output,'third-party/REACT_DOM_LICENSE.txt'));
await copyFile(resolve(here,'node_modules/elkjs/LICENSE.md'),resolve(output,'third-party/ELKJS_LICENSE.md'));
