// Keep fixed search and rail chrome below the title bar even when controls wrap.
const CHROME_SEARCH_GAP=12;
const CHROME_RAIL_GAP=10;
function chromeMetrics(topHeight,searchHeight){
  const searchTop=Math.max(0,topHeight)+CHROME_SEARCH_GAP;
  return{searchTop,railTop:searchTop+Math.max(0,searchHeight)+CHROME_RAIL_GAP};
}
function syncChromeMetrics(){
  const top=document.getElementById('top'),search=document.getElementById('search');
  if(!top||typeof top.getBoundingClientRect!=='function')return null;
  const topHeight=top.getBoundingClientRect().height||0;
  const searchHeight=search&&typeof search.getBoundingClientRect==='function'
    ?search.getBoundingClientRect().height||0:0;
  const metrics=chromeMetrics(topHeight,searchHeight),root=document.documentElement;
  root?.style?.setProperty('--search-top',`${metrics.searchTop}px`);
  root?.style?.setProperty('--rail-top',`${metrics.railTop}px`);
  return metrics;
}
