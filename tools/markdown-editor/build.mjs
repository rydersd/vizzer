import {build} from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
const output=path.resolve(process.argv[2]||'../../src/vizzer/render/constellation/third-party');
fs.mkdirSync(output,{recursive:true});
const result=await build({entryPoints:['index.js'],bundle:true,minify:true,format:'iife',globalName:'VizzerMarkdownEditor',outfile:path.join(output,'milkdown.js'),metafile:true,legalComments:'eof',target:['es2022']});
fs.writeFileSync('bundle-inputs.json',JSON.stringify({milkdown:'7.22.1',inputs:Object.keys(result.metafile.inputs)},null,2)+'\n');
const packages=new Set();
for(const input of Object.keys(result.metafile.inputs)){
 let folder=path.dirname(path.resolve(input));
 while(folder!==path.dirname(folder)){
  if(fs.existsSync(path.join(folder,'package.json'))){packages.add(folder);break;}
  folder=path.dirname(folder);
 }
}
let notices='Vizzer Markdown editor third-party notices\n\nMilkdown / Crepe 7.22.1 — MIT\nhttps://github.com/Milkdown/milkdown\n\n';
for(const folder of [...packages].sort()){
 const pkg=JSON.parse(fs.readFileSync(path.join(folder,'package.json'),'utf8'));
 if(!pkg.name||pkg.private)continue;
 notices+=`\n===== ${pkg.name} ${pkg.version} (${pkg.license||'see license'}) =====\n`;
 const licenses=fs.readdirSync(folder).filter(name=>/^(license|licence|copying)(\.|$)/i.test(name));
 for(const name of licenses)if(fs.statSync(path.join(folder,name)).isFile())notices+=fs.readFileSync(path.join(folder,name),'utf8')+'\n';
 if(!licenses.length)notices+='License identifier: '+(pkg.license||'See package repository')+'\n';
}
fs.writeFileSync(path.join(output,'THIRD-PARTY-NOTICES.txt'),notices.trimEnd()+'\n');
