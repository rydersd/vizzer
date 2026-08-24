import {pathMidpoint} from './layout_contract.mjs';

function esc(value){
  return String(value??'')
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g,'�')
    .replace(/[&<>"']/g,character=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;',
  })[character]);
}
function number(value){return Number.isFinite(Number(value))?Number(value):0;}
function size(node,name,fallback){return number(node.style?.[name]??node[name]??fallback);}
function wrap(value,limit=38,lines=3){
  const words=String(value||'').split(/\s+/).filter(Boolean),result=[];
  let line='';
  for(const word of words){
    const next=line?`${line} ${word}`:word;
    if(next.length>limit&&line){result.push(line);line=word;}else line=next;
    if(result.length===lines)break;
  }
  if(result.length<lines&&line)result.push(line);
  return result.slice(0,lines);
}
function pointsPath(points){
  return points.length?`M ${points.map(point=>`${number(point.x)} ${number(point.y)}`).join(' L ')}`:'';
}

export function developerFlowSvg({title='Developer Flow',nodes=[],edges=[],lod='summary',exportedAt=''}){
  const byId=new Map(nodes.map(node=>[node.id,node])),positions=new Map();
  const absolute=node=>{
    if(positions.has(node.id))return positions.get(node.id);
    const own={x:number(node.position?.x),y:number(node.position?.y)};
    const parent=node.parentId&&byId.get(node.parentId);
    const value=parent?(()=>{const origin=absolute(parent);return{x:origin.x+own.x,y:origin.y+own.y};})():own;
    positions.set(node.id,value);return value;
  };
  const bounds=[];
  for(const node of nodes){
    const origin=absolute(node),width=size(node,'width',320),height=size(node,'height',140);
    bounds.push(origin.x,origin.y,origin.x+width,origin.y+height);
  }
  for(const edge of edges)for(const point of edge.data?.points||[])bounds.push(number(point.x),number(point.y));
  const xs=bounds.filter((_value,index)=>index%2===0),ys=bounds.filter((_value,index)=>index%2===1);
  const padding=48,minX=(xs.length?Math.min(...xs):0)-padding,minY=(ys.length?Math.min(...ys):0)-padding;
  const maxX=(xs.length?Math.max(...xs):800)+padding,maxY=(ys.length?Math.max(...ys):600)+padding;
  const width=Math.max(1,maxX-minX),height=Math.max(1,maxY-minY);
  const edgeMarkup=edges.map(edge=>{
    const points=edge.data?.points||[];
    const path=pointsPath(points);if(!path)return '';
    const middle=pathMidpoint(points);
    return `<g class="edge"><path d="${path}" marker-end="url(#arrow)"/><text x="${number(middle.x)}" y="${number(middle.y)-6}">${esc(edge.label||edge.data?.kind||'relation')}</text></g>`;
  }).join('');
  const ordered=[...nodes].sort((a,b)=>(a.type==='groupFrame'?0:1)-(b.type==='groupFrame'?0:1));
  const nodeMarkup=ordered.map(node=>{
    const origin=absolute(node),width=size(node,'width',320),height=size(node,'height',140),data=node.data||{};
    if(node.type==='groupFrame'){
      const status=Object.entries(data.statusCounts||{}).filter(([,count])=>count).map(([role,count])=>`${count} ${role}`).join(' · ');
      return `<g class="group"><rect x="${origin.x}" y="${origin.y}" width="${width}" height="${height}" rx="14"/><text class="group-title" x="${origin.x+16}" y="${origin.y+26}">${esc(data.title||node.id)}</text><text class="meta" x="${origin.x+16}" y="${origin.y+46}">${esc(status||`${data.count||0} objects`)}</text></g>`;
    }
    const lines=wrap(data.summary||'',46,2);
    return `<g class="object status-${esc(data.statusRole||'ready')}"><rect x="${origin.x}" y="${origin.y}" width="${width}" height="${height}" rx="10"/><text class="kind" x="${origin.x+16}" y="${origin.y+24}">${esc(data.kind||'object')} · ${esc(data.status||'unknown')}</text><text class="title" x="${origin.x+16}" y="${origin.y+48}">${esc(data.title||node.id)}</text>${lines.map((line,index)=>`<text class="summary" x="${origin.x+16}" y="${origin.y+72+index*18}">${esc(line)}</text>`).join('')}${data.failure?`<text class="failure" x="${origin.x+16}" y="${origin.y+height-16}">⚠ ${esc(data.failure.message)}</text>`:''}</g>`;
  }).join('');
  const metadata=esc(JSON.stringify({schema:'vizzer-developer-flow-svg/v1',lod,exportedAt}));
  return `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="${minX} ${minY} ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title><metadata>${metadata}</metadata><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="#64748b"/></marker><style>.edge path{fill:none;stroke:#64748b;stroke-width:2}.edge text,.meta,.kind,.summary{font:12px system-ui,sans-serif;fill:#64748b}.group rect{fill:#f8fafc;stroke:#94a3b8;stroke-width:2}.group-title,.title{font:700 15px system-ui,sans-serif;fill:#0f172a}.object rect{fill:#fff;stroke:#64748b;stroke-width:2}.status-blocked rect{stroke:#dc2626}.status-active rect{stroke:#2563eb}.status-shipped rect{stroke:#16a34a}.kind{font-size:11px;text-transform:uppercase}.failure{font:700 12px system-ui,sans-serif;fill:#dc2626}</style></defs>${edgeMarkup}${nodeMarkup}</svg>`;
}

export function svgFilename(title='developer-flow',scope='overview'){
  const slug=String(title).normalize('NFKD').replace(/[^a-zA-Z0-9]+/g,'-')
    .replace(/^-|-$/g,'').toLowerCase().slice(0,80)||'developer-flow';
  const suffix=String(scope).replace(/[^a-zA-Z0-9-]+/g,'-').slice(0,40)||'overview';
  return `${slug}-${suffix}.svg`;
}

export function triggerSvgDownload(svg,filename,environment={}){
  const documentRef=environment.document||globalThis.document;
  const urlApi=environment.URL||globalThis.URL;
  const BlobRef=environment.Blob||globalThis.Blob;
  const defer=environment.setTimeout||globalThis.setTimeout;
  if(!documentRef?.body||!urlApi?.createObjectURL||!BlobRef)
    throw new Error('SVG download is unavailable in this browser');
  const blob=new BlobRef([svg],{type:'image/svg+xml;charset=utf-8'});
  const url=urlApi.createObjectURL(blob),anchor=documentRef.createElement('a');
  anchor.href=url;anchor.download=filename;anchor.hidden=true;
  documentRef.body.appendChild(anchor);
  try{anchor.click();}finally{
    anchor.remove();
    defer(()=>urlApi.revokeObjectURL(url),1000);
  }
  return {filename,bytes:new TextEncoder().encode(svg).length};
}
