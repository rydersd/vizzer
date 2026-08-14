import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from vizzer import __version__
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import (
    ActiveWork, Graph, Group, Item, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation, Relation,
)
from vizzer.render import render_all


_CONSTELLATION_COUNT_DOM_SHIM = r'''
const fs=require('fs'),vm=require('vm');
class ClassList{constructor(e){this.e=e;this.s=new Set()}sync(){this.e._className=[...this.s].join(' ')}add(...x){x.forEach(v=>this.s.add(v));this.sync()}remove(...x){x.forEach(v=>this.s.delete(v));this.sync()}toggle(x,f){const on=f===undefined?!this.s.has(x):!!f;on?this.s.add(x):this.s.delete(x);this.sync();return on}contains(x){return this.s.has(x)}replaceFrom(x){this.s=new Set(String(x).split(/\s+/).filter(Boolean));this.sync()}}
const ids=new Map(),desc=r=>r.children.flatMap(c=>[c,...desc(c)]);
class Element{constructor(tag='div',id=''){this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.parent=null;this.listeners={};this.attributes={};this.style={setProperty(k,v){this[k]=v}};this.classList=new ClassList(this);this._className='';this._innerHTML='';this.textContent='';this.value='';this.disabled=false;this.hidden=false;this.capturedPointers=new Set();if(id)ids.set(id,this)}set className(v){this.classList.replaceFrom(v)}get className(){return this._className}set innerHTML(v){this._innerHTML=String(v);if(this.id==='meterlab'){for(const id of ['shippedcount','defectcount','questionfilter','completioncount'])this.appendChild(new Element(id==='questionfilter'?'button':'span',id));const q=ids.get('questionfilter');q.className='questioncount';q.setAttribute('aria-pressed','false')}if(this._innerHTML.includes('class="caphead"')){const head=new Element('span');head.className='caphead';const count=new Element('span');count.className='capcount';head.appendChild(count);const bar=new Element('span');bar.className='capbar';bar.appendChild(new Element('i'));bar.appendChild(new Element('b'));this.appendChild(head);this.appendChild(bar)}}get innerHTML(){return this._innerHTML}setAttribute(k,v){this.attributes[k]=String(v)}getAttribute(k){return this.attributes[k]??null}removeAttribute(k){delete this.attributes[k]}addEventListener(k,f){(this.listeners[k]??=[]).push(f)}dispatch(k,e={}){if(this.disabled&&(k==='click'||k==='pointerup'))return;e.currentTarget=this;e.target=this;e.preventDefault??=()=>{};(this.listeners[k]||[]).forEach(f=>f(e));if(k==='click'&&this.onclick)this.onclick(e)}click(){this.dispatch('click')}appendChild(e){e.parent=this;this.children.push(e);return e}replaceChildren(...elements){this.children=[];elements.forEach(e=>this.appendChild(e))}cloneNode(){const e=new Element(this.tagName);e.className=this.className;return e}querySelector(s){if(s==='i'){let e=this.children.find(x=>x.tagName==='I');if(!e){e=new Element('i');this.appendChild(e)}return e}if(s==='.capcount')return desc(this).find(e=>e.classList.contains('capcount'))||null;if(s==='.caphead>span')return desc(this).find(e=>e.parent?.classList.contains('caphead')&&e.tagName==='SPAN')||null;if(s==='.capbar i')return desc(this).find(e=>e.parent?.classList.contains('capbar')&&e.tagName==='I')||null;if(s==='.capbar b')return desc(this).find(e=>e.parent?.classList.contains('capbar')&&e.tagName==='B')||null;return null}querySelectorAll(s){return s==='.cap'?desc(this).filter(e=>e.classList.contains('cap')):[]}contains(e){for(let p=e;p;p=p.parent)if(p===this)return true;return false}focus(){document.activeElement=this}getContext(){return ctx}getBoundingClientRect(){return this.id==='dossier'?{left:880,right:1200,top:106,bottom:800,width:320,height:694}:{left:0,right:0,top:0,bottom:0,width:0,height:0}}setPointerCapture(id){this.capturedPointers.add(id)}hasPointerCapture(id){return this.capturedPointers.has(id)}releasePointerCapture(id){this.capturedPointers.delete(id)}}
for(const id of ['meterfill','meterlab','search','searchinput','searchclear','searchcount','viewempty','viewpanel','viewmenu','exportmenu','chips','rail','dossier','dossierresize','dossieridentity','dbody','dossierfooter','close','tip','hint','bgcv','cv'])new Element(id==='cv'||id==='bgcv'?'canvas':'div',id);
const document={title:'fixture',documentElement:new Element('html'),activeElement:null,getElementById:id=>ids.get(id)||null,createElement:t=>new Element(t)};
const ctx=new Proxy({},{get:(o,k)=>o[k]??(()=>{}),set:(o,k,v)=>(o[k]=v,true)}),windowListeners={};
const sandbox={console,document,location:{protocol:'file:',hash:''},sessionStorage:{getItem(){return null},setItem(){}},window:null,innerWidth:1200,innerHeight:800,devicePixelRatio:1,performance:{now:()=>0},Date,Math,JSON,Map,Set,Boolean,String,Number,Object,Array,Promise,URL,Error,setTimeout,clearTimeout,addEventListener(k,f){(windowListeners[k]??=[]).push(f)},getComputedStyle(){return{getPropertyValue:()=>'#808080'}},matchMedia(){return{matches:true,addEventListener(){}}},requestAnimationFrame(f){sandbox.nextFrame=f},fetch(){throw new Error('unexpected fetch')}};sandbox.window=sandbox;sandbox.window.__vizzerBoot={ready(){}};sandbox.globalThis=sandbox;
const html=fs.readFileSync(0,'utf8'),scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);if(scripts.length!==2)throw new Error(`expected 2 scripts, got ${scripts.length}`);const cx=vm.createContext(sandbox);vm.runInContext(scripts[1],cx,{filename:'constellation.js',timeout:2000});const ev=s=>vm.runInContext(s,cx,{timeout:1000});
const dispatchWindow=(kind,event={})=>{event.target??=document.activeElement;event.defaultPrevented??=false;event.preventDefault??=()=>{event.defaultPrevented=true};(windowListeners[kind]||[]).forEach(listener=>listener(event));return event};
const snapshot=()=>{const cap=desc(ids.get('rail')).find(e=>e.classList.contains('cap'));return{shipped:ids.get('shippedcount').textContent,bugs:ids.get('defectcount').textContent,questions:ids.get('questionfilter').textContent,completion:ids.get('completioncount').textContent,items:ids.get('searchcount').textContent,capCount:cap.querySelector('.capcount').textContent,capShipped:cap.querySelector('.capbar i').style.width,capBugs:cap.querySelector('.capbar b').style.width,capLabel:cap.getAttribute('aria-label')}};
const panelSnapshot=()=>{const html=ids.get('viewpanel').innerHTML;return{cards:(html.match(/data-view-node=/g)||[]).length,metrics:[...html.matchAll(/<strong>(\d+)<\/strong>/g)].map(match=>+match[1]),rows:(html.match(/<tbody>[\s\S]*?<\/tbody>/)?.[0].match(/<tr>/g)||[]).length}};
const routeSnapshots=()=>Object.fromEntries(['dashboard','roadmap','structure','features','completion','workstreams','ledgers'].map(view=>{ev(`switchView('${view}')`);return[view,panelSnapshot()]}));
const out={initial:snapshot(),routes:routeSnapshots()};ev(`segBtns.R1.dispatch('pointerup')`);out.r0=snapshot();out.routesR0=routeSnapshots();ev(`(()=>{switchView('roadmap');searchInput.value='R0 bug';updateSearch();const q=DATA.questions[0];openNode(q.n);rx=.125;ry=.75;zoom=1.4;panX=31;panY=-19;cc={x:2,y:3,z:4};ct={x:5,y:6,z:7};questionContext={revision:0,questions:DATA.questions.slice(),decisions:[]};reconcileAcceptedDecisions([{question:{id:q.id},fingerprint:q.fingerprint,revision:1,answeredAt:'2026-08-10T20:00:00Z',answeredBy:'Ryder',kind:'option',optionId:'a',text:null}],1)})()`);out.reconcile={view:ev(`currentView`),selectedTitle:ev(`DATA.nodes[sel].t`),dossierOpen:ids.get('dossier').classList.contains('open'),dossierHidden:ids.get('dossier').getAttribute('aria-hidden'),search:ev(`searchInput.value`),r1:ev(`rfilt.R1`),camera:ev(`[rx,ry,zoom,panX,panY,cc.x,cc.y,cc.z,ct.x,ct.y,ct.z]`),openQuestions:ev(`(DATA.nodes[sel].oq||[]).length`),decisions:ev(`(DATA.nodes[sel].od||[]).length`)};ev(`switchView('constellation')`);out.constellation={panelHidden:ids.get('viewpanel').hidden,canvasHidden:ids.get('cv').hidden};ev(`(()=>{sel=-1;dossier.classList.remove('open');project();const i=DATA.nodes.findIndex((n,i)=>P[i].on&&visible(n)&&!n.foundation),p=P[i],before=ry;cv.dispatch('pointerdown',{clientX:p.x,clientY:p.y,pointerId:1});cv.dispatch('pointermove',{clientX:p.x+5,clientY:p.y,pointerId:1});cv.dispatch('pointerup',{clientX:p.x+5,clientY:p.y,pointerId:1});globalThis.microJitterCameraStable=ry===before})()`);out.microJitterClick={selected:ev(`sel>=0`),dossierOpen:ids.get('dossier').classList.contains('open'),cameraStable:ev(`microJitterCameraStable`)};ev(`(()=>{sel=-1;dossier.classList.remove('open');project();const i=DATA.nodes.findIndex((n,i)=>P[i].on&&visible(n)&&!n.foundation),p={x:P[i].x,y:P[i].y};cv.dispatch('pointerdown',{clientX:p.x+13,clientY:p.y,pointerId:3});cv.dispatch('pointerup',{clientX:p.x+13,clientY:p.y,pointerId:3})})()`);out.expandedHitTarget={selected:ev(`sel>=0`),dossierOpen:ids.get('dossier').classList.contains('open')};ev(`(()=>{sel=-1;dossier.classList.remove('open');project();const i=DATA.nodes.findIndex((n,i)=>P[i].on&&visible(n)&&!n.foundation),p={x:P[i].x,y:P[i].y};cv.dispatch('pointerdown',{clientX:p.x,clientY:p.y,pointerId:4});cv.dispatch('pointermove',{clientX:p.x+20,clientY:p.y,pointerId:4});cv.dispatch('pointercancel',{clientX:p.x+20,clientY:p.y,pointerId:4})})()`);out.cancelGesture={pointerDown:ev(`pointerDown`),orbiting:ev(`orbiting`),drag:ids.get('cv').classList.contains('drag'),captured:ids.get('cv').hasPointerCapture(4)};ev(`(()=>{sel=-1;dossier.classList.remove('open');project();const i=DATA.nodes.findIndex((n,i)=>P[i].on&&visible(n)&&!n.foundation),p={x:P[i].x,y:P[i].y};cv.dispatch('pointerdown',{clientX:p.x,clientY:p.y,pointerId:2});cv.dispatch('pointermove',{clientX:p.x+20,clientY:p.y,pointerId:2});cv.dispatch('pointerup',{clientX:p.x+20,clientY:p.y,pointerId:2})})()`);out.orbitGesture={selected:ev(`sel>=0`),dossierOpen:ids.get('dossier').classList.contains('open')};process.stdout.write(JSON.stringify(out));
'''

_CONSTELLATION_WORK_NAVIGATION_DOM_SHIM = _CONSTELLATION_COUNT_DOM_SHIM.replace(
    "process.stdout.write(JSON.stringify(out));",
    r'''
const nodeIndex=id=>ev(`DATA.nodes.findIndex(node=>node.id===${JSON.stringify(id)})`);
const a=nodeIndex('story:a'),b=nodeIndex('story:b'),c=nodeIndex('story:c'),d=nodeIndex('story:d');
const title=()=>ev(`DATA.nodes[sel].t`);
const fire=(key,target=ids.get('cv'),extra={})=>dispatchWindow('keydown',{key,target,...extra});
ev(`for(const key of Object.keys(filt))filt[key]=false;for(const key of Object.keys(rfilt))rfilt[key]=false;searchMatches=DATA.nodes.map(()=>false)`);
ev(`openNode(${c})`);const activeEntry=fire('ArrowRight'),activeEntryPrevented=activeEntry.defaultPrevented,activeNewest=title();
fire('ArrowRight');const activeOlder=title();fire('ArrowRight');const activeWrap=title();
fire('ArrowLeft');const activeReverseWrap=title();
ev(`openNode(${d})`);fire('ArrowDown');const recentOlder=title();fire('ArrowUp');const recentNewer=title();
ev(`openNode(${b})`);fire('ArrowDown');const recentWrap=title();
ev(`openNode(${c})`);const input=new Element('input');const inputEvent=fire('ArrowDown',input);const inputPreserved=title();
const modifiedEvent=fire('ArrowDown',ids.get('cv'),{metaKey:true});const modifiedPreserved=title();
const handledEvent=fire('ArrowDown',ids.get('cv'),{defaultPrevented:true});const handledPreserved=title();
ids.get('dossierresize').setAttribute('role','separator');
const separatorEvent=fire('ArrowLeft',ids.get('dossierresize'));const separatorPreserved=title();
ev(`dossier.classList.remove('open')`);const closedEvent=fire('ArrowDown');const closedPreserved=title();
ev(`dossier.classList.add('open');openNode(${c})`);
out.workNavigation={
  activeIndexes:ev(`workNavigationIndexes('active').map(index=>DATA.nodes[index].id)`),
  recentIndexes:ev(`workNavigationIndexes('recent').map(index=>DATA.nodes[index].id)`),
  activeEntryPrevented,activeNewest,activeOlder,activeWrap,activeReverseWrap,
  recentOlder,recentNewer,recentWrap,
  inputPrevented:inputEvent.defaultPrevented,inputPreserved,
  modifiedPrevented:modifiedEvent.defaultPrevented,modifiedPreserved,
  handledPreserved,separatorPrevented:separatorEvent.defaultPrevented,separatorPreserved,
  closedPrevented:closedEvent.defaultPrevented,closedPreserved,
  hint:ids.get('dossieridentity').innerHTML,
  shortcuts:ids.get('dossier').getAttribute('aria-keyshortcuts'),
};
process.stdout.write(JSON.stringify(out));
''',
)

_CONSTELLATION_COUNT_DOM_SHIM = _CONSTELLATION_COUNT_DOM_SHIM.replace(
    "segBtns.R1.dispatch('pointerup')", "segBtns.R1.click()",
)
_CONSTELLATION_COUNT_DOM_SHIM = _CONSTELLATION_COUNT_DOM_SHIM.replace(
    "const i=DATA.nodes.findIndex((n,i)=>P[i].on&&visible(n)&&!n.foundation),p=P[i],before=ry;",
    "const i=DATA.nodes.findIndex(n=>visible(n)&&!n.foundation),p=P[i];p.x=400;p.y=300;p.on=true;const before=ry;",
).replace(
    "const i=DATA.nodes.findIndex((n,i)=>P[i].on&&visible(n)&&!n.foundation),p={x:P[i].x,y:P[i].y};",
    "const i=DATA.nodes.findIndex(n=>visible(n)&&!n.foundation),p={x:400,y:300};P[i].x=p.x;P[i].y=p.y;P[i].on=true;",
)

_CONSTELLATION_INTERACTION_DOM_SHIM = _CONSTELLATION_COUNT_DOM_SHIM.replace(
    "process.stdout.write(JSON.stringify(out));",
    r'''
const exact=ev(`DATA.questions[0].n`);
const neighbor=ev(`DATA.nodes.findIndex((n,i)=>i!==${exact}&&!n.foundation)`);
if(exact<0||neighbor<0)throw new Error('exact-target fixture missing');
// The shared state shim reconciles this question before interaction checks;
// restore it so these tests exercise question geometry rather than plain nodes.
ev(`DATA.nodes[${exact}].oq=[0]`);
ev(`(()=>{sel=-1;dossier.classList.remove('open');sizeMode='delivery';
DATA.nodes[${exact}].rec=true;
P[${exact}].x=200;P[${exact}].y=200;P[${exact}].d=20;P[${exact}].on=true;P[${exact}].s=2;
P[${neighbor}].x=209;P[${neighbor}].y=200;P[${neighbor}].d=-20;P[${neighbor}].on=true;P[${neighbor}].s=2;
cv.dispatch('pointerdown',{clientX:200,clientY:200,pointerId:21});
cv.dispatch('pointerup',{clientX:200,clientY:200,pointerId:21})})()`);
out.overlapTarget={selected:ev(`sel`),expected:exact,title:ev(`DATA.nodes[sel].t`)};
ev(`(()=>{sel=-1;dossier.classList.remove('open');
const originalQuestions=DATA.nodes[${neighbor}].oq;DATA.nodes[${neighbor}].oq=[0];
P[${exact}].x=300;P[${exact}].y=300;P[${exact}].d=20;P[${exact}].on=true;P[${exact}].s=4;
P[${neighbor}].x=305;P[${neighbor}].y=305;P[${neighbor}].d=-20;P[${neighbor}].on=true;P[${neighbor}].s=4;
cv.dispatch('pointermove',{clientX:300,clientY:300,pointerId:27});
globalThis.crossingQuestionHover=hover;
cv.dispatch('pointerdown',{clientX:300,clientY:300,pointerId:27});
cv.dispatch('pointerup',{clientX:300,clientY:300,pointerId:27});
DATA.nodes[${neighbor}].oq=originalQuestions;})()`);
out.crossingQuestionXCenterTarget={selected:ev(`sel`),hover:ev(`crossingQuestionHover`),
  expected:exact,title:ev(`DATA.nodes[sel].t`)};
ev(`(()=>{sel=-1;dossier.classList.remove('open');
const originalQuestions=DATA.nodes[${neighbor}].oq;DATA.nodes[${neighbor}].oq=[0];
P[${exact}].x=300;P[${exact}].y=300;P[${exact}].d=-20;P[${exact}].on=true;P[${exact}].s=4;
P[${neighbor}].x=307.7;P[${neighbor}].y=300.3;P[${neighbor}].d=20;P[${neighbor}].on=true;P[${neighbor}].s=4;
cv.dispatch('pointermove',{clientX:304,clientY:304,pointerId:29});
globalThis.paintedEndpointHover=hover;
cv.dispatch('pointerdown',{clientX:304,clientY:304,pointerId:29});
cv.dispatch('pointerup',{clientX:304,clientY:304,pointerId:29});
DATA.nodes[${neighbor}].oq=originalQuestions;})()`);
out.paintedQuestionXEndpointTarget={selected:ev(`sel`),hover:ev(`paintedEndpointHover`),
  expected:exact,title:ev(`DATA.nodes[sel].t`)};
ev(`(()=>{sel=-1;dossier.classList.remove('open');
P[${exact}].x=300;P[${exact}].y=300;P[${exact}].d=20;P[${exact}].on=true;P[${exact}].s=2;
P[${neighbor}].x=307;P[${neighbor}].y=300;P[${neighbor}].d=-20;P[${neighbor}].on=true;P[${neighbor}].s=2;
cv.dispatch('pointermove',{clientX:300,clientY:300,pointerId:28});
globalThis.advertisedTarget=hover;
// Five pixels of normal press jitter geometrically favors the neighbor. The
// advertised tooltip must remain the click contract instead of baiting and
// switching to the second hit-test winner.
cv.dispatch('pointerdown',{clientX:305,clientY:300,pointerId:28});
cv.dispatch('pointerup',{clientX:305,clientY:300,pointerId:28});})()`);
out.advertisedHoverTarget={selected:ev(`sel`),advertised:ev(`advertisedTarget`),
  expected:exact,title:ev(`DATA.nodes[sel].t`)};
ev(`(()=>{sel=-1;dossier.classList.remove('open');
P[${exact}].x=200;P[${exact}].y=200;P[${exact}].d=20;P[${exact}].on=true;P[${exact}].s=2;
P[${neighbor}].x=209;P[${neighbor}].y=200;P[${neighbor}].d=-20;P[${neighbor}].on=true;P[${neighbor}].s=2;
cv.dispatch('pointerdown',{clientX:209,clientY:200,pointerId:23});
cv.dispatch('pointerup',{clientX:209,clientY:200,pointerId:23})})()`);
out.nearbyStoryTarget={selected:ev(`sel`),expected:neighbor,title:ev(`DATA.nodes[sel].t`)};
ev(`(()=>{sel=-1;dossier.classList.remove('open');
P[${exact}].x=200;P[${exact}].y=200;P[${exact}].d=20;P[${exact}].on=true;P[${exact}].s=2;
P[${neighbor}].x=209;P[${neighbor}].y=200;P[${neighbor}].d=-20;P[${neighbor}].on=true;P[${neighbor}].s=2;
const pulseX=P[${exact}].x+questionAttentionRadius(${exact})*.72;
cv.dispatch('pointerdown',{clientX:pulseX,clientY:200,pointerId:25});
cv.dispatch('pointerup',{clientX:pulseX,clientY:200,pointerId:25})})()`);
out.decorativePulseNearestStory={selected:ev(`sel`),expected:neighbor,title:ev(`DATA.nodes[sel].t`)};
ev(`(()=>{sel=-1;dossier.classList.remove('open');sizeMode='delivery';
P[${exact}].x=200;P[${exact}].y=200;P[${exact}].d=20;P[${exact}].on=true;P[${exact}].s=2;
const pulseX=P[${exact}].x+questionRingRadii(${exact})[0];
P[${neighbor}].x=pulseX;P[${neighbor}].y=200;P[${neighbor}].d=-20;P[${neighbor}].on=true;P[${neighbor}].s=2;
cv.dispatch('pointerdown',{clientX:pulseX,clientY:200,pointerId:26});
cv.dispatch('pointerup',{clientX:pulseX,clientY:200,pointerId:26})})()`);
out.decorativeRingDoesNotCaptureStory={selected:ev(`sel`),expected:neighbor,title:ev(`DATA.nodes[sel].t`)};
ev(`(()=>{sel=-1;dossier.classList.remove('open');
P[${exact}].x=260;P[${exact}].y=220;P[${exact}].on=true;
P[${neighbor}].x=260;P[${neighbor}].y=220;P[${neighbor}].on=false;
cv.dispatch('pointermove',{clientX:260,clientY:220,pointerId:24});
globalThis.hiddenHover=hover;globalThis.pointerClass=cv.classList.contains('hover-target');
cv.dispatch('pointerdown',{clientX:260,clientY:220,pointerId:24});
cv.dispatch('pointerup',{clientX:260,clientY:220,pointerId:24})})()`);
out.hiddenTarget={selected:ev(`sel`),expected:exact,hover:ev(`hiddenHover`),
  pointer:ev(`pointerClass`)};
out.selectionMatrix=ev(`(()=>{
  const failures=[],viewports=[[360,320],[760,520],[1280,800]],zooms=[.55,1,1.8],
    modes=['time','delivery'],rotations=[[-.7,.2],[-.15,1.1]];
  const originalRelease=DATA.nodes[${neighbor}].r;
  for(const [width,height] of viewports)for(const nextZoom of zooms)for(const mode of modes)for(const [nextRx,nextRy] of rotations){
    innerWidth=width;innerHeight=height;size();zoom=nextZoom;sizeMode=mode;rx=nextRx;ry=nextRy;
    for(const key of Object.keys(filt))filt[key]=true;for(const key of Object.keys(rfilt))rfilt[key]=true;
    questionOnly=false;searchTerms=[];searchMatches=DATA.nodes.map(()=>true);project();
    const x=width*.55,y=height*.58;
    P[${exact}].x=x;P[${exact}].y=y;P[${exact}].d=20;P[${exact}].on=true;
    P[${neighbor}].x=x+5;P[${neighbor}].y=y;P[${neighbor}].d=-20;P[${neighbor}].on=true;
    sel=-1;cv.dispatch('pointerdown',{clientX:x,clientY:y,pointerId:31});cv.dispatch('pointerup',{clientX:x,clientY:y,pointerId:31});
    if(sel!==${exact})failures.push(['question',width,height,nextZoom,mode,nextRx,nextRy,sel]);
    project();P[${exact}].x=x;P[${exact}].y=y;P[${exact}].d=20;P[${exact}].on=true;
    P[${neighbor}].x=x+5;P[${neighbor}].y=y;P[${neighbor}].d=-20;P[${neighbor}].on=true;
    sel=-1;cv.dispatch('pointerdown',{clientX:x+5,clientY:y,pointerId:32});cv.dispatch('pointerup',{clientX:x+5,clientY:y,pointerId:32});
    if(sel!==${neighbor})failures.push(['story',width,height,nextZoom,mode,nextRx,nextRy,sel]);
    DATA.nodes[${neighbor}].r='R1';rfilt.R1=false;project();
    P[${exact}].x=x;P[${exact}].y=y;P[${exact}].on=true;
    P[${neighbor}].x=x;P[${neighbor}].y=y;
    sel=-1;cv.dispatch('pointerdown',{clientX:x,clientY:y,pointerId:33});cv.dispatch('pointerup',{clientX:x,clientY:y,pointerId:33});
    if(sel!==${exact}||P[${neighbor}].on)failures.push(['release-hidden',width,height,nextZoom,mode,nextRx,nextRy,sel,P[${neighbor}].on]);
    DATA.nodes[${neighbor}].r=originalRelease;rfilt.R1=true;questionOnly=true;project();
    P[${exact}].x=x;P[${exact}].y=y;P[${exact}].on=true;
    P[${neighbor}].x=x;P[${neighbor}].y=y;
    sel=-1;cv.dispatch('pointerdown',{clientX:x,clientY:y,pointerId:34});cv.dispatch('pointerup',{clientX:x,clientY:y,pointerId:34});
    if(sel!==${exact}||P[${neighbor}].on)failures.push(['question-filter',width,height,nextZoom,mode,nextRx,nextRy,sel,P[${neighbor}].on]);
  }
  DATA.nodes[${neighbor}].r=originalRelease;questionOnly=false;innerWidth=1200;innerHeight=800;size();
  return{cases:viewports.length*zooms.length*modes.length*rotations.length*4,failures};
})()`);
out.resizeSync=ev(`(()=>{innerWidth=913;innerHeight=577;W=360;H=320;project();
  const result={W,H,canvasWidth:cv.width,backgroundWidth:bgcv.width};
  innerWidth=1200;innerHeight=800;size();return result;})()`);
ev(`(()=>{sel=-1;dossier.classList.remove('open');
const p=P[${exact}];p.x=400;p.y=300;p.s=2;p.on=true;
const rr=nodeRadius(${exact}),radius=nodeBadgeRadius(rr);
const badge=nodeBadgePoint(p,rr,radius,-1,0);
cv.dispatch('pointerdown',{clientX:badge.x,clientY:badge.y,pointerId:22});
cv.dispatch('pointerup',{clientX:badge.x,clientY:badge.y,pointerId:22})})()`);
out.questionBadgeTarget={selected:ev(`sel`),expected:exact,
  open:ids.get('dossier').classList.contains('open')};
ev(`(()=>{sel=-1;dossier.classList.remove('open');
P[${exact}].x=400;P[${exact}].y=300;P[${exact}].on=true;
P[${neighbor}].x=500;P[${neighbor}].y=300;P[${neighbor}].on=true;
updatePointerAt(400,300);globalThis.pointerQuestion={hover,cursor:cv.classList.contains('hover-target')};
P[${exact}].x=500;P[${neighbor}].x=400;updatePointerAt(400,300);
globalThis.pointerStory={hover,cursor:cv.classList.contains('hover-target')};
P[${exact}].x=600;P[${neighbor}].x=650;updatePointerAt(400,300);
globalThis.pointerEmpty={hover,cursor:cv.classList.contains('hover-target')};})()`);
out.pointerPresentation={question:ev(`pointerQuestion`),story:ev(`pointerStory`),empty:ev(`pointerEmpty`)};
const card=new Element('button');card.dataset={viewNode:String(exact)};
ids.get('viewpanel').querySelectorAll=selector=>selector==='[data-view-node]'?[card]:[];
ids.get('dbody').scrollTop=999;ev(`switchView('dashboard')`);card.click();
out.cardTarget={selected:ev(`sel`),expected:exact,title:ev(`DATA.nodes[sel].t`),
  open:ids.get('dossier').classList.contains('open'),scrollTop:ids.get('dbody').scrollTop};
ev(`segBtns.R1.dispatch('pointerdown',{button:0})`);
setTimeout(()=>{
  out.releaseHold={r0:ev(`rfilt.R0`),r1:ev(`rfilt.R1`),
    r0Pressed:ev(`segBtns.R0.getAttribute('aria-pressed')`),
    r1Pressed:ev(`segBtns.R1.getAttribute('aria-pressed')`)};
  ev(`segBtns.R1.dispatch('pointerup',{button:0});lifecycleButtons.active.dispatch('pointerdown',{button:0})`);
  setTimeout(()=>{
    out.lifecycleHold={active:ev(`filt.active`),ready:ev(`filt.ready`),
      activePressed:ev(`lifecycleButtons.active.getAttribute('aria-pressed')`),
      readyPressed:ev(`lifecycleButtons.ready.getAttribute('aria-pressed')`)};
    process.stdout.write(JSON.stringify(out));
  },725);
},725);
''',
)

_CONSTELLATION_WORK_NAVIGATION_DOM_SHIM = _CONSTELLATION_COUNT_DOM_SHIM.replace(
    "process.stdout.write(JSON.stringify(out));",
    r'''
const nodeIndex=id=>ev(`DATA.nodes.findIndex(node=>node.id===${JSON.stringify(id)})`);
const a=nodeIndex('story:a'),b=nodeIndex('story:b'),c=nodeIndex('story:c'),d=nodeIndex('story:d');
const title=()=>ev(`DATA.nodes[sel].t`);
const fire=(key,target=ids.get('cv'),extra={})=>dispatchWindow('keydown',{key,target,...extra});
ev(`for(const key of Object.keys(filt))filt[key]=false;for(const key of Object.keys(rfilt))rfilt[key]=false;searchMatches=DATA.nodes.map(()=>false)`);
ev(`openNode(${c})`);const activeEntry=fire('ArrowRight'),activeEntryPrevented=activeEntry.defaultPrevented,activeNewest=title();
fire('ArrowRight');const activeOlder=title();fire('ArrowRight');const activeWrap=title();
fire('ArrowLeft');const activeReverseWrap=title();
ev(`openNode(${d})`);fire('ArrowDown');const recentOlder=title();fire('ArrowUp');const recentNewer=title();
ev(`openNode(${b})`);fire('ArrowDown');const recentWrap=title();
ev(`openNode(${c})`);const input=new Element('input');const inputEvent=fire('ArrowDown',input);const inputPreserved=title();
const modifiedEvent=fire('ArrowDown',ids.get('cv'),{metaKey:true});const modifiedPreserved=title();
const handledEvent=fire('ArrowDown',ids.get('cv'),{defaultPrevented:true});const handledPreserved=title();
ids.get('dossierresize').setAttribute('role','separator');
const separatorEvent=fire('ArrowLeft',ids.get('dossierresize'));const separatorPreserved=title();
ev(`dossier.classList.remove('open')`);const closedEvent=fire('ArrowDown');const closedPreserved=title();
ev(`dossier.classList.add('open');openNode(${c})`);
out.workNavigation={
  activeIndexes:ev(`workNavigationIndexes('active').map(index=>DATA.nodes[index].id)`),
  recentIndexes:ev(`workNavigationIndexes('recent').map(index=>DATA.nodes[index].id)`),
  activeEntryPrevented,activeNewest,activeOlder,activeWrap,activeReverseWrap,
  recentOlder,recentNewer,recentWrap,
  inputPrevented:inputEvent.defaultPrevented,inputPreserved,
  modifiedPrevented:modifiedEvent.defaultPrevented,modifiedPreserved,
  handledPreserved,separatorPrevented:separatorEvent.defaultPrevented,separatorPreserved,
  closedPrevented:closedEvent.defaultPrevented,closedPreserved,
  hint:ids.get('dossieridentity').innerHTML,
  shortcuts:ids.get('dossier').getAttribute('aria-keyshortcuts'),
};
process.stdout.write(JSON.stringify(out));
''',
)


def _graph():
    return Graph(groups=[Group(id="capability:c", kind="capability", title="Cap")],
                 vocab=Config(data=DEFAULTS).vocab,
                 items=[Item(id="story:a", title="A", status="shipped", release="R0",
                             group="capability:c", appetite="large",
                             source={"adapter": "spec_tree", "path": "s/a.md"},
                             activity={"commits": 3, "mentions": 1, "last_touched": 500}),
                        Item(id="story:b", title="B", status="specced", release="R0",
                             deps=["story:a"], group="capability:c",
                             source={"adapter": "spec_tree", "path": "s/b.md"},
                             activity={"commits": 1, "mentions": 0, "last_touched": 900})])


def _work_navigation_graph():
    graph = Graph(
        groups=[Group(id="capability:c", kind="capability", title="Cap")],
        vocab=Config(data=DEFAULTS).vocab,
        items=[
            Item(id=f"story:{slug}", title=slug.upper(), status="specced",
                 release="R0", group="capability:c")
            for slug in ("a", "b", "c", "d")
        ],
        owner_questions=[OwnerQuestion(
            id="question:navigation", story_id="story:a", owner="Ryder",
            prompt="Keep the executable fixture explicit?",
            options=[OwnerQuestionOption(id="yes", label="Yes", tradeoff="Visible")],
            recommendation=OwnerQuestionRecommendation(
                option_id="yes", rationale="The shared DOM shim requires one question.",
            ),
            falsifier="The shared shim no longer exercises question reconciliation.",
            evidence=["tests/test_render_constellation.py"],
        )],
    )
    graph.active_work = [
        ActiveWork(
            story_id="story:a", agent="Ada", task="A active older",
            state="active", completed=1, total=2,
            updated_at="2026-08-10T17:00:00Z",
            stale_at="2099-08-10T17:00:00Z",
        ),
        ActiveWork(
            story_id="story:a", agent="Ada", task="A completed newer",
            state="complete", completed=2, total=2,
            updated_at="2026-08-10T21:00:00Z",
            stale_at="2099-08-10T21:00:00Z",
        ),
        ActiveWork(
            story_id="story:b", agent="Babbage", task="B active newest",
            state="active", completed=1, total=3,
            updated_at="2026-08-10T20:00:00Z",
            stale_at="2099-08-10T20:00:00Z",
        ),
        ActiveWork(
            story_id="story:c", agent="Curie", task="C completed newest",
            state="complete", completed=3, total=3,
            updated_at="2026-08-10T22:00:00Z",
            stale_at="2099-08-10T22:00:00Z",
        ),
        ActiveWork(
            story_id="story:d", agent="Dirac", task="D stale active",
            state="active", completed=1, total=4,
            updated_at="2026-08-10T23:00:00Z",
            stale_at="2026-08-10T23:30:00Z",
        ),
    ]
    return graph


def _data(html):
    return json.loads(re.search(r"const DATA=(\{.*?\});\n", html, re.S).group(1))


def _search_ids(data, query):
    """Mirror the page's documented all-token substring contract over its index."""
    tokens = query.casefold().split()
    return [
        node.get("id", f"foundation:{node['s']}")
        for node in data["nodes"]
        if all(token in node["q"].casefold() for token in tokens)
    ]


def test_constellation_injects_data(tmp_path):
    cfg = Config(data=deep_merge(DEFAULTS, {"project": {"name": "demo"},
                                            "render": {"recommended": ["story:b"]}}))
    html = render_all(_graph(), cfg, tmp_path, only={"constellation"})["constellation.html"]
    assert "__DATA__" not in html and "__TITLE__" not in html and "demo" in html
    d = _data(html)
    assert len(d["nodes"]) == 2 and d["edges"] == [[0, 1]]
    assert d["engineVersion"]
    assert "if(body.engineVersion!==ENGINE_VERSION)" in html
    assert "Restart vizzer serve before answering." in html
    assert d["now"] == 900                       # max last_touched — deterministic, no wall clock
    assert d["nodes"][1]["rec"] == 1
    assert d["nodes"][0]["w"] > d["nodes"][1]["w"]   # appetite large > default
    assert "root" not in d                       # no absolute paths unless obsidian_links=true


def test_constellation_preserves_group_hierarchy_for_structure_navigation(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(
        vocab=cfg.vocab,
        groups=[
            Group(id="product:notes", kind="product", title="Notes"),
            Group(id="capability:notes/library", kind="capability",
                  title="Library", parent="product:notes"),
            Group(id="epic:notes/library/search", kind="epic",
                  title="Search", parent="capability:notes/library"),
        ],
        items=[
            Item(id="story:find-notes", title="Find notes", status="shipped",
                 group="epic:notes/library/search"),
            Item(id="doc:orphan", title="Loose reference", status="unknown",
                 role="reference"),
        ],
    )

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)

    assert data["nodes"][1]["group"] == "epic:notes/library/search"
    assert data["groups"] == [
        {"id": "capability:notes/library", "kind": "capability",
         "title": "Library", "parent": "product:notes"},
        {"id": "epic:notes/library/search", "kind": "epic",
         "title": "Search", "parent": "capability:notes/library"},
        {"id": "product:notes", "kind": "product",
         "title": "Notes", "parent": ""},
    ]
    assert 'href="#structure" data-view="structure">Hierarchy</a>' in html
    assert "function renderStructure(entries)" in html
    assert "Facets describe cross-project membership" in html
    assert "currentView==='structure'?renderStructure(entries)" in html
    assert "let capFocus = null, groupFocus = null" in html
    assert "function renderCapabilityAccordions()" in html
    assert "nodeBelongsToGroup" in html
    assert "grid-template-rows:28px 28px 28px" in html
    assert "#meter{grid-column:1 / -1;grid-row:2" in html
    assert "#chips{grid-column:1 / -1;grid-row:3" in html


def test_structure_exposes_group_contracts_and_unreferenced_foundations(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(
        vocab=cfg.vocab,
        groups=[
            Group(id="subject:foundations", kind="subject", title="Foundations",
                  meta={"source": {"adapter": "spec_tree", "path": "spec/foundations.md"}}),
            Group(id="foundation:geometry", kind="foundation", title="Geometry",
                  parent="subject:foundations", meta={
                      "source": {"adapter": "spec_tree", "path": "spec/geometry.md"},
                      "summary": "One geometry contract.",
                  }),
            Group(id="capability:drawing", kind="capability", title="Drawing",
                  meta={"source": {"adapter": "spec_tree", "path": "spec/drawing.md"}}),
        ],
        items=[Item(id="story:line", title="Line", status="ready",
                    group="capability:drawing")],
    )

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)
    groups = {group["id"]: group for group in data["groups"]}

    assert groups["capability:drawing"]["p"] == "spec/drawing.md"
    assert groups["foundation:geometry"]["summary"] == "One geometry contract."
    assert "if(group.kind==='foundation')" in html
    assert 'data-open-group="${esc(group.id)}"' in html
    assert "fetch('/api/open/'+encodeURIComponent(button.dataset.openGroup)" in html


def test_constellation_renders_workstreams_sessions_collisions_and_source_roles(tmp_path):
    cfg = Config(data=deep_merge(DEFAULTS, {"source_area": [{
        "id": "experience-spec", "title": "Experience Spec", "role": "delivery",
        "path": "s", "adapter": "spec_tree",
    }]}))
    graph = _graph()
    graph.workstreams = {
        "schema": 1, "revision": 2, "runtimeRevision": 3,
        "asOf": "2026-08-10T20:00:00Z",
        "workstreams": [{
            "id": "canvas", "title": "Canvas", "objective": "Ship canvas",
            "status": "active", "lead": "Codex", "reviewer": "Claude",
            "storyIds": ["story:b"], "dependsOn": [],
            "allowedPaths": ["render/canvas"], "sharedPaths": ["vizzer/active-work.json"],
            "checkpoint": "Tests", "completed": 1, "total": 2,
        }],
        "discussions": [{
            "id": "policy", "workstreamId": "canvas", "author": "Claude",
            "kind": "escalation", "scope": "product", "body": "Ryder must choose",
            "createdAt": "2026-08-10T19:00:00Z", "replyTo": None,
            "ownerQuestionId": "question:policy",
        }],
        "sessions": [{
            "id": "codex", "actor": "Codex", "model": "Spark", "role": "lead",
            "workstreamId": "canvas", "state": "active", "branch": "codex/canvas",
            "worktree": "canvas", "startedAt": "2026-08-10T19:00:00Z",
            "heartbeatAt": "2026-08-10T19:50:00Z",
            "leaseExpiresAt": "2099-08-10T20:20:00Z", "stoppedAt": None,
            "fresh": True,
        }],
        "collisions": [{
            "kind": "shared-path", "workstreams": ["canvas", "tokens"],
            "values": ["vizzer/active-work.json"],
        }],
    }

    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]
    data = _data(html)

    assert data["workstreams"]["revision"] == 2
    assert data["sourceAreas"][0]["title"] == "Experience Spec"
    assert 'href="#workstreams" data-view="workstreams">Workstreams</a>' in html
    assert "function renderWorkstreams(entries)" in html
    assert "Coordination warnings" in html
    assert "peer discussion" in html.casefold()
    assert "currentView==='workstreams'?renderWorkstreams(entries)" in html


def test_constellation_serializes_roles_and_facets_and_scopes_delivery_metrics(tmp_path):
    cfg = Config(data=deep_merge(DEFAULTS, {"area": [
        {"id": "products", "title": "Products", "facet": "product",
         "values": ["notes"]},
        {"id": "core", "title": "Core", "facet": "product",
         "values": ["core"]},
    ]}))
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:done", title="Done", status="shipped", role="delivery",
             tags=["markdown"], facets={
                 "product": ["notes", "core"],
                 "capability": ["notes/editor", "core/markdown"],
             }),
        Item(id="story:open", title="Open", status="specced", role="delivery",
             facets={"product": ["notes"], "capability": ["notes/editor"]}),
        Item(id="product-capability:notes/editor", title="Editor coverage",
             status="shipped", role="coverage",
             facets={"product": ["notes"], "capability": ["notes/editor"]}),
    ], owner_questions=[OwnerQuestion(
        id="question:open", story_id="story:open", owner="Ryder",
        prompt="Choose?", options=[
            OwnerQuestionOption(id="a", label="A", tradeoff="A tradeoff"),
            OwnerQuestionOption(id="b", label="B", tradeoff="B tradeoff"),
        ], recommendation=OwnerQuestionRecommendation(
            option_id="a", rationale="A is recommended",
        ), falsifier="Counterexample", evidence=["story.md"],
    )])

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)
    by_id = {node["id"]: node for node in data["nodes"]}

    assert by_id["story:done"]["role"] == "delivery"
    assert by_id["story:done"]["tags"] == ["markdown"]
    assert by_id["story:done"]["facets"]["product"] == ["notes", "core"]
    assert data["caps"] == {"": {"total": 2, "shipped": 1}}
    assert "Products" in html and "Core" in html
    assert "const deliveryNodes = itemNodes.filter" in html
    assert "Lifecycle and regression debt are computed within each item role" in html

    node = shutil.which("node")
    assert node is not None, "Node is required to execute constellation JavaScript tests"
    completed = subprocess.run(
        [node, "-e", _CONSTELLATION_COUNT_DOM_SHIM], input=html,
        text=True, capture_output=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    state = json.loads(completed.stdout)["initial"]
    assert state["shipped"] == "1/2 delivery shipped"
    assert state["completion"] == "50%"
    assert state["items"] == "2 items"
    assert state["capCount"] == "1/2"


def test_constellation_composes_frontend_sources_into_one_dependency_free_artifact(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert not re.search(r"<(?:script|link)\b[^>]+(?:src|href)=", html, re.I)
    assert len(re.findall(r"<script>", html)) == 2
    assert len(re.findall(r"<style>", html)) == 1
    assert not re.search(r"__VIZZER_[A-Z_]+__", html)
    assert "const DATA=" in html
    assert "function workNavigationIndexes(lane)" in html


def test_search_clear_icon_is_centered_in_its_circle(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "display:grid;place-items:center;padding:0" in html
    assert "#searchclear .symbol{display:block;width:13px;height:13px;vertical-align:0}" in html


def test_constellation_serializes_assessment_and_uses_assessed_size(tmp_path):
    graph = _graph()
    graph.assessment = {
        "schema": 1,
        "method": "deterministic-delivery-assessment-v1",
        "items": {"story:b": {
            "size": {
                "assessed_band": "XL", "uncertainty": "U2",
                "plausible_range": {"min": "L", "max": "XL"},
                "provenance": "inferred",
                "dimensions": {
                    "implementation": {"band": "M", "provenance": "inferred"},
                    "verification": {"band": "L", "provenance": "inferred"},
                    "integration": {"band": "L", "provenance": "inferred"},
                    "coordination": {"band": "XL", "provenance": "inferred"},
                },
                "evidence": ["four integration boundaries"],
                "unknowns": ["verification harness is not established"],
            },
            "impact": {
                "structural_target_reach": 3, "immediate_unlock": 2,
                "frontier_reach": 4, "provenance": "authored",
            },
            "parallelism": {"classification": "serial", "conflicts": ["shared build"]},
        }},
        "portfolio": {"small": [], "anchors": [], "defects": [],
                      "questions": ["story:b"], "unknown_size": []},
    }

    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    data = _data(html)
    node = next(value for value in data["nodes"] if value["id"] == "story:b")

    assert node["assess"]["band"] == "XL"
    assert node["assess"]["lane"] == "questions"
    assert node["assess"]["targetReach"] == 3
    assert node["w"] > next(value for value in data["nodes"]
                            if value["id"] == "story:a")["w"]
    assert data["assessment"]["method"] == "deterministic-delivery-assessment-v1"
    assert "delivery size" in html and "assessment unknowns" in html
    assert "sizeMode==='delivery'&&n.assess&&n.assess.band==null" in html


def test_constellation_does_not_render_authored_appetite_as_assessed_burden(tmp_path):
    graph = _graph()
    graph.assessment = {
        "schema": 1,
        "items": {"story:b": {
            "size": {
                "assessed_band": "S", "normalized_appetite": "S",
                "raw_authored_appetite": "small", "uncertainty": "U2",
                "plausible_range": {"min": "XS", "max": "M"},
                "provenance": "authored",
                "dimensions": {
                    name: {"band": None, "provenance": "unknown"}
                    for name in (
                        "implementation", "verification", "integration", "coordination",
                    )
                },
            },
            "impact": {}, "parallelism": {"classification": "unknown"},
        }},
        "portfolio": {"small": [], "anchors": [], "defects": [],
                      "questions": [], "unknown_size": ["story:b"]},
    }

    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    node = next(value for value in _data(html)["nodes"] if value["id"] == "story:b")

    assert node["assess"]["band"] is None
    assert node["assess"]["appetiteBand"] == "S"
    assert node["assess"]["burdenEstablished"] is False
    assert "unassessed · authored-appetite proxy" in html


def test_constellation_marks_unresolved_blocker_lane(tmp_path):
    graph = _graph()
    graph.assessment = {
        "schema": 1,
        "items": {"story:b": {
            "size": {"assessed_band": "S", "uncertainty": "U2"},
            "impact": {"structural_target_reach": 1, "immediate_unlock": 0},
            "parallelism": {"classification": "unknown"},
        }},
        "portfolio": {"small": [], "anchors": [], "defects": [],
                      "questions": [], "occupied": [],
                      "blocked": ["story:b"], "unknown_size": []},
    }

    cfg = Config(data=deep_merge(DEFAULTS, {
        "render": {"recommended": ["story:a", "story:b"]},
    }))
    html = render_all(graph, cfg, tmp_path,
                      only={"constellation"})["constellation.html"]
    node = next(value for value in _data(html)["nodes"]
                if value["id"] == "story:b")

    assert node["assess"]["lane"] == "blocked"


def test_constellation_sanitizes_persisted_assessment_before_html(tmp_path):
    graph = _graph()
    graph.assessment = {
        "schema": 1,
        "items": {"story:b": {
            "size": {
                "assessed_band": "<img>", "uncertainty": "U99",
                "raw_authored_appetite": "</script><script>alert(1)</script>",
                "plausible_range": {"min": "NOPE", "max": "XL"},
                "provenance": "fabricated", "dimensions": {},
                "evidence": ["<b>not markup</b>"], "unknowns": [],
            },
            "impact": {
                "structural_target_reach": "<img onerror=alert(2)>",
                "immediate_unlock": -5, "frontier_reach": 10 ** 20,
                "provenance": "authored",
            },
            "parallelism": {"classification": "maybe", "conflicts": []},
        }},
        "portfolio": {},
    }

    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    node = next(value for value in _data(html)["nodes"] if value["id"] == "story:b")

    assert node["assess"]["band"] is None
    assert node["assess"]["uncertainty"] == "U3"
    assert node["assess"]["targetReach"] == 0
    assert node["assess"]["immediateUnlock"] == 0
    assert node["assess"]["frontierReach"] == 1_000_000
    assert node["assess"]["parallel"] == "unknown"
    assert html.count("</script>") == 2


def test_constellation_keeps_file_mode_source_link_relative_and_http_open_by_id(tmp_path):
    cfg = Config(data=Config(data=DEFAULTS).data)
    html = render_all(_graph(), cfg, tmp_path, only={"constellation"})["constellation.html"]
    data = _data(html)

    assert data["nodes"][0]["h"] == "../../s/a.md"
    assert str(tmp_path) not in html
    assert "const SERVED = location.protocol === 'http:';" in html
    assert "n.h&&!SERVED" in html
    assert "n.id&&SERVED" in html
    assert "fetch('/api/open/'+encodeURIComponent(b.dataset.openItem)" in html
    assert '>read story</button>' in html
    assert "b.textContent = 'story opened'" in html


def test_constellation_default_never_serializes_root(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert '"root"' not in html
    assert str(tmp_path) not in html


def test_constellation_preserves_explicit_obsidian_opt_in(tmp_path):
    cfg = Config(data=deep_merge(DEFAULTS, {"render": {"obsidian_links": True}}))
    html = render_all(_graph(), cfg, tmp_path, only={"constellation"})["constellation.html"]

    assert _data(html)["root"] == str(tmp_path)
    assert "obsidian://open?path=" in html


def test_constellation_uses_configured_lifecycle_roles(tmp_path):
    """codex-sequence-2026-08-08: regression work cannot appear active here."""
    statuses = [
        {"name": "building", "emoji": "🔧", "done": False, "role": "active"},
        {"name": "in-flight", "emoji": "✈️", "done": False, "role": "regression"},
        {"name": "bug-gap", "emoji": "🐛", "done": False, "role": "regression"},
        {"name": "verified", "emoji": "🏁", "done": True, "role": "done"},
    ]
    cfg = Config(data=deep_merge(DEFAULTS, {"status": statuses}))
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:a", title="A", status="building"),
        Item(id="story:b", title="B", status="in-flight"),
        Item(id="story:c", title="C", status="bug-gap"),
        Item(id="story:d", title="D", status="verified"),
    ])

    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]
    groups = {node["s"]: node["g"] for node in _data(html)["nodes"]}

    assert groups == {"a": "active", "b": "buggap", "c": "buggap", "d": "shipped"}
    assert "'in-flight':'active'" not in html
    assert "const metricNodes=deliveryNodes.filter" in html
    assert "const bugGaps=metricNodes.filter(n=>n.st==='bug-gap').length" in html
    assert "defectCount.textContent=`${bugGaps} bug gap${bugGaps===1?'':'s'} open`" in html
    assert '#meterlab .defectcount{color:var(--buggap)}' in html
    assert "const questions=metricNodes.reduce((total,n)=>total+(n.oq||[]).length,0)" in html
    assert "currentQuestionCountLabel=`${questions} open owner question${questions===1?'':'s'} across ${questionStories}" in html
    assert "currentQuestionButtonLabel=`${questions} answer${questions===1?'':'s'} required" in html
    assert 'id="questionfilter" class="questioncount" aria-pressed="false"' in html
    assert '#meterlab .questioncount:focus-visible' in html


def test_constellation_exposes_interactive_views_and_separate_markdown_exports(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert '<details id="viewmenu"><summary>Views</summary>' in html
    for route in ("constellation", "dashboard", "roadmap", "features",
                  "completion", "ledgers"):
        assert f'href="#{route}" data-view="{route}"' in html
    assert '#viewmenu a[aria-current="page"]' in html
    assert '<details id="exportmenu"><summary>Export</summary>' in html
    for target in ("dashboard.md", "roadmap.md", "feature-index.md",
                   "completion-sheet.md", "ledger-table.md"):
        assert f'href="{target}" download' in html
    assert '<main id="viewpanel" tabindex="-1" hidden></main>' in html
    assert "Every panel below reads the exact DATA object" in html
    assert "const viewEntries=()=>DATA.nodes.map" in html
    assert "!node.foundation&&visible(node)&&searchMatches[index]" in html
    assert "function renderDashboard(entries)" in html
    assert "function renderRoadmap(entries)" in html
    assert "function renderFeatures(entries)" in html
    assert "function renderCompletion(entries)" in html
    assert "function renderLedgers(entries)" in html
    assert "addEventListener('hashchange',()=>switchView(requestedView(),true))" in html


def test_titles_cannot_inject_html_or_break_out_of_the_script_block(tmp_path):
    """Project-controlled text must never become executable markup in the rendered page."""
    from vizzer.config import deep_merge
    from vizzer.model import Item as I

    cfg = Config(data=deep_merge(DEFAULTS, {
        "render": {"title": "<img src=x onerror=alert(1)>"}}))
    graph = Graph(vocab=Config(data=DEFAULTS).vocab, items=[
        I(id="story:x", title="</script><script>alert(1)</script>",
          source={"adapter": "spec_tree", "path": "s/x.md"},
          activity={"commits": 0, "mentions": 0, "last_touched": 0})])
    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]

    # the config-supplied page title must be escaped, not injected as live markup
    assert "<img src=x onerror=" not in html
    # no data value may terminate the script element that carries the JSON payload
    assert "</script><script>alert(1)" not in html
    # the payload must still parse and preserve the original text
    data = _data(html)
    assert data["nodes"][0]["t"] == "</script><script>alert(1)</script>"


def test_placeholder_in_config_cannot_smuggle_the_payload_into_html(tmp_path):
    """Substitutions must be single-pass: replaced text must never be re-scanned.

    Escaping the title and then replacing __DATA__ meant a title containing the
    literal string `__DATA__` had the JSON payload injected into the HTML body,
    where node titles are not HTML-escaped — reintroducing live markup.
    """
    from vizzer.config import deep_merge
    from vizzer.model import Item as I

    cfg = Config(data=deep_merge(DEFAULTS, {"render": {"title": "x__DATA__y"}}))
    graph = Graph(vocab=Config(data=DEFAULTS).vocab, items=[
        I(id="story:a", title="<img src=x onerror=alert(7)>",
          source={"adapter": "spec_tree", "path": "s/a.md"},
          activity={"commits": 0, "mentions": 0, "last_touched": 0})])
    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]

    # the payload belongs in the script element and nowhere else
    assert html.count('"nodes":') == 1
    head, _, tail = html.partition('id="title"')
    title_region = tail[:200]
    assert "x__DATA__y" in title_region          # the literal title, escaped
    assert '"nodes":' not in title_region        # not the smuggled payload
    # the value survives intact inside the data block
    assert _data(html)["nodes"][0]["t"] == "<img src=x onerror=alert(7)>"


def test_non_numeric_activity_values_cannot_reach_the_page_as_markup(tmp_path):
    """A hand-edited graph can carry junk in activity; the page must not interpolate it raw."""
    from vizzer.model import Item as I

    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        I(id="story:a", title="A", source={"adapter": "spec_tree", "path": "s/a.md"},
          activity={"commits": "<img src=x onerror=alert(8)>", "mentions": None,
                    "last_touched": "not-a-number"})])
    html = render_all(graph, cfg, tmp_path, only={"constellation"})["constellation.html"]
    assert "onerror=alert(8)" not in html
    node = _data(html)["nodes"][0]
    assert isinstance(node["ac"], int) and isinstance(node["am"], int)
    assert isinstance(node["ts"], int)


def test_constellation_keeps_typed_lineage_separate_from_hard_edges(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:old", title="Old", status="shipped"),
        Item(id="story:new", title="New", status="specced",
             relations=[Relation(kind="revises", target="story:old")],
             priority={
                 "rank": 1, "score": 540,
                 "rationale": "1 incomplete target dependent(s), depth 1",
                 "components": {"target_dependents": 1},
                 "defect": {
                     "rank": 3,
                     "lineage": "bug-against",
                     "rationale": "1 V1 target, 4 total downstream; bug against story:old",
                     "components": {"target_impact": 1, "total_dependents": 4},
                 },
             }),
    ], priority={"recommendations": ["story:new"]})

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)

    assert data["edges"] == []
    assert data["relations"] == [[0, 1, "revises"]]
    assert data["nodes"][0]["rec"] == 1
    assert data["nodes"][0]["pu"] == 1
    assert data["nodes"][0]["dr"] == 3
    assert data["nodes"][0]["dt"] == 1
    assert data["nodes"][0]["dd"] == 4
    assert data["nodes"][0]["dl"] == "bug-against"
    assert "known-reach rank" in html and "known graph reach" in html
    assert "reverse lineage" in html


def test_constellation_draws_foundation_group_targets_as_nonblocking_relations(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab,
                  groups=[Group(id="foundation:coordinate-truth", kind="foundation",
                                title="Coordinate Truth")],
                  items=[Item(id="story:line", title="Line", status="ready",
                              relations=[Relation(
                                  kind="foundation_root",
                                  target="foundation:coordinate-truth",
                              )])])

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)

    assert data["edges"] == []
    assert data["relations"] == [[0, 1, "foundation_root"]]
    assert data["nodes"][1]["foundation"] == 1
    assert data["nodes"][1]["t"] == "Coordinate Truth"
    assert "foundations" not in data["caps"]
    assert "foundation:'foundation'" in html
    # Synthetic relation targets still need a layout cluster. They remain out
    # of product completion counts instead of crashing on DATA.caps[...].total.
    assert "const layoutTotals = {};" in html
    assert "Math.sqrt(layoutTotals[n.c])" in html
    assert "DATA.caps[n.c].total" not in html


def test_constellation_activity_lens_pulses_only_explicit_fresh_work_links(tmp_path):
    graph = _graph()
    graph.active_work = [
        ActiveWork(
            story_id="story:a", agent="Galileo", task="Implement activity lens",
            state="active", completed=2, total=4,
            updated_at="2026-08-08T17:00:00Z",
            stale_at="2099-08-08T19:00:00Z", checkpoint="edge rendering",
            related_story_ids=["story:b"],
        ),
        ActiveWork(
            story_id="story:b", agent="Kepler", task="Old review",
            state="active", completed=0, total=0,
            updated_at="2020-08-08T17:00:00Z",
            stale_at="2020-08-08T19:00:00Z",
        ),
    ]

    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    data = _data(html)

    assert data["nodes"][0]["aw"] == [0]
    assert data["nodes"][1]["aw"] == [1]
    assert data["workLinks"] == [[0, 1]]
    assert data["work"][0]["done"] == 2 and data["work"][0]["total"] == 4
    assert "Date.now()<Date.parse(w.staleAt)" in html
    assert "const activeNode" in html
    assert "Explicit agent-work linkage pulses" in html
    assert "activeCount===2" in html and "activeCount===2?.55:.22" in html
    assert "ctx.setLineDash([4,4])" in html  # typed relation, not hard dependency


def test_constellation_work_keyboard_navigation_executes_recency_and_focus_contract(tmp_path):
    html = render_all(
        _work_navigation_graph(), Config(data=DEFAULTS), tmp_path,
        only={"constellation"},
    )["constellation.html"]
    node = shutil.which("node")
    assert node is not None, "Node is required to execute constellation JavaScript tests"
    completed = subprocess.run(
        [node, "-e", _CONSTELLATION_WORK_NAVIGATION_DOM_SHIM], input=html,
        text=True, capture_output=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    state = json.loads(completed.stdout)["workNavigation"]

    # Source serialization is Story-ID ordered; these lanes prove timestamps,
    # state, freshness, and per-Story deduplication own navigation instead.
    assert state["activeIndexes"] == ["story:b", "story:a"]
    assert state["recentIndexes"] == [
        "story:d", "story:c", "story:a", "story:b",
    ]
    assert state["activeNewest"] == "B"
    assert state["activeOlder"] == "A"
    assert state["activeWrap"] == "B"
    assert state["activeReverseWrap"] == "A"
    assert state["activeEntryPrevented"] is True
    assert state["recentOlder"] == "C"
    assert state["recentNewer"] == "D"
    assert state["recentWrap"] == "D"

    assert state["inputPrevented"] is False and state["inputPreserved"] == "C"
    assert state["modifiedPrevented"] is False and state["modifiedPreserved"] == "C"
    assert state["handledPreserved"] == "C"
    assert state["separatorPrevented"] is False and state["separatorPreserved"] == "C"
    assert state["closedPrevented"] is False and state["closedPreserved"] == "C"
    assert "active 2" in state["hint"] and "recent 4" in state["hint"]
    assert state["shortcuts"] == "ArrowLeft ArrowRight ArrowUp ArrowDown"


def test_constellation_work_keyboard_navigation_physical_browser_smoke(tmp_path):
    html = render_all(
        _work_navigation_graph(), Config(data=DEFAULTS), tmp_path,
        only={"constellation"},
    )["constellation.html"]
    chrome = next((candidate for candidate in (
        shutil.which("google-chrome"), shutil.which("chromium"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ) if candidate and Path(candidate).is_file()), None)
    if chrome is None:
        pytest.skip("Chrome is required for physical work-navigation acceptance")
    script = Path(__file__).with_name("browser_work_navigation_smoke.js")
    completed = subprocess.run(
        [shutil.which("node") or "node", str(script), chrome], input=html,
        text=True, capture_output=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "active": ["story:b", "story:a", "story:b"],
        "recent": ["story:c", "story:d"],
        "inputPreserved": "story:c",
        "inputValue": "draft",
        "filterIndependent": "story:b",
        "hint": {"active": True, "recent": True},
    }


def test_constellation_agent_trails_follow_only_recent_explicit_checkpoints(tmp_path):
    graph = _graph()
    graph.active_work = [
        ActiveWork(
            story_id=story_id, agent="Galileo", task=f"round {round_number}",
            state="complete" if round_number < 6 else "active",
            completed=round_number, total=6,
            updated_at=f"2026-08-0{round_number}T12:00:00Z",
            stale_at="2099-08-08T19:00:00Z",
        )
        for round_number, story_id in enumerate(
            ["story:a", "story:a", "story:b", "story:a", "story:b", "story:a"],
            1,
        )
    ] + [ActiveWork(
        story_id="story:b", agent="Kepler", task="single checkpoint",
        state="active", completed=1, total=1,
        updated_at="2026-08-07T12:00:00Z",
        stale_at="2099-08-08T19:00:00Z",
    )]
    cfg = Config(data=deep_merge(DEFAULTS, {"activity": {"trail_rounds": 3}}))

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)

    assert data["agentTrails"] == [{
        "agent": "Galileo",
        "points": [
            {"n": 0, "at": "2026-08-04T12:00:00Z", "state": "complete", "task": "round 4"},
            {"n": 1, "at": "2026-08-05T12:00:00Z", "state": "complete", "task": "round 5"},
            {"n": 0, "at": "2026-08-06T12:00:00Z", "state": "active", "task": "round 6"},
        ],
    }]
    assert "Straight agent trails connect only explicit chronological checkpoints" in html
    assert "const recency=step/Math.max(1,points.length-1)" in html
    assert "trailArrow(P[a],P[b],color,alpha)" in html


def test_constellation_uses_lightweight_outline_glyphs_and_strong_activity_pulse(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "ctx.strokeStyle=col;ctx.lineWidth=1.5;trianglePath" in html
    assert "ctx.strokeStyle=col;ctx.lineWidth=1.5;\n      xPath" in html
    assert "ctx.strokeStyle = col; ctx.lineWidth = 1;" in html
    assert "1.72+.58*activeWave" in html and "2.35+.42*activeWave" in html
    assert "ctx.filter" not in html


def test_constellation_excludes_interactive_chrome_from_canvas_targets(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "function canvasInteractionBounds()" in html
    assert "return {left:compact?0:236,top:106" in html
    assert "right:drawerOpen?(compact?0:Math.max(236,dossier.getBoundingClientRect().left)):W" in html
    assert "p.on = visible(n)&&insideCanvasInteractionBounds" in html
    assert "context.rect(bounds.left,bounds.top" in html
    assert "for(const context of [bgctx,nodeCtx])context.restore()" in html
    assert "if(target>=0)openNode(target)" in html
    assert "if(target>=0&&P[target].on)" not in html
    assert "#hint{" in html and "pointer-events:none" in html.split("#hint{", 1)[1].split("}", 1)[0]


def test_constellation_only_shows_explicit_researched_owner_questions(tmp_path):
    graph = _graph()
    graph.active_work = [ActiveWork(
        story_id="story:b", agent="Ryder", task="Capture 588-row cadence evidence",
        state="blocked", completed=1, total=3,
        updated_at="2020-08-08T17:00:00Z",
        stale_at="2020-08-08T19:00:00Z",
        checkpoint="Run the archived corpus",
    )]
    graph.owner_questions = [OwnerQuestion(
        id="question:hit-priority",
        story_id="story:a",
        owner="Ryder",
        prompt="Should close-target or handle hit win?",
        options=[
            OwnerQuestionOption("nearest", "Nearest", "Preserves geometric priority."),
            OwnerQuestionOption("close", "Close", "Makes path closure easier."),
        ],
        recommendation=OwnerQuestionRecommendation(
            "nearest", "Shared hit-test truth should remain authoritative.",
        ),
        falsifier="User testing shows nearest makes closure unreliable.",
        evidence=["wiki/product-spec/close-target.md:42"],
    )]

    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    data = _data(html)

    assert data["work"][0]["state"] == "blocked"
    assert data["nodes"][0]["oq"] == [0]
    assert "oq" not in data["nodes"][1]
    assert data["questions"][0]["prompt"] == "Should close-target or handle hit win?"
    assert "const ownerQuestions = i =>\n  (DATA.nodes[i].oq||[])" in html
    assert "const unresolved=ownerQuestions(i)" in html
    assert "xPath(p.x,p.y,Math.max(4,rr*.72))" in html
    assert "const questionAttentionRadius = i => actionableQuestion(i)" in html
    assert "?Math.max(28,nodeRadius(i)*3.25):Math.max(22,nodeRadius(i)*2.5)" in html
    assert "questionHitRadius" not in html
    assert "if(unresolved.length>1)" in html
    assert "Never infer them from a" in html
    assert "[w.state,stale?'stale':'']" in html
    assert "questioncard" in html
    assert ".workcard.blocked{border-color:var(--buggap)}" in html
    assert _search_ids(data, "geometric priority") == ["story:a"]
    assert _search_ids(data, "588 cadence") == ["story:b"]


def test_owner_question_text_cannot_escape_script_or_dossier_html(tmp_path):
    graph = _graph()
    attack = "</script><img src=x onerror=alert(1)>"
    graph.owner_questions = [OwnerQuestion(
        id="question:payload",
        story_id="story:a",
        owner="Ryder",
        prompt=attack,
        options=[
            OwnerQuestionOption("safe", "Safe", attack),
            OwnerQuestionOption("unsafe", "Unsafe", "Reject this."),
        ],
        recommendation=OwnerQuestionRecommendation("safe", attack),
        falsifier=attack,
        evidence=[attack],
    )]

    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    data = _data(html)

    assert data["questions"][0]["prompt"] == attack
    assert "</script><img src=x onerror=alert(1)>" not in html
    assert "<\\/script><img src=x onerror=alert(1)>" in html
    assert "${esc(q.prompt)}" in html


def test_constellation_lenses_are_accessible_and_reduced_motion_is_semantic(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "['progress','Progress']" in html
    assert "aria-pressed" in html and "aria-label','Graph lenses" in html
    assert "prefers-reduced-motion: reduce" in html
    assert "const reducedMotion" in html
    assert "const pulse=reducedMotion?.78" in html
    assert "ctx.lineDashOffset=reducedMotion?0" in html


def test_constellation_declares_utf8_uses_vector_icons_and_supports_command_pan(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert html.startswith('<meta charset="utf-8">')
    assert 'id="sym-xmark"' in html
    assert 'id="sym-star-fill"' in html
    assert 'id="sym-arrow-up-right"' in html
    assert '<kbd>&#8984;</kbd> + two-finger pan' in html
    assert "let rx=-.35, ry=.6, zoom=1, panX=0, panY=0" in html
    assert "if (e.ctrlKey){ // trackpad pinch" in html
    assert "else if (e.metaKey){ // Command + two-finger scroll pans" in html
    assert "panX -= e.deltaX; panY -= e.deltaY;" in html
    assert "cxp=W/2+40+panX, cyp=H/2+panY" in html
    assert "if(pointerActive&&!orbiting)updatePointerAt(pointerX,pointerY)" in html
    assert "project();updatePointerAt(e.clientX,e.clientY);" in html
    assert "#cv.hover-target{cursor:pointer}" in html
    assert "selection-mode" not in html


def test_constellation_renders_semantic_progress_trails_and_capped_stall_markers(tmp_path):
    graph = _graph()
    graph.items[0].progress = {
        "events": [{"at": "2026-08-09T00:00:00Z", "kind": "lifecycle",
                    "source": "story lifecycle header", "detail": "ready → building"}],
        "hotWindowDays": 7,
        "stall": {"since": "2023-01-01T00:00:00Z",
                  "source": "story lifecycle header", "afterDays": 14,
                  "maxDays": 90},
    }
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    data = _data(html)
    assert data["nodes"][0]["pg"]["events"][0]["kind"] == "lifecycle"
    assert data["nodes"][0]["pg"]["stall"]["maxDays"] == 90
    assert "Circle-check marks are a static history trail" in html
    assert "blocked.days/Math.max(1,blocked.maxDays)" in html
    assert "const nodeBadgeRadius = rr => Math.max(1.5,Math.min(8,rr*.42))" in html
    assert "const {x,y}=nodeBadgePoint(p,rr,markerBase,1,order)" in html
    assert "const {x,y}=nodeBadgePoint(p,rr,radius,-1,unresolved.length?1:0)" in html
    assert "const distance=rr+radius*.12" in html
    assert "order*markerBase*1.8" not in html
    assert "const radius=Math.min(10,markerBase*(1+.25*ageRatio))" in html
    assert "Staleness is evidence age, not an owner question" in html
    assert "ctx.lineTo(x+markerBase*.5,y-markerBase*.34)" in html
    assert "const ageDays = at =>" in html
    assert "role=\"tooltip\"" in html and "progressText" in html


def test_constellation_owner_questions_use_one_static_centered_blocker_x(tmp_path):
    graph = _graph()
    graph.owner_questions = [OwnerQuestion(
        id="question:visible",
        story_id="story:a",
        owner="Ryder",
        prompt="Which authority wins?",
        options=[OwnerQuestionOption(id="a", label="A", tradeoff="Tradeoff")],
        recommendation=OwnerQuestionRecommendation(option_id="a", rationale="Because"),
        falsifier="A counterexample",
        evidence=["s/a.md"],
    )]
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "Owner decisions use one centered, static X" in html
    assert "xPath(p.x,p.y,Math.max(4,rr*.72));ctx.stroke()" in html
    assert "questionWavePhase" not in html
    assert "questionPulse" not in html
    assert "for(const offset of [0,.5])" not in html


def test_constellation_pulses_only_actionable_owner_questions(tmp_path):
    graph = _graph()
    graph.active_work = [ActiveWork(
        story_id="story:a", agent="Ryder", task="Waiting for owner direction",
        state="blocked", completed=0, total=1,
        updated_at="2026-08-11T07:00:00Z",
        stale_at="2099-08-11T08:00:00Z",
    )]
    graph.owner_questions = [OwnerQuestion(
        id="question:blocked", story_id="story:a", owner="Ryder",
        prompt="Which path?",
        options=[OwnerQuestionOption(id="a", label="A", tradeoff="Tradeoff")],
        recommendation=OwnerQuestionRecommendation(option_id="a", rationale="Because"),
        falsifier="A counterexample", evidence=["s/a.md"],
    )]
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "const questionStopsWork = i =>" in html
    assert "DATA.work[wi]?.state==='blocked'" in html
    assert "const actionableQuestion = i => ownerQuestions(i).length>0" in html
    assert "questionStopsWork(i)||Boolean(DATA.nodes[i].rec)" in html
    assert "if(actionableQuestion(i)&&!dim)" in html
    assert "ctx.strokeStyle=C.owner;ctx.lineWidth=1.5" in html
    assert "const [innerRadius,outerRadius]=questionRingRadii(i)" in html
    assert "questionRingHitTolerance" not in html
    assert "pulsePaintDistance" not in html
    assert "const nodePaintRadius = i =>" in html
    assert "function questionGlyphPaintDistance(i,x,y)" in html
    assert "glyphPaintDistance<=2.5" in html
    assert "hover=questionCenterBest>=0?questionCenterBest:" in html
    assert "(questionGlyphBest>=0?questionGlyphBest:(paintBest>=0?paintBest:best))" in html
    assert ".62+.12*activeWave" in html and ".82+.16*activeWave" in html


def test_constellation_question_blocker_is_explicit_and_actionable(tmp_path):
    graph = _graph()
    graph.owner_questions = [OwnerQuestion(
        id="question:visible", story_id="story:a", owner="Ryder",
        prompt="Which authority wins?",
        options=[OwnerQuestionOption(id="a", label="A", tradeoff="Tradeoff")],
        recommendation=OwnerQuestionRecommendation(option_id="a", rationale="Because"),
        falsifier="A counterexample", evidence=["s/a.md"],
    )]
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert '<div class="questionblocker" role="status">' in html
    assert "Blocked — answer required" in html
    assert "must be resolved before this story is dispatchable" in html
    assert "decision required · ${esc(q.owner)}" in html
    assert "currentQuestionButtonLabel" in html
    assert "blocked stor${questionStories===1?'y':'ies'}" in html
    assert '#meterlab .questioncount{border:1px solid var(--owner-override)' in html


def test_constellation_question_count_filters_explicit_records_independently_of_activity_lens(tmp_path):
    graph = _graph()
    graph.owner_questions = [OwnerQuestion(
        id="question:visible",
        story_id="story:a",
        owner="Ryder",
        prompt="Which authority wins?",
        options=[OwnerQuestionOption(id="a", label="A", tradeoff="Tradeoff")],
        recommendation=OwnerQuestionRecommendation(option_id="a", rationale="Because"),
        falsifier="A counterexample",
        evidence=["s/a.md"],
    )]
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "let areaFocus=null" in html
    assert "let capFocus = null, groupFocus = null, sel = -1, hover = -1, questionOnly = false" in html
    assert "const nodeHasOwnerQuestions = n => (n.oq||[]).length>0" in html
    assert "(!questionOnly || nodeHasOwnerQuestions(n))" in html
    assert "const all = k===0 || (!questionOnly && !capFocus" in html
    assert "questionFilter.disabled=questions===0&&!questionOnly" in html
    assert "const questionStories=metricNodes.filter(nodeHasOwnerQuestions).length" in html
    assert "questionFilter.setAttribute('aria-pressed',String(questionOnly))" in html
    assert "not optional Activity-lens decoration" in html
    assert "const ownerQuestions = i =>\n  (DATA.nodes[i].oq||[])" in html
    assert "if(questionOnly&&!lens.activity)" not in html
    assert "if(key==='activity'&&!lens[key]&&questionOnly)setQuestionFilter(false)" not in html
    assert "lensButtons[key]=b" in html
    assert "if(sel>=0&&!visible(DATA.nodes[sel]))" not in html
    assert "function applyViewState(focusFallback=null)" in html
    assert "refreshDossier();" in html
    assert "visibleQuestionCount+=(node.oq||[]).length" in html
    assert "No stories with owner questions match the current filters." in html
    assert "questionOnly?'Remove owner-question filter'" in html
    assert "bindToggleOrSolo(b,g,Object.keys(GLAB),filt,syncLifecycle)" in html
    assert "for(const candidate of keys)state[candidate]=candidate===key" in html
    assert "bindToggleOrSolo(b,r,RELS,rfilt,syncSeg)" in html
    assert "const alreadySelected=capFocus===capability&&groupFocus===groupId" in html
    assert "button=>selectHierarchy(button,capability)" in html
    assert "tip.style.display='none'" in html and "cv.classList.remove('hover-target')" in html
    assert "let currentQuestionCountLabel=''" in html
    assert "`${action}. ${currentQuestionCountLabel}.`" in html
    assert "const metricNodes=deliveryNodes.filter" in html
    assert "const nodes=deliveryNodes.filter(n=>meter.matches(n)" in html
    assert "capabilityMeters.set(key" in html
    assert 'id="dossier" aria-hidden="true"' in html
    assert "dossier.setAttribute('aria-hidden','false')" in html
    assert "document.getElementById('close').onclick = ()=>dismissDossier()" in html
    assert "event.key==='Escape'&&dossier.classList.contains('open')" in html
    assert "event.preventDefault();dismissDossier()" in html
    assert "document.documentElement.classList.add('dossier-open')" in html
    assert 'id="cv" role="application" tabindex="0"' in html


def test_constellation_filters_recompute_global_and_capability_counts(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "const metricNodes=deliveryNodes.filter" in html
    assert "shippedCount.textContent=`${shipped}/${metricNodes.length} delivery shipped`" in html
    assert "defectCount.textContent=`${bugGaps} bug gap${bugGaps===1?'':'s'} open`" in html
    assert "completionCount.textContent=completion.toFixed(0)+'%'" in html
    assert "const nodes=deliveryNodes.filter(n=>meter.matches(n)" in html
    assert "meter.count.textContent=`${capShipped}/${nodes.length}`" in html
    assert "meter.shipped.style.width=(100*capShipped/Math.max(1,nodes.length))" in html
    assert "meter.bugs.style.width=(100*capBugs/Math.max(1,nodes.length))" in html
    assert "const d=document.createElement('button')" in html
    assert "d.setAttribute('aria-pressed','false')" in html
    assert "meter.element.setAttribute('aria-label'" in html
    assert "bindToggleOrSolo(b,r,RELS,rfilt,syncSeg)" in html
    assert "updateVisibleCounts();" in html


def test_constellation_version_filter_executes_dynamic_count_updates(tmp_path):
    cfg = Config(data=deep_merge(DEFAULTS, {
        "render": {"recommended": ["story:r0-done", "story:r1-done"]},
    }))
    graph = Graph(
        vocab=cfg.vocab,
        groups=[Group(id="capability:c", kind="capability", title="Cap")],
        items=[
            Item(id="story:r0-done", title="R0 done", status="shipped",
                 release="R0", group="capability:c"),
            Item(id="story:r0-bug", title="R0 bug", status="bug-gap",
                 release="R0", group="capability:c"),
            Item(id="story:r1-done", title="R1 done", status="shipped",
                 release="R1", group="capability:c"),
            Item(id="story:r1-open", title="R1 open", status="specced",
                 release="R1", group="capability:c"),
        ],
        owner_questions=[OwnerQuestion(
            id="question:r0", story_id="story:r0-bug", owner="Ryder",
            prompt="Choose?", options=[
                OwnerQuestionOption(id="a", label="A", tradeoff="A tradeoff"),
                OwnerQuestionOption(id="b", label="B", tradeoff="B tradeoff"),
            ], recommendation=OwnerQuestionRecommendation(
                option_id="a", rationale="A is recommended",
            ), falsifier="Counterexample", evidence=["story.md"],
        )],
        active_work=[
            ActiveWork(
                story_id="story:r0-done", agent="Ryder", task="Ship R0",
                state="active", completed=1, total=2,
                updated_at="2026-08-10T17:00:00Z",
                stale_at="2099-08-10T19:00:00Z",
            ),
            ActiveWork(
                story_id="story:r1-done", agent="Ryder", task="Ship R1",
                state="active", completed=2, total=2,
                updated_at="2026-08-10T18:00:00Z",
                stale_at="2099-08-10T20:00:00Z",
            ),
        ],
    )
    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    node = shutil.which("node")
    assert node is not None, "Node is required to execute constellation JavaScript tests"
    completed = subprocess.run(
        [node, "-e", _CONSTELLATION_COUNT_DOM_SHIM], input=html,
        text=True, capture_output=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    state = json.loads(completed.stdout)

    assert state["initial"] == {
        "shipped": "2/4 delivery shipped", "bugs": "1 bug gap open",
        "questions": "1 answer required · 1 blocked story",
        "completion": "50%", "items": "4 items", "capCount": "2/4",
        "capShipped": "50.0%", "capBugs": "25.0%",
        "capLabel": "All work, 2 of 4 delivery items shipped, 1 bug gap open",
    }
    assert state["r0"] == {
        "shipped": "1/2 delivery shipped", "bugs": "1 bug gap open",
        "questions": "1 answer required · 1 blocked story",
        "completion": "50%", "items": "2 items", "capCount": "1/2",
        "capShipped": "50.0%", "capBugs": "50.0%",
        "capLabel": "All work, 1 of 2 delivery items shipped, 1 bug gap open",
    }
    assert state["routes"] == {
        "dashboard": {"cards": 2, "metrics": [], "rows": 0},
        "roadmap": {"cards": 4, "metrics": [], "rows": 0},
        "structure": {"cards": 4, "metrics": [], "rows": 0},
        "features": {"cards": 4, "metrics": [], "rows": 0},
        "completion": {
            "cards": 0,
            "metrics": [2, 1, 0, 0, 1, 0, 0, 0, 1],
            "rows": 0,
        },
        "workstreams": {"cards": 0, "metrics": [], "rows": 0},
        "ledgers": {"cards": 2, "metrics": [], "rows": 2},
    }
    assert state["routesR0"] == {
        "dashboard": {"cards": 1, "metrics": [], "rows": 0},
        "roadmap": {"cards": 2, "metrics": [], "rows": 0},
        "structure": {"cards": 2, "metrics": [], "rows": 0},
        "features": {"cards": 2, "metrics": [], "rows": 0},
        "completion": {
            "cards": 0,
            "metrics": [1, 1, 0, 0, 0, 0, 0, 0, 1],
            "rows": 0,
        },
        "workstreams": {"cards": 0, "metrics": [], "rows": 0},
        "ledgers": {"cards": 1, "metrics": [], "rows": 1},
    }
    assert state["reconcile"] == {
        "view": "roadmap",
        "selectedTitle": "R0 bug",
        "dossierOpen": True,
        "dossierHidden": "false",
        "search": "R0 bug",
        "r1": False,
        "camera": [.125, .75, 1.4, 31, -19, 2, 3, 4, 5, 6, 7],
        "openQuestions": 0,
        "decisions": 1,
    }
    assert state["constellation"] == {
        "panelHidden": True, "canvasHidden": False,
    }
    assert state["microJitterClick"] == {
        "selected": True, "dossierOpen": True, "cameraStable": True,
    }
    assert state["expandedHitTarget"] == {
        "selected": True, "dossierOpen": True,
    }
    assert state["cancelGesture"] == {
        "pointerDown": False, "orbiting": False, "drag": False,
        "captured": False,
    }
    assert state["orbitGesture"] == {
        "selected": False, "dossierOpen": False,
    }


def test_constellation_question_cards_are_selectable_but_static_files_are_read_only(tmp_path):
    graph = _graph()
    graph.owner_questions = [OwnerQuestion(
        id="question:visible", story_id="story:a", owner="Ryder",
        prompt="Which authority wins?",
        options=[
            OwnerQuestionOption(id="a", label="A", tradeoff="Tradeoff A"),
            OwnerQuestionOption(id="b", label="B", tradeoff="Tradeoff B"),
        ],
        recommendation=OwnerQuestionRecommendation(option_id="a", rationale="Because"),
        falsifier="A counterexample", evidence=["s/a.md"],
    )]
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert '<form class="questioncard" data-question-id=' in html
    assert 'type="radio"' in html and 'data-question-option' in html
    assert 'data-question-custom' in html and "Suggest something else" in html
    assert 'maxlength="2000"' in html and 'data-question-text' in html
    assert 'data-question-queue' in html
    assert "Provide ${questions.length===1?'answer'" in html
    assert 'data-chat-primary' in html and 'data-chat-overflow' in html
    assert "0 of ${questions.length} ready" in html
    assert "const writable=Boolean(SERVED&&questionContext&&!questionError)" in html
    assert "Read-only file · run vizzer serve to answer" in html
    assert "expectedFingerprint:q.fingerprint" in html
    assert "async function preflightQuestionAuthority(forms)" in html
    assert "fetch('/api/questions',{cache:'no-store'})" in html
    assert "Reload this page before answering" in html
    assert "await preflightQuestionAuthority(forms)" in html
    assert "fetch('/api/questions/answers'" in html
    assert "reconcileAcceptedDecisions(body.decisions,body.revision,{showFromTop:true})" in html
    assert "location.reload()" not in html.split("function bindQuestionControls(n){", 1)[1].split("function planSection", 1)[0]
    assert "function refreshDossier()" in html
    assert "const previousScrollExtent=inPlace&&sel===i?(dbody.scrollHeight||0):0" in html
    assert "data-scroll-preserver" in html
    assert "overflow-anchor:none" in html
    assert "if(inPlace)requestAnimationFrame" not in html
    # Recommendation is a visible hint; it must not silently preselect a radio.
    assert "draft.kind==='option'&&draft.optionId===option.id?'checked':''" in html
    queue_logic = html.split("function bindQuestionControls(n){", 1)[1].split(
        "function planSection", 1)[0]
    assert "location.reload()" not in queue_logic
    assert "fetch('/api/questions/answers'" in queue_logic
    assert "count!==forms.length" in queue_logic
    assert "reconcileAcceptedDecisions(body.decisions,body.revision,{showFromTop:true})" in queue_logic
    reconcile = html.split("function reconcileAcceptedDecisions", 1)[1].split(
        "function planSection", 1)[0]
    assert "refreshDossier()" in reconcile
    assert "questionDrafts.delete(q.id)" not in reconcile
    assert "Selected · ready to answer" in queue_logic
    assert "questionSubmissionError||countText" in queue_logic
    assert "if(dossierFooter.contains(queue))syncQueue();else refreshDossier()" in queue_logic
    assert "queueButton.setAttribute('aria-disabled',String(queueButton.disabled))" in queue_logic
    assert ".questionqueuefooter{position:sticky;bottom:0" in html
    assert "else if(sel>=0){sel=-1" not in html
    for reset in ("rx=", "ry=", "zoom=", "panX=", "panY=", "currentView="):
        assert reset not in reconcile
    assert "const ownerDecisions = i =>\n  (DATA.nodes[i].od||[])" in html


def test_constellation_physical_option_click_keeps_dossier_open_and_enables_answer(tmp_path):
    graph = _graph()
    graph.owner_questions = [OwnerQuestion(
        id="question:physical", story_id="story:a", owner="Ryder",
        prompt="Which authority wins?",
        options=[OwnerQuestionOption(id="a", label="A", tradeoff="Tradeoff")],
        recommendation=OwnerQuestionRecommendation(option_id="a", rationale="Because"),
        falsifier="A counterexample", evidence=["s/a.md"],
    ), OwnerQuestion(
        id="question:physical-freeform", story_id="story:a", owner="Ryder",
        prompt="What alternative should we preserve?",
        options=[OwnerQuestionOption(id="b", label="B", tradeoff="Tradeoff B")],
        recommendation=OwnerQuestionRecommendation(option_id="b", rationale="Because B"),
        falsifier="Another counterexample", evidence=["s/a.md"],
    )]
    cfg = Config(data=deep_merge(DEFAULTS, {
        "render": {"recommended": ["story:a", "story:b"]},
    }))
    html = render_all(graph, cfg, tmp_path,
                      only={"constellation"})["constellation.html"]
    chrome = next((candidate for candidate in (
        shutil.which("google-chrome"), shutil.which("chromium"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ) if candidate and Path(candidate).is_file()), None)
    if chrome is None:
        pytest.skip("Chrome is required for the physical dossier click smoke")
    script = Path(__file__).with_name("browser_dossier_click_smoke.js")
    completed = subprocess.run(
        [shutil.which("node") or "node", str(script), chrome], input=html,
        text=True, capture_output=True, timeout=35,
        env={**os.environ, "VIZZER_BROWSER_TERM_GRACE_MS": "0"},
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "checked": True, "customChecked": True, "freeform": "Keep it exact.",
        "dossierOpen": True, "hidden": "false",
        "selected": 0, "expected": 0, "buttonDisabled": False,
        "buttonText": "Provide 2 answers",
        "statuses": ["Selected · ready to answer", "Selected · ready to answer"],
        "queue": "2 selected · 0 remaining",
        "drafts": [
            {"kind": "option", "optionId": "a", "text": ""},
            {"kind": "freeform", "optionId": "", "text": "Keep it exact."},
        ],
        "queueButtons": 5, "outerScroll": 0,
        "headerVisible": True, "bodyVisible": True, "rectInside": True,
        "backgroundPointerEvents": "none", "backgroundOwnsHit": False,
        "actionLayout": {"pinned": True, "below": True, "leftAligned": True},
        "stalePreflight": {
            "error": f"Vizzer version mismatch (page {__version__}, server 0.0.0). Reload this page before answering.",
            "postCalls": 0, "retryAvailable": True, "dossierOpen": True,
            "selected": 0, "scroll": 80, "route": "constellation",
            "drafts": [
                {"kind": "option", "optionId": "a", "text": ""},
                {"kind": "freeform", "optionId": "", "text": "Keep it exact."},
            ],
            "before": {
                "selected": 0, "scroll": 80, "route": "constellation",
                "drafts": [
                    {"kind": "option", "optionId": "a", "text": ""},
                    {"kind": "freeform", "optionId": "", "text": "Keep it exact."},
                ],
            },
        },
        "failedSubmit": {
            "error": "refresh exploded", "retryAvailable": True,
            "buttonText": "Provide 2 answers", "dossierOpen": True,
            "selected": 0, "scroll": 80, "route": "constellation",
            "search": "A", "r1": False,
            "camera": [.125, .75, 1.4, 31, -19],
            "drafts": [
                {"kind": "option", "optionId": "a", "text": ""},
                {"kind": "freeform", "optionId": "", "text": "Keep it exact."},
            ],
            "before": {
                "selected": 0, "scroll": 80, "route": "constellation",
                "search": "A", "r1": False,
                "camera": [.125, .75, 1.4, 31, -19],
                "drafts": [
                    {"kind": "option", "optionId": "a", "text": ""},
                    {"kind": "freeform", "optionId": "", "text": "Keep it exact."},
                ],
            },
            "submitted": {
                "calls": 1, "revision": 0,
                "ids": ["question:physical", "question:physical-freeform"],
                "kinds": ["option", "freeform"],
                "freeform": "Keep it exact.",
            },
        },
        "successfulRetry": {
            "calls": 2, "dossierOpen": True, "selected": 0, "scroll": 0,
            "route": "constellation", "search": "A", "r1": False,
            "camera": [.125, .75, 1.4, 31, -19],
            "drafts": [
                {"kind": "option", "optionId": "a", "text": ""},
                {"kind": "freeform", "optionId": "", "text": "Keep it exact."},
            ],
            "openQuestions": 0, "decisions": 2, "answeredCards": 2,
            "queueGone": True, "metadataVisible": True, "spacerGone": True,
        },
        "generalDiscussion": {
            "label": "Chat · Claude", "provider": "claude", "storyId": "story:a",
            "questions": [], "revision": 1, "position": 0,
            "dossierOpen": True, "selected": 0, "answerQueueAbsent": True,
            "chatPresent": True, "status": "Queued first · claude",
        },
        "responsive": {
            "viewport": [360, 320], "pageFits": True,
            "headerFits": True, "navOneRow": True,
            "countsSecond": True, "chipsAfterCounts": True,
            "panelMoved": True, "panelScrollable": True,
            "canvasHidden": True, "panelVisible": True,
            "wideCard": {
                "route": "dashboard", "dossierOpen": True, "selected": 0,
            },
            "narrowDrawer": {
                "left": 0, "right": 360, "width": 360,
                "fullWidth": True, "handleHidden": True,
                "bodyFits": True, "pageFits": True,
            },
        },
        "drawerResize": {
            "grew": True, "keyboardShrank": True, "ariaMatches": True,
            "stored": True, "panelMeetsDrawer": True, "bodyFits": True,
            "reloadedCompact": True, "restored": True,
        },
    }
def test_constellation_exact_target_cards_and_lifecycle_hold_execute(tmp_path):
    graph = _graph()
    graph.owner_questions = [OwnerQuestion(
        id="question:exact", story_id="story:b", owner="Ryder",
        prompt="Choose the exact story?", options=[
            OwnerQuestionOption(id="a", label="A", tradeoff="Tradeoff A"),
            OwnerQuestionOption(id="b", label="B", tradeoff="Tradeoff B"),
        ], recommendation=OwnerQuestionRecommendation(
            option_id="a", rationale="Because",
        ), falsifier="Counterexample", evidence=["s/b.md"],
    )]
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    node = shutil.which("node")
    assert node is not None, "Node is required to execute constellation JavaScript tests"
    completed = subprocess.run(
        [node, "-e", _CONSTELLATION_INTERACTION_DOM_SHIM], input=html,
        text=True, capture_output=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    state = json.loads(completed.stdout)

    assert state["overlapTarget"] == {
        "selected": 1, "expected": 1, "title": "B",
    }
    assert state["crossingQuestionXCenterTarget"] == {
        "selected": 1, "hover": 1, "expected": 1, "title": "B",
    }
    assert state["paintedQuestionXEndpointTarget"] == {
        "selected": 1, "hover": 1, "expected": 1, "title": "B",
    }
    assert state["advertisedHoverTarget"] == {
        "selected": 1, "advertised": 1, "expected": 1, "title": "B",
    }
    assert state["nearbyStoryTarget"] == {
        "selected": 0, "expected": 0, "title": "A",
    }
    assert state["decorativePulseNearestStory"] == {
        "selected": 0, "expected": 0, "title": "A",
    }
    assert state["decorativeRingDoesNotCaptureStory"] == {
        "selected": 0, "expected": 0, "title": "A",
    }
    assert state["hiddenTarget"] == {
        "selected": 1, "expected": 1, "hover": 1, "pointer": True,
    }
    assert state["selectionMatrix"] == {"cases": 144, "failures": []}
    assert state["resizeSync"] == {
        "W": 913, "H": 577, "canvasWidth": 913, "backgroundWidth": 913,
    }
    assert state["questionBadgeTarget"] == {
        "selected": 1, "expected": 1, "open": True,
    }
    assert state["pointerPresentation"] == {
        "question": {"hover": 1, "cursor": True},
        "story": {"hover": 0, "cursor": True},
        "empty": {"hover": -1, "cursor": False},
    }
    assert state["cardTarget"] == {
        "selected": 1, "expected": 1, "title": "B",
        "open": True, "scrollTop": 0,
    }
    assert state["lifecycleHold"] == {
        "active": True, "ready": False,
        "activePressed": "true", "readyPressed": "false",
    }
    assert state["releaseHold"] == {
        "r0": False, "r1": True,
        "r0Pressed": "false", "r1Pressed": "true",
    }


def test_constellation_dossier_pins_identity_and_compact_summary_above_scroll_body(tmp_path):
    graph = _graph()
    graph.items[0].one_liner = "A concise story summary that remains visible while evidence scrolls."
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    data = _data(html)

    assert data["nodes"][0]["summary"] == graph.items[0].one_liner
    assert '<header id="dossierhead"><div id="dossieridentity"></div>' in html
    assert '<div id="dbody"></div>' in html
    assert "#dossier{position:fixed;right:0;top:106px;bottom:0;width:var(--dossier-width);min-width:320px;max-width:calc(100vw - 260px);display:flex;flex-direction:column;overflow:hidden;overflow:clip" in html
    assert 'id="dossierresize"' in html
    assert "dossier.getBoundingClientRect().left" in html
    assert "#dossierhead{position:relative;z-index:3;flex:none" in html
    assert ".kv{font-size:12px;line-height:1.35" in html
    assert "grid-template-columns:70px 1fr;gap:7px 10px" in html
    assert "#dbody{min-width:0;min-height:0;flex:1;overflow-x:hidden;overflow-y:auto" in html
    assert "transform:translateX(105%);transition:none" in html
    assert "transition:transform .22s ease" not in html
    assert "-webkit-line-clamp:2" in html
    assert 'dossierIdentity.innerHTML=`<h2>${esc(n.t)}</h2><div class="dossierpills">' in html
    assert 'const pinnedSummary=n.summary||trail||\'\'' in html
    body_assignment = html.split("dbody.innerHTML = `", 1)[1].split("`;", 1)[0]
    assert "<h2>" not in body_assignment
    assert "class=\"pill\"" not in body_assignment


def test_constellation_separates_progress_version_opacity_and_has_proximity_hit_states(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    # Fill progress and version ring are independently decodable and each
    # clamps to the owner-requested 50–100% range.
    assert "const progressOpacity = n => .5+.5*(LIFECYCLE_PROGRESS[n.st]??0)" in html
    assert "const VERSION_OPACITY={R0:1,R1:.83,R2:.67,R3:.5,'R?':.5}" in html
    assert "ctx.globalAlpha = progressOpacity(n)*focusAlpha" in html
    assert "ctx.globalAlpha=versionOpacity(n)*focusAlpha" in html
    assert "% fill progress" in html and "% version ring" in html

    # Proximity is continuous; exact hit and persistent selection are distinct
    # rings. The old abrupt 1.7x hover-size mutation must not return.
    assert "const nodeHitRadius = i => Math.max(14,nodeRadius(i)+4)" in html
    assert "p.near=Math.max(0,1-Math.max(0,distance-hitRadius)/32)" in html
    assert "if(i===hover&&!dim)" in html
    assert "if(i===sel)" in html
    assert "i===hover||i===sel?1.7:1" not in html
    assert "distance<bestDistance-.25" in html
    assert "let pointerDown=false, orbiting=false, downTarget=-1" in html
    assert "if(target>=0)openNode(target)" in html
    assert "const orbitThreshold=6" in html
    assert "Math.hypot(e.clientX-downX,e.clientY-downY)>orbitThreshold" in html
    assert "project();updatePointerAt(e.clientX,e.clientY)" in html
    assert "cv.addEventListener('pointercancel'" in html


def test_constellation_routed_views_own_vertical_scroll_and_do_not_leave_canvas_event_shields(tmp_path):
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "#viewpanel{position:fixed" in html
    assert "bottom:0;z-index:3;min-height:0;overflow-x:auto;overflow-y:scroll" in html
    assert "overscroll-behavior:contain;touch-action:pan-x pan-y;scrollbar-gutter:stable" in html
    assert "#viewpanel[hidden]{display:none;pointer-events:none}" in html
    assert "#bgcv[hidden],#cv[hidden]{display:none;pointer-events:none}" in html
    assert '<canvas id="bgcv" aria-hidden="true"></canvas>' in html
    assert "#bgcv{pointer-events:none}" in html
    assert "#bgcv,#cv{position:fixed;inset:0;width:100vw;height:100vh}" in html
    assert "viewBackdrop.hidden=currentView!=='constellation'" in html
    assert "#top{position:fixed;top:0;left:0;right:0;display:grid" in html
    assert "#chips{grid-column:1 / -1;grid-row:3;display:flex;gap:6px;flex-wrap:nowrap" in html
    assert "overflow-x:auto" in html


def test_constellation_marks_owner_overrides_and_traces_punt_effects_on_real_edges(tmp_path):
    graph = _graph()
    graph.priority = {
        "planning": {
            "enabled": True,
            "revision": 3,
            "author": "owner",
            "rationale": "Change course deliberately",
            "promote": ["story:a"],
            "defer": ["story:b"],
            "order": ["story:a"],
        },
        "base_targets": ["story:b"],
        "effective_targets": ["story:a"],
    }
    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]
    data = _data(html)

    assert data["planning"]["author"] == "owner"
    assert data["planning"]["promote"] == ["story:a"]
    assert data["planning"]["defer"] == ["story:b"]
    assert "--owner-override:#E879F9" in html
    assert "--owner-override:#B832B8" in html
    assert "const ownerPromoted=new Set" in html
    assert "const ownerDeferred=new Set" in html
    assert "const ownerOrdered=new Map" in html
    assert "ownerOrdered.has(i)?'prioritized'" in html
    assert "puntImpactLinks.push([parent,child,source])" in html
    assert "downstream effects:" in html
    assert "affected by owner punt:" in html
    assert "ctx.strokeStyle=C.owner" in html
    assert "course==='punted'?[4,3]:[]" in html
    assert "owner ${ownerCourseText(best)}" in html


def test_constellation_boot_failure_is_visible_and_older_webkit_is_supported(tmp_path):
    """codex-sequence-2026-08-08: standalone HTML must not fail as a blank page."""
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert 'id="boot" role="status"' in html
    assert "addEventListener('error',function(event)" in html
    assert "Vizzer could not start." in html
    assert "typeof colorSchemeQuery.addEventListener==='function'" in html
    assert "typeof colorSchemeQuery.addListener==='function'" in html
    assert "window.__vizzerBoot.ready();" in html


def test_agent_activity_text_cannot_escape_script_payload(tmp_path):
    graph = _graph()
    graph.active_work = [ActiveWork(
        story_id="story:a", agent="</script><script>alert(9)</script>",
        task='<img src=x onerror="alert(10)">', state="active",
        completed=1, total=2, updated_at="2026-08-08T17:00:00Z",
        stale_at="2099-08-08T19:00:00Z",
    )]

    html = render_all(graph, Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert "</script><script>alert(9)" not in html
    assert _data(html)["work"][0]["agent"] == "</script><script>alert(9)</script>"


def test_constellation_has_portable_path_escaped_markdown_anchor(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:linked", title="Linked", status="specced",
             source={"adapter": "spec_tree", "path": "stories/a story#1.md"}),
    ])

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    node = _data(html)["nodes"][0]

    assert node["h"] == "../../stories/a%20story%231.md"
    assert node["id"] == "story:linked"
    assert str(tmp_path) not in html
    assert 'open Markdown ${icon(\'arrow-up-right\')}' in html
    assert "n.h&&!SERVED" in html and "n.id&&SERVED" in html
    assert "data-source-path" not in html


def test_constellation_drops_story_href_that_escapes_repository(tmp_path):
    cfg = Config(data=DEFAULTS)
    graph = Graph(vocab=cfg.vocab, items=[
        Item(id="story:escape", title="Escape", status="specced",
             source={"adapter": "spec_tree", "path": "../../outside.md"}),
    ])

    node = _data(render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ])["nodes"][0]

    assert node["h"] == ""


def test_constellation_search_indexes_every_authored_item_field_and_live_work(tmp_path):
    """codex-sequence-2026-08-08: search follows meaning, not just filenames."""
    cfg = Config(data=DEFAULTS)
    graph = Graph(
        vocab=cfg.vocab,
        groups=[
            Group(id="capability:design-system", kind="capability",
                  title="Interface foundations"),
            Group(id="epic:visual-language", kind="epic",
                  title="Captured visual language", parent="capability:design-system"),
        ],
        items=[
            Item(
                id="story:captured-visual-language",
                title="Captured visual language",
                one_liner="Give each designer style a reusable semantic home.",
                status="building",
                release="R1",
                group="epic:visual-language",
                source={"adapter": "spec_tree", "path": "stories/style-capture.md"},
            ),
            Item(id="story:unrelated", title="Export canvas", status="specced",
                 release="R2", source={"adapter": "spec_tree", "path": "export.md"}),
        ],
        active_work=[ActiveWork(
            story_id="story:captured-visual-language", agent="Galileo",
            task="Tune inspector swatches", state="active", completed=2, total=4,
            updated_at="2026-08-08T17:00:00Z", stale_at="2099-08-08T19:00:00Z",
            checkpoint="semantic contrast review",
        )],
    )

    html = render_all(graph, cfg, tmp_path, only={"constellation"})[
        "constellation.html"
    ]
    data = _data(html)

    # The owner acceptance phrase spans one-liner words; all tokens must match
    # the same item, case-insensitively.
    assert _search_ids(data, "DESIGNER style") == [
        "story:captured-visual-language"
    ]
    for query in (
        "captured visual", "story:captured-visual-language", "building", "r1",
        "design-system", "interface foundations", "epic:visual-language",
        "stories/style-capture.md", "galileo", "inspector swatches",
        "semantic contrast",
    ):
        assert _search_ids(data, query) == ["story:captured-visual-language"]
    assert _search_ids(data, "designer export") == []


def test_constellation_search_is_accessible_local_and_topology_preserving(tmp_path):
    """codex-sequence-2026-08-08: search must work in a file:// constellation."""
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path,
                      only={"constellation"})["constellation.html"]

    assert 'role="search"' in html and 'aria-label="Search work items"' in html
    assert 'aria-live="polite"' in html and 'aria-label="Clear search"' in html
    assert "event.key==='Escape'" in html
    assert "!document.getElementById('dossier').classList.contains('open')" in html
    assert "toLocaleLowerCase" in html and "split(/\\s+/)" in html
    assert "searchTerms.every" in html
    assert "searchDim" in html
    # Search dims painter output; it does not enter visibility/layout filtering.
    visible_body = html.split("function visible(n)", 1)[1].split("}", 1)[0]
    assert "search" not in visible_body
    # Neither source-opening route becomes server-dependent merely because search exists.
    assert "n.h&&!SERVED" in html and "n.id&&SERVED" in html
    assert "fetch('/api/open/'+encodeURIComponent(b.dataset.openItem)" in html
    assert "prefers-reduced-motion: reduce" in html
