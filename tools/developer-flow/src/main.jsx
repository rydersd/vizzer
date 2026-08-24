import React,{memo,useCallback,useDeferredValue,useEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import ELK from 'elkjs/lib/elk.bundled.js';
import {
  Background,BaseEdge,Controls,EdgeLabelRenderer,Handle,MiniMap,Panel,Position,
  ReactFlow,ReactFlowProvider,getSmoothStepPath,useReactFlow,
} from '@xyflow/react';
import {developerFlowSvg,svgFilename,triggerSvgDownload} from './export_svg.mjs';
import {
  groupFrameMetrics,groupLayoutOptions,objectCardMetrics,pathMidpoint,
  rootLayoutOptions,roundedOrthogonalPath,
} from './layout_contract.mjs';
import {
  decodeViewState,encodeViewState,normalizeSavedViews,normalizeViewState,
  savedViewsStorageKey,
} from './view_state.mjs';

const INITIAL_DATA=globalThis.__VIZZER_DEVELOPER_GRAPH__;
const INITIAL_VIEW=decodeViewState(globalThis.location?.search||'');
const elk=new ELK();
const ACTIVE=new Set(['building','in-flight','active']);
const KIND_ICON={database:'▰',dataset:'▰',service:'◈',endpoint:'◈',cloud:'☁',test:'✓',story:'◇',job:'◆',module:'▧',epic:'▧',capability:'▦',component:'▣',decision:'◆',object:'○'};

function kindIcon(kind){return KIND_ICON[kind]||KIND_ICON.object;}
function lifecycleRole(object){
  if(object.failure||object.statusRole==='blocked')return 'blocked';
  if(object.statusRole==='shipped')return 'shipped';
  if(object.statusRole==='active'||ACTIVE.has(object.status))return 'active';
  return 'ready';
}
function scoreObject(object){
  return (object.failure?1000:0)+(object.statusRole==='active'?400:0)
    +(object.details?.activeWork?200:0)+(object.summary?10:0);
}
function groupMaps(data){
  const byId=new Map(data.groups.map(group=>[group.id,group]));
  const ancestors=id=>{const result=[];let current=id,guard=0;while(current&&byId.has(current)&&guard++<100){result.push(current);current=byId.get(current).parentId;}return result;};
  return {byId,ancestors};
}

function projectVisible(data,filters,collapsed,selectedId){
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
  const matches=data.objects.filter(object=>!object.boundaryOnly&&(()=>{
    const text=`${object.id} ${object.title} ${object.summary||''} ${object.status} ${object.kind}`.toLowerCase();
    return (!query||text.includes(query))
      &&(!filters.kind||object.kind===filters.kind)
      &&(!filters.status||object.status===filters.status)
      &&(!filters.group||ancestors(object.groupId).includes(filters.group))
      &&(!filters.focusGroupId||ancestors(object.groupId).includes(filters.focusGroupId))
      &&(!filters.focusObjectId||neighborhood.has(object.id));
  })());
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
  const visibleObjects=materialized.filter(object=>!hiddenByCollapse.has(object.id));
  const visibleIds=new Set(visibleObjects.map(object=>object.id));
  const requiredGroups=new Set(),groupCounts=new Map(),groupStatusCounts=new Map();
  for(const object of data.objects)if(!object.boundaryOnly)for(const id of ancestors(object.groupId)){
    groupCounts.set(id,(groupCounts.get(id)||0)+1);
    const counts=groupStatusCounts.get(id)||{active:0,blocked:0,ready:0,shipped:0};
    counts[lifecycleRole(object)]++;
    groupStatusCounts.set(id,counts);
  }
  for(const summary of data.summaries||[]){
    for(const id of ancestors(summary.groupId))requiredGroups.add(id);
    if(!groupCounts.has(summary.groupId)){
      groupCounts.set(summary.groupId,summary.objectCount||0);
      groupStatusCounts.set(summary.groupId,summary.statusComposition||{});
    }
  }
  for(const object of materialized)for(const id of ancestors(object.groupId))requiredGroups.add(id);

  // Keep collapsed external dependency boundaries, not their whole subtrees.
  if(filters.focusGroupId){
    const focusParent=byId.get(filters.focusGroupId)?.parentId||null;
    const boundaryFor=object=>{
      const lineage=ancestors(object?.groupId);
      if(focusParent&&lineage.includes(focusParent))return lineage.find(id=>byId.get(id)?.parentId===focusParent)||focusParent;
      return lineage.at(-1)||null;
    };
    for(const relation of data.relations){
      const sourceInside=candidateIds.has(relation.source),targetInside=candidateIds.has(relation.target);
      if(sourceInside===targetInside)continue;
      const boundary=boundaryFor(objectById.get(sourceInside?relation.target:relation.source));
      if(boundary)for(const id of ancestors(boundary))requiredGroups.add(id);
    }
  }

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
    if(filters.focusObjectId&&(!sourceCandidate||!targetCandidate))continue;
    if(filters.focusGroupId&&!sourceCandidate&&!targetCandidate)continue;
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
      omitted:serverObjectOmitted+Math.max(0,matches.length-materialized.length),
      boundaryOmitted:data.page?.boundaryOmitted||0,
      relationOmitted:data.page?.relationOmitted||0,
      collapsed:hiddenByCollapse.size,source:data.limits.sourceObjectCount},
    groupCounts,groupStatusCounts,
  };
}

function buildElkGraph(projected,collapsed,expanded,direction){
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
function edgePoints(edge){
  const section=edge.sections?.[0];
  return section?[section.startPoint,...(section.bendPoints||[]),section.endPoint]:[];
}
function flattenLayout(layout,projected,collapsed,expanded,onToggleGroup,onToggleExpanded,onSelect){
  const objectById=new Map(projected.objects.map(object=>[object.id,object]));
  const groupById=new Map(projected.groups.map(group=>[group.id,group]));
  const nodes=[];
  const visit=(entry,parentId=null)=>{
    if(entry.vizzerType==='group'){
      const group=groupById.get(entry.id);
      const statusCounts=projected.groupStatusCounts.get(entry.id)||{};
      const metrics=groupFrameMetrics(group.title,statusCounts,collapsed.has(entry.id));
      nodes.push({id:entry.id,type:'groupFrame',parentId:parentId||undefined,position:{x:entry.x||0,y:entry.y||0},style:{width:entry.width,height:entry.height},selectable:true,draggable:false,data:{...group,count:projected.groupCounts.get(entry.id)||0,statusCounts,headerHeight:metrics.headerHeight,collapsed:collapsed.has(entry.id),onToggle:onToggleGroup}});
      for(const child of entry.children||[])visit(child,entry.id);
    }else{
      const object=objectById.get(entry.id);
      const metrics=objectCardMetrics(object,expanded.has(entry.id));
      nodes.push({id:entry.id,type:'objectCard',parentId:parentId||undefined,extent:parentId?'parent':undefined,position:{x:entry.x||0,y:entry.y||0},style:{width:entry.width,height:entry.height},draggable:false,data:{...object,headerHeight:metrics.headerHeight,expanded:expanded.has(entry.id),onToggleExpanded,onSelect}});
    }
  };
  for(const child of layout.children||[])visit(child);
  const relationById=new Map(projected.relations.map(relation=>[relation.id,relation])),edges=[];
  const collect=entry=>{
    for(const edge of entry.edges||[]){
      const relation=relationById.get(edge.id);if(!relation)continue;
      edges.push({id:edge.id,source:relation.source,target:relation.target,type:'routed',data:{...relation,points:edgePoints(edge)},label:relation.count>1?`${relation.kind} ×${relation.count}`:relation.kind,markerEnd:'developer-arrow'});
    }
    for(const child of entry.children||[])collect(child);
  };
  collect(layout);
  return {nodes,edges};
}

const GroupFrame=memo(function GroupFrame({data}){
  const roles=['blocked','active','ready','shipped'];
  return <section className={`group-frame${data.collapsed?' is-collapsed':''}`} aria-label={`${data.title} group`}>
    <header style={{minHeight:data.headerHeight}}><span>{data.title}</span><small>{data.count} objects</small><button type="button" onClick={event=>{event.stopPropagation();data.onToggle(data.id);}} aria-expanded={!data.collapsed}>{data.collapsed?'Expand':'Collapse'}</button></header>
    {data.collapsed&&<div className="group-aggregate"><span>{kindIcon(data.kind)} <b>{data.count}</b></span><span className="status-composition" aria-label="Subcomponent status">{roles.filter(role=>data.statusCounts[role]).map(role=><i className={`role-${role}`} key={role} title={`${data.statusCounts[role]} ${role}`}>{data.statusCounts[role]} {role}</i>)}</span></div>}
    <Handle type="target" position={Position.Left}/><Handle type="source" position={Position.Right}/>
  </section>;
});
const ObjectCard=memo(function ObjectCard({data,selected}){
  return <article className={`object-card status-${data.status}${data.failure?' has-failure':''}${selected?' selected':''}`} data-expanded={data.expanded?'true':'false'}>
    <Handle type="target" position={Position.Left}/>
    <header style={{minHeight:data.headerHeight}}><span className="kind-icon" aria-hidden="true">{kindIcon(data.kind)}</span><button className="object-select" type="button" onClick={event=>{event.stopPropagation();data.onSelect(data.id);}}><small>{data.kind}</small><b>{data.title}</b></button><em>{data.status}</em></header>
    {data.summary&&<p>{data.summary}</p>}
    {data.failure&&<button type="button" className="failure-strip" title={`${data.failure.source} · ${data.failure.at}`}>⚠ {data.failure.message}</button>}
    {data.expanded&&<dl className="card-details">{Object.entries(data.details||{}).filter(([,value])=>typeof value==='string'&&value).slice(0,5).map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd>{value}</dd></React.Fragment>)}</dl>}
    <button type="button" className="card-expand" onClick={event=>{event.stopPropagation();data.onToggleExpanded(data.id);}} aria-label={`${data.expanded?'Collapse':'Expand'} ${data.title} card`}>{data.expanded?'−':'+'}</button>
    <Handle type="source" position={Position.Right}/>
  </article>;
});
function RoutedEdge(props){
  const points=props.data?.points||[];
  const path=points.length>1?roundedOrthogonalPath(points,10):getSmoothStepPath({...props,borderRadius:10})[0];
  const middle=points.length?pathMidpoint(points)
    :{x:(props.sourceX+props.targetX)/2,y:(props.sourceY+props.targetY)/2};
  return <><BaseEdge path={path} markerEnd={props.markerEnd} className={`relation-edge relation-${props.data?.kind||'other'}`}/><EdgeLabelRenderer><span className="relation-label" style={{transform:`translate(-50%,-50%) translate(${middle.x}px,${middle.y}px)`}}>{props.label}</span></EdgeLabelRenderer></>;
}
const nodeTypes={groupFrame:GroupFrame,objectCard:ObjectCard},edgeTypes={routed:RoutedEdge};

function detailText(value){
  if(value==null||value==='')return '';
  if(typeof value==='string')return value;
  if(Array.isArray(value))return value.map(entry=>typeof entry==='string'?entry:JSON.stringify(entry)).join('\n');
  return JSON.stringify(value,null,2);
}
function DetailSection({title,value,empty}){
  return <section className="detail-section"><h3>{title}</h3><div>{detailText(value)||empty}</div></section>;
}
function Dossier({object,onClose,onFocusObject,focused}){
  if(!object)return <aside className="dossier" aria-hidden="true"/>;
  const detail=object.detail||{},sections=detail.sections||{};
  const details=Object.entries(object.details||{}).filter(([,value])=>value!==''&&value!=null);
  return <aside className="dossier open" aria-label={`${object.title} details`}><header><div><small>{object.kind}</small><h2>{object.title}</h2></div><button type="button" onClick={onClose} aria-label="Close details">×</button></header>
    <div className="dossier-body"><span className={`status-pill status-${object.status}`}>{object.status}</span><button type="button" className="focus-neighborhood" aria-pressed={focused} onClick={()=>onFocusObject(object.id)}>{focused?'Showing functional neighborhood':'Focus related objects'}</button>{object.summary&&<p className="summary">{object.summary}</p>}
      {object.failure&&<section className="failure-detail"><h3>Work failure</h3><p>{object.failure.message}</p><small>{object.failure.source} · {object.failure.at} · {object.failure.provenance.source}</small></section>}
      <div data-detail-schema={detail.schema||'unknown'}>
        <DetailSection title="Review steps" value={sections.reviewSteps} empty="No review steps available for this object."/>
        <DetailSection title="Acceptance" value={sections.acceptance} empty="No acceptance criteria available for this object."/>
        <DetailSection title="Definition of done" value={sections.definitionOfDone} empty="No Definition of Done available for this object."/>
      </div>
      <h3>Core details</h3><dl>{details.map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd>{Array.isArray(value)?value.join(', '):typeof value==='object'?JSON.stringify(value):String(value)}</dd></React.Fragment>)}</dl>
      <h3>Relationships</h3><dl><dt>depends on</dt><dd>{detail.relationships?.dependsOn?.join(', ')||'none declared'}</dd><dt>typed</dt><dd>{detail.relationships?.typed?.map(value=>`${value.kind}: ${value.target}`).join(', ')||'none declared'}</dd></dl>
      <h3>Provenance</h3><dl>{Object.entries(object.provenance||{}).map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd>{value}</dd></React.Fragment>)}</dl>
      <a className="constellation-detail-link" href={`constellation.html#story/${encodeURIComponent(object.id)}`}>Open in Constellation</a>
    </div></aside>;
}

function DeveloperFlow(){
  const {fitView}=useReactFlow();
  const [data,setData]=useState(INITIAL_DATA);
  const served=data.delivery?.mode==='served';
  const unstableHttpOrigin=/^https?:$/.test(globalThis.location?.protocol||'')
    && !INITIAL_DATA.delivery?.restartStableOrigin;
  const querySequence=useRef(0);
  const kinds=useMemo(()=>[...new Set([
    ...Object.keys(data.vocab?.objectKinds||{}),...data.objects.map(object=>object.kind),
  ])].sort(),[data]);
  const statuses=useMemo(()=>[...new Set([
    ...(data.vocab?.statuses||[]),...data.objects.map(object=>object.status),
  ])].sort(),[data]);
  const relationKinds=useMemo(()=>[...new Set([
    ...Object.keys(data.vocab?.relationKinds||{}),...data.relations.map(relation=>relation.kind),
  ])].sort(),[data]);
  const [filters,setFilters]=useState(INITIAL_VIEW.filters);
  const allGroupIds=useMemo(()=>data.groups.map(group=>group.id),[data.groups]);
  const groupById=useMemo(()=>new Map(data.groups.map(group=>[group.id,group])),[data.groups]);
  const objectById=useMemo(()=>new Map(data.objects.map(object=>[object.id,object])),[data.objects]);
  const [collapsed,setCollapsed]=useState(()=>{
    if(INITIAL_VIEW.scope==='all'||INITIAL_VIEW.scope==='object')return new Set();
    if(INITIAL_VIEW.scope==='group'){
      const next=new Set(allGroupIds);let cursor=INITIAL_VIEW.id;
      while(cursor){next.delete(cursor);cursor=groupById.get(cursor)?.parentId||null;}
      return next;
    }
    return new Set(allGroupIds);
  });
  const [expanded,setExpanded]=useState(()=>new Set());
  const [selectedId,setSelectedId]=useState(INITIAL_VIEW.selectedId||null);
  const [focusGroupId,setFocusGroupId]=useState(INITIAL_VIEW.scope==='group'?INITIAL_VIEW.id:null);
  const [focusObjectId,setFocusObjectId]=useState(INITIAL_VIEW.scope==='object'?INITIAL_VIEW.id:null);
  const [direction,setDirection]=useState(INITIAL_VIEW.direction);
  const [zoom,setZoom]=useState(1);
  const [fitRequested,setFitRequested]=useState(true);
  const [layout,setLayout]=useState({nodes:[],edges:[],busy:true,error:'',stats:null});
  const savedKey=savedViewsStorageKey(INITIAL_DATA.title,globalThis.location?.pathname||'');
  const [savedViews,setSavedViews]=useState(()=>{
    try{return normalizeSavedViews(JSON.parse(localStorage.getItem(savedKey)||'[]'));}catch(_){return [];}
  });
  const [saveName,setSaveName]=useState('');
  const [viewStatus,setViewStatus]=useState('');
  const deferredQuery=useDeferredValue(filters.query);
  const projected=useMemo(()=>projectVisible(data,{...filters,query:deferredQuery,focusGroupId,focusObjectId},collapsed,selectedId),[data,filters,deferredQuery,focusGroupId,focusObjectId,collapsed,selectedId]);
  const requestFit=()=>{setLayout(value=>({...value,busy:true,error:''}));setFitRequested(true);};
  const fetchSlice=useCallback(async(scope,nextFilters)=>{
    const sequence=++querySequence.current;
    setLayout(value=>({...value,busy:true,error:''}));
    const params=new URLSearchParams({scope:scope.kind,limit:String(INITIAL_DATA.limits.materializationCap)});
    if(scope.id)params.set('id',scope.id);
    if(nextFilters.query)params.set('q',nextFilters.query);
    if(nextFilters.kind)params.append('kind',nextFilters.kind);
    if(nextFilters.status)params.append('status',nextFilters.status);
    for(const kind of nextFilters.relationKinds)params.append('relation',kind);
    const response=await fetch(`${INITIAL_DATA.delivery.endpoint}?${params}`);
    const payload=await response.json();
    if(!response.ok)throw new Error(payload.error||'Developer graph query failed');
    if(sequence!==querySequence.current)return null;
    const next={
      ...INITIAL_DATA,objects:payload.objects,relations:payload.relations,
      groups:payload.groups,summaries:payload.summaries,page:payload.page,
      queryScope:payload.scope,
      delivery:{...INITIAL_DATA.delivery,snapshot:payload.snapshot},
    };
    setData(next);return next;
  },[]);
  useEffect(()=>{
    if(!served||!['group','object'].includes(INITIAL_VIEW.scope)||!INITIAL_VIEW.id)return;
    fetchSlice({kind:INITIAL_VIEW.scope,id:INITIAL_VIEW.id},INITIAL_VIEW.filters).then(next=>{
      if(!next)return;
      const nextGroups=new Map(next.groups.map(group=>[group.id,group]));
      const nextCollapsed=new Set(next.groups.map(group=>group.id));
      let cursor=INITIAL_VIEW.scope==='group'?INITIAL_VIEW.id
        :next.objects.find(object=>object.id===INITIAL_VIEW.id)?.groupId||null;
      while(cursor){nextCollapsed.delete(cursor);cursor=nextGroups.get(cursor)?.parentId||null;}
      setCollapsed(nextCollapsed);setSelectedId(
        INITIAL_VIEW.selectedId||(INITIAL_VIEW.scope==='object'?INITIAL_VIEW.id:null)
      );setFitRequested(true);
    }).catch(error=>setLayout(value=>({...value,busy:false,error:String(error)})));
  },[served,fetchSlice]);
  const toggleGroup=useCallback(id=>{
    setLayout(value=>({...value,busy:true,error:''}));
    if(served){
      const opening=collapsed.has(id),parent=groupById.get(id)?.parentId||null;
      const scope=opening?{kind:'group',id}:parent?{kind:'group',id:parent}:{kind:'overview'};
      fetchSlice(scope,filters).then(next=>{
        if(!next)return;
        const nextGroups=new Map(next.groups.map(group=>[group.id,group]));
        const nextCollapsed=new Set(next.groups.map(group=>group.id));
        const focus=scope.kind==='group'?scope.id:null;
        let cursor=focus;
        while(cursor){nextCollapsed.delete(cursor);cursor=nextGroups.get(cursor)?.parentId||null;}
        setCollapsed(nextCollapsed);setFocusGroupId(focus);setFocusObjectId(null);
        setSelectedId(null);setFitRequested(true);
      }).catch(error=>setLayout(value=>({...value,busy:false,error:String(error)})));
      return;
    }
    setCollapsed(current=>{
      const opening=current.has(id),parent=groupById.get(id)?.parentId||null,next=new Set(allGroupIds);
      if(opening){let cursor=id;while(cursor){next.delete(cursor);cursor=groupById.get(cursor)?.parentId||null;}setFocusGroupId(id);}
      else if(parent){let cursor=parent;while(cursor){next.delete(cursor);cursor=groupById.get(cursor)?.parentId||null;}setFocusGroupId(parent);}
      else setFocusGroupId(null);
      setFocusObjectId(null);setSelectedId(null);setFitRequested(true);return next;
    });
  },[allGroupIds,groupById,served,collapsed,fetchSlice,filters]);
  const toggleExpanded=useCallback(id=>setExpanded(current=>{const next=new Set(current);next.has(id)?next.delete(id):next.add(id);return next;}),[]);
  const selectObject=useCallback(id=>setSelectedId(id),[]);
  useEffect(()=>{
    let live=true;setLayout(current=>({...current,busy:true,error:'',stats:projected.stats}));
    elk.layout(buildElkGraph(projected,collapsed,expanded,direction)).then(result=>{
      if(!live)return;
      const flat=flattenLayout(result,projected,collapsed,expanded,toggleGroup,toggleExpanded,selectObject);
      setLayout({...flat,busy:false,error:'',stats:projected.stats});
    }).catch(error=>live&&setLayout(current=>({...current,busy:false,error:String(error)})));
    return()=>{live=false;};
  },[projected,collapsed,expanded,direction,toggleGroup,toggleExpanded,selectObject]);
  useEffect(()=>{
    if(!fitRequested||layout.busy||layout.error||!layout.nodes.length)return;
    let depth=0,cursor=focusGroupId;while(cursor){depth++;cursor=groupById.get(cursor)?.parentId||null;}
    const minZoom=focusObjectId ? .62 : depth>1 ? .44 : depth===1 ? .24 : .04;
    const frame=requestAnimationFrame(()=>{fitView({padding:.14,duration:240,minZoom,maxZoom:1.05});setFitRequested(false);});
    return()=>cancelAnimationFrame(frame);
  },[fitRequested,layout.busy,layout.error,layout.nodes,fitView,focusGroupId,focusObjectId,groupById]);
  const selected=objectById.get(selectedId)||null;
  const focusPath=focusGroupId?[...groupMaps(data).ancestors(focusGroupId)].reverse().map(id=>groupById.get(id)).filter(Boolean):[];
  const lod=zoom<.2?'overview':zoom<.42?'glyph':zoom<.78?'compact':'summary';
  const currentScope=focusObjectId?{scope:'object',id:focusObjectId}
    :focusGroupId?{scope:'group',id:focusGroupId}
      :collapsed.size===allGroupIds.length?{scope:'overview',id:''}:{scope:'all',id:''};
  const currentView=normalizeViewState({
    ...currentScope,direction,selectedId:selectedId||'',filters,
  });
  useEffect(()=>{
    const search=encodeViewState(currentView);
    if(globalThis.history?.replaceState&&globalThis.location?.search!==search)
      history.replaceState(null,'',`${location.pathname}${search}${location.hash||''}`);
    setViewStatus('');
  },[currentView.scope,currentView.id,currentView.direction,currentView.selectedId,
    currentView.filters.query,currentView.filters.kind,currentView.filters.status,
    currentView.filters.group,currentView.filters.relationKinds.join('\u0000')]);
  const setFilter=(key,value)=>{
    requestFit();const next={...filters,[key]:value};setFilters(next);
    if(served){
      const scope=key==='group'&&value?{kind:'group',id:value}
        :focusObjectId?{kind:'object',id:focusObjectId}:focusGroupId?{kind:'group',id:focusGroupId}:{kind:'overview'};
      if(key==='group'){setFocusGroupId(value||null);setFocusObjectId(null);}
      fetchSlice(scope,next).then(result=>{if(result){setCollapsed(new Set());setFitRequested(true);}})
        .catch(error=>setLayout(current=>({...current,busy:false,error:String(error)})));
    }else{setFocusGroupId(null);setFocusObjectId(null);setCollapsed(new Set());}
  };
  const showOverview=()=>{
    requestFit();setSelectedId(null);setFocusGroupId(null);setFocusObjectId(null);setExpanded(new Set());
    if(served)fetchSlice({kind:'overview'},filters).then(next=>{if(next){setCollapsed(new Set(next.groups.map(group=>group.id)));setFitRequested(true);}})
      .catch(error=>setLayout(value=>({...value,busy:false,error:String(error)})));
    else setCollapsed(new Set(allGroupIds));
  };
  const showDetails=()=>{requestFit();setFocusGroupId(null);setFocusObjectId(null);setCollapsed(new Set());};
  const focusObject=id=>{
    requestFit();const next={query:'',kind:'',status:'',group:'',relationKinds:filters.relationKinds};setFilters(next);
    setFocusGroupId(null);setFocusObjectId(id);setCollapsed(new Set());
    if(served)fetchSlice({kind:'object',id},next).then(result=>{if(result){setSelectedId(id);setFitRequested(true);}})
      .catch(error=>setLayout(current=>({...current,busy:false,error:String(error)})));
  };
  const clearFilters=()=>{
    const empty={query:'',kind:'',status:'',group:'',relationKinds:[]};setFilters(empty);
    requestFit();setSelectedId(null);setFocusGroupId(null);setFocusObjectId(null);setExpanded(new Set());
    if(served)fetchSlice({kind:'overview'},empty).then(next=>{if(next){setCollapsed(new Set(next.groups.map(group=>group.id)));setFitRequested(true);}})
      .catch(error=>setLayout(value=>({...value,busy:false,error:String(error)})));
    else setCollapsed(new Set(allGroupIds));
  };
  const applyView=value=>{
    const next=normalizeViewState(value);setFilters(next.filters);setDirection(next.direction);
    setSelectedId(next.selectedId||null);setFocusGroupId(next.scope==='group'?next.id:null);
    setFocusObjectId(next.scope==='object'?next.id:null);setExpanded(new Set());requestFit();
    const scope=next.scope==='group'||next.scope==='object'?{kind:next.scope,id:next.id}:{kind:'overview'};
    if(served)fetchSlice(scope,next.filters).then(result=>{
      if(!result)return;const closed=new Set(result.groups.map(group=>group.id));
      let cursor=next.scope==='group'?next.id
        :next.scope==='object'?result.objects.find(object=>object.id===next.id)?.groupId:null;
      const nextGroups=new Map(result.groups.map(group=>[group.id,group]));
      while(cursor){closed.delete(cursor);cursor=nextGroups.get(cursor)?.parentId||null;}
      setCollapsed(closed);setFitRequested(true);
    }).catch(error=>setLayout(value=>({...value,busy:false,error:String(error)})));
    else if(next.scope==='overview')setCollapsed(new Set(allGroupIds));
    else if(next.scope==='all'||next.scope==='object')setCollapsed(new Set());
    else{const closed=new Set(allGroupIds);let cursor=next.id;while(cursor){closed.delete(cursor);cursor=groupById.get(cursor)?.parentId||null;}setCollapsed(closed);}
  };
  const saveView=()=>{
    const name=saveName.trim();if(!name)return;
    const entry={name:name.slice(0,80),view:currentView};
    const next=normalizeSavedViews([entry,...savedViews.filter(saved=>saved.name!==entry.name)]);
    setSavedViews(next);setSaveName('');
    try{
      localStorage.setItem(savedKey,JSON.stringify(next));
      setViewStatus(unstableHttpOrigin
        ? 'View saved for this server origin; set server.port to keep it across restarts'
        : 'View saved');
    }
    catch(_){setViewStatus('Saved for this tab; browser storage is unavailable');}
  };
  const shareView=async()=>{
    const url=new URL(encodeViewState(currentView),location.href).href;
    try{
      await navigator.clipboard.writeText(url);
      setViewStatus(unstableHttpOrigin
        ? 'Link copied; set server.port for a restart-stable URL'
        : 'Link copied');
    }
    catch(_){setViewStatus(url);}
  };
  const exportSvg=()=>{
    const svg=developerFlowSvg({title:data.title,nodes:layout.nodes,edges:layout.edges,lod,exportedAt:new Date().toISOString()});
    try{
      const result=triggerSvgDownload(svg,svgFilename(data.title,currentView.scope));
      setViewStatus(`Downloaded ${result.filename}`);
    }catch(error){setViewStatus(String(error.message||error));}
  };
  return <main className={`developer-shell${selected?' has-dossier':''}`} data-lod={lod}>
    <header className="appbar"><div className="breadcrumbs"><a href="constellation.html" aria-label="Back to constellation">Vizzer</a><span>/</span><button type="button" onClick={showOverview}>Overview</button>{focusPath.map(group=><React.Fragment key={group.id}><span>/</span><strong>{group.title}</strong></React.Fragment>)}{focusObjectId&&selected&&<><span>/</span><strong>{selected.title}</strong></>}<small>{data.title}</small></div>
      <div className="view-actions"><select aria-label="Saved Developer Flow views" defaultValue="" onChange={event=>{const saved=savedViews[Number(event.target.value)];if(saved)applyView(saved.view);event.target.value='';}}><option value="">Saved views</option>{savedViews.map((saved,index)=><option value={index} key={saved.name}>{saved.name}</option>)}</select><input aria-label="Saved view name" value={saveName} onChange={event=>setSaveName(event.target.value)} placeholder="View name" maxLength="80"/><button type="button" onClick={saveView} disabled={!saveName.trim()}>Save</button><button type="button" onClick={shareView}>Share link</button><button type="button" onClick={exportSvg} disabled={!layout.nodes.length}>Export SVG</button><span role="status">{viewStatus}</span></div>
      <div className="orientation" role="group" aria-label="Layout direction"><button aria-pressed={direction==='RIGHT'} onClick={()=>{requestFit();setDirection('RIGHT');}}>→</button><button aria-pressed={direction==='DOWN'} onClick={()=>{requestFit();setDirection('DOWN');}}>↓</button></div>
    </header>
    <section className="filterbar" aria-label="Developer graph filters">
      <input type="search" value={filters.query} onChange={event=>setFilter('query',event.target.value)} placeholder="Filter objects…" aria-label="Filter objects"/>
      <select value={filters.kind} onChange={event=>setFilter('kind',event.target.value)} aria-label="Object kind"><option value="">All object kinds</option>{kinds.map(kind=><option key={kind}>{kind}</option>)}</select>
      <select value={filters.status} onChange={event=>setFilter('status',event.target.value)} aria-label="Status"><option value="">All statuses</option>{statuses.map(status=><option key={status}>{status}</option>)}</select>
      <select value={filters.group} onChange={event=>setFilter('group',event.target.value)} aria-label="Group"><option value="">All groups</option>{data.groups.map(group=><option key={group.id} value={group.id}>{group.title}</option>)}</select>
      <select value={filters.relationKinds[0]||''} onChange={event=>setFilter('relationKinds',event.target.value?[event.target.value]:[])} aria-label="Relationship kind"><option value="">All relationships</option>{relationKinds.map(kind=><option key={kind}>{kind}</option>)}</select>
      <button type="button" onClick={showOverview}>Overview</button>{!served&&<button type="button" onClick={showDetails}>Expand frames</button>}<button type="button" onClick={clearFilters}>Clear</button>
    </section>
    <section className="flowstage">
      <ReactFlow nodes={layout.nodes} edges={layout.edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView minZoom={.04} maxZoom={2.2} onlyRenderVisibleElements nodesDraggable={false} nodesConnectable={false} onMove={(_event,viewport)=>setZoom(viewport.zoom)} onNodeClick={(_event,node)=>{if(node.type==='objectCard')setSelectedId(node.id);}} proOptions={{hideAttribution:false}}>
        <svg aria-hidden="true"><defs><marker id="developer-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z"/></marker></defs></svg>
        <Background gap={28} size={1}/><Controls/><MiniMap pannable zoomable nodeStrokeWidth={2}/>
        <Panel position="bottom-center" className="stats" aria-live="polite">{layout.stats&&<><b>{layout.stats.mounted.toLocaleString()}</b> cards · {layout.nodes.filter(node=>node.type==='groupFrame').length.toLocaleString()} frames · {layout.stats.matched.toLocaleString()} matched · {layout.stats.source.toLocaleString()} source{layout.stats.omitted?` · ${layout.stats.omitted.toLocaleString()} objects omitted; narrow filters`:''}{layout.stats.boundaryOmitted?` · ${layout.stats.boundaryOmitted.toLocaleString()} external objects omitted`:''}{layout.stats.relationOmitted?` · ${layout.stats.relationOmitted.toLocaleString()} relations omitted`:''}{layout.stats.collapsed?` · ${layout.stats.collapsed.toLocaleString()} summarized`:''} · {lod}</>}</Panel>
      </ReactFlow>
      {layout.busy&&<div className="layout-state" role="status">Routing objects and relationships…</div>}
      {layout.error&&<div className="layout-state error" role="alert"><b>Layout failed</b><pre>{layout.error}</pre></div>}
    </section>
    <Dossier object={selected} onClose={()=>setSelectedId(null)} onFocusObject={focusObject} focused={focusObjectId===selectedId}/>
  </main>;
}

createRoot(document.getElementById('root')).render(<ReactFlowProvider><DeveloperFlow/></ReactFlowProvider>);
