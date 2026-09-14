"""A local, read-only proposal inbox with downloadable engine-relative patches."""
from __future__ import annotations

from collections import Counter
import html
import hashlib
import json

from ..radar import RadarError, patch_text, report


def summary(root):
    try:
        data = report(root)
        return {'enabled': True, 'scannedAt': data.get('scannedAt'),
                'counts': dict(Counter(p['state'] for p in data['proposals'])),
                'projects': len(data.get('projects', {})), 'errors': data.get('errors', {})}
    except (RadarError, KeyError, TypeError) as exc:
        return {'enabled': True, 'errors': {'radar': str(exc)}, 'counts': {}}


def render(graph, cfg, root):
    if not cfg.get('radar.enabled', False):
        return {}
    esc = lambda value: html.escape(str(value), quote=True)
    data = report(root)
    outputs = {}
    cards = []
    labels = {'exact': 'Exact code present', 'patch_present': 'Matching patch present',
              'missing': 'Missing · baseline unchanged', 'applicable': 'Patch applies cleanly',
              'needs_reconciliation': 'Needs reconciliation', 'unavailable': 'Unavailable'}
    proposals = sorted(data['proposals'], key=lambda p: (
        p['title'].startswith('Review engine change:'), p['state'] == 'adopted', p['title']))
    for p in proposals:
        patch_name = 'radar-patches/' + p['id'] + '.patch'
        patch = patch_text(p['path'], p['before'], p['after'])
        outputs[patch_name] = patch
        rows = ''.join('<tr><th>' + esc(project) + '</th><td>' + esc(labels.get(state, state)) + '</td></tr>'
                       for project, state in p['observations'].items())
        origins = ', '.join(f'{name} ({("uncommitted" if origin.get("dirty") else "working copy")}, '
                            f'HEAD {origin.get("head") or "unknown"}; comparison {origin.get("baseline")}; source {origin.get("fingerprint")})'
                            for name, origin in p['origins'].items())
        evidence = ''.join('<li>' + esc(e['path']) + ' · SHA-256 <code>' + esc(e['sha256']) + '</code></li>'
                           for e in p['evidence']) or '<li>No linked evidence yet.</li>'
        history = ''.join('<li>' + esc(h['at']) + ' · ' + esc(h['state']) + '</li>' for h in p['history'])
        review = esc(p['review']['note']) if p['review'] else 'No review recorded for this fingerprint.'
        narrative = '<p>Intent and rationale not yet captured. Attach an article brief before bringing this idea upstream.</p>'
        if p.get('brief'):
            brief = p['brief']
            if brief['fingerprint'] != p['id'] or hashlib.sha256(brief['body'].encode()).hexdigest() != brief['sha256']:
                raise RadarError('Article brief fingerprint mismatch')
            brief_name = 'radar-briefs/' + p['id'] + '.md'
            outputs[brief_name] = brief['body']
            narrative = (f'<details><summary>Intent, rationale and article material</summary>'
                         f'<p>Captured from {esc(brief["path"])} · {esc(brief["at"])}</p>'
                         f'<p><a href="{brief_name}" download>Download article brief</a> · '
                         f'{len(p.get("briefHistory", []))} captured revision(s)</p>'
                         f'<pre style="white-space:pre-wrap">{esc(brief["body"])}</pre></details>')
        cards.append(f'''<article data-state="{esc(p['state'])}">
<h2>{esc(p['title'])}</h2><p><strong>{esc(p['state'])}</strong> · <code>{esc(p['path'])}</code></p>
<p>{esc(p['summary'])}</p>{narrative}<table><caption>Observed installations</caption>{rows}</table>
<p><a href="{patch_name}" download>Download review patch</a> · Engine-relative paths; inspect and dry-run before applying.</p>
<details><summary>Diff and provenance</summary><p>Origins: {esc(origins)}</p>
<p>Change fingerprint: <code>{esc(p['id'])}</code></p>
<p>Before: <code>{esc(hashlib.sha256((p['before'] or '').encode()).hexdigest())}</code><br>
After: <code>{esc(hashlib.sha256((p['after'] or '').encode()).hexdigest())}</code></p>
<pre>{esc(patch[:30000])}</pre>{'<p>Preview truncated; download contains the full patch.</p>' if len(patch)>30000 else ''}
<h3>Linked evidence</h3><ul>{evidence}</ul><p>Linked artifacts are not proof that tests ran.</p>
<h3>Review</h3><p>{review}</p><h3>History</h3><ul>{history}</ul></details></article>''')
    errors = ''.join('<p class="error">' + esc(k) + ': ' + esc(v) + '</p>' for k, v in data.get('errors', {}).items())
    scanned = data.get('scannedAt', '')
    scanned_json = json.dumps(scanned).replace('<', '\u003c')
    outputs['radar.html'] = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Vizzer change radar</title>
<style>body{{margin:0;background:#10141c;color:#edf0f7;font:16px/1.55 system-ui}}main{{max-width:1080px;margin:auto;padding:24px}}a{{color:#8dccff}}h1{{margin-bottom:6px}}h2{{font-size:20px}}article{{margin:20px 0;padding:22px;border:1px solid #3a4458;border-radius:12px;background:#18202c}}table{{width:100%;text-align:left;border-collapse:collapse}}td,th{{padding:6px;border-bottom:1px solid #364053}}caption{{text-align:left;font-weight:bold}}pre{{overflow:auto;padding:12px;background:#0b1018;max-height:500px}}code{{overflow-wrap:anywhere;font-size:12px}}summary{{cursor:pointer}}input,select{{font:inherit;max-width:100%;padding:8px;margin:8px 12px 8px 0}}.error{{color:#ffb7a5}}[hidden]{{display:none}}small{{color:#b1bdd0}}</style>
<main><a href="constellation.html#dashboard">← Project dashboard</a><h1>Cross-project change radar</h1>
<p>Discover → review → integrate → adopt. Compare exact changes across registered local engines.</p>
<p><strong>{len(data['proposals'])} proposals</strong> · {len(data.get('projects', {}))} readable engines · Last scan: <time>{esc(scanned or 'not scanned')}</time></p>
<p id="watchstatus">Snapshot view. Scanning does not modify registered projects.</p>{errors}
<p><small>Integrated means the patch is in the local upstream commit, not necessarily published remotely. Matching hunks are code evidence, not semantic equivalence. Different implementations require review.</small></p>
<label>Find a change <input id="search" type="search" placeholder="Path, title or project"></label>
<label>State <select id="state"><option value="">All states</option>{''.join('<option>'+s+'</option>' for s in ['discovered','reviewed','integrated','adopted','superseded','unavailable'])}</select></label>
<p id="count"></p>{''.join(cards) or '<p>No proposals yet. Register a project and run radar scan.</p>'}</main>
<script>
const cards=[...document.querySelectorAll('article')],search=document.querySelector('#search'),state=document.querySelector('#state');
function filter(){{let count=0;for(const card of cards){{card.hidden=!(card.textContent.toLowerCase().includes(search.value.toLowerCase())&&(!state.value||card.dataset.state===state.value));if(!card.hidden)count++;}}document.querySelector('#count').textContent=count+' matching proposals';}}
search.addEventListener('input',filter);state.addEventListener('change',filter);filter();
const scanned={scanned_json};
if(location.protocol==='http:')setInterval(async()=>{{try{{const r=await fetch('/api/radar/status',{{cache:'no-store'}});if(!r.ok)throw Error();const s=await r.json();document.querySelector('#watchstatus').textContent=s.watchMessage;if(s.scannedAt&&s.scannedAt!==scanned)location.reload();}}catch(_){{document.querySelector('#watchstatus').textContent='Live status unavailable; this is the last rendered scan.';}}}},10000);
</script></html>'''
    return outputs
