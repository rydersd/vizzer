import {normalizeViewState} from './view_state.mjs';

const COLORS=new Set(['blue','yellow','pink','green','white']);
const ID=/^[a-z0-9][a-z0-9._-]{0,79}$/;
const MAX_ANNOTATIONS=200,MAX_STROKE_POINTS=4096,MAX_TOTAL_POINTS=20000;

function text(value,maximum,empty=true){
  if(typeof value!=='string')return '';
  const result=value.slice(0,maximum);
  return empty?result:result.trim();
}
function coordinate(value){
  const number=Number(value);
  return Number.isFinite(number)&&Math.abs(number)<=10000000?number:null;
}
function legacyId(name,index){
  const slug=name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,48)||'view';
  let hash=2166136261;
  for(const char of `${name}:${index}`)hash=Math.imul(hash^char.charCodeAt(0),16777619);
  return `local-${slug}-${(hash>>>0).toString(16)}`.slice(0,80);
}

export function newViewId(prefix='view'){
  const raw=globalThis.crypto?.randomUUID?.().replaceAll('-','')
    ||`${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${raw}`.toLowerCase().replace(/[^a-z0-9._-]/g,'').slice(0,80);
}

export function normalizeAnnotation(value){
  if(!value||typeof value!=='object'||!ID.test(value.id||'')||!COLORS.has(value.color))return null;
  if(value.kind==='note'){
    const x=coordinate(value.x),y=coordinate(value.y),note=text(value.text,2000,false);
    if(x===null||y===null||!note)return null;
    const result={id:value.id,kind:'note',color:value.color,x,y,text:note};
    const objectId=text(value.objectId,500,false);if(objectId)result.objectId=objectId;
    return result;
  }
  if(value.kind==='stroke'){
    if(!Array.isArray(value.points))return null;
    const points=[];
    for(const point of value.points.slice(0,MAX_STROKE_POINTS)){
      if(!Array.isArray(point)||point.length!==2)continue;
      const x=coordinate(point[0]),y=coordinate(point[1]);if(x!==null&&y!==null)points.push([x,y]);
    }
    const width=Number(value.width);
    if(points.length<2||!Number.isFinite(width)||width<1||width>16)return null;
    return {id:value.id,kind:'stroke',color:value.color,width,points};
  }
  return null;
}

export function normalizeViewDocument(value={},index=0){
  const name=text(value.name,80,false);if(!name)return null;
  const id=ID.test(value.id||'')?value.id:legacyId(name,index);
  const annotations=[];let totalPoints=0;
  for(const raw of Array.isArray(value.annotations)?value.annotations.slice(0,MAX_ANNOTATIONS):[]){
    const annotation=normalizeAnnotation(raw);if(!annotation)continue;
    const points=annotation.kind==='stroke'?annotation.points.length:0;
    if(totalPoints+points>MAX_TOTAL_POINTS)break;
    totalPoints+=points;annotations.push(annotation);
  }
  return {schema:1,id,name,view:normalizeViewState(value.view),notes:text(value.notes,20000),annotations,
    annotationsVisible:value.annotationsVisible!==false,
    ...(typeof value.updatedAt==='string'?{updatedAt:value.updatedAt.slice(0,80)}:{})};
}

export function normalizeViewDocuments(value){
  if(!Array.isArray(value))return [];
  const ids=new Set(),result=[];
  for(const [index,raw] of value.entries()){
    const document=normalizeViewDocument(raw,index);if(!document||ids.has(document.id))continue;
    ids.add(document.id);result.push(document);if(result.length===100)break;
  }
  return result;
}

export function annotationPath(points=[]){
  return points.map((point,index)=>`${index?'L':'M'} ${Number(point[0])} ${Number(point[1])}`).join(' ');
}
