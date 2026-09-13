"""Execute the production trail pass with offscreen and filtered endpoints."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('offscreen,filtered,expected', [
    ([False, False, False], [], 2),
    ([True, False, False], [], 2),
    ([True, True, True], [], 2),
    ([False, False, False], [1], 0),
])
def test_trails_clip_offscreen_points_without_bridging_filters(offscreen, filtered, expected):
    source = (Path(__file__).parents[1] / 'src/vizzer/render/constellation/canvas.js').read_text()
    body = source.split('  // Straight agent trails', 1)[1].split('  // Explicit agent-work', 1)[0]
    body = body[body.index('  if(lens.activity)'):]
    script = '''
const DATA={nodes:[0,1,2],agentTrails:[{agent:'A',points:[{n:0},{n:1},{n:2}]}]};
const offscreen=OFFSCREEN,filtered=FILTERED;
const P=[{x:-100,y:200},{x:400,y:200},{x:1000,y:200}].map((p,i)=>({...p,on:!offscreen[i]&&!filtered.includes(i)}));
const visible=n=>!filtered.includes(n),lens={activity:true};
const searchTerms=[],searchMatches=[true,true,true];
const agentTrailColor=()=>'#ffffff',rgbOf=()=>[255,255,255];
const gradients=[],arrows=[];let strokes=0;
const ctx={setLineDash(){},beginPath(){},moveTo(){},lineTo(){},stroke(){strokes++},
 createLinearGradient(){const stops=[];gradients.push(stops);return {addColorStop(p,c){stops.push([p,c])}}}};
const trailArrow=(a,b,c,alpha)=>arrows.push(alpha);
BODY
process.stdout.write(JSON.stringify({strokes,gradients,arrows}));
'''.replace('OFFSCREEN', json.dumps(offscreen)).replace('FILTERED', json.dumps(filtered)).replace('BODY', body)
    result = subprocess.run([shutil.which('node') or 'node', '-e', script],
                            capture_output=True, text=True, timeout=5, check=True)
    data = json.loads(result.stdout)
    assert data['strokes'] == expected
    if expected:
        assert data['gradients'][0][0][1] == 'rgba(255,255,255,0.12)'
        assert data['gradients'][-1][-1][1] == 'rgba(255,255,255,0.88)'
        assert data['arrows'][0] < data['arrows'][1]
