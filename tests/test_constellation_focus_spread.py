"""A focused cluster eases its stories apart and other capabilities make way."""
from __future__ import annotations

import json
import shutil
import subprocess

from vizzer.config import Config, DEFAULTS
from vizzer.render import render_all

from test_constellation_cluster_velocity import _graph
from test_render_constellation import _CONSTELLATION_COUNT_DOM_SHIM


def _probe(tmp_path) -> dict:
    node = shutil.which("node")
    assert node is not None, "Node is required to execute the rendered constellation"
    html = render_all(_graph(), Config(data=DEFAULTS), tmp_path, only={"constellation"})["constellation.html"]
    driver = _CONSTELLATION_COUNT_DOM_SHIM.replace(
        "sandbox.window=sandbox;",
        "sandbox.Element=Element;sandbox.window=sandbox;",
    ).replace(
        "process.stdout.write(JSON.stringify(out));",
        "const result=ev(`(()=>{"
        "document.body=document.body||{appendChild(){}};"
        "const settle=()=>{for(let f=0;f<400&&stepClusterSpread();f++);};"
        "const entered=enterClusterFocus('canvas');"
        "const animating=clusterSpread<CLUSTER_SPREAD;settle();"
        "const c=spreadCenter,R=spreadRadius;let memberRatioOk=true,otherOk=true;"
        "for(const n of DATA.nodes){const q=spreadPos(n),d0=Math.hypot(n.x-c.x,n.y-c.y,n.z-c.z),"
        "d1=Math.hypot(q.x-c.x,q.y-c.y,q.z-c.z);"
        "if(n.c==='canvas'){if(d0>1e-6&&Math.abs(d1/d0-CLUSTER_SPREAD)>1e-6)memberRatioOk=false;}"
        "else if(d0<=R&&d1<R*CLUSTER_SPREAD-1e-6)otherOk=false;else if(d1<d0-1e-9)otherOk=false;}"
        "const exited=exitClusterFocus();settle();"
        "const restored=DATA.nodes.every(n=>spreadPos(n)===n);"
        "return {entered,animating,memberRatioOk,otherOk,exited,restored,reduced:reducedMotion};})()`);"
        "process.stdout.write(JSON.stringify(result));",
    )
    run = subprocess.run(
        [node, "-e", driver], input=html, text=True, capture_output=True,
        timeout=10, check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout)


def test_focus_spreads_cluster_and_restores_on_exit(tmp_path) -> None:
    result = _probe(tmp_path)
    assert result["entered"] and result["exited"]
    # The shared DOM shim reports prefers-reduced-motion, so the spread must
    # snap to its end state; with motion allowed it eases instead.
    assert result["animating"] is (not result["reduced"]), "ease with motion, snap without"
    assert result["memberRatioOk"], "members spread radially by CLUSTER_SPREAD"
    assert result["otherOk"], "other capabilities are pushed out, never pulled inside"
    assert result["restored"], "exit returns every node to its layout position"
