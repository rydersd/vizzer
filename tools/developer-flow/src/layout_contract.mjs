const EDGE_LANE_GAP = 18;
const EDGE_NODE_GAP = 24;

function lineCount(value, maxCharacters) {
  const words=String(value||'').trim().split(/\s+/).filter(Boolean);
  if(!words.length)return 1;
  let lines=1,used=0;
  for(const word of words){
    if(!used){
      lines+=Math.floor((word.length-1)/maxCharacters);
      used=((word.length-1)%maxCharacters)+1;
    }else if(used+1+word.length<=maxCharacters)used+=1+word.length;
    else{
      lines++;
      lines+=Math.floor((word.length-1)/maxCharacters);
      used=((word.length-1)%maxCharacters)+1;
    }
  }
  return lines;
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
  const titleLines=lineCount(title,collapsed?24:36);
  const headerHeight=Math.max(52,18+titleLines*18);
  const rows=statusRowCount(statusCounts,(width||360)-36);
  const aggregateHeight=collapsed?56+(rows?rows*19+8:0):0;
  return {width,headerHeight,height:collapsed?headerHeight+aggregateHeight:undefined};
}

export function objectCardMetrics(object,expanded=false) {
  const width=expanded?440:320;
  const titleLines=lineCount(object?.title,expanded?40:22);
  const headerHeight=Math.max(62,34+titleLines*18);
  const summaryLines=object?.summary?lineCount(object.summary,expanded?62:43):0;
  const summaryHeight=summaryLines?22+summaryLines*19:0;
  const failureLines=object?.failure?.message?lineCount(object.failure.message,expanded?62:42):0;
  const failureHeight=failureLines?16+failureLines*18:0;
  const contentHeight=headerHeight+summaryHeight+failureHeight+38;
  return {width,headerHeight,height:expanded?Math.max(340,contentHeight+112):Math.max(138,contentHeight)};
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

export function roundedOrthogonalPath(points,radius=10) {
  const clean=[];
  for(const point of points||[]){
    const next={x:Number(point?.x)||0,y:Number(point?.y)||0};
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
