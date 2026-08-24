import {
  groupFrameMetrics,groupLayoutOptions,objectCardMetrics,rootLayoutOptions,
} from './layout_contract.mjs';

const ACTIVE=new Set(['building','in-flight','active']);

export function lifecycleRole(object){
  if(object.failure||object.statusRole==='blocked')return 'blocked';
  if(object.statusRole==='shipped')return 'shipped';
  if(object.statusRole==='active'||ACTIVE.has(object.status))return 'active';
  return 'ready';
}

function scoreObject(object){
  return (object.failure?1000:0)+(object.statusRole==='active'?400:0)
    +(object.details?.activeWork?200:0)+(object.summary?10:0);
}

export function groupMaps(data){
  const byId=new Map(data.groups.map(group=>[group.id,group]));
  const ancestors=id=>{const result=[];let current=id,guard=0;while(current&&byId.has(current)&&guard++<100){result.push(current);current=byId.get(current).parentId;}return result;};
  return {byId,ancestors};
}

function boundaryRole(relation,sourceInside){
  if(relation.kind==='depends-on')return sourceInside?'input dependency':'external dependent';
  return sourceInside?'external target':'external source';
}

export function projectVisible(data,filters,collapsed,selectedId){
  const {byId,ancestors}=groupMaps(data);
  const objectById=new Map(data.objects.map(object=>[object.id,object]));
  const relationKinds=new Set(filters.relationKinds);
  const neighborhood=new Set();
  if(filters.focusObjectId){
    neighborhood.add(filters.focusObjectId);
    for(const relation of data.relations){
      if(relationKinds.size&&!relationKinds.has(relation.kind))continue;
      if(relation.source===filters.focusObjectId)neighborhood.add(relation.target);
      if(relation.target===filters.focusObjectId)neighborhood.add(relation.source);
    }
  }
  const query=filters.query.toLowerCase();
  const primaryObjects=data.objects.filter(object=>!object.boundaryOnly);
  const focusScopeIds=new Set(filters.focusGroupId?primaryObjects
    .filter(object=>ancestors(object.groupId).includes(filters.focusGroupId))
    .map(object=>object.id):[]);
  const matches=primaryObjects.filter(object=>{
    const text=`${object.id} ${object.title} ${object.summary||''} ${object.status} ${object.kind}`.toLowerCase();
    return (!query||text.includes(query))
      &&(!filters.kind||object.kind===filters.kind)
      &&(!filters.status||object.status===filters.status)
      &&(!filters.group||ancestors(object.groupId).includes(filters.group))
      &&(!filters.focusGroupId||ancestors(object.groupId).includes(filters.focusGroupId))
      &&(!filters.focusObjectId||neighborhood.has(object.id));
  });
  const ordered=[...matches].sort((a,b)=>scoreObject(b)-scoreObject(a)||a.id.localeCompare(b.id));
  const cap=data.limits.materializationCap;
  const selected=selectedId?ordered.find(object=>object.id===selectedId):null;
  const materialized=ordered.slice(0,cap);
  if(selected&&!materialized.some(object=>object.id===selected.id))materialized[materialized.length-1]=selected;
  const candidateIds=new Set(materialized.map(object=>object.id));
  const hiddenByCollapse=new Set();
  for(const object of materialized){
    if(ancestors(object.groupId).some(groupId=>collapsed.has(groupId)))hiddenByCollapse.add(object.id);
  }
  const internalObjects=materialized.filter(object=>!hiddenByCollapse.has(object.id));
  const boundaryById=new Map();
  if(filters.focusGroupId){
    const boundaryCap=data.limits.boundaryMaterializationCap||250;
    const candidates=new Map();
    for(const relation of data.relations){
      if(relationKinds.size&&!relationKinds.has(relation.kind))continue;
      const sourceInside=candidateIds.has(relation.source),targetInside=candidateIds.has(relation.target);
      if(sourceInside===targetInside)continue;
      const outsideId=sourceInside?relation.target:relation.source;
      if(focusScopeIds.has(outsideId))continue;
      const object=objectById.get(outsideId);if(!object)continue;
      const role=boundaryRole(relation,sourceInside),candidate=candidates.get(outsideId);
      candidates.set(outsideId,{object,role:candidate&&candidate.role!==role?'external relation':role});
    }
    for(const outsideId of [...candidates.keys()].sort().slice(0,boundaryCap)){
      const {object,role}=candidates.get(outsideId);
      boundaryById.set(outsideId,{...object,groupId:null,boundaryOnly:true,
        boundaryGroupId:object.groupId||null,boundaryRole:role});
    }
  }
  const boundaryObjects=[...boundaryById.values()];
  const visibleObjects=[...internalObjects,...boundaryObjects];
  const visibleIds=new Set(visibleObjects.map(object=>object.id));
  const requiredGroups=new Set(),groupCounts=new Map(),groupStatusCounts=new Map();
  for(const object of primaryObjects)for(const id of ancestors(object.groupId)){
    groupCounts.set(id,(groupCounts.get(id)||0)+1);
    const counts=groupStatusCounts.get(id)||{active:0,blocked:0,ready:0,shipped:0};
    counts[lifecycleRole(object)]++;
    groupStatusCounts.set(id,counts);
  }
  for(const summary of data.summaries||[]){
    if(filters.focusGroupId&&!ancestors(summary.groupId).includes(filters.focusGroupId))continue;
    for(const id of ancestors(summary.groupId))requiredGroups.add(id);
    if(!groupCounts.has(summary.groupId)){
      groupCounts.set(summary.groupId,summary.objectCount||0);
      groupStatusCounts.set(summary.groupId,summary.statusComposition||{});
    }
  }
  for(const object of materialized)for(const id of ancestors(object.groupId))requiredGroups.add(id);

  const representative=objectId=>{
    if(visibleIds.has(objectId))return objectId;
    const object=objectById.get(objectId);if(!object)return null;
    const lineage=ancestors(object.groupId);
    const collapsedLineage=lineage.filter(id=>collapsed.has(id)&&requiredGroups.has(id));
    return collapsedLineage.at(-1)||lineage.find(id=>requiredGroups.has(id))||null;
  };
  const relationBuckets=new Map();
  for(const relation of data.relations){
    if(relationKinds.size&&!relationKinds.has(relation.kind))continue;
    const sourceCandidate=candidateIds.has(relation.source),targetCandidate=candidateIds.has(relation.target);
    const touchesBoundary=boundaryById.has(relation.source)||boundaryById.has(relation.target);
    if(filters.focusObjectId&&(!sourceCandidate||!targetCandidate))continue;
    if(filters.focusGroupId&&!sourceCandidate&&!targetCandidate&&!touchesBoundary)continue;
    const source=representative(relation.source),target=representative(relation.target);
    if(!source||!target||source===target)continue;
    const key=`${source}\u0000${target}\u0000${relation.kind}`;
    const bucket=relationBuckets.get(key)||{...relation,source,target,count:0,sourceIds:[],targetIds:[]};
    bucket.count++;
    if(bucket.sourceIds.length<8)bucket.sourceIds.push(relation.source);
    if(bucket.targetIds.length<8)bucket.targetIds.push(relation.target);
    relationBuckets.set(key,bucket);
  }
  const serverObjectOmitted=data.queryScope?.kind==='overview'?0
    :Math.max(0,(data.page?.matched||0)-(data.page?.primaryReturned||0));
  return {
    objects:visibleObjects,
    groups:data.groups.filter(group=>requiredGroups.has(group.id)),
    relations:[...relationBuckets.values()],
    stats:{matched:Number.isFinite(data.page?.matched)?data.page.matched
      :(data.summaries||[]).length?data.summaries.reduce((total,row)=>total+(row.objectCount||0),0):matches.length,
      mounted:visibleObjects.length,
      boundaryMounted:boundaryObjects.length,
      omitted:serverObjectOmitted+Math.max(0,matches.length-materialized.length),
      boundaryOmitted:data.page?.boundaryOmitted||0,
      relationOmitted:data.page?.relationOmitted||0,
      collapsed:hiddenByCollapse.size,source:data.limits.sourceObjectCount},
    groupCounts,groupStatusCounts,
  };
}

export function buildElkGraph(projected,collapsed,expanded,direction){
  const groupsByParent=new Map(),objectsByGroup=new Map();
  for(const group of projected.groups){const key=group.parentId||'';groupsByParent.set(key,[...(groupsByParent.get(key)||[]),group]);}
  for(const object of projected.objects){const key=object.groupId||'';objectsByGroup.set(key,[...(objectsByGroup.get(key)||[]),object]);}
  const objectNode=object=>({id:object.id,...objectCardMetrics(object,expanded.has(object.id)),vizzerType:'object'});
  const groupNode=group=>{
    const isCollapsed=collapsed.has(group.id);
    const metrics=groupFrameMetrics(group.title,projected.groupStatusCounts.get(group.id)||{},isCollapsed);
    const children=isCollapsed?[]:[
      ...(groupsByParent.get(group.id)||[]).sort((a,b)=>a.id.localeCompare(b.id)).map(groupNode),
      ...(objectsByGroup.get(group.id)||[]).sort((a,b)=>a.id.localeCompare(b.id)).map(objectNode),
    ];
    return {id:group.id,vizzerType:'group',...(isCollapsed?{width:metrics.width,height:metrics.height}:{}),children,layoutOptions:groupLayoutOptions(direction,metrics.headerHeight)};
  };
  return {
    id:'developer-root',
    children:[
      ...(groupsByParent.get('')||[]).sort((a,b)=>a.id.localeCompare(b.id)).map(groupNode),
      ...(objectsByGroup.get('')||[]).sort((a,b)=>a.id.localeCompare(b.id)).map(objectNode),
    ],
    edges:projected.relations.map(relation=>({id:relation.id,sources:[relation.source],targets:[relation.target]})),
    layoutOptions:rootLayoutOptions(direction),
  };
}
