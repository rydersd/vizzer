"""Executable constellation contracts for portable epic clusters."""
from __future__ import annotations

import json
import shutil
import subprocess

from vizzer.config import Config, DEFAULTS
from vizzer.model import (
    Graph, Group, Item, OwnerQuestion, OwnerQuestionOption,
    OwnerQuestionRecommendation,
)
from vizzer.render import render_all

from test_render_constellation import _CONSTELLATION_COUNT_DOM_SHIM


def _graph() -> Graph:
    groups = [
        Group(id="capability:canvas", kind="capability", title="Canvas"),
        Group(id="epic:shapes", kind="epic", title="Shapes", parent="capability:canvas"),
        Group(id="epic:text", kind="epic", title="Text", parent="capability:canvas"),
        Group(id="capability:library", kind="capability", title="Library"),
        Group(id="epic:assets", kind="epic", title="Assets", parent="capability:library"),
    ]
    items = [
        Item(id="story:shape-a", title="Shape A", status="ready", release="R0", group="epic:shapes"),
        Item(id="story:shape-b", title="Shape B", status="ready", release="R0", group="epic:shapes"),
        Item(id="story:text-a", title="Text A", status="ready", release="R0", group="epic:text"),
        Item(id="story:text-b", title="Text B", status="ready", release="R0", group="epic:text"),
        Item(id="story:asset-a", title="Asset A", status="ready", release="R0", group="epic:assets"),
        Item(id="story:asset-b", title="Asset B", status="ready", release="R0", group="epic:assets"),
    ]
    return Graph(
        groups=groups, items=items, vocab=Config(data=DEFAULTS).vocab,
        owner_questions=[OwnerQuestion(
            id="question:cluster-fixture", story_id="story:shape-a", owner="Fixture",
            prompt="Use the shared browser fixture?",
            options=[OwnerQuestionOption(id="yes", label="Yes", tradeoff="Keeps this executable.")],
            recommendation=OwnerQuestionRecommendation(
                option_id="yes", rationale="The DOM driver requires one question.",
            ),
            falsifier="The driver can no longer boot the constellation.",
            evidence=["tests/test_constellation_cluster_velocity.py"],
        )],
    )


def _probe(html: str) -> dict:
    node = shutil.which("node")
    assert node is not None, "Node is required to execute the rendered constellation"
    driver = _CONSTELLATION_COUNT_DOM_SHIM.replace(
        "sandbox.window=sandbox;",
        "sandbox.Element=Element;sandbox.window=sandbox;",
    ).replace(
        "process.stdout.write(JSON.stringify(out));",
        "const result=ev(`(()=>{"
        "document.body=document.body||{appendChild(){}};"
        "const members=DATA.nodes.map((n,i)=>({n,i}));"
        "const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z);"
        "const pick=e=>members.filter(({n})=>n.c==='canvas'&&n.e===e).map(({n})=>n);"
        "const shapes=pick('Shapes'),text=pick('Text');"
        "const mean=values=>values.reduce((sum,value)=>sum+value,0)/values.length;"
        "const intra=mean([distance(shapes[0],shapes[1]),distance(text[0],text[1])]);"
        "const cross=mean(shapes.flatMap(a=>text.map(b=>distance(a,b))));"
        "const before=zoom,entered=enterClusterFocus('canvas'),focused=clusterFocus;"
        "const libraryIndex=members.find(({n})=>n.c==='library').i;"
        "const canvasIndex=members.find(({n})=>n.c==='canvas').i;"
        "P[libraryIndex]={x:400,y:300,s:4,d:-20,on:true,near:0};"
        "P[canvasIndex]={x:401,y:300,s:4,d:20,on:true,near:0};"
        "updatePointerState(400,300);const focusHit=hover;"
        "const background=focusBackground(libraryIndex);"
        "const simple=[{x:0,y:0},{x:4,y:0},{x:4,y:4},{x:0,y:4},{x:2,y:2}];"
        "const hull=convexHull(simple),degenerate=convexHull([]),collinear=convexHull([{x:0,y:0},{x:1,y:0},{x:2,y:0}]);"
        "const undone=canvasIndex;for(let i=0;i<P.length;i++)P[i].on=i===undone;"
        "Object.assign(DATA.nodes[undone],{g:'ready',rec:false,oq:[],aw:[]});"
        "P[undone]={x:400,y:300,s:5,d:0,on:true,near:0};"
        "const arcs=[];ctx.arc=(x,y,r)=>arcs.push([x,y,r]);draw();"
        "const nodeArcs=arcs.filter(([x,y])=>x===400&&y===300).map(([, ,r])=>r/nodeRadius(undone));"
        "const outerVersionRings=nodeArcs.filter(r=>Math.abs(r-1.16)<.001).length;"
        "const orient2=(o,a,b)=>(a.x-o.x)*(b.y-o.y)-(a.y-o.y)*(b.x-o.x);"
        "const onOrInside=(point,poly)=>{let inside=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const a=poly[i],b=poly[j],edge=orient2(a,b,point),within=point.x>=Math.min(a.x,b.x)-1e-6&&point.x<=Math.max(a.x,b.x)+1e-6&&point.y>=Math.min(a.y,b.y)-1e-6&&point.y<=Math.max(a.y,b.y)+1e-6;if(Math.abs(edge)<1e-6&&within)return true;if((a.y>point.y)!==(b.y>point.y)&&point.x<(b.x-a.x)*(point.y-a.y)/(b.y-a.y)+a.x)inside=!inside;}return inside;};"
        "const polygonCrossings=poly=>{let count=0;for(let a=0;a<poly.length;a++)for(let b=a+2;b<poly.length;b++){if(a===0&&b===poly.length-1)continue;if(segmentsCross(poly[a],poly[(a+1)%poly.length],poly[b],poly[(b+1)%poly.length]))count++;}return count;};"
        "const concavePoints=[{x:0,y:0},{x:100,y:0},{x:100,y:100},{x:0,y:100},{x:50,y:0},{x:50,y:24},{x:20,y:30}];"
        "const concave=concaveHull(concavePoints,12),concaveAgain=concaveHull(concavePoints,12);"
        "const labelEntries=[{c:'a',title:'Alpha',members:5,hull:[{x:80,y:120},{x:180,y:120},{x:180,y:200},{x:80,y:200}],pad:6,reach:8,minX:80,maxX:180,minY:120,maxY:200},{c:'b',title:'Beta',members:4,hull:[{x:220,y:120},{x:320,y:120},{x:320,y:200},{x:220,y:200}],pad:6,reach:8,minX:220,maxX:320,minY:120,maxY:200}];"
        "hullLabelGrid=null;placeHullLabels(labelEntries,[{x0:110,x1:150,y0:88,y1:112},{x0:250,x1:290,y0:88,y1:112}],{left:0,top:40,right:420,bottom:300});"
        "const aBox=labelEntries[0].label.box,bBox=labelEntries[1].label.box;const labelsDisjoint=!(aBox.x0<bBox.x1&&bBox.x0<aBox.x1&&aBox.y0<bBox.y1&&bBox.y0<aBox.y1);"
        "const dock=new Element('div','historydock');dock.getBoundingClientRect=()=>({top:260,height:40});"
        "const dockBounds=hullLabelBounds();"
        "const hostileFoundation=[{id:'delivery',g:'ready',role:'delivery',foundational:true,tags:[]},{id:'reference',g:'ready',role:'reference',foundational:true,tags:[]},{id:'synthetic',g:'ready',role:'delivery',foundation:true,foundational:true,tags:[]},{id:'shipped',g:'shipped',role:'delivery',foundational:true,tags:[]}];"
        "const hostileFoundationRemaining=foundationRemaining(hostileFoundation);"
        "const hierarchyGroup='epic:shapes';activePlanningArea='stale-area';areaRequest=41;sel=77;capFocus='canvas';groupFocus='epic:shapes';questionEditor={open:true};openHierarchyDetails(hierarchyGroup);const drawerGuard=activePlanningArea==='stale-area'&&areaRequest===41&&sel===77;const selectionGuard=selectHierarchy(null,'library','epic:assets')===false&&capFocus==='canvas'&&groupFocus==='epic:shapes';"
        "questionEditor=null;openHierarchyDetails(hierarchyGroup);const hierarchyOpened=activePlanningArea===null&&areaRequest===42&&sel===-1&&dossier.classList.contains('open');"
        "const exited=exitClusterFocus();"
        "return {intra,cross,entered,focused,background,focusHit,canvasIndex,exited,restored:zoom===before,"
        "anchors:Object.keys(epicAnchor).sort(),extent:capExtent.canvas,"
        "hull:hull.map(p=>[p.x,p.y]),degenerate,collinear:collinear.map(p=>[p.x,p.y]),nodeArcs,outerVersionRings,"
        "concaveContains:concavePoints.every(point=>onOrInside(point,concave)),concaveSimple:polygonCrossings(concave)===0,"
        "concaveDeterministic:JSON.stringify(concave)===JSON.stringify(concaveAgain),concaveVertices:concave.length,"
        "labelled:labelEntries.every(entry=>entry.label&&entry.label.box),labelsDisjoint,dockBottom:dockBounds.bottom,"
        "hostileFoundationRemaining,drawerGuard,selectionGuard,hierarchyOpened};})()`);"
        "process.stdout.write(JSON.stringify(result));",
    )
    run = subprocess.run(
        [node, "-e", driver], input=html, text=True, capture_output=True,
        timeout=10, check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout)


def _no_epic_spread_probe(html: str) -> dict:
    node = shutil.which("node")
    assert node is not None, "Node is required to execute the rendered constellation"
    driver = _CONSTELLATION_COUNT_DOM_SHIM.replace(
        "process.stdout.write(JSON.stringify(out));",
        "const spread=ev(`(()=>{const xs=DATA.nodes.map(node=>node.x),ys=DATA.nodes.map(node=>node.y),zs=DATA.nodes.map(node=>node.z);return {allWithoutEpic:DATA.nodes.every(node=>node.e===''),diameter:Math.hypot(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys),Math.max(...zs)-Math.min(...zs))};})()`);"
        "process.stdout.write(JSON.stringify(spread));",
    )
    run = subprocess.run(
        [node, "-e", driver], input=html, text=True, capture_output=True,
        timeout=10, check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout)


def _no_epic_graph() -> Graph:
    group = Group(id="capability:general", kind="capability", title="General")
    items = [
        Item(id=f"story:general-{index}", title=f"General {index}", status="ready", group=group.id)
        for index in range(13)
    ]
    return Graph(
        groups=[group], items=items, vocab=Config(data=DEFAULTS).vocab,
        owner_questions=[OwnerQuestion(
            id="question:no-epic", story_id=items[0].id, owner="Fixture",
            prompt="Can the generic no-epic constellation boot?",
            options=[OwnerQuestionOption(id="yes", label="Yes", tradeoff="Exercises the shared DOM driver.")],
            recommendation=OwnerQuestionRecommendation(
                option_id="yes", rationale="The shared DOM driver expects one question.",
            ),
            falsifier="The no-epic fixture fails to boot.",
            evidence=["tests/test_constellation_cluster_velocity.py"],
        )],
    )


def test_epics_cluster_deterministically_and_focus_recedes_other_capabilities(tmp_path) -> None:
    cfg = Config(data=DEFAULTS)
    first = _probe(render_all(_graph(), cfg, tmp_path, only={"constellation"})["constellation.html"])
    second = _probe(render_all(_graph(), cfg, tmp_path, only={"constellation"})["constellation.html"])

    assert first == second
    assert first["anchors"] == ["canvas/Shapes", "canvas/Text", "library/Assets"]
    assert first["intra"] < first["cross"]
    assert first["extent"] > 0
    assert first["entered"] and first["focused"] == "canvas"
    assert first["background"]
    assert first["focusHit"] == first["canvasIndex"]
    assert first["exited"] and first["restored"]
    assert set(map(tuple, first["hull"])) == {(0, 0), (4, 0), (4, 4), (0, 4)}
    assert first["degenerate"] == []
    assert first["collinear"] == [[0, 0], [2, 0]]
    # An ordinary undone Story is one hollow lifecycle circle. A second 1.16r
    # version ring is exactly the doubled-circle regression this port prevents.
    assert len(first["nodeArcs"]) == 1
    assert first["outerVersionRings"] == 0
    assert first["concaveContains"] and first["concaveSimple"]
    assert first["concaveDeterministic"] and first["concaveVertices"] >= 4
    assert first["labelled"] and first["labelsDisjoint"]
    assert first["dockBottom"] == 256
    assert first["hostileFoundationRemaining"] == 1
    assert first["drawerGuard"] and first["selectionGuard"] and first["hierarchyOpened"]


def test_no_epic_capability_keeps_a_readable_generic_scatter(tmp_path) -> None:
    html = render_all(_no_epic_graph(), Config(data=DEFAULTS), tmp_path, only={"constellation"})[
        "constellation.html"
    ]

    # Generic projects have no authored epics to magnetize toward.  Their
    # deterministic cloud must not collapse into an illegible one-point knot.
    result = _no_epic_spread_probe(html)
    assert result["allWithoutEpic"]
    assert result["diameter"] > 50
