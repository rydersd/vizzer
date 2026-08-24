// Stable view-query algorithms over normalized ids and graph evidence.
globalThis.VizzerViewQuery=Object.freeze({
  rootGroupId(groupId,groups){
    const byId=groups instanceof Map?groups:new Map((groups||[]).map(group=>[group.id,group]));
    let current=groupId||'',last='',guard=0;
    while(current&&byId.has(current)&&guard++<100){
      last=current;current=byId.get(current).parent||byId.get(current).parentId||'';
    }
    return last;
  },
  dependencyOrder(indexes,nodes,edges){
    const visible=new Set(indexes),outgoing=new Map(),indegree=new Map(indexes.map(index=>[index,0]));
    for(const [prerequisite,dependent] of edges||[]){
      if(!visible.has(prerequisite)||!visible.has(dependent))continue;
      if(!outgoing.has(prerequisite))outgoing.set(prerequisite,[]);
      outgoing.get(prerequisite).push(dependent);
      indegree.set(dependent,(indegree.get(dependent)||0)+1);
    }
    const byId=(a,b)=>String(nodes[a]?.id||a).localeCompare(String(nodes[b]?.id||b));
    const ready=indexes.filter(index=>indegree.get(index)===0).sort(byId),ordered=[];
    while(ready.length){
      const index=ready.shift();ordered.push(index);
      for(const dependent of (outgoing.get(index)||[]).sort(byId)){
        indegree.set(dependent,indegree.get(dependent)-1);
        if(indegree.get(dependent)===0){ready.push(dependent);ready.sort(byId);}
      }
    }
    const emitted=new Set(ordered);
    return ordered.concat(indexes.filter(index=>!emitted.has(index)).sort(byId));
  },
  compareModified(a,b){
    return (b.node.ts||0)-(a.node.ts||0)
      ||String(a.node.id).localeCompare(String(b.node.id));
  },
});
