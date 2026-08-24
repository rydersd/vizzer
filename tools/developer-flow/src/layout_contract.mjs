export function rootLayoutOptions(direction) {
  return {
    'elk.algorithm': 'layered',
    'elk.direction': direction,
    'elk.edgeRouting': 'ORTHOGONAL',
    'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
    'elk.layered.mergeEdges': 'false',
    'elk.spacing.nodeNode': '72',
    'elk.layered.spacing.nodeNodeBetweenLayers': '110',
    'elk.layered.crossingMinimization.greedySwitch.type': 'TWO_SIDED',
    'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    'elk.padding': '[top=60,left=60,bottom=60,right=60]',
  };
}

export function groupLayoutOptions(direction) {
  return {
    'elk.algorithm': 'layered',
    'elk.direction': direction,
    'elk.edgeRouting': 'ORTHOGONAL',
    'elk.padding': '[top=54,left=28,bottom=28,right=28]',
    'elk.spacing.nodeNode': '52',
    'elk.layered.spacing.nodeNodeBetweenLayers': '92',
  };
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
