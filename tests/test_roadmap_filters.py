import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWS = ROOT / "src" / "vizzer" / "render" / "constellation" / "views.js"
STATE = ROOT / "src" / "vizzer" / "render" / "constellation" / "state.js"


def query_probe(expression):
    module = "./src/vizzer/render/constellation/view_query.js"
    script = f"await import({json.dumps(module)});console.log(JSON.stringify({expression}));"
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], cwd=ROOT,
        capture_output=True, text=True, timeout=15, check=True,
    )
    return json.loads(result.stdout)


def test_roadmap_release_and_capability_filters_are_an_intersection():
    source = VIEWS.read_text(encoding="utf-8")
    assert "roadmapQuery.release?[roadmapQuery.release]:RELS" in source
    assert "roadmapCapabilityId(node)===roadmapQuery.capability" in source
    assert 'data-roadmap-filter="release"' in source
    assert 'data-roadmap-filter="capability"' in source
    assert "Drawing Tools" not in source


def test_dependency_order_is_stable_and_places_visible_prerequisites_first():
    ordered = query_probe(
        "globalThis.VizzerViewQuery.dependencyOrder([0,1,2],"
        "[{id:'consumer'},{id:'foundation'},{id:'middle'}],[[1,2],[2,0]])"
    )
    assert ordered == [1, 2, 0]


def test_dependency_cycle_fallback_is_deterministic():
    ordered = query_probe(
        "globalThis.VizzerViewQuery.dependencyOrder([2,0,1],"
        "[{id:'b'},{id:'c'},{id:'a'}],[[0,1],[1,0]])"
    )
    assert ordered == [2, 0, 1]


def test_last_modified_uses_normalized_evidence_and_unknown_sorts_last():
    ordered = query_probe(
        "[{node:{id:'unknown',ts:0}},{node:{id:'older',ts:4}},"
        "{node:{id:'newer',ts:9}}].sort(globalThis.VizzerViewQuery.compareModified)"
        ".map(entry=>entry.node.id)"
    )
    assert ordered == ["newer", "older", "unknown"]
    assert "modified ${node.ts?" in VIEWS.read_text(encoding="utf-8")


def test_route_state_restores_supported_query_values_without_urlsearchparams():
    state = STATE.read_text(encoding="utf-8")
    views = VIEWS.read_text(encoding="utf-8")
    assert "split('?')[0]" in state
    assert "decodeURIComponent(value" in state
    assert "URLSearchParams" not in state
    assert "roadmapParams.get('column')" in views
    assert "roadmapParams.get('capability')" in views
    assert "history.replaceState" in views


def test_clear_restores_all_and_empty_state_names_active_scope():
    source = VIEWS.read_text(encoding="utf-8")
    assert "No Roadmap items match ${roadmapQuery.release||'all columns'}" in source
    assert "roadmapQuery.release='';roadmapQuery.capability='';roadmapQuery.order='default'" in source
