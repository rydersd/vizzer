import importlib.util
import json
import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest

import vizzer.evolution as history

def test_configured_output_directory_and_escape_rejection(tmp_path):
    old = history.ROOT, history.STORE, history.VIEWS
    config = tmp_path / 'vizzer/vizzer.toml'
    config.parent.mkdir()
    try:
        config.write_text('[render]\noutput_dir = "reports/work"\n')
        history.configure(tmp_path)
        assert history.VIEWS == (tmp_path / 'reports/work').resolve()
        config.write_text('[render]\noutput_dir = "../outside"\n')
        with unittest.TestCase().assertRaisesRegex(ValueError, 'inside the project'):
            history.configure(tmp_path)
    finally:
        history.ROOT, history.STORE, history.VIEWS = old

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.old=(history.ROOT,history.STORE,history.VIEWS)
        history.ROOT=root;history.STORE=root/'vizzer/evolution';history.VIEWS=root/'vizzer/views'
        (root/'scripts/templates').mkdir(parents=True)
        (root/'scripts/templates/vizzer-evolution.html').write_text('<html>player</html>')
        self.baseline=root/'baseline';self.baseline.mkdir()
        self.page='<html><head></head><body><script>const SERVED = location.protocol === \'http:\';</script></body></html>'
        (self.baseline/'constellation.html').write_text(self.page)
        self.write_graph([dict(id='story:a',deps=[],status='specced')])
    def tearDown(self):
        history.ROOT,history.STORE,history.VIEWS=self.old;self.tmp.cleanup()
    def write_graph(self,items,warnings=None):
        (self.baseline/'vizzer-graph.json').write_text(json.dumps(dict(items=items,groups=[],warnings=warnings or [])))
    def capture(self):return history.record('test checkpoint',self.baseline)
    def test_record_deduplicates_and_replays_exact_content(self):
        self.assertTrue(self.capture());self.assertFalse(self.capture())
        self.assertEqual(len(history.events()),1)
        history.render()
        frozen=(history.VIEWS/'evolution/frames/000001.html').read_text()
        self.assertIn('const SERVED = false;',frozen)
        self.assertIn("connect-src 'none'",frozen)
        self.assertIn("form-action 'none'",frozen)
        self.assertIn('Date.now=()=>',frozen)
    def test_add_remove_and_dependency_changes_are_actual_deltas(self):
        self.capture()
        self.write_graph([dict(id='story:a',deps=['story:b'],status='specced'),dict(id='story:b',deps=[],status='backlog')])
        self.capture();e=history.events()[-1]
        self.assertEqual(e['delta']['added'],['story:b'])
        self.assertEqual(e['delta']['dependenciesAdded'],[['story:a','story:b']])
        self.write_graph([dict(id='story:b',deps=[],status='backlog')]);self.capture()
        self.assertEqual(history.events()[-1]['delta']['removed'],['story:a'])
        history.render()
    def test_explicit_annotation_preserves_unchanged_graph(self):
        self.capture()
        self.assertTrue(history.record('A new explanatory annotation',self.baseline))
        before,after=history.events()
        self.assertEqual(before['identity'],after['identity'])
        self.assertEqual(after['delta']['added'],[])
        self.assertEqual(after['caption'],'A new explanatory annotation')
        history.render()
    def test_tampered_snapshot_is_rejected(self):
        self.capture();(history.STORE/'snapshots/000001.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):history.render()
    def test_reordered_journal_is_rejected(self):
        self.capture();p=history.STORE/'events.jsonl';e=history.events()[0];e['sequence']=2;p.write_text(json.dumps(e)+'\n')
        with self.assertRaisesRegex(ValueError,'sequence'):history.render()
    def test_unknown_live_seam_and_missing_csp_location_fail_closed(self):
        for page in (self.page.replace('const SERVED','let SERVED'),self.page.replace('<head>','<HEAD>')):
            with self.assertRaisesRegex(ValueError,'Cannot freeze'):history.freeze(page,'2026-09-05T14:00:00Z')
    def test_source_warnings_are_not_archived(self):
        self.write_graph([],['unknown prerequisite'])
        with self.assertRaisesRegex(ValueError,'source warnings'):self.capture()
        self.assertFalse(history.events())
    def test_early_capture_is_hardened_without_rewriting_the_journal(self):
        self.capture()
        # Construct the original implicit-head capture format without CSP.
        event=history.events()[0]
        early=self.page.replace("const SERVED = location.protocol === 'http:';",'const SERVED = false; // archived, never call live services')
        packed=gzip.compress(early.encode(),mtime=0)
        (history.STORE/event['frame']).write_bytes(packed)
        event['frameSha256']=hashlib.sha256(packed).hexdigest()
        (history.STORE/'events.jsonl').write_text(json.dumps(event)+'\n')
        # Re-materialization must keep the append-only journal byte-identical.
        before=(history.STORE/'events.jsonl').read_bytes()
        history.render()
        self.assertEqual(before,(history.STORE/'events.jsonl').read_bytes())
        self.assertIn('data-vizzer-frozen="1"',(history.VIEWS/'evolution/frames/000001.html').read_text())
    def test_payload_cannot_escape_the_history_store(self):
        self.capture();p=history.STORE/'events.jsonl';e=history.events()[0];e['graph']='../../outside.json';p.write_text(json.dumps(e)+'\n')
        with self.assertRaisesRegex(ValueError,'path/schema'):history.render()

if __name__=='__main__':unittest.main()


def test_actual_rendered_page_has_early_csp(tmp_path,make_repo):
    from vizzer.cli import main
    repo=make_repo(tmp_path,'mixed_proj')
    assert main(['refresh','--root',str(repo)])==0
    page=(repo/'vizzer/views/constellation.html').read_text()
    frozen=history.freeze(page,'2026-09-05T14:00:00Z')
    assert 'data-vizzer-frozen="1"' in frozen
    assert frozen.index("connect-src 'none'") < frozen.index('<script>')
    assert 'const SERVED = false;' in frozen


def test_installed_recorder_captures_and_renders_without_project_scripts(tmp_path,make_repo):
    import subprocess,sys
    from vizzer.cli import main
    from vizzer.install import _vendor,_write_version
    repo=make_repo(tmp_path,'mixed_proj')
    _vendor(repo/'vizzer/engine');_write_version(repo)
    assert main(['refresh','--root',str(repo)])==0
    command=[sys.executable,str(repo/'vizzer/engine/vizzer/evolution.py'),'--root',str(repo)]
    result=subprocess.run(command+['record','--caption','Portable progress pathing proof'],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    entries=[json.loads(line) for line in (repo/'vizzer/evolution/events.jsonl').read_text().splitlines()]
    assert entries[0]['caption']=='Portable progress pathing proof'
    assert (repo/'vizzer/views/evolution.html').is_file()
    result=subprocess.run(command+['verify'],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


def test_editor_assets_and_about_are_in_rendered_views(tmp_path,make_repo):
    from vizzer.cli import main
    repo=make_repo(tmp_path,'mixed_proj')
    assert main(['refresh','--root',str(repo)])==0
    views=repo/'vizzer/views'
    page=(views/'constellation.html').read_text()
    assert 'src="milkdown.js"' in page and 'href="milkdown.css"' in page
    assert 'href="about.html"' in page
    assert 'Milkdown / Crepe 7.22.1' in (views/'about.html').read_text()
    assert 'Copyright (c) 2020-present Mirone' in (views/'THIRD-PARTY-NOTICES.txt').read_text()
    assert (views/'milkdown.js').stat().st_size>100000
