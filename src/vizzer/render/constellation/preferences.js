// Theme belongs to the local UI, not to a project or its delivery state.
const themeStorageKey='vizzer:color-mode';
const themeChoice=document.getElementById('themechoice');
function applyColorMode(mode,{persist=false}={}){
  mode=['light','dark','system'].includes(mode)?mode:'system';
  if(mode==='system')document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme',mode);
  themeChoice?.querySelectorAll('[data-theme-choice]').forEach(button=>{
    const active=button.dataset.themeChoice===mode;
    button.setAttribute('aria-pressed',String(active));button.classList.toggle('on',active);
  });
  recolor();
  if(persist){try{localStorage.setItem(themeStorageKey,mode);}catch(_){}}
}
let storedColorMode='system';try{storedColorMode=localStorage.getItem(themeStorageKey)||'system';}catch(_){}
applyColorMode(storedColorMode);
themeChoice?.querySelectorAll('[data-theme-choice]').forEach(button=>button.addEventListener('click',()=>applyColorMode(button.dataset.themeChoice,{persist:true})));

// ---- title-bar reading preferences and left-sidebar geometry ----
const sidebarTypeControl=document.getElementById('sidebartype');
const sidebarTypeSizes=[12,14,16];
const sidebarTypeStorageKey=`vizzer:sidebar-type-px:${document.title}`;
function applySidebarTypeSize(value,{persist=false}={}){
  const parsed=Number(value),size=sidebarTypeSizes.includes(parsed)?parsed:12;
  document.documentElement.style.setProperty('--sidebar-type-size',`${size}px`);
  sidebarTypeControl?.querySelectorAll('[data-sidebar-size]').forEach(button=>{
    const active=Number(button.dataset.sidebarSize)===size;
    button.classList.toggle('on',active);button.setAttribute('aria-pressed',String(active));
  });
  if(persist){try{sessionStorage.setItem(sidebarTypeStorageKey,String(size));}catch(_){}}
}
let storedSidebarType=null;try{storedSidebarType=sessionStorage.getItem(sidebarTypeStorageKey);}catch(_){}
applySidebarTypeSize(storedSidebarType);
sidebarTypeControl?.querySelectorAll('[data-sidebar-size]').forEach(button=>button.onclick=()=>applySidebarTypeSize(button.dataset.sidebarSize,{persist:true}));

const railResize=document.getElementById('railresize'),railElement=document.getElementById('rail');
const RAIL_MIN=180,RAIL_MAX=420,RAIL_COMPACT=760;
const railStorageKey=`vizzer:rail-width:${document.title}`;
let railWidth=236,railResizeState=null;
function railWidthBounds(){return{min:RAIL_MIN,max:Math.max(RAIL_MIN,Math.min(RAIL_MAX,innerWidth-340))};}
function applyRailWidth(value,{persist=false}={}){
  const bounds=railWidthBounds(),parsed=Number(value);
  railWidth=Math.round(Math.max(bounds.min,Math.min(bounds.max,Number.isFinite(parsed)?parsed:236)));
  document.documentElement.style.setProperty('--rail-width',`${railWidth}px`);
  railResize?.setAttribute('aria-valuemin',String(bounds.min));railResize?.setAttribute('aria-valuemax',String(bounds.max));railResize?.setAttribute('aria-valuenow',String(railWidth));
  if(persist){try{sessionStorage.setItem(railStorageKey,String(railWidth));}catch(_){}}
}
let storedRailWidth=null;try{storedRailWidth=sessionStorage.getItem(railStorageKey);}catch(_){}
applyRailWidth(storedRailWidth);
railResize?.addEventListener('pointerdown',event=>{
  if(innerWidth<=RAIL_COMPACT)return;
  event.preventDefault();railResize.setPointerCapture(event.pointerId);
  railResizeState={pointerId:event.pointerId,startX:event.clientX,startWidth:railElement.getBoundingClientRect().width};
  railResize.classList.add('dragging');
});
railResize?.addEventListener('pointermove',event=>{
  if(!railResizeState||event.pointerId!==railResizeState.pointerId)return;
  applyRailWidth(railResizeState.startWidth+event.clientX-railResizeState.startX);
});
function finishRailResize(event){
  if(!railResizeState||event.pointerId!==railResizeState.pointerId)return;
  if(railResize.hasPointerCapture(event.pointerId))railResize.releasePointerCapture(event.pointerId);
  railResizeState=null;railResize.classList.remove('dragging');applyRailWidth(railWidth,{persist:true});
}
railResize?.addEventListener('pointerup',finishRailResize);railResize?.addEventListener('pointercancel',finishRailResize);
railResize?.addEventListener('dblclick',()=>applyRailWidth(236,{persist:true}));
railResize?.addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','Home'].includes(event.key)||innerWidth<=RAIL_COMPACT)return;
  event.preventDefault();const step=event.shiftKey?48:16;
  applyRailWidth(event.key==='Home'?236:railWidth+(event.key==='ArrowLeft'?-step:step),{persist:true});
});
addEventListener('resize',()=>{if(innerWidth>RAIL_COMPACT)applyRailWidth(railWidth);});
