import React,{memo,useCallback,useDeferredValue,useEffect,useMemo,useReducer,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import ELK from 'elkjs/lib/elk.bundled.js';
import {
  Background,BaseEdge,Controls,EdgeLabelRenderer,Handle,MiniMap,Panel,Position,
  ReactFlow,ReactFlowProvider,ViewportPortal,getSmoothStepPath,useReactFlow,
} from '@xyflow/react';
import {developerFlowSvg,svgFilename,triggerSvgDownload} from './export_svg.mjs';
import {
  absoluteEdgeRoutes,groupFrameMetrics,objectCardMetrics,pathMidpoint,placePathLabel,
  roundedOrthogonalPath,routeMatchesEndpoints,
} from './layout_contract.mjs';
import {placeOverlay} from './overlay_geometry.mjs';
import {annotationHistory,annotationHistoryReducer} from './annotation_history.mjs';
import {buildElkGraph,groupMaps,projectVisible} from './graph_projection.mjs';
import {
  groupSymbolName,objectSymbolName,sfSymbolPresentation,
} from './vizzer_sf_symbols.mjs';
import {decodeViewState,encodeViewState,normalizeViewState,savedViewsStorageKey} from './view_state.mjs';
import {
  annotationPath,newViewId,normalizeViewDocument,normalizeViewDocuments,
} from './view_document.mjs';

const INITIAL_DATA=globalThis.__VIZZER_DEVELOPER_GRAPH__;
const INITIAL_VIEW=decodeViewState(globalThis.location?.search||'');
const elk=new ELK();
function flattenLayout(layout,projected,collapsed,expanded,selectedId,onToggleGroup,onToggleExpanded,onSelect,onPreview){
  const objectById=new Map(projected.objects.map(object=>[object.id,object]));
  const groupById=new Map(projected.groups.map(group=>[group.id,group]));
  const nodes=[],labelObstacles=[];
  const visit=(entry,parentId=null,parentOrigin={x:0,y:0})=>{
    const origin={x:parentOrigin.x+(Number(entry.x)||0),y:parentOrigin.y+(Number(entry.y)||0)};
    if(entry.vizzerType==='group'){
      const group=groupById.get(entry.id);
      const statusCounts=projected.groupStatusCounts.get(entry.id)||{};
      const metrics=groupFrameMetrics(group.title,statusCounts,collapsed.has(entry.id));
      nodes.push({id:entry.id,type:'groupFrame',parentId:parentId||undefined,position:{x:entry.x||0,y:entry.y||0},style:{width:entry.width,height:entry.height},selectable:true,selected:selectedId===entry.id,draggable:false,data:{...group,count:projected.groupCounts.get(entry.id)||0,statusCounts,headerHeight:metrics.headerHeight,collapsed:collapsed.has(entry.id),onToggle:onToggleGroup,onSelect}});
      labelObstacles.push({x:origin.x,y:origin.y,width:entry.width||0,height:metrics.headerHeight});
      for(const child of entry.children||[])visit(child,entry.id,origin);
    }else{
      const object=objectById.get(entry.id);
      const metrics=objectCardMetrics(object,expanded.has(entry.id));
      nodes.push({id:entry.id,type:'objectCard',parentId:parentId||undefined,extent:parentId?'parent':undefined,position:{x:entry.x||0,y:entry.y||0},style:{width:entry.width,height:entry.height},selected:selectedId===entry.id,draggable:false,data:{...object,headerHeight:metrics.headerHeight,expanded:expanded.has(entry.id),onToggleExpanded,onSelect,onPreview}});
      labelObstacles.push({x:origin.x,y:origin.y,width:entry.width||0,height:entry.height||0});
    }
  };
  for(const child of layout.children||[])visit(child);
  const relationById=new Map(projected.relations.map(relation=>[relation.id,relation]));
  const routes=absoluteEdgeRoutes(layout),edges=[],labelRects=[];
  const collect=entry=>{
    for(const edge of entry.edges||[]){
      const relation=relationById.get(edge.id);if(!relation)continue;
      const label=relation.count>1?`${relation.kind} ×${relation.count}`:relation.kind;
      const points=routes.get(edge.id)||[];
      const placement=placePathLabel(points,label,labelObstacles,labelRects);
      labelRects.push(placement.rect);
      edges.push({id:edge.id,source:relation.source,target:relation.target,type:'routed',data:{...relation,points,labelPoint:{x:placement.x,y:placement.y}},label,markerEnd:'developer-arrow'});
    }
    for(const child of entry.children||[])collect(child);
  };
  collect(layout);
  return {nodes,edges};
}

function VizzerSymbol({name}){
  const symbol=sfSymbolPresentation(name);
  return symbol?<svg className="sf-symbol" viewBox={symbol.viewBox} focusable="false" aria-hidden="true"><path d={symbol.d} fillRule={symbol.fillRule}/></svg>
    :<span className="sf-symbol-dot" aria-hidden="true"/>;
}

const GroupFrame=memo(function GroupFrame({data,selected}){
  const roles=['blocked','active','ready','shipped'];
  return <section className={`group-frame${data.collapsed?' is-collapsed':''}${selected?' selected':''}`} aria-label={`${data.title} group`} tabIndex="0" onClick={event=>{event.stopPropagation();data.onSelect(data.id);}} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();data.onSelect(data.id);}}}>
    <header style={{minHeight:data.headerHeight}}><span>{data.title}</span><small>{data.count} objects</small><button type="button" onClick={event=>{event.stopPropagation();data.onToggle(data.id);}} aria-expanded={!data.collapsed}>{data.collapsed?'Expand':'Collapse'}</button></header>
    {data.collapsed&&<div className="group-aggregate"><span className="group-symbol"><VizzerSymbol name={groupSymbolName()}/><b>{data.count}</b></span><span className="status-composition" aria-label="Subcomponent status">{roles.filter(role=>data.statusCounts[role]).map(role=><i className={`role-${role}`} key={role} title={`${data.statusCounts[role]} ${role}`}>{data.statusCounts[role]} {role}</i>)}</span></div>}
    <Handle type="target" position={Position.Left}/><Handle type="source" position={Position.Right}/>
  </section>;
});
const ObjectCard=memo(function ObjectCard({data,selected}){
  const preview=event=>data.onPreview(data.id,event.currentTarget.getBoundingClientRect());
  return <article className={`object-card status-${data.status}${data.failure?' has-failure':''}${data.boundaryOnly?' is-boundary':''}${selected?' selected':''}`} data-expanded={data.expanded?'true':'false'} onPointerEnter={preview} onPointerLeave={()=>data.onPreview(null)} onFocusCapture={preview} onBlurCapture={event=>{if(!event.currentTarget.contains(event.relatedTarget))data.onPreview(null);}}>
    <Handle type="target" position={Position.Left}/>
    <button className="node-dot" type="button" aria-label={`Open ${data.title} details`} onClick={event=>{event.stopPropagation();data.onSelect(data.id);}}><VizzerSymbol name={objectSymbolName(data)}/></button>
    <header style={{minHeight:data.headerHeight}}><span className="kind-icon" aria-hidden="true"><VizzerSymbol name={objectSymbolName(data)}/></span><button className="object-select" type="button" onClick={event=>{event.stopPropagation();data.onSelect(data.id);}}><small>{data.boundaryRole?`${data.boundaryRole} · `:''}{data.kind}</small><b>{data.title}</b></button><em>{data.status}</em></header>
    {data.summary&&<p>{data.summary}</p>}
    {data.failure&&<button type="button" className="failure-strip" title={`${data.failure.source} · ${data.failure.at}`}><VizzerSymbol name="exclamationmark.triangle"/><span>{data.failure.message}</span></button>}
    {data.expanded&&<dl className="card-details">{Object.entries(data.details||{}).filter(([,value])=>typeof value==='string'&&value).slice(0,5).map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd>{value}</dd></React.Fragment>)}</dl>}
    <button type="button" className="card-expand" onClick={event=>{event.stopPropagation();data.onToggleExpanded(data.id);}} aria-label={`${data.expanded?'Collapse':'Expand'} ${data.title} card`}>{data.expanded?'−':'+'}</button>
    <Handle type="source" position={Position.Right}/>
  </article>;
});
function NodePreview({preview}){
  if(!preview)return null;
  const object=preview.object;
  return <aside className="node-preview" role="tooltip" style={{left:preview.x,top:preview.y,width:preview.width,maxHeight:preview.height}} data-side={preview.side}><small>{object.kind} · {object.status}</small><b>{object.title}</b>{object.summary&&<span>{object.summary}</span>}</aside>;
}
function RoutedEdge(props){
  const points=props.data?.points||[];
  const source={x:props.sourceX,y:props.sourceY},target={x:props.targetX,y:props.targetY};
  const routeIsCurrent=routeMatchesEndpoints(points,source,target);
  const path=routeIsCurrent?roundedOrthogonalPath(points,10)
    :getSmoothStepPath({...props,borderRadius:10})[0];
  const middle=routeIsCurrent?(props.data?.labelPoint||pathMidpoint(points))
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
function Breadcrumbs({title,focusPath,selectedEntity,onOverview,onGroup}){
  const trail=[{id:'overview',title:'Overview',kind:'overview'},...focusPath];
  if(selectedEntity&&!trail.some(entry=>entry.id===selectedEntity.id))trail.push(selectedEntity);
  const current=trail.at(-1),hidden=trail.slice(0,-1);
  const activate=entry=>entry.kind==='overview'?onOverview():entry.entityType==='group'||entry.grouping?onGroup(entry.id):null;
  return <nav className="breadcrumbs" aria-label="Breadcrumb"><a href="constellation.html" aria-label="Back to constellation">Vizzer</a><span>/</span>
    {hidden.length>0&&<details className="breadcrumb-overflow" aria-label="Breadcrumb path"><summary aria-label="Show collapsed breadcrumb path">…</summary><div>{hidden.map(entry=><button type="button" key={entry.id} onClick={()=>activate(entry)}>{entry.title}</button>)}</div></details>}
    {trail.map((entry,index)=><React.Fragment key={entry.id}>{index>0&&<span className="breadcrumb-separator">/</span>}<button type="button" className={entry.id===current.id?'breadcrumb-current':'breadcrumb-intermediate'} onClick={()=>activate(entry)} disabled={entry.id===current.id&&entry.kind!=='overview'}>{entry.title}</button></React.Fragment>)}
    <small>{title}</small>
  </nav>;
}
function groupDossierEntity(group,projected,groupById){
  if(!group)return null;
  const statusCounts=projected.groupStatusCounts.get(group.id)||{};
  const count=projected.groupCounts.get(group.id)||0;
  const parent=group.parentId?groupById.get(group.parentId):null;
  return {...group,entityType:'group',status:'group',statusCounts,count,
    summary:group.summary||`${count.toLocaleString()} descendant objects.`,
    details:{...(group.details||{}),objectCount:count,parent:parent?.title||''},
    detail:group.detail||{schema:'vizzer-object-detail/v1',sections:{},relationships:{dependsOn:[],typed:[]}}};
}
function Dossier({entity,onClose,onFocusEntity,focused,annotations=[]}){
  if(!entity)return <aside className="dossier" aria-hidden="true"/>;
  const detail=entity.detail||{},sections=detail.sections||{};
  const details=Object.entries(entity.details||{}).filter(([,value])=>value!==''&&value!=null);
  const objectNotes=annotations.filter(item=>item.kind==='note'&&item.objectId===entity.id);
  const isGroup=entity.entityType==='group';
  const roles=['blocked','active','ready','shipped'];
  return <aside className="dossier open" aria-label={`${entity.title} details`}><header><div><small>{entity.kind}{isGroup?' group':''}</small><h2>{entity.title}</h2></div><button type="button" onClick={onClose} aria-label="Close details">×</button></header>
    <div className="dossier-body">{isGroup?<span className="group-detail-count">{entity.count.toLocaleString()} objects</span>:<span className={`status-pill status-${entity.status}`}>{entity.status}</span>}<button type="button" className="focus-neighborhood" aria-pressed={focused} onClick={()=>onFocusEntity(entity)}>{focused?(isGroup?'Showing this group':'Showing functional neighborhood'):(isGroup?'Focus this group':'Focus related objects')}</button>
      {isGroup&&<span className="status-composition dossier-composition" aria-label="Subcomponent status">{roles.filter(role=>entity.statusCounts[role]).map(role=><i className={`role-${role}`} key={role}>{entity.statusCounts[role]} {role}</i>)}</span>}
      {entity.summary&&<p className="summary">{entity.summary}</p>}
      {entity.failure&&<section className="failure-detail"><h3>Work failure</h3><p>{entity.failure.message}</p><small>{entity.failure.source} · {entity.failure.at} · {entity.failure.provenance.source}</small></section>}
      <div data-detail-schema={detail.schema||'unknown'}>
        <DetailSection title="Review steps" value={sections.reviewSteps} empty="No review steps available for this object."/>
        <DetailSection title="Acceptance" value={sections.acceptance} empty="No acceptance criteria available for this object."/>
        <DetailSection title="Definition of done" value={sections.definitionOfDone} empty="No Definition of Done available for this object."/>
      </div>
      <h3>Core details</h3><dl>{details.map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd>{Array.isArray(value)?value.join(', '):typeof value==='object'?JSON.stringify(value):String(value)}</dd></React.Fragment>)}</dl>
      <h3>Relationships</h3><dl><dt>depends on</dt><dd>{detail.relationships?.dependsOn?.join(', ')||'none declared'}</dd><dt>typed</dt><dd>{detail.relationships?.typed?.map(value=>`${value.kind}: ${value.target}`).join(', ')||'none declared'}</dd></dl>
      <h3>View annotations</h3>{objectNotes.length?<ul className="object-annotations">{objectNotes.map(note=><li key={note.id}>{note.text}</li>)}</ul>:<p className="detail-empty">No saved-view notes are attached to this object.</p>}
      <h3>Provenance</h3><dl>{Object.entries(entity.provenance||{}).map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd>{value}</dd></React.Fragment>)}</dl>
      <a className="constellation-detail-link" href={`constellation.html#${isGroup?'group':'story'}/${encodeURIComponent(entity.id)}`}>Open in Constellation</a>
    </div></aside>;
}

function AnnotationLayer({annotations,draft,selectedId,onSelect}){
  const strokes=[...annotations.filter(item=>item.kind==='stroke'),...(draft?[draft]:[])];
  return <ViewportPortal>
    <svg className="sketch-layer" aria-hidden="true">{strokes.map(stroke=><path key={stroke.id} d={annotationPath(stroke.points)} data-color={stroke.color} style={{strokeWidth:stroke.width}}/>)}</svg>
    {annotations.filter(item=>item.kind==='note').map(note=><button key={note.id} type="button" className={`canvas-note${selectedId===note.id?' selected':''}`} data-color={note.color} style={{left:note.x,top:note.y}} onClick={event=>{event.stopPropagation();onSelect(note.id);}}><span>{note.text}</span>{note.objectId&&<small>{note.objectId}</small>}</button>)}
  </ViewportPortal>;
}

function AnnotationPanel({open,notes,onNotes,annotations,selectedId,onSelect,onUpdate,onDelete,onClear,onClose}){
  if(!open)return null;
  const selected=annotations.find(item=>item.id===selectedId)||null;
  return <aside className="annotation-panel" aria-label="View notes and annotations"><header><div><small>Saved view</small><h2>Notes & annotations</h2></div><button type="button" onClick={onClose} aria-label="Close annotations">×</button></header>
    <label><span>View notes</span><textarea value={notes} onChange={event=>onNotes(event.target.value)} maxLength="20000" rows="5" placeholder="Context, review notes, decisions, or follow-ups…"/></label>
    <section><header><h3>Canvas annotations</h3><button type="button" onClick={onClear} disabled={!annotations.length}>Clear all</button></header>
      {annotations.length?<ul>{annotations.map(item=><li key={item.id}><button type="button" className={selectedId===item.id?'selected':''} onClick={()=>onSelect(item.id)}>{item.kind==='note'?item.text:`Sketch · ${item.points.length} points`}</button></li>)}</ul>:<p>No notes or sketches on this view.</p>}
    </section>
    {selected?.kind==='note'&&<label><span>Selected note</span><textarea value={selected.text} onChange={event=>onUpdate({...selected,text:event.target.value.slice(0,2000)})} maxLength="2000" rows="4"/><button type="button" className="delete-annotation" onClick={()=>onDelete(selected.id)}>Delete note</button></label>}
    {selected?.kind==='stroke'&&<button type="button" className="delete-annotation" onClick={()=>onDelete(selected.id)}>Delete selected sketch</button>}
  </aside>;
}

function DeveloperFlow(){
  const {fitView,getViewport,screenToFlowPosition,setViewport}=useReactFlow();
  const [data,setData]=useState(INITIAL_DATA);
  const served=data.delivery?.mode==='served';
  const viewService=/^https?:$/.test(globalThis.location?.protocol||'');
  const unstableHttpOrigin=viewService
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
    try{return normalizeViewDocuments(JSON.parse(localStorage.getItem(savedKey)||'[]'));}catch(_){return [];}
  });
  const [viewStoreRevision,setViewStoreRevision]=useState(0);
  const [viewCsrf,setViewCsrf]=useState('');
  const [activeViewId,setActiveViewId]=useState('');
  const [sharedViewId,setSharedViewId]=useState(()=>new URLSearchParams(globalThis.location?.search||'').get('saved')||'');
  const [saveName,setSaveName]=useState('');
  const [viewStatus,setViewStatus]=useState('');
  const [viewNotes,setViewNotes]=useState('');
  const [annotationState,dispatchAnnotations]=useReducer(annotationHistoryReducer,[],annotationHistory);
  const annotations=annotationState.present;
  const [annotationsVisible,setAnnotationsVisible]=useState(true);
  const [exportAnnotations,setExportAnnotations]=useState(true);
  const [annotationMode,setAnnotationMode]=useState('none');
  const [annotationColor,setAnnotationColor]=useState('yellow');
  const [annotationPanelOpen,setAnnotationPanelOpen]=useState(false);
  const [selectedAnnotationId,setSelectedAnnotationId]=useState('');
  const [nodePreview,setNodePreview]=useState(null);
  const [draftStroke,setDraftStroke]=useState(null);
  const draftStrokeRef=useRef(null);
  const annotationCaptureRef=useRef(null);
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
  const selectObject=useCallback(id=>{
    setAnnotationPanelOpen(false);setNodePreview(null);setSelectedId(id);
  },[]);
  const previewObject=useCallback((id,anchor)=>{
    if(!id||!anchor){setNodePreview(null);return;}
    const object=objectById.get(id),stage=document.querySelector('.flowstage');
    if(!object||!stage){setNodePreview(null);return;}
    const boundary=stage.getBoundingClientRect();
    const obstacles=[...document.querySelectorAll('.react-flow__controls,.react-flow__minimap,.stats,.layout-state')]
      .filter(element=>getComputedStyle(element).display!=='none')
      .map(element=>element.getBoundingClientRect());
    setNodePreview({object,...placeOverlay(anchor,{width:280,height:160},boundary,obstacles)});
  },[objectById]);
  useEffect(()=>{
    let live=true;setLayout(current=>({...current,busy:true,error:'',stats:projected.stats}));
    elk.layout(buildElkGraph(projected,collapsed,expanded,direction)).then(result=>{
      if(!live)return;
      const flat=flattenLayout(result,projected,collapsed,expanded,selectedId,toggleGroup,toggleExpanded,selectObject,previewObject);
      setLayout({...flat,busy:false,error:'',stats:projected.stats});
    }).catch(error=>live&&setLayout(current=>({...current,busy:false,error:String(error)})));
    return()=>{live=false;};
  },[projected,collapsed,expanded,selectedId,direction,toggleGroup,toggleExpanded,selectObject,previewObject]);
  useEffect(()=>{
    if(!fitRequested||layout.busy||layout.error||!layout.nodes.length)return;
    let depth=0,cursor=focusGroupId;while(cursor){depth++;cursor=groupById.get(cursor)?.parentId||null;}
    const minZoom=focusObjectId ? .62 : depth>1 ? .44 : depth===1 ? .24 : .04;
    const frame=requestAnimationFrame(()=>{fitView({padding:.14,duration:240,minZoom,maxZoom:1.05});setFitRequested(false);});
    return()=>cancelAnimationFrame(frame);
  },[fitRequested,layout.busy,layout.error,layout.nodes,fitView,focusGroupId,focusObjectId,groupById]);
  const selectedObject=objectById.get(selectedId)||null;
  const selectedGroup=groupById.get(selectedId)||null;
  const selectedEntity=selectedObject?{...selectedObject,entityType:'object'}
    :groupDossierEntity(selectedGroup,projected,groupById);
  const breadcrumbGroupId=focusGroupId||selectedObject?.groupId||selectedGroup?.parentId||null;
  const focusPath=breadcrumbGroupId?[...groupMaps(data).ancestors(breadcrumbGroupId)].reverse().map(id=>groupById.get(id)).filter(Boolean):[];
  const lod=zoom<.2?'overview':zoom<.42?'glyph':zoom<.78?'compact':'summary';
  const currentScope=focusObjectId?{scope:'object',id:focusObjectId}
    :focusGroupId?{scope:'group',id:focusGroupId}
      :collapsed.size===allGroupIds.length?{scope:'overview',id:''}:{scope:'all',id:''};
  const currentView=normalizeViewState({
    ...currentScope,direction,selectedId:selectedId||'',filters,
  });
  const activeSavedView=savedViews.find(saved=>saved.id===activeViewId)||null;
  const viewIsDirty=Boolean(activeSavedView)&&JSON.stringify({
    name:saveName.trim(),view:currentView,notes:viewNotes,annotations,annotationsVisible,
  })!==JSON.stringify({
    name:activeSavedView.name,view:activeSavedView.view,
    notes:activeSavedView.notes,annotations:activeSavedView.annotations,
    annotationsVisible:activeSavedView.annotationsVisible,
  });
  useEffect(()=>{
    const search=encodeViewState(currentView);
    const params=new URLSearchParams(search);
    if(sharedViewId)params.set('saved',sharedViewId);
    const nextSearch=`?${params}`;
    if(globalThis.history?.replaceState&&globalThis.location?.search!==nextSearch)
      history.replaceState(null,'',`${location.pathname}${nextSearch}${location.hash||''}`);
  },[currentView.scope,currentView.id,currentView.direction,currentView.selectedId,
    currentView.filters.query,currentView.filters.kind,currentView.filters.status,
    currentView.filters.group,currentView.filters.relationKinds.join('\u0000'),sharedViewId]);
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
  const focusGroup=id=>{
    requestFit();setSelectedId(id);setFocusGroupId(id);setFocusObjectId(null);setExpanded(new Set());
    if(served)fetchSlice({kind:'group',id},filters).then(result=>{
      if(!result)return;const nextGroups=new Map(result.groups.map(group=>[group.id,group]));
      const closed=new Set(result.groups.map(group=>group.id));let cursor=id;
      while(cursor){closed.delete(cursor);cursor=nextGroups.get(cursor)?.parentId||null;}
      setCollapsed(closed);setSelectedId(id);setFitRequested(true);
    }).catch(error=>setLayout(current=>({...current,busy:false,error:String(error)})));
    else{const closed=new Set(allGroupIds);let cursor=id;
      while(cursor){closed.delete(cursor);cursor=groupById.get(cursor)?.parentId||null;}
      setCollapsed(closed);}
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
  const markViewDirty=useCallback(()=>setViewStatus(activeViewId?'Unsaved view changes':'Save this view to keep notes and sketches'),[activeViewId]);
  const applyDocument=document=>{
    const normalized=normalizeViewDocument(document);if(!normalized)return;
    applyView(normalized.view);setActiveViewId(normalized.id);setSharedViewId(normalized.id);setSaveName(normalized.name);
    setViewNotes(normalized.notes);dispatchAnnotations({type:'reset',value:normalized.annotations});
    setAnnotationsVisible(normalized.annotationsVisible);setExportAnnotations(normalized.annotationsVisible);
    setSelectedAnnotationId('');setViewStatus(`Opened ${normalized.name}`);
  };
  useEffect(()=>{
    if(!viewService)return;
    let live=true;
    fetch('/api/developer-flow/views').then(async response=>{
      const body=await response.json();if(!response.ok)throw new Error(body.error||'Could not load saved views');
      if(!live)return;const documents=normalizeViewDocuments(body.views);
      setSavedViews(documents);setViewStoreRevision(body.revision);setViewCsrf(body.csrfToken||'');
      const requested=sharedViewId;
      const shared=documents.find(document=>document.id===requested);
      if(shared)applyDocument(shared);
      else if(requested){setSharedViewId('');setViewStatus('The shared saved view is unavailable');}
    }).catch(error=>live&&setViewStatus(String(error.message||error)));
    return()=>{live=false;};
  },[viewService]);
  const saveView=async()=>{
    const name=saveName.trim();if(!name)return;
    const prior=savedViews.find(saved=>saved.name===name);
    const id=activeViewId||prior?.id||newViewId();
    const entry=normalizeViewDocument({schema:1,id,name:name.slice(0,80),view:currentView,notes:viewNotes,annotations,annotationsVisible});
    if(!entry)return;
    if(viewService){
      try{
        const response=await fetch('/api/developer-flow/views',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':viewCsrf},body:JSON.stringify({action:'upsert',expectedRevision:viewStoreRevision,view:entry})});
        const body=await response.json();if(!response.ok)throw new Error(body.error||'Could not save view');
        const documents=normalizeViewDocuments(body.views);setSavedViews(documents);
        setViewStoreRevision(body.revision);setActiveViewId(id);setSharedViewId(id);setViewStatus('View, notes, and annotations saved');
      }catch(error){setViewStatus(String(error.message||error));}
      return;
    }
    const next=normalizeViewDocuments([entry,...savedViews.filter(saved=>saved.id!==entry.id)]);
    setSavedViews(next);setActiveViewId(id);setSharedViewId(id);
    try{
      localStorage.setItem(savedKey,JSON.stringify(next));
      setViewStatus(unstableHttpOrigin
        ? 'View saved for this server origin; set server.port to keep it across restarts'
        : 'View saved');
    }
    catch(_){setViewStatus('Saved for this tab; browser storage is unavailable');}
  };
  const newView=()=>{setActiveViewId('');setSharedViewId('');setSaveName('');setViewNotes('');dispatchAnnotations({type:'reset',value:[]});setAnnotationsVisible(true);setExportAnnotations(true);setSelectedAnnotationId('');setViewStatus('New unsaved view');};
  const deleteView=async()=>{
    if(!activeViewId)return;
    if(viewService){
      try{
        const response=await fetch('/api/developer-flow/views',{method:'POST',headers:{'Content-Type':'application/json','X-Vizzer-CSRF':viewCsrf},body:JSON.stringify({action:'delete',expectedRevision:viewStoreRevision,id:activeViewId})});
        const body=await response.json();if(!response.ok)throw new Error(body.error||'Could not delete view');
        setSavedViews(normalizeViewDocuments(body.views));setViewStoreRevision(body.revision);newView();
      }catch(error){setViewStatus(String(error.message||error));}
      return;
    }
    const next=savedViews.filter(saved=>saved.id!==activeViewId);setSavedViews(next);
    try{localStorage.setItem(savedKey,JSON.stringify(next));}catch(_){}newView();
  };
  const shareView=async()=>{
    if((viewNotes||annotations.length)&&!viewService){setViewStatus('Serve Vizzer and save this view before sharing its notes or sketches');return;}
    if((viewNotes||annotations.length)&&!activeViewId){setViewStatus('Save the view before sharing its notes or sketches');return;}
    if(activeViewId&&viewIsDirty){setViewStatus('Save the latest view changes before sharing');return;}
    const urlObject=new URL(encodeViewState(currentView),location.href);
    if(viewService&&activeViewId)urlObject.searchParams.set('saved',activeViewId);
    const url=urlObject.href;
    try{
      await navigator.clipboard.writeText(url);
      setViewStatus(unstableHttpOrigin
        ? 'Link copied; set server.port for a restart-stable URL'
        : 'Link copied');
    }
    catch(_){setViewStatus(url);}
  };
  const exportSvg=()=>{
    const svg=developerFlowSvg({title:data.title,nodes:layout.nodes,edges:layout.edges,annotations,
      includeAnnotations:exportAnnotations,lod,exportedAt:new Date().toISOString()});
    try{
      const result=triggerSvgDownload(svg,svgFilename(data.title,currentView.scope));
      setViewStatus(`Downloaded ${result.filename} ${exportAnnotations?'with':'without'} notes & sketches`);
    }catch(error){setViewStatus(String(error.message||error));}
  };
  const updateAnnotations=next=>{dispatchAnnotations({type:'commit',value:next});markViewDirty();};
  const toggleAnnotationVisibility=()=>setAnnotationsVisible(current=>{
    const next=!current;setExportAnnotations(next);markViewDirty();return next;
  });
  const toggleAnnotationMode=mode=>{
    if(!annotationsVisible){setAnnotationsVisible(true);markViewDirty();}
    setAnnotationMode(current=>current===mode?'none':mode);
  };
  const updateAnnotation=next=>updateAnnotations(annotations.map(item=>item.id===next.id?next:item));
  const deleteAnnotation=id=>{updateAnnotations(annotations.filter(item=>item.id!==id));setSelectedAnnotationId('');};
  const undoAnnotations=useCallback(()=>{
    if(!annotationState.past.length)return;
    dispatchAnnotations({type:'undo'});setSelectedAnnotationId('');markViewDirty();
  },[annotationState.past.length,markViewDirty]);
  const redoAnnotations=useCallback(()=>{
    if(!annotationState.future.length)return;
    dispatchAnnotations({type:'redo'});setSelectedAnnotationId('');markViewDirty();
  },[annotationState.future.length,markViewDirty]);
  useEffect(()=>{
    const onKeyDown=event=>{
      const target=event.target;
      if(target?.matches?.('input,textarea,select,[contenteditable=true]'))return;
      if(!(event.metaKey||event.ctrlKey)||event.altKey||event.key.toLowerCase()!=='z')return;
      event.preventDefault();event.shiftKey?redoAnnotations():undoAnnotations();
    };
    globalThis.addEventListener('keydown',onKeyDown);
    return()=>globalThis.removeEventListener('keydown',onKeyDown);
  },[undoAnnotations,redoAnnotations]);
  useEffect(()=>{
    const capture=annotationCaptureRef.current;
    if(!capture)return;
    const navigate=event=>{
      event.preventDefault();event.stopPropagation();
      const current=getViewport(),bounds=capture.getBoundingClientRect();
      if(event.ctrlKey){
        const nextZoom=Math.min(2.2,Math.max(.04,current.zoom*Math.exp(-event.deltaY*.01)));
        const screenX=event.clientX-bounds.left,screenY=event.clientY-bounds.top;
        const flowX=(screenX-current.x)/current.zoom,flowY=(screenY-current.y)/current.zoom;
        setViewport({x:screenX-flowX*nextZoom,y:screenY-flowY*nextZoom,zoom:nextZoom});
      }else setViewport({x:current.x-event.deltaX*.7,y:current.y-event.deltaY*.7,zoom:current.zoom});
    };
    capture.addEventListener('wheel',navigate,{passive:false});
    return()=>capture.removeEventListener('wheel',navigate);
  },[annotationMode,getViewport,setViewport]);
  const flowPoint=event=>screenToFlowPosition({x:event.clientX,y:event.clientY});
  const annotationPointerDown=event=>{
    if(event.button!==0)return;event.preventDefault();
    const point=flowPoint(event);
    if(annotationMode==='note'){
      const note={id:newViewId('note'),kind:'note',color:annotationColor,x:point.x,y:point.y,text:'New note',...(selectedId?{objectId:selectedId}:{})};
      updateAnnotations([...annotations,note]);setSelectedAnnotationId(note.id);setSelectedId(null);setAnnotationPanelOpen(true);setAnnotationMode('none');return;
    }
    if(annotationMode==='draw'){
      const stroke={id:newViewId('stroke'),kind:'stroke',color:annotationColor,width:4,points:[[point.x,point.y]]};
      draftStrokeRef.current=stroke;setDraftStroke(stroke);event.currentTarget.setPointerCapture(event.pointerId);
    }
  };
  const annotationPointerMove=event=>{
    const current=draftStrokeRef.current;if(!current||annotationMode!=='draw')return;
    const point=flowPoint(event),last=current.points.at(-1);
    if((point.x-last[0])**2+(point.y-last[1])**2<4||current.points.length>=4096)return;
    const next={...current,points:[...current.points,[point.x,point.y]]};draftStrokeRef.current=next;setDraftStroke(next);
  };
  const finishStroke=()=>{
    const current=draftStrokeRef.current;draftStrokeRef.current=null;setDraftStroke(null);
    if(current?.points.length>1){updateAnnotations([...annotations,current]);setSelectedAnnotationId(current.id);}
  };
  const toggleAnnotationPanel=()=>setAnnotationPanelOpen(open=>{
    const next=!open;
    if(next){setSelectedId(null);setNodePreview(null);}
    return next;
  });
  return <main className={`developer-shell${selectedEntity||annotationPanelOpen?' has-sidebar':''}`} data-lod={lod}>
    <header className="appbar"><Breadcrumbs title={data.title} focusPath={focusPath} selectedEntity={selectedEntity} onOverview={showOverview} onGroup={focusGroup}/>
      <div className="view-actions"><select aria-label="Saved Developer Flow views" defaultValue="" onChange={event=>{const saved=savedViews.find(view=>view.id===event.target.value);if(saved)applyDocument(saved);event.target.value='';}}><option value="">Saved / bookmarked views</option>{savedViews.map(saved=><option value={saved.id} key={saved.id}>{saved.name}</option>)}</select><input aria-label="Saved view name" value={saveName} onChange={event=>setSaveName(event.target.value)} placeholder="View name" maxLength="80"/><button type="button" onClick={saveView} disabled={!saveName.trim()}>Save</button><button type="button" onClick={newView}>New</button><button type="button" onClick={deleteView} disabled={!activeViewId}>Delete</button><button type="button" onClick={shareView}>Share link</button><label className="export-option"><input type="checkbox" checked={exportAnnotations} onChange={event=>setExportAnnotations(event.target.checked)} aria-label="Include notes and sketches in SVG export"/><span>Markup</span></label><button type="button" onClick={exportSvg} disabled={!layout.nodes.length}>Export SVG</button><span role="status">{viewStatus}</span></div>
      <div className="orientation" role="group" aria-label="Layout direction"><button aria-pressed={direction==='RIGHT'} onClick={()=>{requestFit();setDirection('RIGHT');}}>→</button><button aria-pressed={direction==='DOWN'} onClick={()=>{requestFit();setDirection('DOWN');}}>↓</button></div>
    </header>
    <section className="filterbar" aria-label="Developer graph filters">
      <input type="search" value={filters.query} onChange={event=>setFilter('query',event.target.value)} placeholder="Filter objects…" aria-label="Filter objects"/>
      <select value={filters.kind} onChange={event=>setFilter('kind',event.target.value)} aria-label="Object kind"><option value="">All object kinds</option>{kinds.map(kind=><option key={kind}>{kind}</option>)}</select>
      <select value={filters.status} onChange={event=>setFilter('status',event.target.value)} aria-label="Status"><option value="">All statuses</option>{statuses.map(status=><option key={status}>{status}</option>)}</select>
      <select value={filters.group} onChange={event=>setFilter('group',event.target.value)} aria-label="Group"><option value="">All groups</option>{data.groups.map(group=><option key={group.id} value={group.id}>{group.title}</option>)}</select>
      <select value={filters.relationKinds[0]||''} onChange={event=>setFilter('relationKinds',event.target.value?[event.target.value]:[])} aria-label="Relationship kind"><option value="">All relationships</option>{relationKinds.map(kind=><option key={kind}>{kind}</option>)}</select>
      <button type="button" onClick={showOverview}>Overview</button>{!served&&<button type="button" onClick={showDetails}>Expand frames</button>}<button type="button" onClick={clearFilters}>Clear</button><span className="annotation-tools" role="group" aria-label="Annotation tools"><button type="button" aria-pressed={annotationMode==='note'} onClick={()=>toggleAnnotationMode('note')}>Add note</button><button type="button" aria-pressed={annotationMode==='draw'} onClick={()=>toggleAnnotationMode('draw')}>Sketch</button><select value={annotationColor} onChange={event=>setAnnotationColor(event.target.value)} aria-label="Annotation color"><option value="yellow">Yellow</option><option value="blue">Blue</option><option value="pink">Pink</option><option value="green">Green</option><option value="white">White</option></select><button type="button" aria-pressed={annotationsVisible} onClick={toggleAnnotationVisibility}>{annotationsVisible?'Hide notes & sketches':'Show notes & sketches'}</button><button type="button" onClick={undoAnnotations} disabled={!annotationState.past.length} aria-label="Undo annotation">Undo</button><button type="button" onClick={redoAnnotations} disabled={!annotationState.future.length} aria-label="Redo annotation">Redo</button><button type="button" aria-pressed={annotationPanelOpen} onClick={toggleAnnotationPanel}>Notes ({annotations.length})</button></span>
    </section>
    <section className="flowstage">
      <ReactFlow nodes={layout.nodes} edges={layout.edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView minZoom={.04} maxZoom={2.2} panOnDrag panOnScroll panOnScrollSpeed={.7} zoomOnScroll={false} zoomOnPinch preventScrolling onlyRenderVisibleElements nodesDraggable={false} nodesConnectable={false} onMove={(_event,viewport)=>setZoom(viewport.zoom)} onNodeClick={(_event,node)=>{if(node.type==='objectCard'||node.type==='groupFrame')selectObject(node.id);}} proOptions={{hideAttribution:false}}>
        <svg aria-hidden="true"><defs><marker id="developer-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z"/></marker></defs></svg>
        {annotationsVisible&&<AnnotationLayer annotations={annotations} draft={draftStroke} selectedId={selectedAnnotationId} onSelect={id=>{setSelectedAnnotationId(id);setSelectedId(null);setAnnotationPanelOpen(true);}}/>}
        <Background gap={28} size={1}/><Controls/><MiniMap pannable zoomable nodeStrokeWidth={2}/>
        <Panel position="bottom-center" className="stats" aria-live="polite">{layout.stats&&<><b>{layout.stats.mounted.toLocaleString()}</b> cards{layout.stats.boundaryMounted?` · ${layout.stats.boundaryMounted.toLocaleString()} external`:''} · {layout.nodes.filter(node=>node.type==='groupFrame').length.toLocaleString()} frames · {layout.stats.matched.toLocaleString()} matched · {layout.stats.source.toLocaleString()} source{layout.stats.omitted?` · ${layout.stats.omitted.toLocaleString()} objects omitted; narrow filters`:''}{layout.stats.boundaryOmitted?` · ${layout.stats.boundaryOmitted.toLocaleString()} external objects omitted`:''}{layout.stats.relationOmitted?` · ${layout.stats.relationOmitted.toLocaleString()} relations omitted`:''}{layout.stats.collapsed?` · ${layout.stats.collapsed.toLocaleString()} summarized`:''} · {lod}</>}</Panel>
      </ReactFlow>
      {annotationMode!=='none'&&<div ref={annotationCaptureRef} className={`annotation-capture mode-${annotationMode}`} onPointerDown={annotationPointerDown} onPointerMove={annotationPointerMove} onPointerUp={finishStroke} onPointerCancel={finishStroke} aria-label={annotationMode==='draw'?'Sketch on flow':'Place a note on flow'}/>}
      {layout.busy&&<div className="layout-state" role="status">Routing objects and relationships…</div>}
      {layout.error&&<div className="layout-state error" role="alert"><b>Layout failed</b><pre>{layout.error}</pre></div>}
    </section>
    <NodePreview preview={nodePreview}/>
    {annotationPanelOpen
      ?<AnnotationPanel open notes={viewNotes} onNotes={value=>{setViewNotes(value);markViewDirty();}} annotations={annotations} selectedId={selectedAnnotationId} onSelect={setSelectedAnnotationId} onUpdate={updateAnnotation} onDelete={deleteAnnotation} onClear={()=>{updateAnnotations([]);setSelectedAnnotationId('');}} onClose={()=>setAnnotationPanelOpen(false)}/>
      :<Dossier entity={selectedEntity} onClose={()=>setSelectedId(null)} onFocusEntity={entity=>entity.entityType==='group'?focusGroup(entity.id):focusObject(entity.id)} focused={selectedEntity?.entityType==='group'?focusGroupId===selectedId:focusObjectId===selectedId} annotations={annotations}/>}
  </main>;
}

createRoot(document.getElementById('root')).render(<ReactFlowProvider><DeveloperFlow/></ReactFlowProvider>);
