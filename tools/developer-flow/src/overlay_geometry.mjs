function normalizedRect(rect) {
  const x=Number(rect?.x)||0,y=Number(rect?.y)||0;
  const width=Math.max(0,Number(rect?.width)||0),height=Math.max(0,Number(rect?.height)||0);
  return {x,y,width,height,right:x+width,bottom:y+height};
}

export function overlapArea(first,second,gap=0) {
  const a=normalizedRect(first),b=normalizedRect(second);
  const width=Math.max(0,Math.min(a.right,b.right)-Math.max(a.x,b.x)+gap*2);
  const height=Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)+gap*2);
  return width*height;
}

function clamp(value,minimum,maximum) {
  return Math.min(Math.max(value,minimum),Math.max(minimum,maximum));
}

export function placeOverlay(anchor,size,boundary,obstacles=[],gap=10,padding=8) {
  const a=normalizedRect(anchor),bounds=normalizedRect(boundary);
  const width=Math.min(Math.max(1,Number(size?.width)||1),Math.max(1,bounds.width-padding*2));
  const height=Math.min(Math.max(1,Number(size?.height)||1),Math.max(1,bounds.height-padding*2));
  const centeredX=a.x+a.width/2-width/2,centeredY=a.y+a.height/2-height/2;
  const raw=[
    {side:'right',x:a.right+gap,y:centeredY},
    {side:'left',x:a.x-width-gap,y:centeredY},
    {side:'below',x:centeredX,y:a.bottom+gap},
    {side:'above',x:centeredX,y:a.y-height-gap},
  ];
  const normalizedObstacles=obstacles.map(normalizedRect);
  for(const obstacle of normalizedObstacles)raw.push(
    {side:'left',x:obstacle.x-width-gap,y:centeredY},
    {side:'right',x:obstacle.right+gap,y:centeredY},
    {side:'above',x:centeredX,y:obstacle.y-height-gap},
    {side:'below',x:centeredX,y:obstacle.bottom+gap},
  );
  const blockers=[a,...normalizedObstacles];
  const candidates=raw.map((candidate,index)=>{
    const x=clamp(candidate.x,bounds.x+padding,bounds.right-padding-width);
    const y=clamp(candidate.y,bounds.y+padding,bounds.bottom-padding-height);
    const rect={x,y,width,height};
    const overlap=blockers.reduce((sum,blocker)=>sum+overlapArea(rect,blocker,2),0);
    const displacement=Math.abs(x-candidate.x)+Math.abs(y-candidate.y);
    return {...candidate,x,y,width,height,overlap,score:overlap*1000+displacement,index};
  });
  candidates.sort((left,right)=>left.score-right.score||left.index-right.index);
  const winner=candidates[0];
  return {x:winner.x,y:winner.y,width:winner.width,height:winner.height,side:winner.side};
}
