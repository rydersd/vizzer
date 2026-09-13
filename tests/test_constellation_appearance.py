"""Check rendered palettes and execute production appearance functions."""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1] / 'src/vizzer/render/constellation'


def palettes():
    css = (ROOT / 'tokens.css').read_text()
    blocks = re.findall(r'\{([^{}]+)\}', css)
    return [dict(re.findall(r'--([\w-]+):(#\w{6});', block)) for block in blocks
            if '--sky-top:' in block][:2]


def rgb(h):
    return [int(h[i:i+2], 16) for i in (1, 3, 5)]


def luminance(c):
    return sum(w*(v/255/12.92 if v/255 <= .04045 else ((v/255+.055)/1.055)**2.4)
               for w, v in zip([.2126, .7152, .0722], c))


def ratio(a, b):
    x, y = sorted([luminance(a), luminance(b)])
    return (y+.05)/(x+.05)


def test_text_and_control_palette_contrast_across_gradient():
    for palette in palettes():
        surfaces = [rgb(palette[k]) for k in ['bg', 'bg2', 'panel']]
        stops = [rgb(palette[k]) for k in ['sky-top', 'sky-mid', 'sky-bottom']]
        surfaces += [[a+(b-a)*t/100 for a,b in zip(start,end)]
                     for start,end in zip(stops,stops[1:]) for t in range(101)]
        for key in ['ink', 'mut', 'active', 'ready', 'buggap', 'shipped', 'accent',
                    'owner-override', 'specced', 'faint', 'parked', 'foundation']:
            assert min(ratio(rgb(palette[key]), bg) for bg in surfaces) >= 4.5, key
        assert min(ratio(rgb(palette['line']), bg) for bg in surfaces[:3]) >= 3


def test_production_node_colors_keep_contrast_for_low_contrast_tags():
    source = (ROOT/'state.js').read_text().split('function relativeLuminance', 1)[1]
    source = 'function relativeLuminance'+source.split('const canvasVisible', 1)[0]
    script = 'const palettes='+json.dumps(palettes())+''';
const mixA=(a,b,t)=>a.map((v,i)=>Math.round(v+(b[i]-v)*t));
const parse=h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));
let RGB={};const contrastColors=new Map();
''' + source + '''
const out=[];
for(const p of palettes){RGB={ink:parse(p.ink),sky:['sky-top','sky-mid','sky-bottom'].map(k=>parse(p[k]))};contrastColors.clear();
for(const input of [[255,255,255],[0,0,0],[128,128,128],[255,0,255]]){
for(const target of [3.1,4.5,7])out.push({target,color:contrastNodeColor(input,target),sky:RGB.sky});}}
process.stdout.write(JSON.stringify(out));
'''
    result = subprocess.run([shutil.which('node'), '-e', script], capture_output=True,
                            text=True, check=True, timeout=5)
    for row in json.loads(result.stdout):
        assert min(ratio(row['color'], bg) for bg in row['sky']) >= row['target']


def test_theme_buttons_persist_and_system_removes_override():
    source = (ROOT/'preferences.js').read_text().split('// ---- title-bar',1)[0]
    script = '''
const assert=require('assert');const attrs={},store={},buttons=['light','dark','system'].map(mode=>({dataset:{themeChoice:mode},setAttribute(k,v){this[k]=v},classList:{toggle(){}},addEventListener(k,f){this.click=f}}));
const document={documentElement:{setAttribute(k,v){attrs[k]=v},removeAttribute(k){delete attrs[k]}},getElementById(){return {querySelectorAll(){return buttons}}}};
const localStorage={getItem:k=>store[k],setItem(k,v){store[k]=v}};let recolors=0;const recolor=()=>recolors++;
''' + source + '''
buttons[0].click();assert.equal(attrs['data-theme'],'light');assert.equal(buttons[0]['aria-pressed'],'true');
buttons[1].click();assert.equal(attrs['data-theme'],'dark');assert.equal(store['vizzer:color-mode'],'dark');
buttons[2].click();assert.equal(attrs['data-theme'],undefined);assert.equal(store['vizzer:color-mode'],'system');assert.equal(buttons[1]['aria-pressed'],'false');
assert.equal(recolors,4);
'''
    subprocess.run([shutil.which('node'), '-e', script], capture_output=True,
                   text=True, check=True, timeout=5)


def test_cluster_focus_preserves_context_but_respects_explicit_filters(tmp_path):
    from vizzer.config import Config, DEFAULTS
    from vizzer.model import Graph, Group, Item
    from vizzer.render import render_all
    from test_render_constellation import _CONSTELLATION_COUNT_DOM_SHIM
    graph = Graph(groups=[Group(id='capability:a', kind='capability', title='A'),
                          Group(id='capability:b', kind='capability', title='B')], items=[
        Item(id='story:a', title='A', status='ready', group='capability:a'),
        Item(id='story:b', title='B', status='ready', group='capability:b')])
    html = render_all(graph, Config(data=DEFAULTS), tmp_path, only={'constellation'})['constellation.html']
    script = _CONSTELLATION_COUNT_DOM_SHIM.split('const out={initial:', 1)[0]+'''
ev(`capFocus=DATA.nodes[0].c;groupFocus=null`);
const before=ev(`DATA.nodes.map(n=>({canvas:canvasVisible(n),outside:outsideCluster(n),focused:visible(n)}))`);
ev(`filt.ready=false`);
const filtered=ev(`DATA.nodes.map(canvasVisible)`);
process.stdout.write(JSON.stringify({before,filtered}));
'''
    result = subprocess.run([shutil.which('node'), '-e', script], input=html,
                            capture_output=True, text=True, check=True, timeout=5)
    data = json.loads(result.stdout)
    assert data['before'] == [{'canvas': True, 'outside': False, 'focused': True},
                              {'canvas': True, 'outside': True, 'focused': False}]
    assert data['filtered'] == [False, False]


def test_foundation_chip_uses_authored_membership_and_handles_parent_cycles():
    source=(ROOT/'filters.js').read_text()
    functions=source[source.index('function foundationalGroup'):source.index('function registerMeter')]
    script="""
const DATA={groups:[{id:'root',kind:'foundation'},{id:'epic',parent:'root'},
{id:'cycle',parent:'cycle'}]};
const esc=value=>String(value);const structuralKindLabel=value=>value;
"""+functions+"""
const results=[foundationalGroup(DATA.groups[1]),foundationalGroup(DATA.groups[2]),
foundationalGroup(null,[{tags:['foundational']}]),foundationalGroup(null,[{tags:['unrelated']}]),
meterMarkup('Epic',4,1,0,'epic',true).includes('aria-label="Foundational"'),
meterMarkup('Other',4,1,0,'epic',false).includes('foundationchip')];
console.log(JSON.stringify(results));
"""
    result=subprocess.run([shutil.which('node'),'-e',script],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==[True,False,True,False,True,False]
