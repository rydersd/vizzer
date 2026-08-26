import {groupSymbolName,objectSymbolName} from './vizzer_sf_symbols.mjs';

const EDGE_LANE_GAP = 18;
const EDGE_NODE_GAP = 24;

function textUnits(value) {
  let units=0;
  for(const character of String(value||'')){
    if(/\s/.test(character))units+=.55;
    else if(/[MW@#%&]/.test(character))units+=1.9;
    else if(/[ilI1|.,:;!'`]/.test(character))units+=.48;
    else if(/[A-Z0-9]/.test(character))units+=1.1;
    else if(character.codePointAt(0)>0x7f)units+=1.35;
    else units+=1;
  }
  return units;
}

function splitToken(value,maximum) {
  const chunks=[];let chunk='';
  for(const character of String(value||'')){
    if(chunk&&textUnits(chunk+character)>maximum){chunks.push(chunk);chunk=character;}
    else chunk+=character;
  }
  if(chunk)chunks.push(chunk);
  return chunks;
}

export function wrapTextLines(value,maxUnits) {
  const maximum=Math.max(1,Number(maxUnits)||1);
  const words=String(value||'').trim().split(/\s+/).filter(Boolean)
    .flatMap(word=>textUnits(word)<=maximum?[word]:splitToken(word,maximum));
  if(!words.length)return [];
  const lines=[];let line='';
  for(const word of words){
    const next=line?`${line} ${word}`:word;
    if(line&&textUnits(next)>maximum){lines.push(line);line=word;}else line=next;
  }
  if(line)lines.push(line);
  return lines;
}

export function groupFramePresentation(title,statusCounts={},collapsed=false) {
  const titleLines=wrapTextLines(title,collapsed?24:36);
  const statusEntries=Object.entries(statusCounts||{}).filter(([,count])=>count)
    .map(([role,count])=>({role,count,label:`${count} ${role}`}));
  return {titleLines:titleLines.length?titleLines:['Untitled group'],statusEntries,
    symbol:groupSymbolName()};
}

export function objectCardPresentation(object,expanded=false) {
  const detailEntries=expanded?Object.entries(object?.details||{})
    .filter(([,value])=>typeof value==='string'&&value).slice(0,5)
    .map(([key,value])=>({
      key,
      keyLines:wrapTextLines(key,12),
      valueLines:wrapTextLines(value,42),
    })):[];
  return {
    symbol:objectSymbolName(object),
    titleLines:wrapTextLines(object?.title||object?.id||'Untitled object',expanded?40:22),
    summaryLines:object?.summary?wrapTextLines(object.summary,expanded?62:43):[],
    failureLines:object?.failure?.message
      ?wrapTextLines(object.failure.message,expanded?54:42):[],
    detailEntries,
  };
}

function statusRowCount(statusCounts, availableWidth) {
  const widths=Object.entries(statusCounts||{}).filter(([,count])=>count)
    .map(([role,count])=>Math.max(46,(`${count} ${role}`).length*6+16));
  if(!widths.length)return 0;
  let rows=1,used=0;
  for(const width of widths){
    const next=used?used+4+width:width;
    if(next>availableWidth&&used){rows++;used=width;}else used=next;
  }
  return rows;
}

export function groupFrameMetrics(title,statusCounts={},collapsed=false) {
  const width=collapsed?360:undefined;
  const presentation=groupFramePresentation(title,statusCounts,collapsed);
  const headerHeight=Math.max(52,18+presentation.titleLines.length*18);
  const rows=statusRowCount(statusCounts,(width||360)-36);
  const aggregateHeight=collapsed?56+(rows?rows*19+8:0):0;
  return {width,headerHeight,height:collapsed?headerHeight+aggregateHeight:undefined};
}

export function objectCardMetrics(object,expanded=false) {
  const width=expanded?440:320;
  const presentation=objectCardPresentation(object,expanded);
  const headerHeight=Math.max(62,34+presentation.titleLines.length*18);
  const summaryHeight=presentation.summaryLines.length?22+presentation.summaryLines.length*19:0;
  const failureHeight=presentation.failureLines.length?16+presentation.failureLines.length*18:0;
  const detailHeight=presentation.detailEntries.length?20+presentation.detailEntries.reduce(
    (height,entry)=>height+Math.max(entry.keyLines.length,entry.valueLines.length,1)*16+7,0,
  ):0;
  const contentHeight=headerHeight+summaryHeight+detailHeight+failureHeight+38;
  return {width,headerHeight,height:expanded?Math.max(340,contentHeight):Math.max(138,contentHeight),
    summaryHeight,detailHeight,failureHeight,presentation};
}

export function rootLayoutOptions(direction) {
  return {
    'elk.algorithm': 'layered',
    'elk.direction': direction,
    'elk.edgeRouting': 'ORTHOGONAL',
    'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
    'elk.layered.mergeEdges': 'false',
    'elk.spacing.nodeNode': '72',
    'elk.spacing.edgeEdge': String(EDGE_LANE_GAP),
    'elk.spacing.edgeNode': String(EDGE_NODE_GAP),
    'elk.layered.spacing.edgeEdgeBetweenLayers': String(EDGE_LANE_GAP),
    'elk.layered.spacing.edgeNodeBetweenLayers': String(EDGE_NODE_GAP),
    'elk.layered.spacing.nodeNodeBetweenLayers': '110',
    'elk.layered.crossingMinimization.greedySwitch.type': 'TWO_SIDED',
    'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    'elk.padding': '[top=60,left=60,bottom=60,right=60]',
  };
}

export function groupLayoutOptions(direction,headerHeight=52) {
  return {
    'elk.algorithm': 'layered',
    'elk.direction': direction,
    'elk.edgeRouting': 'ORTHOGONAL',
    'elk.padding': `[top=${headerHeight+12},left=28,bottom=28,right=28]`,
    'elk.spacing.nodeNode': '52',
    'elk.spacing.edgeEdge': String(EDGE_LANE_GAP),
    'elk.spacing.edgeNode': String(EDGE_NODE_GAP),
    'elk.layered.spacing.edgeEdgeBetweenLayers': String(EDGE_LANE_GAP),
    'elk.layered.spacing.edgeNodeBetweenLayers': String(EDGE_NODE_GAP),
    'elk.layered.spacing.nodeNodeBetweenLayers': '92',
  };
}

export function absoluteEdgeRoutes(layout) {
  const parentById=new Map(),originById=new Map(),edges=[];
  const visit=(entry,parentId=null,parentOrigin={x:0,y:0})=>{
    const origin={x:parentOrigin.x+(Number(entry?.x)||0),
      y:parentOrigin.y+(Number(entry?.y)||0)};
    parentById.set(entry.id,parentId);
    originById.set(entry.id,origin);
    edges.push(...(entry.edges||[]));
    for(const child of entry.children||[])visit(child,entry.id,origin);
  };
  visit(layout);
  const ancestors=id=>{
    const result=[];let cursor=id,guard=0;
    while(cursor!=null&&parentById.has(cursor)&&guard++<100){
      result.push(cursor);cursor=parentById.get(cursor);
    }
    return result;
  };
  const lowestCommonAncestor=ids=>{
    const lineages=ids.filter(id=>parentById.has(id)).map(ancestors);
    if(!lineages.length||lineages.length!==ids.length)return null;
    return lineages[0].find(candidate=>lineages.every(lineage=>lineage.includes(candidate)))||null;
  };
  const routes=new Map();
  for(const edge of edges){
    const section=edge.sections?.[0];
    if(!section){routes.set(edge.id,[]);continue;}
    // ELK returns compound edges on the root graph, but section coordinates are
    // local to the endpoints' lowest common ancestor—not to the edge owner.
    const endpointIds=[...(edge.sources||[]),...(edge.targets||[])];
    const lca=lowestCommonAncestor(endpointIds);
    const offset=originById.get(lca)||{x:0,y:0};
    const points=[section.startPoint,...(section.bendPoints||[]),section.endPoint]
      .map(point=>({x:Number(point?.x),y:Number(point?.y)}));
    if(!points.every(point=>Number.isFinite(point.x)&&Number.isFinite(point.y))){
      routes.set(edge.id,[]);continue;
    }
    routes.set(edge.id,points.map(point=>({x:point.x+offset.x,y:point.y+offset.y})));
  }
  return routes;
}

export function roundedOrthogonalPath(points,radius=10) {
  const clean=[];
  for(const point of points||[]){
    const next={x:Number(point?.x),y:Number(point?.y)};
    if(!Number.isFinite(next.x)||!Number.isFinite(next.y))return '';
    const previous=clean.at(-1);
    if(!previous||previous.x!==next.x||previous.y!==next.y)clean.push(next);
  }
  if(!clean.length)return '';
  if(clean.length===1)return `M ${clean[0].x} ${clean[0].y}`;
  let path=`M ${clean[0].x} ${clean[0].y}`;
  for(let index=1;index<clean.length-1;index++){
    const previous=clean[index-1],corner=clean[index],next=clean[index+1];
    const incoming=Math.hypot(corner.x-previous.x,corner.y-previous.y);
    const outgoing=Math.hypot(next.x-corner.x,next.y-corner.y);
    const cross=(corner.x-previous.x)*(next.y-corner.y)
      -(corner.y-previous.y)*(next.x-corner.x);
    if(!incoming||!outgoing||Math.abs(cross)<.001){path+=` L ${corner.x} ${corner.y}`;continue;}
    const bend=Math.min(Math.max(0,radius),incoming/2,outgoing/2);
    const before={x:corner.x-(corner.x-previous.x)/incoming*bend,
      y:corner.y-(corner.y-previous.y)/incoming*bend};
    const after={x:corner.x+(next.x-corner.x)/outgoing*bend,
      y:corner.y+(next.y-corner.y)/outgoing*bend};
    path+=` L ${before.x} ${before.y} Q ${corner.x} ${corner.y} ${after.x} ${after.y}`;
  }
  const last=clean.at(-1);
  return `${path} L ${last.x} ${last.y}`;
}

export function routeMatchesEndpoints(
  points, source, target, tolerance = 12,
) {
  if(!Array.isArray(points)||points.length<2)return false;
  const start=points[0],end=points.at(-1);
  const endpointCoordinates=[source?.x,source?.y,target?.x,target?.y];
  if(!endpointCoordinates.every(value=>Number.isFinite(Number(value)))
    ||!points.every(point=>Number.isFinite(Number(point?.x))
      &&Number.isFinite(Number(point?.y))))return false;
  const limit=Math.max(0,Number(tolerance)||0);
  const distance=(left,right)=>Math.hypot(
    Number(left.x)-Number(right.x),Number(left.y)-Number(right.y),
  );
  return distance(start,source)<=limit&&distance(end,target)<=limit;
}

export function routeCrossesRect(points, rect, inset = 0.01) {
  const left=rect.x+inset,right=rect.x+rect.width-inset;
  const top=rect.y+inset,bottom=rect.y+rect.height-inset;
  for(let index=1;index<points.length;index++){
    const a=points[index-1],b=points[index];
    if(Math.abs(a.x-b.x)<.001){
      const low=Math.min(a.y,b.y),high=Math.max(a.y,b.y);
      if(a.x>left&&a.x<right&&high>top&&low<bottom)return true;
    }else if(Math.abs(a.y-b.y)<.001){
      const low=Math.min(a.x,b.x),high=Math.max(a.x,b.x);
      if(a.y>top&&a.y<bottom&&high>left&&low<right)return true;
    }
  }
  return false;
}

export function pathMidpoint(points) {
  if (!points.length) return { x: 0, y: 0 };
  if (points.length === 1) return { x: points[0].x, y: points[0].y };
  const segments=[];
  let total=0;
  for(let index=1;index<points.length;index++){
    const start=points[index-1],end=points[index];
    const length=Math.hypot(end.x-start.x,end.y-start.y);
    segments.push({start,end,length});total+=length;
  }
  if(!total)return {x:points[0].x,y:points[0].y};
  let remaining=total/2;
  for(const segment of segments){
    if(remaining<=segment.length){
      const ratio=segment.length?remaining/segment.length:0;
      return {x:segment.start.x+(segment.end.x-segment.start.x)*ratio,
        y:segment.start.y+(segment.end.y-segment.start.y)*ratio};
    }
    remaining-=segment.length;
  }
  return {x:points.at(-1).x,y:points.at(-1).y};
}

function pointAlongPath(points,fraction) {
  if(points.length<2)return {...(points[0]||{x:0,y:0}),dx:1,dy:0};
  const segments=[];let total=0;
  for(let index=1;index<points.length;index++){
    const start=points[index-1],end=points[index];
    const length=Math.hypot(end.x-start.x,end.y-start.y);
    if(length){segments.push({start,end,length});total+=length;}
  }
  let remaining=total*Math.min(1,Math.max(0,fraction));
  for(const segment of segments){
    if(remaining<=segment.length){
      const ratio=remaining/segment.length;
      return {x:segment.start.x+(segment.end.x-segment.start.x)*ratio,
        y:segment.start.y+(segment.end.y-segment.start.y)*ratio,
        dx:(segment.end.x-segment.start.x)/segment.length,
        dy:(segment.end.y-segment.start.y)/segment.length};
    }
    remaining-=segment.length;
  }
  const last=segments.at(-1);
  return {x:last.end.x,y:last.end.y,dx:(last.end.x-last.start.x)/last.length,
    dy:(last.end.y-last.start.y)/last.length};
}

function rectangleOverlap(first,second,gap=0) {
  return Math.max(0,Math.min(first.x+first.width,second.x+second.width)
    -Math.max(first.x,second.x)+gap*2)
    *Math.max(0,Math.min(first.y+first.height,second.y+second.height)
      -Math.max(first.y,second.y)+gap*2);
}

export function placePathLabel(points,label,obstacles=[],occupied=[]) {
  const width=Math.max(42,Math.min(180,String(label||'').length*5.4+14)),height=18;
  const candidates=[];
  for(const fraction of [.5,.35,.65,.2,.8]){
    const point=pointAlongPath(points,fraction);
    for(const offset of [0,-16,16]){
      const x=point.x-point.dy*offset,y=point.y+point.dx*offset;
      const rect={x:x-width/2,y:y-height/2,width,height};
      const nodeOverlap=obstacles.reduce((sum,item)=>sum+rectangleOverlap(rect,item,5),0);
      const labelOverlap=occupied.reduce((sum,item)=>sum+rectangleOverlap(rect,item,7),0);
      candidates.push({x,y,rect,score:nodeOverlap*1000+labelOverlap*2000+Math.abs(offset)});
    }
  }
  candidates.sort((left,right)=>left.score-right.score);
  return candidates[0]||{x:0,y:0,rect:{x:0,y:0,width,height}};
}
