#!/usr/bin/env python3
"""Record validated Vizzer checkpoints and render a read-only, offline replay."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
try:
    import fcntl
except ImportError:
    fcntl = None
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vizzer.config import Config

ROOT = Path.cwd()
STORE = ROOT / 'vizzer/evolution'
VIEWS = ROOT / 'vizzer/views'

def configure(root):
    """Use the same contained output directory as refresh and serve."""
    global ROOT, STORE, VIEWS
    root = root.resolve()
    views = (root / Config.load(root).get('render.output_dir', 'vizzer/views')).resolve()
    if not views.is_relative_to(root):
        raise ValueError('Progress pathing output directory must stay inside the project')
    ROOT, STORE, VIEWS = root, root / 'vizzer/evolution', views

def digest(data):
    return hashlib.sha256(data).hexdigest()

def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data); out.flush(); os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)

@contextmanager
def lock():
    directory = ROOT / '.vizzer/runtime'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'evolution.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield

def events():
    path = STORE / 'events.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

def story_delta(old, new):
    before = {x['id']: x for x in old.get('items', [])}
    after = {x['id']: x for x in new.get('items', [])}
    added = sorted(after.keys() - before.keys())
    removed = sorted(before.keys() - after.keys())
    changed = sorted(i for i in before.keys() & after.keys() if before[i] != after[i])
    edges = lambda g: {(x['id'], d) for x in g.get('items', []) for d in x.get('deps', [])}
    return dict(added=added, removed=removed, changed=changed,
                dependenciesAdded=[list(x) for x in sorted(edges(new)-edges(old))],
                dependenciesRemoved=[list(x) for x in sorted(edges(old)-edges(new))])

def freeze(html, recorded_at):
    # Fail closed if an engine update changes the live-mode seam.
    seam = "const SERVED = location.protocol === 'http:';"
    if html.count(seam) != 1:
        raise ValueError('Cannot freeze this engine: live-mode seam changed')
    html = html.replace(seam, 'const SERVED = false; // archived, never call live services')
    epoch = int(datetime.fromisoformat(recorded_at.replace('Z', '+00:00')).timestamp()*1000)
    csp = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"
    frozen = f'<meta data-vizzer-frozen="1" http-equiv="Content-Security-Policy" content="{csp}"><script>Date.now=()=>{epoch};document.addEventListener("click",e=>{{if(e.target.closest("a"))e.preventDefault();}},true);</script>'
    if html.startswith('<meta charset="utf-8">'):
        return html.replace('<meta charset="utf-8">', '<meta charset="utf-8">'+frozen, 1)
    if html.count('<head>') == 1:
        return html.replace('<head>', '<head>'+frozen, 1)
    raise ValueError('Cannot freeze this engine: no supported metadata insertion point')

def record(caption='', baseline=None):
    with lock():
        graph_path = baseline / 'vizzer-graph.json' if baseline else ROOT/'vizzer/vizzer-graph.json'
        page_path = baseline / 'constellation.html' if baseline else VIEWS/'constellation.html'
        graph_bytes, page_bytes = graph_path.read_bytes(), page_path.read_bytes()
        graph = json.loads(graph_bytes)
        if graph.get('warnings'):
            raise ValueError('Refusing to archive a graph with source warnings')
        if not baseline:
            check = subprocess.run([sys.executable, str(ROOT/'vizzer/engine'), 'check'], cwd=ROOT, capture_output=True, text=True)
            if check.returncode:
                raise ValueError('Vizzer sources/views are stale; refresh before recording')
            if graph_bytes != graph_path.read_bytes() or page_bytes != page_path.read_bytes():
                raise ValueError('Vizzer changed during capture; retry the completed checkpoint')
        history = events()
        identity = digest(graph_bytes+page_bytes)
        if history and history[-1]['identity'] == identity and (not caption or caption == history[-1]['caption']):
            print('evolution: unchanged; no duplicate checkpoint', flush=True)
            return False
        now = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        previous = json.loads((STORE/history[-1]['graph']).read_text()) if history else {}
        delta = story_delta(previous, graph)
        if not caption:
            caption = (f"{len(delta['added'])} stories added, {len(delta['changed'])} changed, "
                       f"{len(delta['removed'])} removed; {len(graph.get('owner_questions', []))} open questions. "
                       'Recorded after a validated refresh; no invented intermediate steps.')
            old_work = {(w['story_id'],w['agent'],w['task']):w for w in previous.get('active_work',[])}
            changed_work = [w for w in graph.get('active_work',[]) if old_work.get((w['story_id'],w['agent'],w['task'])) != w]
            if changed_work:
                latest = max(changed_work,key=lambda w:w.get('updated_at',''))
                caption += ' '+latest['task']+': '+str(latest.get('checkpoint') or latest['state'])
        number = len(history)+1
        graph_name = f'snapshots/{number:06d}.json'
        frame_name = f'frames/{number:06d}.html.gz'
        frozen_bytes = freeze(page_bytes.decode(), now).encode()
        packed = gzip.compress(frozen_bytes, mtime=0)
        event = dict(schema=1, sequence=number, recordedAt=now, caption=caption,
                     identity=identity, graph=graph_name, graphSha256=digest(graph_bytes),
                     frame=frame_name, frameSha256=digest(packed), storyCount=len(graph['items']),
                     groupCount=len(graph.get('groups', [])), questionCount=len(graph.get('owner_questions', [])),
                     delta=delta, baseline=bool(baseline),
                     previousEventSha256=digest(json.dumps(history[-1],sort_keys=True).encode()) if history else None)
        # Payloads land before the journal entry that makes them visible. Orphans
        # from interruption are harmless; no event references an incomplete file.
        atomic(STORE/graph_name, graph_bytes)
        atomic(STORE/frame_name, packed)
        journal = STORE/'events.jsonl'
        with journal.open('ab') as out:
            out.write((json.dumps(event,sort_keys=True)+'\n').encode()); out.flush(); os.fsync(out.fileno())
        render_locked()
        print(f'evolution: checkpoint {number}: {caption}', flush=True)
        return True

def render_locked():
    history = events(); previous = None
    for index,event in enumerate(history,1):
        if event.get('schema') != 1 or event['graph'] != f'snapshots/{index:06d}.json' or event['frame'] != f'frames/{index:06d}.html.gz':
            raise ValueError('Evolution payload path/schema is invalid')
        if event['sequence'] != index or event['previousEventSha256'] != previous:
            raise ValueError('Evolution journal sequence/hash chain is invalid')
        graph = (STORE/event['graph']).read_bytes(); packed=(STORE/event['frame']).read_bytes()
        if digest(graph)!=event['graphSha256'] or digest(packed)!=event['frameSha256']:
            raise ValueError('Evolution snapshot content hash mismatch')
        frame = gzip.decompress(packed).decode()
        offline = 'const SERVED = false; // archived, never call live services'
        if frame.count(offline) != 1:
            raise ValueError('Archived frame has no recognized offline boundary')
        # Early captures used implicit-head HTML. Preserve immutable capture
        # bytes, but harden their playback projection before serving them.
        if 'data-vizzer-frozen="1"' not in frame:
            frame = freeze(frame.replace(offline, "const SERVED = location.protocol === 'http:';"), event['recordedAt'])
        atomic(VIEWS/f'evolution/frames/{index:06d}.html', frame.encode())
        previous=digest(json.dumps(event,sort_keys=True).encode())
    atomic(VIEWS/'evolution/index.json', (json.dumps(history,ensure_ascii=False)+'\n').encode())
    atomic(VIEWS/'evolution.html', (Path(__file__).parent/'render/constellation/evolution.html').read_bytes())

def render():
    with lock(): render_locked()
    print(f'evolution: rendered {len(events())} verified checkpoints',flush=True)

def watch(interval):
    # Observe completed refreshes, including owner-answer/server refreshes.
    # Do not race authors by initiating refreshes of half-written specifications.
    previous=None
    runtime=ROOT/'.vizzer/runtime';runtime.mkdir(parents=True,exist_ok=True)
    with (runtime/'evolution-watcher.lock').open('a') as watcher:
        try: fcntl.flock(watcher,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('Evolution watcher already running')
        while True:
            try:
                signature=digest((ROOT/'vizzer/vizzer-graph.json').read_bytes()+(VIEWS/'constellation.html').read_bytes())
                if signature!=previous:
                    record();previous=signature
                atomic(VIEWS/'evolution/recorder.json',json.dumps({'state':'watching','checkedAt':datetime.now(timezone.utc).isoformat(),'checkpoints':len(events())}).encode())
            except (ValueError, OSError, json.JSONDecodeError) as error:
                print('evolution: waiting for a valid checkpoint:',error,flush=True)
            time.sleep(interval)

def main():
    global ROOT, STORE, VIEWS
    if fcntl is None:
        raise SystemExit("Progress pathing recorder currently requires POSIX file locking (macOS/Linux).")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    subs=parser.add_subparsers(dest='command',required=True)
    capture=subs.add_parser('record');capture.add_argument('--caption',default='');capture.add_argument('--baseline',type=Path)
    subs.add_parser('render');subs.add_parser('verify')
    watcher=subs.add_parser('watch');watcher.add_argument('--interval',type=float,default=3)
    args=parser.parse_args()
    configure(args.root)
    if args.command=='record':record(args.caption,args.baseline)
    elif args.command in ('render','verify'):render()
    else:
        if args.interval<1:parser.error('interval must be at least one second')
        watch(args.interval)
if __name__=='__main__':main()
