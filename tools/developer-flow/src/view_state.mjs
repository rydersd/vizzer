const SCHEMA='1';
const SCOPES=new Set(['overview','all','group','object']);
const DIRECTIONS=new Set(['RIGHT','DOWN']);

function bounded(value,maximum=500){
  return typeof value==='string'?value.slice(0,maximum):'';
}

export function normalizeViewState(value={}){
  const filters=value.filters||{};
  const scope=SCOPES.has(value.scope)?value.scope:'overview';
  const id=scope==='group'||scope==='object'?bounded(value.id):'';
  return {
    schema:1,
    scope:id?scope:(scope==='group'||scope==='object'?'overview':scope),
    id,
    direction:DIRECTIONS.has(value.direction)?value.direction:'RIGHT',
    selectedId:bounded(value.selectedId),
    filters:{
      query:bounded(filters.query),
      kind:bounded(filters.kind,120),
      status:bounded(filters.status,120),
      group:bounded(filters.group),
      relationKinds:Array.isArray(filters.relationKinds)
        ?[...new Set(filters.relationKinds.filter(entry=>typeof entry==='string'&&entry).map(entry=>entry.slice(0,120)))].sort().slice(0,16):[],
    },
  };
}

export function encodeViewState(value){
  const state=normalizeViewState(value),params=new URLSearchParams();
  params.set('v',SCHEMA);params.set('scope',state.scope);
  if(state.id)params.set('id',state.id);
  if(state.direction!=='RIGHT')params.set('direction',state.direction);
  if(state.selectedId)params.set('selected',state.selectedId);
  if(state.filters.query)params.set('q',state.filters.query);
  if(state.filters.kind)params.set('kind',state.filters.kind);
  if(state.filters.status)params.set('status',state.filters.status);
  if(state.filters.group)params.set('group',state.filters.group);
  for(const relation of state.filters.relationKinds)params.append('relation',relation);
  return `?${params.toString()}`;
}

export function decodeViewState(search=''){
  const params=new URLSearchParams(String(search).replace(/^\?/,''));
  if(params.get('v')!==SCHEMA)return normalizeViewState();
  return normalizeViewState({
    scope:params.get('scope')||'overview',id:params.get('id')||'',
    direction:params.get('direction')||'RIGHT',selectedId:params.get('selected')||'',
    filters:{
      query:params.get('q')||'',kind:params.get('kind')||'',
      status:params.get('status')||'',group:params.get('group')||'',
      relationKinds:params.getAll('relation'),
    },
  });
}

export function savedViewsStorageKey(title='',pathname=''){
  return `vizzer:developer-saved-views:v1:${bounded(pathname,1000)}:${bounded(title)}`;
}

export function normalizeSavedViews(value){
  if(!Array.isArray(value))return [];
  const names=new Set(),result=[];
  for(const entry of value){
    if(!entry||typeof entry!=='object'||typeof entry.name!=='string')continue;
    const name=entry.name.trim().slice(0,80);
    if(!name||names.has(name))continue;
    names.add(name);result.push({name,view:normalizeViewState(entry.view)});
    if(result.length===30)break;
  }
  return result;
}
