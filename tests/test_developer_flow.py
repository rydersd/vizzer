import html
import json
import subprocess
from pathlib import Path

from vizzer.config import Config
from vizzer.developer_graph import from_work_graph
from vizzer.model import ActiveWork, Graph, Group, Item
from vizzer.object_detail import object_detail_for
from vizzer.render import developer_flow


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "developer-flow"
MAIN = TOOLS / "src" / "main.jsx"
PROJECTION = TOOLS / "src" / "graph_projection.mjs"


def fixture():
    return Graph(
        groups=[
            Group(id="capability:search", kind="capability", title="Search"),
            Group(id="module:search/index", kind="module", title="Index",
                  parent="capability:search"),
        ],
        items=[
            Item(id="service:query", title="Query service", status="building",
                 group="module:search/index", deps=["database:index"],
                 source={"adapter": "manifest", "path": "services/query.yml"}),
            Item(id="database:index", title="Search index", status="shipped",
                 group="module:search/index"),
        ],
        active_work=[ActiveWork(
            story_id="service:query", agent="runner", task="verify", state="failed",
            completed=0, total=1, updated_at="2026-08-23T20:00:00Z",
            stale_at="2026-08-23T22:00:00Z", checkpoint="probe failed",
        )],
    )


def config(enabled=True, cap=300):
    return Config(data={
        "project": {"name": "Search fixture"},
        "render": {"title": "Search architecture"},
        "developer_flow": {
            "enabled": enabled,
            "materialization_cap": cap,
            "direction": "RIGHT",
        },
    })


def test_nested_frames_semantic_focus_keyboard_selection_and_bounded_lod_are_wired():
    data = from_work_graph(fixture(), config())
    groups = {group["id"]: group for group in data["groups"]}
    source = MAIN.read_text(encoding="utf-8")
    projection = PROJECTION.read_text(encoding="utf-8")

    assert groups["module:search/index"]["parentId"] == "capability:search"
    assert "map(groupNode)" in projection
    assert "visit(child,entry.id,origin)" in source
    assert "new Set(allGroupIds)" in source
    assert "setFocusGroupId(id)" in source
    assert "Focus related objects" in source
    assert "className=\"object-select\"" in source
    assert "materializationCap" in projection
    assert "zoom<.2?'overview':zoom<.42?'glyph'" in source
    assert "onlyRenderVisibleElements" in source


def test_responsive_breadcrumb_and_every_graph_entity_share_the_dossier():
    source = MAIN.read_text(encoding="utf-8")
    css = (TOOLS / "src" / "app.css").read_text(encoding="utf-8")

    assert "function Breadcrumbs" in source
    assert 'className="breadcrumb-overflow"' in source
    assert 'aria-label="Breadcrumb path"' in source
    assert "data.onSelect(data.id)" in source
    assert "node.type==='groupFrame'" in source
    assert "selectedEntity" in source
    assert "entity.entityType==='group'" in source
    assert "function flattenLayout(layout,projected,collapsed,expanded,selectedId" in source
    assert "flattenLayout(result,projected,collapsed,expanded,selectedId" in source
    assert ".breadcrumb-intermediate" in css
    assert ".breadcrumb-overflow" in css
    assert ".appbar {" in css and "overflow:hidden" in css
    assert ".view-actions span { min-width:0" in css
    assert "@media(max-width:820px)" in css


def test_low_detail_uses_true_dots_hover_detail_and_semantic_sf_symbols():
    source = MAIN.read_text(encoding="utf-8")
    css = (TOOLS / "src" / "app.css").read_text(encoding="utf-8")
    result = _node_module_probe(r"""
import {objectSymbolName,sfSymbolPresentation} from './src/vizzer_sf_symbols.mjs';
const cases=[
  {id:'story:drawing',kind:'story',title:'Editable vector path geometry'},
  {id:'database:index',kind:'database',title:'Search index'},
  {id:'story:ai',kind:'story',title:'AI depth model prediction'},
  {id:'test:contract',kind:'test',title:'Contract verification'},
  {id:'service:api',kind:'service',title:'Public API service'},
  {id:'story:auth',kind:'story',title:'Authentication lock policy'},
  {id:'story:fps',kind:'story',title:'FPS performance budget'},
  {id:'story:ui',kind:'story',title:'Responsive panel view'},
  {id:'story:group',kind:'story',title:'Plane grouping behavior'},
  {id:'story:command',kind:'story',title:'Batch transaction command'},
  {id:'story:detect',kind:'story',title:'Feature detection estimate'},
  {id:'story:grid',kind:'story',title:'Perspective grid'},
  {id:'story:plain',kind:'story',title:'A generic delivery story'},
];
const names=cases.map(objectSymbolName);
console.log(JSON.stringify({names,resolved:names.map(name=>Boolean(sfSymbolPresentation(name)))}));
""")
    assert result["names"] == [
        "scribble.variable", "cylinder", "sparkles", "checkmark.square", "server.rack",
        "lock", "arrow.up.right", "rectangle.on.rectangle", "arrow.trianglehead.branch",
        "list.dash.header.rectangle", "eyeglasses", "rectangle.on.rectangle", "document",
    ]
    assert all(result["resolved"])
    assert 'className="node-preview"' in source
    assert ".developer-shell[data-lod=glyph] .object-card" in css
    assert "width:24px;height:24px" in css
    assert ".node-preview" in css
    assert "placeOverlay" in source


def test_overlay_placement_stays_inside_its_lane_and_avoids_chrome():
    result = _node_module_probe(r"""
import {overlapArea,placeOverlay} from './src/overlay_geometry.mjs';
const boundary={x:0,y:96,width:890,height:624};
const minimap={x:673,y:553,width:202,height:152};
const right=placeOverlay({x:850,y:300,width:24,height:24},{width:280,height:150},boundary,[minimap]);
const bottom=placeOverlay({x:690,y:660,width:24,height:24},{width:280,height:150},boundary,[minimap]);
console.log(JSON.stringify({right,bottom,rightMap:overlapArea(right,minimap),bottomMap:overlapArea(bottom,minimap)}));
""")
    assert result["right"]["side"] == "left"
    assert result["right"]["x"] >= 8
    assert result["right"]["y"] >= 104
    assert result["right"]["x"] + result["right"]["width"] <= 882
    assert result["rightMap"] == 0
    assert result["bottomMap"] == 0


def _route_probe():
    script = r"""
import ELK from 'elkjs/lib/elk.bundled.js';
import {
  groupFrameMetrics,objectCardMetrics,pathMidpoint,placePathLabel,rootLayoutOptions,
  roundedOrthogonalPath,routeCrossesRect,
} from './src/layout_contract.mjs';
const elk=new ELK();
const graph={id:'root',layoutOptions:rootLayoutOptions('RIGHT'),children:[
  {id:'a',width:120,height:80},{id:'b',width:120,height:80},
  {id:'c',width:120,height:80},{id:'d',width:120,height:80}],edges:[
  {id:'ad',sources:['a'],targets:['d']},{id:'bc',sources:['b'],targets:['c']} ]};
const layout=await elk.layout(graph);
const fanout=await elk.layout({id:'fanout',layoutOptions:rootLayoutOptions('RIGHT'),children:[
  {id:'source',width:120,height:70},
  {id:'target-0',width:120,height:70},{id:'target-1',width:120,height:70},
  {id:'target-2',width:120,height:70},{id:'target-3',width:120,height:70}],
  edges:[0,1,2,3].map(index=>({id:`fan-${index}`,sources:['source'],targets:[`target-${index}`]}))});
const laneXs=fanout.edges.flatMap(edge=>edge.sections?.[0]?.bendPoints||[])
  .filter((point,index,points)=>index%2===0&&points[index+1]?.x===point.x)
  .map(point=>point.x).sort((a,b)=>a-b);
const rects=new Map(layout.children.map(n=>[n.id,{x:n.x,y:n.y,width:n.width,height:n.height}]));
let hits=0;
for(const edge of layout.edges){
  const section=edge.sections?.[0];if(!section)continue;
  const points=[section.startPoint,...(section.bendPoints||[]),section.endPoint];
  for(const [id,rect] of rects){
    if(edge.sources.includes(id)||edge.targets.includes(id))continue;
    if(routeCrossesRect(points,rect))hits++;
  }
}
const b=rects.get('b');
const mutation=[{x:b.x-20,y:b.y+b.height/2},{x:b.x+b.width+20,y:b.y+b.height/2}];
const midpoint=pathMidpoint([{x:0,y:0},{x:100,y:0},{x:100,y:300}]);
const label=placePathLabel([{x:0,y:0},{x:300,y:0}],'depends-on',
  [{x:120,y:-30,width:60,height:60}],[]);
const options=rootLayoutOptions('RIGHT');
const rounded=roundedOrthogonalPath([{x:0,y:0},{x:80,y:0},{x:80,y:70}],10);
const frame=groupFrameMetrics('Component Authoring & Instances',
  {blocked:13,active:6,ready:33,shipped:49},true);
const card=objectCardMetrics({title:'A deliberately long object title that wraps safely',
  summary:'A summary with enough content to occupy multiple complete lines without a clamp.'});
console.log(JSON.stringify({hits,mutationDetected:routeCrossesRect(mutation,b),midpoint,
  edgeGap:options['elk.spacing.edgeEdge'],betweenGap:options['elk.layered.spacing.edgeEdgeBetweenLayers'],
  rounded,frame,card,laneXs,label}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=TOOLS, capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(result.stdout)


def test_orthogonal_layout_avoids_card_interiors_and_mutation_detects_overlap():
    result = _route_probe()
    assert result["hits"] == 0
    assert result["mutationDetected"] is True
    assert result["midpoint"] == {"x": 100, "y": 100}
    assert result["edgeGap"] == result["betweenGap"] == "18"
    assert result["laneXs"] == [204, 222, 240]
    assert result["rounded"] == "M 0 0 L 70 0 Q 80 0 80 10 L 80 70"
    assert not (120 <= result["label"]["x"] <= 180 and -30 <= result["label"]["y"] <= 30)
    assert result["frame"]["width"] == 360
    assert result["frame"]["height"] > 132
    assert result["frame"]["headerHeight"] >= 54
    assert result["card"]["height"] > 138


def test_nested_compound_edges_are_shifted_from_lca_space_to_root_space():
    result = _node_module_probe(r"""
import ELK from 'elkjs/lib/elk.bundled.js';
import {
  absoluteEdgeRoutes,groupLayoutOptions,rootLayoutOptions,
} from './src/layout_contract.mjs';
const elk=new ELK();
const card=id=>({id,width:320,height:150});
const layout=await elk.layout({id:'developer-root',layoutOptions:rootLayoutOptions('RIGHT'),children:[
  {id:'outer',layoutOptions:groupLayoutOptions('RIGHT',52),children:[
    {id:'inner',layoutOptions:groupLayoutOptions('RIGHT',52),children:[card('a'),card('b'),card('c')]},
    card('d'),
  ]},
],edges:[
  {id:'ab',sources:['a'],targets:['b']},
  {id:'bc',sources:['b'],targets:['c']},
  {id:'ad',sources:['a'],targets:['d']},
]});
const routes=absoluteEdgeRoutes(layout);
const nodes=new Map();
const visit=(entry,origin={x:0,y:0})=>{
  const absolute={x:origin.x+(entry.x||0),y:origin.y+(entry.y||0)};
  nodes.set(entry.id,{...absolute,width:entry.width,height:entry.height});
  for(const child of entry.children||[])visit(child,absolute);
};
visit(layout);
const onBoundary=(point,node)=>{
  const horizontal=(Math.abs(point.x-node.x)<.01||Math.abs(point.x-node.x-node.width)<.01)
    &&point.y>=node.y-.01&&point.y<=node.y+node.height+.01;
  const vertical=(Math.abs(point.y-node.y)<.01||Math.abs(point.y-node.y-node.height)<.01)
    &&point.x>=node.x-.01&&point.x<=node.x+node.width+.01;
  return horizontal||vertical;
};
const checks={};
for(const edge of layout.edges){
  const points=routes.get(edge.id),source=nodes.get(edge.sources[0]),target=nodes.get(edge.targets[0]);
  checks[edge.id]={source:onBoundary(points[0],source),target:onBoundary(points.at(-1),target),points};
}
const top=await elk.layout({id:'top',layoutOptions:rootLayoutOptions('RIGHT'),
  children:[card('left'),card('right')],edges:[{id:'lr',sources:['left'],targets:['right']}]});
const local=top.edges[0].sections[0],topRoute=absoluteEdgeRoutes(top).get('lr');
console.log(JSON.stringify({checks,topUnshifted:JSON.stringify(topRoute)===JSON.stringify(
  [local.startPoint,...(local.bendPoints||[]),local.endPoint])}));
""")
    assert result["checks"]["ab"]["source"] is True
    assert result["checks"]["ab"]["target"] is True
    assert result["checks"]["bc"]["source"] is True
    assert result["checks"]["bc"]["target"] is True
    assert result["checks"]["ad"]["source"] is True
    assert result["checks"]["ad"]["target"] is True
    assert result["topUnshifted"] is True


def test_neighborhood_includes_prerequisites_consumers_and_typed_relations():
    source = MAIN.read_text(encoding="utf-8")
    projection = PROJECTION.read_text(encoding="utf-8")
    assert "relation.source===filters.focusObjectId" in projection
    assert "relation.target===filters.focusObjectId" in projection
    assert "EdgeLabelRenderer" in source
    assert 'className="relation-label"' in source


def test_relation_labels_own_an_opaque_layer_above_dependency_routes():
    css = (TOOLS / "src" / "app.css").read_text(encoding="utf-8")
    assert ".react-flow__edgelabel-renderer { z-index:6" in css
    assert "background:var(--panel)" in css
    assert "box-shadow:0 0 0 4px var(--panel)" in css


def test_inspectors_and_graph_chrome_use_exclusive_layout_lanes():
    source = MAIN.read_text(encoding="utf-8")
    css = (TOOLS / "src" / "app.css").read_text(encoding="utf-8")
    assert "selectedEntity||annotationPanelOpen?' has-sidebar'" in source
    assert "?<AnnotationPanel open" in source
    assert ":<Dossier" in source
    assert ".developer-shell.has-sidebar" in css
    assert ".developer-shell.has-sidebar .flowstage { display:none; }" in css
    assert "grid-column:2;grid-row:3" in css
    assert ".developer-shell { grid-template-rows:auto 46px minmax(0,1fr); }" in css
    assert ".appbar { min-height:50px;flex-wrap:wrap" in css
    assert ".view-actions { flex:1 1 0;justify-content:flex-start;overflow-x:auto" in css
    assert "@media(max-width:900px) { .react-flow__minimap { display:none; }" in css


def test_group_status_keeps_failure_active_ready_and_shipped_separate():
    data = from_work_graph(fixture(), config())
    roles = {obj["id"]: obj["statusRole"] for obj in data["objects"]}
    assert roles == {"database:index": "shipped", "service:query": "blocked"}
    assert "status-composition" in MAIN.read_text(encoding="utf-8")


def test_detail_is_injected_and_renderer_uses_the_shared_schema():
    def detail(item):
        return object_detail_for(item, sections={
            "reviewSteps": ["Start the fixture host.", "Request the query."],
            "acceptance": ["The response is successful."],
            "definitionOfDone": ["The public contract check passes."],
        })

    data = from_work_graph(fixture(), config(), detail_provider=detail)
    assert data["objects"][0]["detail"]["schema"] == "vizzer-object-detail/v1"
    source = MAIN.read_text(encoding="utf-8")
    assert "sections.reviewSteps" in source
    assert "sections.definitionOfDone" in source
    assert "Open in Constellation" in source


def test_disabled_renderer_returns_before_optional_assets_are_read(monkeypatch):
    monkeypatch.setattr(developer_flow, "_asset", lambda _name: (_ for _ in ()).throw(
        AssertionError("disabled renderer read an optional asset")
    ))
    assert developer_flow.render(fixture(), config(False), ROOT) == {}


def test_enabled_bundle_is_self_contained_escaped_and_licensed():
    graph = fixture()
    graph.items[0].one_liner = "safe </script><script>alert(1)</script>"
    page = developer_flow.render(graph, config(True), ROOT)["developer-flow.html"]

    assert "<script src=" not in page
    assert "<link rel=" not in page
    assert "\\u003c/script>" in page
    assert "React Flow attribution" in page
    assets = ROOT / "src" / "vizzer" / "render" / "developer_flow_assets"
    notices = (assets / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "React Flow" in notices
    assert "Eclipse Public License 2.0" in notices
    assert (assets / "third-party" / "ELKJS_LICENSE.md").is_file()


def test_developer_flow_injects_constellations_shared_theme_tokens():
    tokens = (ROOT / "src" / "vizzer" / "render" / "constellation" / "tokens.css").read_text(
        encoding="utf-8"
    )
    page = developer_flow.render(fixture(), config(True), ROOT)["developer-flow.html"]
    source_css = (TOOLS / "src" / "app.css").read_text(encoding="utf-8")
    assert tokens in page
    assert "__VIZZER_TOKENS__" not in page
    assert "--panel-2:var(--bg2)" in source_css
    assert "--muted:var(--mut)" in source_css
    assert "--danger:var(--buggap)" in source_css
    assert "--bg:#" not in source_css and "--accent:#" not in source_css


def test_group_focus_renders_incoming_and_outgoing_boundaries_as_root_cards():
    result = _node_module_probe(r"""
import {buildElkGraph,projectVisible} from './src/graph_projection.mjs';
const provenance={kind:'observed',source:'fixture'};
const object=(id,groupId)=>({id,kind:'service',title:id,summary:'',status:'ready',statusRole:'ready',groupId,provenance});
const data={groups:[
  {id:'focus',title:'Focus',kind:'capability',parentId:null,provenance},
  {id:'external',title:'External',kind:'capability',parentId:null,provenance},
],objects:[object('internal','focus'),object('input','external'),object('consumer','external')],relations:[
  {id:'needs',source:'internal',target:'input',kind:'depends-on'},
  {id:'uses',source:'consumer',target:'internal',kind:'depends-on'},
],summaries:[],limits:{materializationCap:100,boundaryMaterializationCap:250,sourceObjectCount:3}};
const filters={query:'',kind:'',status:'',group:'',relationKinds:[],focusGroupId:'focus',focusObjectId:null};
const projected=projectVisible(data,filters,new Set(),null);
const graph=buildElkGraph(projected,new Set(),new Set(),'RIGHT');
console.log(JSON.stringify({objects:projected.objects.map(entry=>({id:entry.id,groupId:entry.groupId,
  boundaryOnly:entry.boundaryOnly||false,boundaryRole:entry.boundaryRole||''})),
  groups:projected.groups.map(entry=>entry.id),relations:projected.relations.map(entry=>[entry.source,entry.target]),
  rootChildren:graph.children.map(entry=>entry.id),stats:projected.stats}));
""")
    objects = {entry["id"]: entry for entry in result["objects"]}
    assert objects["internal"]["groupId"] == "focus"
    assert objects["input"] == {
        "id": "input", "groupId": None, "boundaryOnly": True,
        "boundaryRole": "input dependency",
    }
    assert objects["consumer"] == {
        "id": "consumer", "groupId": None, "boundaryOnly": True,
        "boundaryRole": "external dependent",
    }
    assert result["groups"] == ["focus"]
    assert result["relations"] == [["internal", "input"], ["consumer", "internal"]]
    assert set(result["rootChildren"]) == {"focus", "input", "consumer"}
    assert result["stats"]["boundaryMounted"] == 2


def test_rendered_page_embeds_the_current_vizzer_sf_symbol_catalog():
    symbols = _node_module_probe(r"""
import {sfSymbolPresentation} from './src/vizzer_sf_symbols.mjs';
console.log(JSON.stringify({
  document:sfSymbolPresentation('document').d,
  failure:sfSymbolPresentation('exclamationmark.triangle').d,
  group:sfSymbolPresentation('list.dash.header.rectangle').d,
}));
""")
    page = developer_flow.render(fixture(), config(True), ROOT)["developer-flow.html"]
    assert all(path in page for path in symbols.values())
    assert "◇" not in page and "⚠" not in page


def test_view_delivery_discloses_ephemeral_and_configured_server_origins():
    page = developer_flow.render(fixture(), config(True), ROOT)["developer-flow.html"]
    assert '"restartStableOrigin":false' in page

    stable = config(True)
    stable.data["server"] = {"port": 64123}
    stable_page = developer_flow.render(fixture(), stable, ROOT)["developer-flow.html"]
    assert '"restartStableOrigin":true' in stable_page

    source = MAIN.read_text(encoding="utf-8")
    assert "set server.port to keep it across restarts" in source
    assert "set server.port for a restart-stable URL" in source


def _node_module_probe(script):
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=TOOLS, capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(result.stdout)


def test_bookmark_state_round_trips_filters_scope_selection_and_orientation():
    result = _node_module_probe(r"""
import {decodeViewState,encodeViewState} from './src/view_state.mjs';
const source={scope:'group',id:'capability:commerce',direction:'DOWN',
  selectedId:'service:orders',filters:{query:'ready & owned',kind:'service',
  status:'building',group:'capability:commerce',relationKinds:['consumes','depends-on']}};
const encoded=encodeViewState(source),decoded=decodeViewState(encoded);
const invalid=decodeViewState('?v=99&scope=object&id=untrusted');
console.log(JSON.stringify({encoded,decoded,invalid}));
""")
    assert "ready+%26+owned" in result["encoded"]
    assert result["decoded"]["scope"] == "group"
    assert result["decoded"]["direction"] == "DOWN"
    assert result["decoded"]["filters"]["relationKinds"] == ["consumes", "depends-on"]
    assert result["invalid"]["scope"] == "overview"


def test_saved_views_are_scoped_normalized_deduplicated_and_bounded():
    result = _node_module_probe(r"""
import {normalizeSavedViews,savedViewsStorageKey} from './src/view_state.mjs';
const noisy=[null,'bad',{name:'  Operations  ',view:{scope:'object',id:'service:ops'}},
  {name:'Operations',view:{scope:'all'}},{name:'',view:{}},
  {name:'Broken',view:{scope:'object',id:''}}];
const many=Array.from({length:40},(_entry,index)=>({name:`View ${index}`,view:{scope:'all'}}));
console.log(JSON.stringify({key:savedViewsStorageKey('Project','/developer-flow.html'),
  noisy:normalizeSavedViews(noisy),many:normalizeSavedViews(many)}));
""")
    assert result["key"] == (
        "vizzer:developer-saved-views:v1:/developer-flow.html:Project"
    )
    assert [entry["name"] for entry in result["noisy"]] == ["Operations", "Broken"]
    assert result["noisy"][1]["view"]["scope"] == "overview"
    assert len(result["many"]) == 30


def test_view_documents_bound_notes_object_annotations_and_freehand_strokes():
    result = _node_module_probe(r"""
import {annotationPath,newViewId,normalizeViewDocuments} from './src/view_document.mjs';
const source=[{name:'Drawing review',view:{scope:'group',id:'capability:drawing'},
  notes:'Release owner walkthrough',annotationsVisible:false,annotations:[
    {id:'note-one',kind:'note',color:'yellow',x:10,y:20,text:'Check fan-out',objectId:'story:a'},
    {id:'stroke-one',kind:'stroke',color:'pink',width:4,points:[[0,0],[5,7],[11,12]]},
    {id:'bad-stroke',kind:'stroke',color:'pink',width:99,points:[[0,0],[1,1]]},
  ]}];
const documents=normalizeViewDocuments(source);
console.log(JSON.stringify({documents,id:newViewId(),path:annotationPath(documents[0].annotations[1].points)}));
""")
    document = result["documents"][0]
    assert document["id"].startswith("local-drawing-review-")
    assert document["notes"] == "Release owner walkthrough"
    assert [item["kind"] for item in document["annotations"]] == ["note", "stroke"]
    assert document["annotations"][0]["objectId"] == "story:a"
    assert document["annotationsVisible"] is False
    assert result["id"].startswith("view-") and len(result["id"]) <= 80
    assert result["path"] == "M 0 0 L 5 7 L 11 12"


def test_svg_export_is_real_vector_markup_for_current_routed_scope():
    result = _node_module_probe(r"""
import {developerFlowSvg} from './src/export_svg.mjs';
const nodes=[
  {id:'g',type:'groupFrame',position:{x:10,y:10},style:{width:500,height:260},data:{title:'Commerce <core>',count:2,statusCounts:{active:1,shipped:1}}},
  {id:'a',type:'objectCard',parentId:'g',position:{x:30,y:70},style:{width:180,height:120},data:{title:'Orders',kind:'service',status:'building',statusRole:'active',summary:'Creates orders'}},
  {id:'b',type:'objectCard',parentId:'g',position:{x:280,y:70},style:{width:180,height:120},data:{title:'Database',kind:'database',status:'failed',statusRole:'blocked',failure:{message:'probe <failed>'}}},
];
const edges=[{id:'e',label:'depends-on',data:{kind:'depends-on',points:[{x:220,y:140},{x:290,y:140}]}}];
const annotations=[
  {id:'stroke',kind:'stroke',color:'pink',width:4,points:[[20,30],[40,50],[70,50]]},
  {id:'note',kind:'note',color:'yellow',x:80,y:220,text:'Owner <script>alert(1)</script> note',objectId:'a'},
];
const svg=developerFlowSvg({title:'Export test\u0000',nodes,edges,annotations,lod:'summary',exportedAt:'2026-08-24T00:00:00Z'});
const cleanSvg=developerFlowSvg({title:'Export without markup',nodes,edges,annotations,
  includeAnnotations:false,lod:'summary',exportedAt:'2026-08-24T00:00:00Z'});
const longSvg=developerFlowSvg({nodes:[],edges:[{label:'relationship-label-that-is-deliberately-wide',data:{points:[{x:0,y:0},{x:10,y:0}]}}]});
const viewBox=longSvg.match(/viewBox="([^"]+)"/)[1].split(' ').map(Number);
const labelRect=longSvg.match(/edge-label-bg" x="([^"]+)"[^>]+width="([^"]+)"/).slice(1).map(Number);
console.log(JSON.stringify({svg,cleanSvg,longLabelContained:labelRect[0]>=viewBox[0]&&labelRect[0]+labelRect[1]<=viewBox[0]+viewBox[2]}));
""")
    svg = result["svg"]
    assert svg.startswith('<?xml version="1.0"')
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in svg
    assert '<foreignObject' not in svg
    assert '<path d="M 220 140 L 290 140"' in svg
    assert '<rect class="edge-label-bg" x="213" y="123" width="84" height="18" rx="9"/>' in svg
    assert '<text x="255" y="134">depends-on</text>' in svg
    assert ".edge-label-bg{fill:#fff" in svg
    assert "depends-on" in svg and "Orders" in svg and "probe &lt;failed&gt;" in svg
    assert "Commerce &lt;core&gt;" in svg
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in svg and "<script>" not in svg
    assert "vizzer-developer-flow-svg/v1" in svg
    assert 'class="annotation-stroke annotation-pink"' in svg
    assert "Owner" in svg and "alert(1)" in svg and "note" in svg
    assert "&quot;annotationCount&quot;:2" in svg
    assert '<path class="annotation-stroke' not in result["cleanSvg"]
    assert '<g class="annotation-note' not in result["cleanSvg"]
    assert "&quot;annotationCount&quot;:0" in result["cleanSvg"]
    assert "&quot;annotationsIncluded&quot;:false" in result["cleanSvg"]
    assert "\u0000" not in svg
    assert result["longLabelContained"] is True


def test_svg_export_uses_live_card_wrapping_iconography_and_lod_contract():
    result = _node_module_probe(r"""
import {developerFlowSvg} from './src/export_svg.mjs';
import {
  groupFrameMetrics,groupFramePresentation,objectCardMetrics,
  objectCardPresentation,wrapTextLines,
} from './src/layout_contract.mjs';
import {
  groupSymbolName,lifecycleSymbolName,sfSymbolPresentation,
} from './src/vizzer_sf_symbols.mjs';
const object={id:'story:centerline',kind:'story',status:'specced',statusRole:'ready',
  title:'Recovered centerline — visual-equivalence gate on anchor reduction',
  summary:'As a designer cleaning up an imported icon, I want anchor reduction on a recovered centerline without silently losing the final acceptance phrase.',
  failure:{message:'A deliberately wide WWWWWWWWWWWWWWWWWWWWWWWWWWWW failure remains visible.'},
  details:{'deliberately-long-detail-key':'A detail value with enough words to require several explicit SVG lines without borrowing the live card scrollbar.'}};
const metrics=objectCardMetrics(object,false),presentation=objectCardPresentation(object,false);
const expandedMetrics=objectCardMetrics(object,true),expandedPresentation=objectCardPresentation(object,true);
const groupTitle='Geometry Editing & Centerline Recovery With Deliberately Wide WWWWWWWWWWWW Text';
const groupMetrics=groupFrameMetrics(groupTitle,{},false);
const groupPresentation=groupFramePresentation(groupTitle,{},false);
const objectY=groupMetrics.headerHeight+28;
const nodes=[
  {id:'group',type:'groupFrame',position:{x:0,y:0},style:{width:720,height:520},
    data:{title:groupTitle,kind:'capability',count:1,statusCounts:{},headerHeight:groupMetrics.headerHeight}},
  {id:object.id,type:'objectCard',parentId:'group',position:{x:36,y:objectY},
    style:{width:metrics.width,height:metrics.height},data:{...object,headerHeight:metrics.headerHeight}},
];
const summary=developerFlowSvg({nodes,lod:'summary'});
const compact=developerFlowSvg({nodes,lod:'compact'});
const glyph=developerFlowSvg({nodes,lod:'glyph'});
const collapsedMetrics=groupFrameMetrics(groupTitle,{blocked:2,active:1},true);
const collapsedGroup=developerFlowSvg({nodes:[{id:'collapsed',type:'groupFrame',position:{x:0,y:0},
  style:{width:collapsedMetrics.width,height:collapsedMetrics.height},data:{title:groupTitle,
  count:3,statusCounts:{blocked:2,active:1},collapsed:true,headerHeight:collapsedMetrics.headerHeight}}]});
const expanded=developerFlowSvg({nodes:[{id:object.id,type:'objectCard',position:{x:0,y:0},
  style:{width:expandedMetrics.width,height:expandedMetrics.height},
  data:{...object,expanded:true,headerHeight:expandedMetrics.headerHeight}}],lod:'summary'});
const titleYs=[...summary.matchAll(/<text class="title"[^>]+y="([^"]+)"/g)].map(match=>Number(match[1]));
const summaryYs=[...summary.matchAll(/<text class="summary"[^>]+y="([^"]+)"/g)].map(match=>Number(match[1]));
const symbolNames=[
  lifecycleSymbolName({status:'specced',statusRole:'ready'}),
  lifecycleSymbolName({status:'shipped',statusRole:'shipped'}),
  lifecycleSymbolName({status:'blocked',statusRole:'blocked'}),
  lifecycleSymbolName({status:'failed',statusRole:'blocked',failure:{message:'failed'}}),
  lifecycleSymbolName({status:'parked',statusRole:'ready'}),
  lifecycleSymbolName({status:'backlog',statusRole:'ready'}),
  lifecycleSymbolName({status:'building',statusRole:'active'}),
  lifecycleSymbolName({status:'ready',statusRole:'ready'}),
  groupSymbolName(),
];
console.log(JSON.stringify({summary,compact,glyph,collapsedGroup,expanded,metrics,presentation,expandedMetrics,
  expandedPresentation,groupPresentation,objectY,
  titleYs,summaryYs,wideLines:wrapTextLines('W'.repeat(40),22),
  symbols:symbolNames,resolvedSymbols:symbolNames.filter(Boolean).map(name=>Boolean(sfSymbolPresentation(name))),
  symbol:sfSymbolPresentation(presentation.symbol),groupSymbol:sfSymbolPresentation(groupSymbolName())}));
""")
    summary = result["summary"]
    presentation = result["presentation"]
    assert len(presentation["titleLines"]) >= 3
    assert len(presentation["summaryLines"]) >= 3
    assert len(result["wideLines"]) >= 3
    assert result["symbols"] == [
        "document", "checkmark", "ladybug", "exclamationmark.triangle",
        "parkingsign", "lightbulb", "arrow.up.right", "",
        "list.dash.header.rectangle",
    ]
    assert all(result["resolvedSymbols"])
    for line in presentation["titleLines"]:
        assert f'>{line}</text>' in summary
    for line in presentation["summaryLines"]:
        assert f'>{line}</text>' in summary
    for line in result["groupPresentation"]["titleLines"]:
        assert f'>{html.escape(line, quote=True)}</text>' in summary
    assert f'>{" ".join(presentation["titleLines"])}</text>' not in summary
    assert '<rect class="kind-icon"' in summary
    assert '<svg class="sf-symbol"' in summary
    assert result["symbol"]["d"] in summary
    assert result["groupSymbol"]["d"] in result["collapsedGroup"]
    assert 'fill-rule="evenodd"' in summary
    assert "◇" not in summary and "⚠" not in summary
    assert '<g class="status-pill">' in summary
    assert max(result["titleYs"]) - result["objectY"] < result["metrics"]["headerHeight"]
    assert max(result["summaryYs"]) - result["objectY"] < result["metrics"]["height"]
    assert 'class="summary"' not in result["compact"]
    assert 'class="sf-symbol"' in result["compact"]
    assert 'class="title"' not in result["glyph"]
    assert result["symbol"]["d"] in result["glyph"]
    assert result["expandedMetrics"]["detailHeight"] > 0
    for entry in result["expandedPresentation"]["detailEntries"]:
        for line in entry["keyLines"] + entry["valueLines"]:
            assert f'>{html.escape(line, quote=True)}</text>' in result["expanded"]


def test_svg_download_uses_a_mounted_link_safe_name_and_delayed_revoke():
    result = _node_module_probe(r"""
import {svgFilename,triggerSvgDownload} from './src/export_svg.mjs';
const events=[];
const anchor={hidden:false,click(){events.push('click')},remove(){events.push('remove')}};
const document={body:{appendChild(value){events.push(value===anchor?'append':'wrong')}},
  createElement(tag){events.push(tag);return anchor}};
const URL={createObjectURL(blob){events.push(`blob:${blob.type}`);return 'blob:test'},
  revokeObjectURL(url){events.push(`revoke:${url}`)}};
const delayed=[];
const result=triggerSvgDownload('<svg/>',svgFilename('Commerce / Core','object'),{
  document,URL,Blob,setTimeout(callback,delay){delayed.push(delay);callback()},
});
console.log(JSON.stringify({events,delayed,result,href:anchor.href,
  download:anchor.download,hidden:anchor.hidden}));
""")
    assert result["events"] == [
        "blob:image/svg+xml;charset=utf-8", "a", "append", "click", "remove",
        "revoke:blob:test",
    ]
    assert result["delayed"] == [1000]
    assert result["download"] == "commerce-core-object.svg"
    assert result["href"] == "blob:test" and result["hidden"] is True
    assert result["result"]["bytes"] == len("<svg/>")


def test_generated_bundle_exposes_save_share_bookmark_and_svg_actions():
    source = MAIN.read_text(encoding="utf-8")
    assert "encodeViewState(currentView)" in source
    assert "localStorage.setItem(savedKey" in source
    assert "normalizeViewDocuments" in source
    assert "navigator.clipboard.writeText" in source
    assert "triggerSvgDownload" in source
    assert "Export SVG" in source


def test_canvas_annotations_share_flow_coordinates_and_saved_view_authority():
    source = MAIN.read_text(encoding="utf-8")
    assert "ViewportPortal" in source
    assert "screenToFlowPosition" in source
    assert "View, notes, and annotations saved" in source
    assert "/api/developer-flow/views" in source
    assert "expectedRevision:viewStoreRevision" in source
    assert "Save the view before sharing its notes or sketches" in source
    assert "Save the latest view changes before sharing" in source
    assert "The shared saved view is unavailable" in source
    assert "const viewService=/^https?:$/.test" in source
    assert "annotations={annotations}" in source
    assert "annotationsVisible&&<AnnotationLayer" in source
    assert "Hide notes & sketches" in source
    assert "includeAnnotations:exportAnnotations" in source
    assert "Include notes and sketches in SVG export" in source


def test_annotation_history_is_bounded_undoable_and_clears_redo_on_edit():
    result = _node_module_probe(r"""
import {annotationHistory,annotationHistoryReducer} from './src/annotation_history.mjs';
let state=annotationHistory([]);
state=annotationHistoryReducer(state,{type:'commit',value:[{id:'note-1',kind:'note'}]});
state=annotationHistoryReducer(state,{type:'commit',value:[...state.present,{id:'stroke-1',kind:'stroke'}]});
const afterUndo=annotationHistoryReducer(state,{type:'undo'});
const afterRedo=annotationHistoryReducer(afterUndo,{type:'redo'});
const divergent=annotationHistoryReducer(afterUndo,{type:'commit',value:[{id:'note-2',kind:'note'}]});
let bounded=annotationHistory([]);
for(let index=0;index<120;index++)bounded=annotationHistoryReducer(bounded,{type:'commit',value:[{id:String(index)}]});
console.log(JSON.stringify({afterUndo,afterRedo,divergent,boundedPast:bounded.past.length}));
""")
    assert [item["id"] for item in result["afterUndo"]["present"]] == ["note-1"]
    assert [item["id"] for item in result["afterRedo"]["present"]] == ["note-1", "stroke-1"]
    assert result["divergent"]["future"] == []
    assert result["boundedPast"] == 100


def test_navigation_is_baseline_and_annotation_tools_do_not_own_a_pan_mode():
    source = MAIN.read_text(encoding="utf-8")
    assert ">Pan</button>" not in source
    assert "panOnDrag panOnScroll" in source
    assert "zoomOnScroll={false} zoomOnPinch preventScrolling" in source
    assert "capture.addEventListener('wheel',navigate,{passive:false})" in source
    assert "aria-label=\"Undo annotation\"" in source
    assert "aria-label=\"Redo annotation\"" in source
    assert "event.metaKey||event.ctrlKey" in source
