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

    assert groups["module:search/index"]["parentId"] == "capability:search"
    assert "map(groupNode)" in source
    assert "visit(child,entry.id)" in source
    assert "new Set(allGroupIds)" in source
    assert "setFocusGroupId(id)" in source
    assert "Focus related objects" in source
    assert "className=\"object-select\"" in source
    assert "materializationCap" in source
    assert "zoom<.2?'overview':zoom<.42?'glyph'" in source
    assert "onlyRenderVisibleElements" in source


def _route_probe():
    script = r"""
import ELK from 'elkjs/lib/elk.bundled.js';
import {
  groupFrameMetrics,objectCardMetrics,pathMidpoint,rootLayoutOptions,
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
const options=rootLayoutOptions('RIGHT');
const rounded=roundedOrthogonalPath([{x:0,y:0},{x:80,y:0},{x:80,y:70}],10);
const frame=groupFrameMetrics('Component Authoring & Instances',
  {blocked:13,active:6,ready:33,shipped:49},true);
const card=objectCardMetrics({title:'A deliberately long object title that wraps safely',
  summary:'A summary with enough content to occupy multiple complete lines without a clamp.'});
console.log(JSON.stringify({hits,mutationDetected:routeCrossesRect(mutation,b),midpoint,
  edgeGap:options['elk.spacing.edgeEdge'],betweenGap:options['elk.layered.spacing.edgeEdgeBetweenLayers'],
  rounded,frame,card,laneXs}));
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
    assert result["frame"]["width"] == 360
    assert result["frame"]["height"] > 132
    assert result["frame"]["headerHeight"] >= 54
    assert result["card"]["height"] > 138


def test_neighborhood_includes_prerequisites_consumers_and_typed_relations():
    source = MAIN.read_text(encoding="utf-8")
    assert "relation.source===filters.focusObjectId" in source
    assert "relation.target===filters.focusObjectId" in source
    assert "EdgeLabelRenderer" in source
    assert 'className="relation-label"' in source


def test_relation_labels_own_an_opaque_layer_above_dependency_routes():
    css = (TOOLS / "src" / "app.css").read_text(encoding="utf-8")
    assert ".react-flow__edgelabel-renderer { z-index:6" in css
    assert "background:var(--panel)" in css
    assert "box-shadow:0 0 0 4px var(--panel)" in css


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


def test_svg_export_is_real_vector_markup_for_current_routed_scope():
    result = _node_module_probe(r"""
import {developerFlowSvg} from './src/export_svg.mjs';
const nodes=[
  {id:'g',type:'groupFrame',position:{x:10,y:10},style:{width:500,height:260},data:{title:'Commerce <core>',count:2,statusCounts:{active:1,shipped:1}}},
  {id:'a',type:'objectCard',parentId:'g',position:{x:30,y:70},style:{width:180,height:120},data:{title:'Orders',kind:'service',status:'building',statusRole:'active',summary:'Creates orders'}},
  {id:'b',type:'objectCard',parentId:'g',position:{x:280,y:70},style:{width:180,height:120},data:{title:'Database',kind:'database',status:'failed',statusRole:'blocked',failure:{message:'probe <failed>'}}},
];
const edges=[{id:'e',label:'depends-on',data:{kind:'depends-on',points:[{x:220,y:140},{x:290,y:140}]}}];
const svg=developerFlowSvg({title:'Export test\u0000',nodes,edges,lod:'summary',exportedAt:'2026-08-24T00:00:00Z'});
const longSvg=developerFlowSvg({nodes:[],edges:[{label:'relationship-label-that-is-deliberately-wide',data:{points:[{x:0,y:0},{x:10,y:0}]}}]});
const viewBox=longSvg.match(/viewBox="([^"]+)"/)[1].split(' ').map(Number);
const labelRect=longSvg.match(/edge-label-bg" x="([^"]+)"[^>]+width="([^"]+)"/).slice(1).map(Number);
console.log(JSON.stringify({svg,longLabelContained:labelRect[0]>=viewBox[0]&&labelRect[0]+labelRect[1]<=viewBox[0]+viewBox[2]}));
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
    assert "vizzer-developer-flow-svg/v1" in svg
    assert "\u0000" not in svg
    assert result["longLabelContained"] is True


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
    assert "normalizeSavedViews" in source
    assert "navigator.clipboard.writeText" in source
    assert "triggerSvgDownload" in source
    assert "Export SVG" in source
