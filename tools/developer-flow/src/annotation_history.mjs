function sameAnnotations(first,second) {
  return JSON.stringify(first||[])===JSON.stringify(second||[]);
}

export function annotationHistory(initial=[]) {
  return {past:[],present:Array.isArray(initial)?initial:[],future:[]};
}

export function annotationHistoryReducer(state,action) {
  if(action.type==='reset')return annotationHistory(action.value);
  if(action.type==='commit'){
    const next=Array.isArray(action.value)?action.value:[];
    if(sameAnnotations(state.present,next))return state;
    return {past:[...state.past,state.present].slice(-100),present:next,future:[]};
  }
  if(action.type==='undo'&&state.past.length){
    return {past:state.past.slice(0,-1),present:state.past.at(-1),
      future:[state.present,...state.future].slice(0,100)};
  }
  if(action.type==='redo'&&state.future.length){
    return {past:[...state.past,state.present].slice(-100),present:state.future[0],
      future:state.future.slice(1)};
  }
  return state;
}
