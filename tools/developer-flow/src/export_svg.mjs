import {
  groupFrameMetrics,groupFramePresentation,objectCardMetrics,objectCardPresentation,
  pathMidpoint,roundedOrthogonalPath,wrapTextLines,
} from './layout_contract.mjs';
import {sfSymbolPresentation} from './vizzer_sf_symbols.mjs';

function esc(value){
  return String(value??'')
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g,'�')
    .replace(/[&<>"']/g,character=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;',
  })[character]);
}
function number(value){return Number.isFinite(Number(value))?Number(value):0;}
function size(node,name,fallback){return number(node.style?.[name]??node[name]??fallback);}
function token(value){return String(value||'').toLowerCase().replace(/[^a-z0-9_-]+/g,'-')||'unknown';}
function textLines(lines,className,x,y,lineHeight=18,anchor='start'){
  return lines.map((line,index)=>`<text class="${className}" x="${x}" y="${y+index*lineHeight}" text-anchor="${anchor}">${esc(line)}</text>`).join('');
}
function symbolMarkup(name,className,x,y,width,height){
  const symbol=sfSymbolPresentation(name);
  if(!symbol)return `<circle class="${className} symbol-dot" cx="${x+width/2}" cy="${y+height/2}" r="${Math.min(width,height)*.24}"/>`;
  return `<svg class="${className}" x="${x}" y="${y}" width="${width}" height="${height}" viewBox="${symbol.viewBox}" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><path d="${symbol.d}" fill-rule="${symbol.fillRule}"/></svg>`;
}
function pointsPath(points){
  return roundedOrthogonalPath(points.map(point=>({x:number(point.x),y:number(point.y)})),10);
}
function edgeLabelLayout(edge,points){
  const middle=pathMidpoint(points),label=String(edge.label||edge.data?.kind||'relation');
  const width=Math.max(36,label.length*7+14);
  return {middle,label,width,x:number(middle.x)-width/2,y:number(middle.y)-17};
}
function noteLayout(note){
  const lines=wrapTextLines(note.text,30),width=240;
  const height=28+Math.max(1,lines.length)*17+(note.objectId?18:0);
  return {x:number(note.x),y:number(note.y),width,height,lines};
}
function sketchPath(points){
  return points.map((point,index)=>`${index?'L':'M'} ${number(point[0])} ${number(point[1])}`).join(' ');
}

function statusBadge(label,role,x,y){
  const width=Math.max(46,label.length*6+16);
  return {width,markup:`<g class="status-badge role-${token(role)}"><rect x="${x}" y="${y}" width="${width}" height="18" rx="9"/><text x="${x+width/2}" y="${y+12}" text-anchor="middle">${esc(label)}</text></g>`};
}

function groupMarkup(node,origin,width,height){
  const data=node.data||{},collapsed=Boolean(data.collapsed);
  const metrics=groupFrameMetrics(data.title||node.id,data.statusCounts||{},collapsed);
  const headerHeight=number(data.headerHeight)||metrics.headerHeight;
  const presentation=groupFramePresentation(
    data.title||node.id,data.statusCounts||{},collapsed,
  );
  const title=textLines(presentation.titleLines,'group-title',origin.x+16,origin.y+25,17);
  const count=`<text class="meta group-count" x="${origin.x+width-16}" y="${origin.y+25}" text-anchor="end">${number(data.count)} objects</text>`;
  let aggregate='';
  if(collapsed){
    const iconY=origin.y+headerHeight+34;
    aggregate=`${symbolMarkup(presentation.symbol,'group-symbol',origin.x+18,iconY-22,24,24)}<text class="group-total" x="${origin.x+49}" y="${iconY}">${number(data.count)}</text>`;
    let badgeX=origin.x+18,badgeY=iconY+17;
    for(const entry of presentation.statusEntries){
      const widthNeeded=Math.max(46,entry.label.length*6+16);
      if(badgeX>origin.x+18&&badgeX+widthNeeded>origin.x+width-18){badgeX=origin.x+18;badgeY+=22;}
      const badge=statusBadge(entry.label,entry.role,badgeX,badgeY);
      aggregate+=badge.markup;badgeX+=badge.width+5;
    }
  }
  return `<g class="group${collapsed?' collapsed':''}"><rect class="group-body" x="${origin.x}" y="${origin.y}" width="${width}" height="${height}" rx="14"/><rect class="group-header" x="${origin.x+1}" y="${origin.y+1}" width="${Math.max(0,width-2)}" height="${Math.max(0,headerHeight-1)}" rx="13"/><line class="group-divider" x1="${origin.x}" x2="${origin.x+width}" y1="${origin.y+headerHeight}" y2="${origin.y+headerHeight}"/>${title}${count}${aggregate}</g>`;
}

function objectMarkup(node,origin,width,height,lod){
  const data=node.data||{},expanded=Boolean(data.expanded);
  const metrics=objectCardMetrics(data,expanded);
  const presentation=objectCardPresentation(data,expanded);
  const headerHeight=number(data.headerHeight)||metrics.headerHeight;
  const role=token(data.statusRole||'ready'),status=String(data.status||'unknown');
  const base=`<rect class="object-body" x="${origin.x}" y="${origin.y}" width="${width}" height="${height}" rx="10"/><line class="status-rule" x1="${origin.x+8}" x2="${origin.x+width-8}" y1="${origin.y+2}" y2="${origin.y+2}"/>`;
  if(lod==='overview')return `<g class="object status-${role} lod-overview"><circle class="object-dot" cx="${origin.x+width/2}" cy="${origin.y+height/2}" r="6"/></g>`;
  if(lod==='glyph')return `<g class="object status-${role} lod-glyph"><circle class="object-dot" cx="${origin.x+width/2}" cy="${origin.y+height/2}" r="12"/>${symbolMarkup(presentation.symbol,'sf-symbol',origin.x+width/2-7,origin.y+height/2-7,14,14)}</g>`;

  const iconX=origin.x+13,iconY=origin.y+15,textX=origin.x+57;
  const pillWidth=Math.min(Math.max(46,status.length*6+18),Math.max(46,width-86));
  const pillX=origin.x+width-pillWidth-12;
  const header=`<rect class="object-header" x="${origin.x+1}" y="${origin.y+3}" width="${Math.max(0,width-2)}" height="${Math.max(0,headerHeight-3)}" rx="9"/><line class="object-divider" x1="${origin.x}" x2="${origin.x+width}" y1="${origin.y+headerHeight}" y2="${origin.y+headerHeight}"/><rect class="kind-icon" x="${iconX}" y="${iconY}" width="32" height="32" rx="8"/>${symbolMarkup(presentation.symbol,'sf-symbol',iconX+7,iconY+7,18,18)}<text class="kind" x="${textX}" y="${origin.y+24}">${esc(data.kind||'object')}</text>${textLines(presentation.titleLines,'title',textX,origin.y+46,18)}<g class="status-pill"><rect x="${pillX}" y="${origin.y+12}" width="${pillWidth}" height="18" rx="9"/><text x="${pillX+pillWidth/2}" y="${origin.y+24}" text-anchor="middle">${esc(status)}</text></g>`;
  if(lod==='compact')return `<g class="object status-${role} lod-compact">${base}${header}</g>`;

  const summaryY=origin.y+headerHeight+22;
  const summary=textLines(presentation.summaryLines,'summary',origin.x+14,summaryY,19);
  let details='';
  if(expanded){
    let detailY=summaryY+presentation.summaryLines.length*19+12;
    for(const entry of presentation.detailEntries){
      details+=`${textLines(entry.keyLines,'detail-key',origin.x+14,detailY,16)}${textLines(entry.valueLines,'detail-value',origin.x+112,detailY,16)}`;
      detailY+=Math.max(entry.keyLines.length,entry.valueLines.length,1)*16+7;
    }
  }
  let failure='';
  if(presentation.failureLines.length){
    const stripHeight=metrics.failureHeight,stripY=origin.y+height-stripHeight;
    failure=`<g class="failure-strip"><rect x="${origin.x+1}" y="${stripY}" width="${Math.max(0,width-2)}" height="${Math.max(0,stripHeight-1)}" rx="8"/>${symbolMarkup('exclamationmark.triangle','sf-symbol',origin.x+14,stripY+14,15,15)}${textLines(presentation.failureLines,'failure',origin.x+33,stripY+23,18)}</g>`;
  }
  return `<g class="object status-${role} lod-summary">${base}${header}${summary}${details}${failure}</g>`;
}

export function developerFlowSvg({title='Developer Flow',nodes=[],edges=[],annotations=[],includeAnnotations=true,lod='summary',exportedAt=''}){
  const exportedAnnotations=includeAnnotations?annotations:[];
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
  for(const edge of edges){
    const points=edge.data?.points||[];
    for(const point of points)bounds.push(number(point.x),number(point.y));
    if(points.length){
      const label=edgeLabelLayout(edge,points);
      bounds.push(label.x,label.y,label.x+label.width,label.y+18);
    }
  }
  for(const annotation of exportedAnnotations){
    if(annotation.kind==='stroke')for(const point of annotation.points||[])bounds.push(number(point[0]),number(point[1]));
    if(annotation.kind==='note'){
      const note=noteLayout(annotation);bounds.push(note.x,note.y,note.x+note.width,note.y+note.height);
    }
  }
  const xs=bounds.filter((_value,index)=>index%2===0),ys=bounds.filter((_value,index)=>index%2===1);
  const padding=48,minX=(xs.length?Math.min(...xs):0)-padding,minY=(ys.length?Math.min(...ys):0)-padding;
  const maxX=(xs.length?Math.max(...xs):800)+padding,maxY=(ys.length?Math.max(...ys):600)+padding;
  const width=Math.max(1,maxX-minX),height=Math.max(1,maxY-minY);
  const edgeMarkup=edges.map(edge=>{
    const points=edge.data?.points||[];
    const path=pointsPath(points);if(!path)return '';
    const label=edgeLabelLayout(edge,points);
    return `<g class="edge"><path d="${path}" marker-end="url(#arrow)"/><rect class="edge-label-bg" x="${label.x}" y="${label.y}" width="${label.width}" height="18" rx="9"/><text x="${number(label.middle.x)}" y="${number(label.middle.y)-6}">${esc(label.label)}</text></g>`;
  }).join('');
  const ordered=[...nodes].sort((a,b)=>(a.type==='groupFrame'?0:1)-(b.type==='groupFrame'?0:1));
  const nodeMarkup=ordered.map(node=>{
    const origin=absolute(node),width=size(node,'width',320),height=size(node,'height',140);
    return node.type==='groupFrame'
      ?groupMarkup(node,origin,width,height)
      :objectMarkup(node,origin,width,height,lod);
  }).join('');
  const annotationMarkup=exportedAnnotations.map(annotation=>{
    const color=esc(annotation.color||'yellow');
    if(annotation.kind==='stroke')return `<path class="annotation-stroke annotation-${color}" d="${sketchPath(annotation.points||[])}" style="stroke-width:${Math.max(1,Math.min(16,number(annotation.width)||4))}"/>`;
    if(annotation.kind!=='note')return '';
    const note=noteLayout(annotation);
    return `<g class="annotation-note annotation-${color}"><rect x="${note.x}" y="${note.y}" width="${note.width}" height="${note.height}" rx="8"/>${note.lines.map((line,index)=>`<text x="${note.x+12}" y="${note.y+22+index*17}">${esc(line)}</text>`).join('')}${annotation.objectId?`<text class="annotation-object" x="${note.x+12}" y="${note.y+note.height-9}">${esc(annotation.objectId)}</text>`:''}</g>`;
  }).join('');
  const metadata=esc(JSON.stringify({schema:'vizzer-developer-flow-svg/v1',lod,exportedAt,
    annotationCount:exportedAnnotations.length,annotationsIncluded:Boolean(includeAnnotations)}));
  const styles=`svg{background:#fff}.edge path{fill:none;stroke:#64748b;stroke-width:2}.edge-label-bg{fill:#fff;stroke:#cbd5e1;stroke-width:1}.edge text{font:700 11px ui-monospace,monospace;fill:#64748b}.group-body{fill:#f8fafc;stroke:#94a3b8;stroke-width:2}.group-header{fill:#f1f5f9;stroke:none}.group-divider,.object-divider{stroke:#cbd5e1;stroke-width:1}.group-title,.title{font:700 15px system-ui,sans-serif;fill:#0f172a}.meta{font:11px system-ui,sans-serif;fill:#64748b}.group-symbol,.sf-symbol{fill:#2563eb}.group-total{font:700 23px system-ui,sans-serif;fill:#2563eb}.status-badge rect{fill:#fff;stroke:#94a3b8}.status-badge text{font:700 9px ui-monospace,monospace;fill:#64748b}.status-badge.role-blocked rect{stroke:#dc2626}.status-badge.role-blocked text{fill:#dc2626}.status-badge.role-active rect{stroke:#2563eb}.status-badge.role-active text{fill:#2563eb}.object-body{fill:#fff;stroke:#64748b;stroke-width:1.5}.object-header{fill:#f8fafc;stroke:none}.status-rule{stroke:#64748b;stroke-width:4;stroke-linecap:round}.object-dot{fill:#fff;stroke:#64748b;stroke-width:3}.status-blocked .status-rule,.status-blocked .object-dot{stroke:#dc2626}.status-active .status-rule,.status-active .object-dot{stroke:#2563eb}.status-shipped .status-rule,.status-shipped .object-dot{stroke:#16a34a}.kind-icon{fill:#fff;stroke:#94a3b8;stroke-width:1}.symbol-dot{fill:#2563eb}.kind{font:11px ui-monospace,monospace;fill:#64748b;text-transform:uppercase}.status-pill rect{fill:#fff;stroke:#94a3b8}.status-pill text{font:700 9px ui-monospace,monospace;fill:#64748b;text-transform:uppercase}.summary{font:12px system-ui,sans-serif;fill:#64748b}.detail-key{font:700 9px ui-monospace,monospace;fill:#64748b;text-transform:uppercase}.detail-value{font:11px system-ui,sans-serif;fill:#334155}.failure-strip rect{fill:#fff1f2;stroke:#fda4af}.failure{font:700 12px system-ui,sans-serif;fill:#dc2626}.failure-strip .sf-symbol{fill:#dc2626}.lod-overview{opacity:.75}.annotation-stroke{fill:none;stroke:#f59e0b;stroke-linecap:round;stroke-linejoin:round}.annotation-note rect{fill:#fff7cc;stroke:#f59e0b;stroke-width:2}.annotation-note text{font:12px system-ui,sans-serif;fill:#0f172a}.annotation-note .annotation-object{font:10px ui-monospace,monospace;fill:#64748b}.annotation-blue{stroke:#2563eb}.annotation-pink{stroke:#db2777}.annotation-green{stroke:#16a34a}.annotation-white{stroke:#e2e8f0}.annotation-note.annotation-blue rect{fill:#eff6ff;stroke:#2563eb}.annotation-note.annotation-pink rect{fill:#fdf2f8;stroke:#db2777}.annotation-note.annotation-green rect{fill:#ecfdf5;stroke:#16a34a}.annotation-note.annotation-white rect{fill:#fff;stroke:#94a3b8}`;
  return `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="${minX} ${minY} ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title><metadata>${metadata}</metadata><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="#64748b"/></marker><style>${styles}</style></defs>${edgeMarkup}${nodeMarkup}${annotationMarkup}</svg>`;
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
