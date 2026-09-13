"""Bounded temporary-repository checks for radar provenance and containment."""
import json
from pathlib import Path
import subprocess

import pytest

from vizzer import radar
from vizzer.cli import main
from vizzer.config import Config, DEFAULTS, deep_merge
from vizzer.model import Graph
from vizzer.render import render_all


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.STDOUT).decode().strip()


@pytest.fixture
def projects(tmp_path):
    root = tmp_path / 'upstream'
    downstream = tmp_path / 'project'
    for path in (root, downstream):
        path.mkdir()
        git(path, 'init', '-q')
        git(path, 'config', 'user.name', 'Radar fixture')
        git(path, 'config', 'user.email', 'radar@example.invalid')
    engine = root / 'src/vizzer'
    installed = downstream / 'vizzer/engine/vizzer'
    engine.mkdir(parents=True)
    installed.mkdir(parents=True)
    source = '\n'.join(f'line {n}' for n in range(30)) + '\n'
    for path in (engine / 'canvas.js', installed / 'canvas.js'):
        path.write_text(source)
    for path in (root, downstream):
        git(path, 'add', '.')
        git(path, 'commit', '-qm', 'baseline')
    radar.register(root, 'fixture', downstream, 'vizzer/engine/vizzer', 'HEAD')
    return root, downstream, engine, installed, source


def test_dirty_upstream_fix_is_discovered_not_integrated_and_does_not_write_target(projects):
    root, downstream, engine, installed, source = projects
    (engine / 'canvas.js').write_text(source.replace('line 12', 'repaired 12'))
    result = radar.scan(root)
    p, = result['proposals']
    assert p['state'] == 'discovered'
    assert p['observations'] == {'upstream': 'exact', 'fixture': 'missing'}
    assert p['origins']['upstream']['dirty'] is True
    assert (installed / 'canvas.js').read_text() == source
    assert git(downstream, 'status', '--porcelain') == ''
    assert radar.patch_text(p['path'], p['before'], p['after']).startswith('--- a/canvas.js')


def test_review_integrate_adopt_and_revoke_on_target_regression(projects):
    root, downstream, engine, installed, source = projects
    changed = source.replace('line 12', 'repaired 12')
    (installed / 'canvas.js').write_text(changed)
    first, = radar.scan(root)['proposals']
    radar.annotate(root, first['id'], review='Reviewed this exact patch')
    reviewed, = radar.scan(root)['proposals']
    assert reviewed['state'] == 'reviewed'
    (engine / 'canvas.js').write_text(changed)
    git(root, 'add', 'src')
    git(root, 'commit', '-qm', 'different commit message and history')
    adopted, = radar.scan(root)['proposals']
    assert adopted['state'] == 'adopted'
    assert adopted['id'] == first['id']
    assert adopted['review']['fingerprint'] == first['id']
    (installed / 'canvas.js').write_text(source)
    regressed, = radar.scan(root)['proposals']
    assert regressed['state'] == 'integrated'
    assert [h['state'] for h in regressed['history']] == ['discovered', 'reviewed', 'adopted', 'integrated']


def test_patch_equivalence_ignores_unrelated_edits_but_not_conflicting_implementation(projects):
    _, _, _, _, source = projects
    changed = source.replace('line 12', 'repaired 12')
    assert radar.presence('canvas.js', source, changed, changed.replace('line 0\n', 'unrelated\n')) == 'patch_present'
    assert radar.presence('canvas.js', source, changed, source.replace('line 0\n', 'unrelated\n')) == 'applicable'
    assert radar.presence('canvas.js', source, changed, source.replace('line 12', 'other repair')) == 'needs_reconciliation'


def test_content_change_does_not_inherit_previous_review(projects):
    root, _, _, installed, source = projects
    (installed / 'canvas.js').write_text(source.replace('line 12', 'repair one'))
    p, = radar.scan(root)['proposals']
    radar.annotate(root, p['id'], review='First patch only')
    (installed / 'canvas.js').write_text(source.replace('line 12', 'repair two'))
    result = radar.scan(root)
    new = next(x for x in result['proposals'] if x['id'] != p['id'])
    old = next(x for x in result['proposals'] if x['id'] == p['id'])
    assert new['review'] is None and new['state'] == 'discovered'
    assert old['state'] == 'superseded'


def test_missing_project_is_unavailable_not_adopted(projects):
    root, downstream, engine, _, source = projects
    (engine / 'canvas.js').write_text(source.replace('line 12', 'repair'))
    radar.scan(root)
    downstream.rename(downstream.with_name('offline'))
    result = radar.scan(root)
    assert 'fixture' in result['errors']
    assert result['proposals'][0]['observations']['fixture'] == 'unavailable'
    assert result['proposals'][0]['state'] != 'adopted'


def test_baseline_and_snapshot_reject_path_escape_and_symlinks(projects, tmp_path):
    root, downstream, _, installed, _ = projects
    with pytest.raises(radar.RadarError):
        radar.snapshot(root, '../project')
    outside = tmp_path / 'outside.py'
    outside.write_text('private')
    (installed / 'escape.py').symlink_to(outside)
    with pytest.raises(radar.RadarError):
        radar.snapshot(downstream, 'vizzer/engine/vizzer')
    with pytest.raises(radar.RadarError):
        radar.register(root, '../escape', downstream, 'vizzer/engine/vizzer', 'HEAD')


def test_tampered_baseline_does_not_replace_prior_report(projects):
    root, _, engine, _, source = projects
    (engine / 'canvas.js').write_text(source.replace('line 12', 'repair'))
    radar.scan(root)
    store = root / '.vizzer/radar'
    previous = (store / 'report.json').read_bytes()
    path, = store.glob('baseline-*.json')
    data = json.loads(path.read_text())
    data['files']['canvas.js'] = 'tampered'
    path.write_text(json.dumps(data))
    with pytest.raises(radar.RadarError, match='fingerprint'):
        radar.scan(root)
    assert (store / 'report.json').read_bytes() == previous


def test_downloaded_patch_applies_in_isolated_copy_and_handles_no_final_newline(tmp_path):
    before, after = 'old', 'new'
    patch = radar.patch_text('file.py', before, after)
    (tmp_path / 'file.py').write_text(before)
    subprocess.run(['git', 'apply', '--no-index', '-'], cwd=tmp_path,
                   input=patch.encode(), check=True, capture_output=True, timeout=5)
    assert (tmp_path / 'file.py').read_text() == after
    assert radar.presence('new.py', None, 'new\n', None) == 'missing'
    assert radar.presence('old.py', 'old\n', None, None) == 'exact'


def test_cli_and_opt_in_renderer_escape_proposals(projects):
    root, _, engine, _, source = projects
    (engine / 'canvas.js').write_text(source.replace('line 12', 'repair'))
    assert main(['radar', 'scan', '--root', str(root)]) == 0
    p, = radar.report(root)['proposals']
    radar.annotate(root, p['id'], title='<script>alert(1)</script>')
    cfg = Config(data=deep_merge(DEFAULTS, {'radar': {'enabled': True}}))
    rendered = render_all(Graph(), cfg, root, only={'radar'})
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in rendered['radar.html']
    assert '<script>alert(1)</script>' not in rendered['radar.html']
    assert 'radar-patches/' + p['id'] + '.patch' in rendered
    assert render_all(Graph(), Config(data=DEFAULTS), root, only={'radar'}) == {}


def test_empty_file_patch_creation_and_deletion(tmp_path):
    for before, after in [(None, ''), ('', None)]:
        path = tmp_path / 'empty.py'
        if before is not None:
            path.write_text(before)
        patch = radar.patch_text('empty.py', before, after)
        subprocess.run(['git', 'apply', '--no-index', '-'], cwd=tmp_path,
                       input=patch.encode(), capture_output=True, check=True, timeout=5)
        assert path.exists() == (after is not None)


def test_second_snapshot_detects_edit_during_scan(projects, monkeypatch):
    root, downstream, engine, installed, source = projects
    (engine / 'canvas.js').write_text(source.replace('line 12', 'repair'))
    radar.scan(root)
    report_path = root / '.vizzer/radar/report.json'
    prior = report_path.read_bytes()
    real = radar.snapshot
    calls = 0
    def changing(project, engine_path):
        nonlocal calls
        calls += 1
        if calls == 4:
            (installed / 'canvas.js').write_text('concurrent edit\n')
        return real(project, engine_path)
    monkeypatch.setattr(radar, 'snapshot', changing)
    with pytest.raises(radar.RadarError, match='changed during scan'):
        radar.scan(root)
    assert report_path.read_bytes() == prior


def test_corrupt_proposal_cannot_export_an_unsafe_patch_path(projects):
    root, _, engine, _, source = projects
    (engine / 'canvas.js').write_text(source.replace('line 12', 'repair'))
    radar.scan(root)
    path = root / '.vizzer/radar/report.json'
    data = json.loads(path.read_text())
    data['proposals'][0]['id'] = '../../outside'
    path.write_text(json.dumps(data))
    with pytest.raises(radar.RadarError, match='fingerprint'):
        radar.report(root)


def test_review_history_retains_previous_notes(projects):
    root, _, engine, _, source = projects
    (engine / 'canvas.js').write_text(source.replace('line 12', 'repair'))
    p, = radar.scan(root)['proposals']
    radar.annotate(root, p['id'], review='First review')
    radar.annotate(root, p['id'], review='Second review')
    updated, = radar.report(root)['proposals']
    assert [r['note'] for r in updated['reviewHistory']] == ['First review', 'Second review']


def test_article_brief_survives_edits_and_rescans_without_rewriting_history(projects):
    root, _, engine, _, source = projects
    (engine / 'canvas.js').write_text(source.replace('line 12', 'repair'))
    p, = radar.scan(root)['proposals']
    brief = root / 'idea.md'
    original = '## Intent\nKeep trails visible.\n## Rationale\n<script>source</script>\n## Sources\nOwner report.\n'
    brief.write_text(original)
    assert main(['radar', 'annotate', '--root', str(root), '--id', p['id'], '--brief', 'idea.md']) == 0
    brief.write_text(original.replace('Owner report.', 'New source.'))
    captured, = radar.scan(root)['proposals']
    assert captured['brief']['body'] == original
    from vizzer.render.radar import render
    cfg = Config(deep_merge(DEFAULTS, {'radar': {'enabled': True}}))
    outputs = render(Graph(), cfg, root)
    assert outputs['radar-briefs/' + p['id'] + '.md'] == original
    assert '&lt;script&gt;source&lt;/script&gt;' in outputs['radar.html']
    assert '<script>source</script>' not in outputs['radar.html']
    radar.annotate(root, p['id'], brief='idea.md')
    captured, = radar.report(root)['proposals']
    assert len(captured['briefHistory']) == 2
    assert captured['briefHistory'][0]['body'] == original
    (engine / 'canvas.js').write_text(source.replace('line 12', 'different repair'))
    changed = next(x for x in radar.scan(root)['proposals'] if x['id'] != p['id'])
    assert not changed.get('brief')


def test_article_brief_rejects_missing_context_and_path_escape(projects):
    root, _, engine, _, source = projects
    (engine / 'canvas.js').write_text(source.replace('line 12', 'repair'))
    p, = radar.scan(root)['proposals']
    (root / 'idea.md').write_text('Just a confident-sounding explanation.')
    before = (root / '.vizzer/radar/report.json').read_bytes()
    with pytest.raises(radar.RadarError, match='requires Intent'):
        radar.annotate(root, p['id'], brief='idea.md')
    with pytest.raises(radar.RadarError):
        radar.annotate(root, p['id'], brief='../escape.md')
    assert (root / '.vizzer/radar/report.json').read_bytes() == before
