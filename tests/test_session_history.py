import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
import subprocess
from unittest.mock import patch

from vizzer import session_history as h

module=Path(h.__file__)

class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        (self.base/'repo').mkdir()
        self.index=h.History(self.base/'repo',self.base,self.base/'cache')
        self.index.last_scan=time.time()
        self.now=time.time();self.path=self.base/'source.jsonl'
    def tearDown(self): self.tmp.cleanup()
    def write(self,records,mode='w'):
        with self.path.open(mode) as f:
            for r in records:f.write(json.dumps(r)+'\n')
    def meta(self,cwd=None):
        cwd = cwd or str(self.base/'repo')
        return {'type':'session_meta','payload':{'id':'sample','cwd':cwd}}
    def message(self,text='Changed the view because the graph was stale.',ts=None,kind='agent_message'):
        return {'timestamp':h.iso(ts or self.now),'type':'event_msg','payload':{'type':kind,'message':text}}
    def rows(self):
        with self.index.connect() as c:return [dict(x) for x in c.execute('SELECT * FROM events')]
    def test_rolling_window_and_duplicate_import(self):
        self.write([self.meta(),self.message(ts=self.now-h.WINDOW-1),self.message()])
        self.index.ingest(self.path,'Codex',self.now);self.index.ingest(self.path,'Codex',self.now)
        self.assertEqual(len(self.rows()),1)
    def test_replayed_record_at_new_offset_deduplicates(self):
        record=self.message()
        self.write([self.meta(),record,record]);self.index.ingest(self.path,'Codex',self.now)
        self.assertEqual(len(self.rows()),1)
    def test_partial_tail_is_retried(self):
        self.write([self.meta()]);raw=json.dumps(self.message())
        with self.path.open('a') as f:f.write(raw[:30])
        self.index.ingest(self.path,'Codex',self.now);self.assertEqual(self.rows(),[])
        with self.path.open('a') as f:f.write(raw[30:]+'\n')
        self.index.ingest(self.path,'Codex',self.now);self.assertEqual(len(self.rows()),1)
    def test_reasoning_tool_arguments_and_outputs_never_imported(self):
        records=[self.meta(),self.message('PRIVATE',kind='agent_reasoning'),{'timestamp':h.iso(self.now),'type':'response_item','payload':{'type':'custom_tool_call_output','output':'PRIVATE'}},{'timestamp':h.iso(self.now),'type':'response_item','payload':{'type':'function_call','name':'exec','arguments':'PRIVATE'}}]
        self.write(records);self.index.ingest(self.path,'Codex',self.now)
        self.assertEqual(len(self.rows()),1);self.assertNotIn('PRIVATE',json.dumps(self.rows()))
    def test_injected_context_is_removed_without_dropping_authored_request(self):
        contexts = []
        for tag in ('in-app-browser-context', 'app-context', 'environment_context'):
            text = (f'<{tag}>Secret injected {tag} metadata.</{tag}>\n'
                    '## My request:\nKeep the real request.')
            codex = {'type': 'event_msg', 'payload': {
                'type': 'user_message', 'message': text,
            }}
            claude = {'type': 'user', 'message': {'content': text}}
            for provider, record in (('Codex', codex), ('Claude', claude)):
                public = list(h.public_events(record, provider))
                self.assertEqual(
                    public, [('guidance', '## My request:\nKeep the real request.', '')],
                    (provider, tag),
                )
                self.assertNotIn('Secret injected', json.dumps(public))
            contexts.append(codex)
        self.write([
            self.meta(),
            self.message(contexts[0]['payload']['message'], kind='user_message'),
        ])
        self.index.ingest(self.path, 'Codex', self.now)
        imported = json.dumps(self.rows())
        self.assertIn('Keep the real request.', imported)
        self.assertNotIn('Secret injected', imported)
    def test_context_only_public_message_is_not_imported(self):
        self.write([
            self.meta(),
            self.message('<environment_context>ambient only</environment_context>',
                         kind='user_message'),
        ])
        self.index.ingest(self.path, 'Codex', self.now)
        self.assertEqual(self.rows(), [])
    def test_claude_injected_command_wrappers_are_never_guidance(self):
        tags = (
            'system-reminder', 'local-command-caveat', 'local-command-stdout',
            'command-name', 'command-message', 'command-args',
        )
        for tag in tags:
            mixed = (f'<{tag}>PRIVATE injected command material</{tag}>\n'
                     'Keep the authentic request.')
            for content in (mixed, [{'type': 'text', 'text': mixed}]):
                record = {'type': 'user', 'message': {'content': content}}
                public = list(h.public_events(record, 'Claude'))
                self.assertEqual(
                    public, [('guidance', 'Keep the authentic request.', '')],
                    (tag, type(content).__name__),
                )
                self.assertNotIn('PRIVATE', json.dumps(public))
            only = {'type': 'user', 'message': {
                'content': f'<{tag}>PRIVATE only</{tag}>',
            }}
            self.assertEqual(list(h.public_events(only, 'Claude')), [], tag)
    def test_claude_assistant_context_is_sanitized(self):
        record = {'type': 'assistant', 'message': {'content': [
            {'type': 'text', 'text': (
                '<system-reminder>PRIVATE assistant context</system-reminder>\n'
                'Public progress remains.'
            )},
        ]}}
        self.assertEqual(
            list(h.public_events(record, 'Claude')),
            [('progress', 'Public progress remains.', '')],
        )
        record['message']['content'][0]['text'] = (
            '<system-reminder>PRIVATE only</system-reminder>'
        )
        self.assertEqual(list(h.public_events(record, 'Claude')), [])
    def test_privacy_migration_rekeys_events_refs_and_generated_archives(self):
        sid = 'claude:legacy'
        old_id = 'legacy-event'
        with self.index.connect() as c:
            c.execute(
                'INSERT INTO sessions VALUES(?,?,?,?,?,?,?)',
                (sid, 'Claude',
                 '<system-reminder>PRIVATE title</system-reminder>\nAuthentic title',
                 str(self.base/'repo'), '', '',
                 str(self.path)),
            )
            c.execute(
                'INSERT INTO events VALUES(?,?,?,?,?,?,?)',
                (old_id, sid, self.now, 'progress',
                 '<system-reminder>PRIVATE story:secret</system-reminder>\n'
                 'Public progress for story:visible.', '', 1),
            )
            c.execute(
                'INSERT INTO event_story_refs VALUES(?,?)',
                (old_id, 'story:secret'),
            )
            c.execute("DELETE FROM history_meta WHERE key='public_event_schema'")
            c.execute("DELETE FROM history_meta WHERE key='public_archive_schema'")
        generated = self.base/'cache/work-history'
        generated.mkdir(parents=True, exist_ok=True)
        (generated/'00000000000000000000.md').write_text(
            '<system-reminder>PRIVATE stale archive</system-reminder>\n'
        )
        (generated/'00000000000000000000.jsonl').write_text(
            '{"text":"PRIVATE stale archive"}\n'
        )

        original_rewrite = h.History._rewrite_all_exports
        try:
            h.History._rewrite_all_exports = lambda _self: (_ for _ in ()).throw(
                OSError('simulated archive write failure')
            )
            with self.assertRaisesRegex(OSError, 'simulated archive write failure'):
                h.History(self.base/'repo', self.base, self.base/'cache')
        finally:
            h.History._rewrite_all_exports = original_rewrite

        # Database privacy work commits independently; archive completion does not.
        with self.index.connect() as c:
            self.assertEqual(
                c.execute("SELECT value FROM history_meta WHERE key='public_event_schema'").fetchone()[0],
                h.PUBLIC_EVENT_SCHEMA,
            )
            self.assertIsNone(c.execute(
                "SELECT value FROM history_meta WHERE key='public_archive_schema'"
            ).fetchone())
        self.assertIn('PRIVATE stale archive',
                      (generated/'00000000000000000000.md').read_text())

        migrated = h.History(self.base/'repo', self.base, self.base/'cache')
        migrated.last_scan = time.time()
        with migrated.connect() as c:
            events = [dict(row) for row in c.execute('SELECT * FROM events')]
            refs = [tuple(row) for row in c.execute(
                'SELECT event,story FROM event_story_refs'
            )]
            title = c.execute(
                'SELECT title FROM sessions WHERE id=?', (sid,)
            ).fetchone()[0]
            archive_schema = c.execute(
                "SELECT value FROM history_meta WHERE key='public_archive_schema'"
            ).fetchone()[0]
        self.assertEqual(len(events), 1)
        self.assertNotEqual(events[0]['id'], old_id)
        self.assertEqual(events[0]['text'], 'Public progress for story:visible.')
        self.assertEqual(refs, [(events[0]['id'], 'story:visible')])
        self.assertEqual(title, 'Authentic title')
        self.assertEqual(archive_schema, h.PUBLIC_ARCHIVE_SCHEMA)
        self.assertNotIn('PRIVATE', json.dumps(migrated.payload()))
        archives = ''.join(
            path.read_text() for path in generated.iterdir() if path.is_file()
        )
        self.assertNotIn('PRIVATE', archives)
        self.assertNotIn('<system-reminder>', archives)
        self.assertFalse((generated/'00000000000000000000.md').exists())
    def test_unrelated_project_excluded(self):
        self.write([self.meta('/tmp/unrelated'),self.message('mentions the project')]);self.index.ingest(self.path,'Codex',self.now);self.assertEqual(self.rows(),[])
    def test_claude_text_only_and_provider_identity(self):
        self.write([{'type':'assistant','sessionId':'sample','cwd':str(self.base/'repo'),'timestamp':h.iso(self.now),'message':{'content':[{'type':'thinking','thinking':'PRIVATE'},{'type':'text','text':'Test failed because fixture was stale.'},{'type':'tool_use','name':'Bash','input':{'command':'PRIVATE'}}]}}])
        self.index.ingest(self.path,'Claude',self.now)
        self.assertEqual(len(self.rows()),2);self.assertTrue(all(x['session']=='claude:sample' for x in self.rows()));self.assertNotIn('PRIVATE',json.dumps(self.rows()))
    def test_log_is_known_session_only_and_export_correlates(self):
        self.write([self.meta(),self.message()]);self.index.ingest(self.path,'Codex',self.now)
        self.assertIsNone(self.index.log('../../etc/passwd'))
        self.index.export('codex:sample');log=self.index.log('codex:sample')
        self.assertIn(self.rows()[0]['id'],log['markdown'])
        archive = self.index.cache/'work-history'/(
            hashlib.sha256('codex:sample'.encode()).hexdigest()[:20]+'.md'
        )
        self.assertTrue(archive.is_file())
    def test_markdown_export_never_emits_machine_local_file_links(self):
        path = ('file:///Users/example/Developer/GitHub/'
                'sample-project-feature-co/wiki/dev/report.md')
        self.write([self.meta(), self.message('Inspect '+path)])
        self.index.ingest(self.path, 'Codex', self.now)
        self.index.export('codex:sample')
        log = self.index.log('codex:sample')['markdown']
        self.assertNotIn('file://', log)
        self.assertNotIn('/Users/example', log)
        self.assertIn('`local file: wiki/dev/report.md`', log)
        exported = (self.index.cache/'work-history'/
                    (h.hashlib.sha256(b'codex:sample').hexdigest()[:20]+'.md'))
        self.assertEqual(exported.read_text(), log)
    def test_local_file_reference_markdown_and_punctuation_remain_readable(self):
        cases = {
            '[report](file:///Users/me/sample-project/wiki/dev/a.md).':
                'report (`local file: wiki/dev/a.md`).',
            '<file:///Users/me/sample-project/wiki/dev/a.md>.':
                '`local file: wiki/dev/a.md`.',
            'file:///Users/me/sample-project/wiki/dev/a.md, next':
                '`local file: wiki/dev/a.md`, next',
            'file://localhost/Users/me/sample-project/wiki/My%20Report.md!':
                '`local file: wiki/My Report.md`!',
            'file:///Users/me/private/secret.txt;':
                '`local file: secret.txt`;',
            '`file:///Users/me/sample-project/wiki/dev/a.md` now':
                '`local file: wiki/dev/a.md` now',
            '"file:///Users/me/sample-project/wiki/dev/a.md"':
                '"`local file: wiki/dev/a.md`"',
            "'file:///Users/me/private/secret.txt'":
                "'`local file: secret.txt`'",
            '{"source":"file:///Users/me/sample-project/wiki/a.md"}':
                '{"source":"`local file: wiki/a.md`"}',
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                rendered = h.archive_markdown_text(source)
                self.assertEqual(rendered, expected)
                self.assertNotIn('file://', rendered)
    def test_secret_redaction(self):
        self.assertNotIn('ghp_12345678901234567890',h.clean('key ghp_12345678901234567890'))
        self.assertNotIn('password=abc',h.clean('password=abc'))
    def test_public_team_handoff_keeps_reason_and_sender(self):
        raw='<codex_delegation><source_thread_id>team-1</source_thread_id><input>Hold because the test failed.</input></codex_delegation>'
        self.write([self.meta(),self.message(raw,kind='user_message')])
        self.index.ingest(self.path,'Codex',self.now)
        self.assertEqual(self.rows()[0]['kind'],'guidance')
        self.assertIn('team-1',self.rows()[0]['text'])
        self.assertIn('because the test failed',self.rows()[0]['text'])
        self.assertEqual(h.session_label(raw),'Hold because the test failed.')
    def test_session_labels_are_compact_and_identifiable(self):
        self.assertEqual(h.session_label('<teammate-message summary="Repair typography">'),'Repair typography')
        self.assertIn('session-123',h.session_label('', '/tmp/sample-project-co','session-123'))
        self.assertLessEqual(len(h.session_label('x'*400)),111)
    def test_orphan_markdown_table_line_does_not_hang_sidebar(self):
        renderer=module.parent/'render/constellation/markdown.js'
        script="const vm=require('vm'),fs=require('fs');const c={esc:s=>String(s)};vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);if(!vm.runInContext(\"renderStoryMarkdown('| a log row |')\",c,{timeout:500}).includes('a log row'))process.exit(1)"
        result=subprocess.run(['node','-e',script,str(renderer)],capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_canvas_trails_filter_hit_and_preserve_answer_draft(self):
        frontend=module.parent/'render/constellation/session_history.js'
        script=r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',value:'',textContent:'',classList:{add(){},toggle(){}},setAttribute(){},addEventListener(){}});return elements.get(id)};
const c={document:{getElementById:element,addEventListener(){},documentElement:{classList:{add(){}}}},SERVED:false,esc:s=>s,setTimeout:()=>1,clearTimeout(){},
 nodeById:new Map([['story:a',0],['story:b',1],['story:c',2]]),P:[{x:0,y:0,on:true},{x:100,y:0,on:true},{x:100,y:100,on:true}],lens:{activity:true},
 C:{trails:['blue','unused','gold']},sel:-1,dbody:element('body'),dossier:element('dossier'),dismissDossier:()=>false};
vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
vm.runInContext(`sessionHistory.payload={sessions:[{id:'c',provider:'Codex',model:'gpt-6-astra',title:'Codex lane'},{id:'a',provider:'Claude',model:'claude-opus-5',title:'Claude lane'},{id:'c2',provider:'Codex',model:'gpt-6-astra',title:'Same model'}],bins:[],references:[
{session:'c',storyId:'story:a',event:'e1'},{session:'c',storyId:'story:b',event:'e2'},
{session:'a',storyId:'story:b',event:'e3'},{session:'a',storyId:'story:c',event:'e4'}]};sessionHistory.payload.references.forEach((r,i)=>{r.timestamp=Date.now()/1000-7200+i;r.eventStoryCount=1});historyRenderDock()`,c);
assert.equal(vm.runInContext("historyColor('c')===historyColor('c2')",c),true);
assert.equal(vm.runInContext("historyColor('c')!==historyColor('a')",c),true);
assert.equal(vm.runInContext('historyOpacity(10000,10000)',c),1);
assert.equal(vm.runInContext('historyOpacity(10000,10000+36*3600)',c),.5);
assert.equal(vm.runInContext('historyOpacity(10000,10000+72*3600)',c),0);
assert.equal(vm.runInContext('hitSessionHistory(58.25,-8.15).event',c),'e2');
assert.equal(vm.runInContext('hitSessionHistory(102.25,35.85).event',c),'e4');
vm.runInContext('historyQueueClick(hitSessionHistory(58.25,-8.15),58.25,-8.15)',c);
assert.equal(vm.runInContext('historyDoubleClick(58.25,-8.15)',c),true);
assert.equal(vm.runInContext('sessionHistory.session',c),'c');
assert.equal(vm.runInContext('hitSessionHistory(102.25,35.85)',c),null);
assert.equal(element('historyisolation').hidden,false);
assert.ok(element('historyisolatedlabel').textContent.includes('Path isolated'));
element('historyall').onclick();
assert.equal(element('historyisolation').hidden,true);
assert.equal(vm.runInContext('sessionHistory.hours',c),72);
assert.equal(vm.runInContext('typeof historyEscape',c),'undefined');
assert.equal(vm.runInContext('hitSessionHistory(102.25,35.85).event',c),'e4');
element('historylength').oninput({target:{value:'1'}});
assert.equal(vm.runInContext('sessionHistory.points.length',c),0);
assert.equal(vm.runInContext('hitSessionHistory(58.25,-8.15)',c),null);
element('historylength').oninput({target:{value:'72'}});
assert.equal(vm.runInContext('hitSessionHistory(58.25,-8.15).event',c),'e2');
vm.runInContext("sessionHistory.provider='Claude';historyRenderDock()",c);
assert.equal(vm.runInContext('hitSessionHistory(58.25,-8.15)',c),null);
assert.equal(vm.runInContext('hitSessionHistory(102.25,35.85).event',c),'e4');
vm.runInContext('P[2].on=false',c);assert.equal(vm.runInContext('hitSessionHistory(102.25,35.85).event',c),'e4');
vm.runInContext('P[2]=null',c);assert.equal(vm.runInContext('hitSessionHistory(102.25,35.85)',c),null);
c.sel=1;element('body').innerHTML='UNSAVED ANSWER';
assert.equal(vm.runInContext("historySidebar('history','overwrite')",c),false);
assert.equal(element('body').innerHTML,'UNSAVED ANSWER');
// Parking a draft must replay the exact requested history navigation.
c.storyDraftDirty=()=>true;c.guardNavigationAway=fn=>{c.pendingNavigation=fn;return false};
c.dismissDossier=()=>{c.sel=-1;return true};c.sel=1;element('body').innerHTML='DRAFT';
assert.equal(vm.runInContext("historySidebar('history','LOG')",c),false);assert.equal(element('body').innerHTML,'DRAFT');
c.pendingNavigation();assert.equal(element('body').innerHTML,'LOG');
vm.runInContext("sessionHistory.provider='';sessionHistory.payload.references[1].event='e1';sessionHistory.payload.references[0].eventStoryCount=2;sessionHistory.payload.references[1].eventStoryCount=2;historyRenderDock()",c);
assert.equal(vm.runInContext("sessionHistory.segments.some(s=>s.session==='c')",c),false);
assert.equal(vm.runInContext("sessionHistory.points.filter(p=>p.session==='c').length",c),2);
// Original ambiguity survives when the event's other Story is not on the map.
vm.runInContext("sessionHistory.payload.references=[{session:'c',storyId:'story:a',event:'one',eventStoryCount:1,timestamp:Date.now()/1000-20},{session:'c',storyId:'story:b',event:'many',eventStoryCount:2,timestamp:Date.now()/1000-10},{session:'c',storyId:'story:removed',event:'many',eventStoryCount:2,timestamp:Date.now()/1000-10}];historyRenderDock()",c);
assert.equal(vm.runInContext("sessionHistory.segments.some(s=>s.session==='c')",c),false);
const request='Perform an independent adversarial shipping review of a frozen task-selection repair. Main risk: selectedTaskMembership returns a request-local union. Attack missing or duplicate IDs, mixed selection, filtering, locked state, request lifetime, source ordering and complexity, module growth, test tautology, evidence attribution, and foreign composition constraints. Inspect the raw regression record: one failed method, eighteen assertion occurrences but three deduplicated issue summaries. Full cleanup remains slow: commit 823 ms and cancel 408 ms. Return PASS or REPAIR.';
c.record=request+' Evidence directory local-review/diagnosis includes the corrected fixture failure and final summary.';
const insight=vm.runInContext('historyInsights(record)',c);
assert.equal(insight.risks.length,1);assert.equal(insight.checks.length,10);
assert.equal(insight.challenges.length,1);assert.ok(insight.challenges[0].includes('823 ms'));
assert.equal(insight.evidence.length,1);assert.ok(insight.evidence[0].includes('corrected fixture'));
assert.equal(insight.checks[9],'foreign composition constraints');
assert.ok(!insight.challenges.join(' ').includes('Attack'));
assert.ok(insight.suggestions.some(s=>s.includes('negative control')));
assert.ok(insight.suggestions.some(s=>s.includes('Performance follow-up')));
assert.ok(insight.markdown.includes('not confirmed defects'));
assert.ok(insight.markdown.includes('UI-generated suggestions'));
assert.equal(vm.runInContext("historyInsights('No failures or blockers were found.').challenges.length",c),0);
assert.equal(vm.runInContext("historyInsights('We should add a regression because the fixture was stale.').opportunities.length",c),1);
const vanished=vm.runInContext("historyInsights('The worktree disappeared. Checking whether anything was lost.')",c);
assert.equal(vanished.challenges.length,1);assert.ok(vanished.suggestions.some(s=>s.includes('Continuity:')));
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),c);
c.esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const html=vm.runInContext('renderStoryMarkdown(historyInsights(record).markdown)',c);
assert.ok(html.includes('<ul'));assert.ok(html.includes('<strong>Coverage:'));
assert.ok(!vm.runInContext("renderStoryMarkdown(historyInsights('The task failed <script>alert(1)</script>.').markdown)",c).includes('<script>'));
(async()=>{
 c.sel=-1;
 c.URLSearchParams=URLSearchParams;
 c.fetch=async()=>({ok:true,json:async()=>({events:[],nextOffset:null,total:0,tools:['exec'],matchingEvents:0,totalEvents:10,eventCount:0,path:'local.md',markdown:'# Log'})});
 await vm.runInContext("historyOpenSession('c')",c);
 assert.ok(element('body').innerHTML.indexOf('Work progress filters')<element('body').innerHTML.indexOf('Recorded worktree'));
 assert.equal(element('historykind').value,'progress');
 vm.runInContext("historyLogFilter.tool='@exec';historyLogFilter.q='needle'",c);
 await vm.runInContext("historyOpenLog('c')",c);
 assert.ok(element('body').innerHTML.includes('class="historyfilterbar" aria-label="Work log filters"'));
 assert.equal(element('historylogtool').value,'@exec');
 assert.ok(element('body').innerHTML.includes('value="needle"'));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',script,str(frontend),str(frontend.parent/'markdown.js')],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_history_filter_bars_stick_inside_existing_sidebar_scroller(self):
        css=(module.parent/'render/constellation/session_history.css').read_text()
        rule=css.split('.historyfilterbar{',1)[1].split('}',1)[0]
        for declaration in ('position:sticky','top:-12px','background:var(--panel)','z-index:2'):
            self.assertIn(declaration,rule)
        layout=(module.parent/'render/constellation/layout.css').read_text()
        self.assertIn('overflow-y:auto',layout.split('#dbody{',1)[1].split('}',1)[0])
    def test_pagination_and_filter(self):
        self.write([self.meta()]+[self.message(str(i),self.now-i) for i in range(102)])
        self.index.ingest(self.path,'Codex',self.now);self.index.last_scan=time.time()
        first=self.index.payload('session=codex:sample');second=self.index.payload('session=codex:sample&offset=100')
        self.assertEqual(first['total'],102);self.assertEqual(len(first['events']),100);self.assertEqual(len(second['events']),2)
        self.assertEqual(self.index.payload('provider=Claude')['total'],0)
        self.assertEqual(self.index.payload('session=codex:sample&hour=0')['total'],0)

    def test_summary_uses_materialized_story_refs_without_event_pages(self):
        self.write([
            self.meta(),
            self.message('Touched story:one-dogfood-document and '
                         'wiki/product-spec/x/stories/trace-commits-to-new-layer.md.'),
        ])
        self.index.ingest(self.path, 'Codex', self.now)
        summary = self.index.payload('summary=1')
        self.assertEqual(summary['events'], [])
        self.assertEqual(summary['bins'], [])
        self.assertEqual(summary['total'], 0)
        self.assertEqual(
            {row['storyId'] for row in summary['references']},
            {'story:one-dogfood-document', 'story:trace-commits-to-new-layer'},
        )
        self.assertEqual({row['eventStoryCount'] for row in summary['references']}, {2})
        with self.index.connect() as c:
            c.execute('DELETE FROM event_story_refs')
            c.execute("DELETE FROM history_meta WHERE key='story_refs_schema'")
        reopened = h.History(self.base/'repo', self.base, self.base/'cache')
        self.assertEqual(
            {row['storyId'] for row in reopened.payload('summary=1')['references']},
            {'story:one-dogfood-document', 'story:trace-commits-to-new-layer'},
        )
        original = h.story_refs
        try:
            h.story_refs = lambda _text: self.fail('second initialization rescanned event text')
            h.History(self.base/'repo', self.base, self.base/'cache')
        finally:
            h.story_refs = original

    def test_transcript_and_generated_archive_symlinks_are_rejected(self):
        repo = self.base/'repo-symlink-co'
        repo.mkdir()
        approved = self.base/'.codex/sessions'
        approved.mkdir(parents=True)
        outside = self.base/'outside.jsonl'
        outside.write_text(json.dumps(self.meta())+'\n')
        (approved/'escape.jsonl').symlink_to(outside)
        outside_dir = self.base/'outside-dir';outside_dir.mkdir()
        (outside_dir/'nested.jsonl').write_text(json.dumps(self.meta())+'\n')
        (approved/'escape-dir').symlink_to(outside_dir, target_is_directory=True)
        index = h.History(repo, self.base, self.base/'symlink-cache')
        self.assertEqual(list(index.paths()), [])

        generated = index.cache/'work-history'
        for child in generated.iterdir(): child.unlink()
        generated.rmdir()
        output_escape = self.base/'output-escape';output_escape.mkdir()
        generated.symlink_to(output_escape, target_is_directory=True)
        with self.assertRaises(ValueError):
            index.export_index(self.now)
        self.assertEqual(list(output_escape.iterdir()), [])

    def test_project_scope_uses_git_identity_not_colliding_name_prefix(self):
        served = self.base/'alpha'
        sibling = self.base/'alpha-secrets'
        served.mkdir(); sibling.mkdir()
        subprocess.run(['git', 'init', '-q', str(served)], check=True)
        subprocess.run(['git', 'init', '-q', str(sibling)], check=True)
        index = h.History(served, self.base, self.base/'identity-cache')
        self.assertTrue(index.in_project({'cwd': str(served)}))
        self.assertFalse(index.in_project({'cwd': str(sibling)}))
        self.assertFalse(index.in_project({'cwd': str(self.base/'alpha-deleted-co')}))
        explicit = h.History(
            served, self.base, self.base/'explicit-cache',
            checkout_roots=[self.base/'alpha-deleted-co'],
        )
        self.assertTrue(explicit.in_project({
            'cwd': str(self.base/'alpha-deleted-co')
        }))

        # An allowlisted path may later be reused by a different repository.
        reused = self.base/'alpha-deleted-co'; reused.mkdir()
        subprocess.run(['git', 'init', '-q', str(reused)], check=True)
        self.assertFalse(explicit.in_project({'cwd': str(reused)}))

    def test_narrowed_allowlist_revokes_cached_rows_and_archives(self):
        retired = self.base/'repo-retired-co'
        cache = self.base/'scope-cache'
        broad = h.History(
            self.base/'repo', self.base, cache, checkout_roots=[retired]
        )
        self.write([self.meta(str(retired)), self.message('story:private-work')])
        broad.ingest(self.path, 'Codex', self.now)
        broad.export('codex:sample')
        broad.last_scan = time.time()
        self.assertEqual(len(broad.payload()['sessions']), 1)
        self.assertTrue(any((cache/'work-history').glob('*.md')))

        narrow = h.History(self.base/'repo', self.base, cache, checkout_roots=[])
        narrow.last_scan = time.time()
        self.assertEqual(narrow.payload()['sessions'], [])
        self.assertEqual(narrow.payload()['references'], [])
        self.assertEqual(
            [path.name for path in (cache/'work-history').iterdir()], ['INDEX.md']
        )

    def test_scope_narrowing_retries_revoked_archive_cleanup_after_failure(self):
        retired = self.base/'repo-retired-co'
        cache = self.base/'scope-retry-cache'
        broad = h.History(
            self.base/'repo', self.base, cache, checkout_roots=[retired]
        )
        self.write([self.meta(str(retired)), self.message('story:secret')])
        broad.ingest(self.path, 'Codex', self.now)
        broad.export('codex:sample')
        revoked = list((cache/'work-history').glob('[0-9a-f]*.*'))
        self.assertEqual(len(revoked), 2)

        original_rewrite = h.History._rewrite_all_exports
        try:
            h.History._rewrite_all_exports = lambda _self: (_ for _ in ()).throw(
                OSError('simulated revoked archive cleanup failure')
            )
            with self.assertRaisesRegex(OSError, 'cleanup failure'):
                h.History(self.base/'repo', self.base, cache, checkout_roots=[])
        finally:
            h.History._rewrite_all_exports = original_rewrite

        with sqlite3.connect(cache/'history-v3.sqlite3') as connection:
            self.assertIsNone(connection.execute(
                "SELECT value FROM history_meta WHERE key='public_archive_schema'"
            ).fetchone())
        self.assertTrue(all(path.exists() for path in revoked))
        recovered = h.History(
            self.base/'repo', self.base, cache, checkout_roots=[]
        )
        recovered.last_scan = time.time()
        self.assertEqual(recovered.payload()['sessions'], [])
        self.assertTrue(all(not path.exists() for path in revoked))

    def test_scope_narrowing_blocks_and_invalidates_an_inflight_broad_scan(self):
        retired = self.base/'repo-retired-co'
        cache = self.base/'scope-race-cache'
        broad = h.History(
            self.base/'repo', self.base, cache, checkout_roots=[retired]
        )
        self.write([self.meta(str(retired)), self.message('story:private-race')])
        entered = threading.Event()
        release = threading.Event()
        original_ingest = broad._ingest_locked

        def paused_ingest(path, provider, now):
            entered.set()
            self.assertTrue(release.wait(5), 'test did not release broad scan')
            return original_ingest(path, provider, now)

        broad._ingest_locked = paused_ingest
        broad.paths = lambda: [('Codex', self.path)]
        scanner = threading.Thread(target=broad._scan)
        scanner.start()
        self.assertTrue(entered.wait(5), 'broad scan never entered ingestion')

        narrowed = []
        constructor = threading.Thread(target=lambda: narrowed.append(h.History(
            self.base/'repo', self.base, cache, checkout_roots=[]
        )))
        constructor.start()
        self.assertTrue(constructor.is_alive(), 'scope transition bypassed active scan')
        release.set()
        scanner.join(5); constructor.join(5)
        self.assertFalse(scanner.is_alive())
        self.assertFalse(constructor.is_alive())

        narrow = narrowed[0]
        narrow.last_scan = time.time()
        self.assertEqual(narrow.payload()['sessions'], [])
        self.assertEqual(narrow.payload()['references'], [])
        self.assertEqual(
            [path.name for path in (cache/'work-history').iterdir()], ['INDEX.md']
        )
        # Even an explicitly invoked stale instance cannot repopulate rows or
        # exports after its admission generation has been revoked.
        broad.ingest(self.path, 'Codex', self.now)
        broad.export('codex:sample')
        self.assertEqual(narrow.payload()['sessions'], [])
        self.assertEqual(
            [path.name for path in (cache/'work-history').iterdir()], ['INDEX.md']
        )

    def test_exports_stay_outside_checkout(self):
        self.write([self.meta(), self.message()])
        self.index.ingest(self.path, 'Codex', self.now)
        self.index.export_index(self.now)
        self.assertTrue((self.index.cache/'work-history/INDEX.md').is_file())
        self.assertFalse((self.index.root/'vizzer/work-history').exists())

    def test_history_routes_require_loopback_host(self):
        class Handler:
            def __init__(self, host): self.headers={'Host':host};self.responses=[]
            def _send_json(self, status, body): self.responses.append((status,body))
        from urllib.parse import urlsplit
        hostile=Handler('attacker.example:8482')
        self.assertTrue(h.handle(hostile,self.base/'repo',urlsplit('/api/work-history?summary=1')))
        self.assertEqual(hostile.responses[0][0],403)
        self.assertTrue(h.loopback_host(Handler('127.0.0.1:8482')))
        self.assertTrue(h.loopback_host(Handler('localhost:8482')))

    def test_first_loopback_history_request_constructs_without_deadlock(self):
        root = self.base/'fresh-repo'; root.mkdir()
        script = r'''
import json, sys
from unittest.mock import patch
from urllib.parse import urlsplit
from vizzer import session_history as h
class Handler:
    headers={'Host':'127.0.0.1:8482'}
    def __init__(self): self.responses=[]
    def _send_json(self,status,body): self.responses.append((status,body))
handler=Handler()
with patch('vizzer.session_history.Path.home',return_value=h.Path(sys.argv[2])):
    handled=h.handle(handler,h.Path(sys.argv[1]),urlsplit('/api/work-history?summary=1'))
key=(sys.argv[1],())
print(json.dumps({'handled':handled,'status':handler.responses[0][0],
                  'hours':handler.responses[0][1]['hours'],
                  'instance':isinstance(h._instances.get(key),h.History)}))
'''
        result = subprocess.run(
            [os.sys.executable, '-c', script, str(root), str(self.base)],
            capture_output=True, text=True, timeout=3,
            env={**os.environ, 'PYTHONPATH': str(module.parents[1])},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            'handled': True, 'status': 200, 'hours': 72, 'instance': True,
        })

    def test_payload_does_not_wait_for_an_active_transcript_scan(self):
        entered = threading.Event()
        release = threading.Event()

        def paused_scan():
            entered.set()
            self.assertTrue(release.wait(5), 'test did not release active scan')

        self.index._scan_locked = paused_scan
        self.index.refreshing = True
        scanner = threading.Thread(target=self.index._scan)
        scanner.start()
        self.assertTrue(entered.wait(5), 'scan did not acquire mutation lock')
        result = []
        reader = threading.Thread(target=lambda: result.append(
            self.index.payload('summary=1')
        ))
        reader.start(); reader.join(1)
        self.assertFalse(reader.is_alive(), 'payload waited for transcript scan')
        self.assertTrue(result[0]['refreshing'])
        release.set(); scanner.join(5)
        self.assertFalse(scanner.is_alive())

    def test_http_extension_is_opt_in_and_serves_bounded_payload(self):
        from types import SimpleNamespace
        from urllib.parse import urlsplit
        from vizzer.serve_extensions import SessionHistoryHttpExtension

        responses = []
        class DotConfig:
            def __init__(self, enabled): self.enabled = enabled
            def get(self, key, default=None):
                return self.enabled if key == 'session_history.enabled' else default

        context = SimpleNamespace(
            root=self.base/'repo', cfg=DotConfig(False),
            current_engine=lambda: True,
            send_json=lambda status, body: responses.append((status, body)),
        )
        extension = SessionHistoryHttpExtension()
        self.assertTrue(extension.get(context, urlsplit('/api/work-history?summary=1')))
        self.assertEqual(responses[-1], (404, {'error': 'session history is disabled'}))

        class FakeHistory:
            def __init__(self): self.started = False
            def start(self): self.started = True
            def payload(self, query): return {'query': query, 'hours': 72}
            def event(self, event_id): return {'id': event_id}
            def log(self, session_id, query): return {'session': session_id, 'query': query}

        fake = FakeHistory()
        context.cfg = DotConfig(True)
        with patch('vizzer.serve_extensions.session_history', return_value=fake):
            self.assertTrue(extension.get(
                context, urlsplit('/api/work-history?summary=1')
            ))
        self.assertTrue(fake.started)
        self.assertEqual(responses[-1], (200, {'query': 'summary=1', 'hours': 72}))
    def test_rollover_filters_existing_index(self):
        self.write([self.meta(),self.message(ts=self.now-h.WINDOW+60)]);self.index.ingest(self.path,'Codex',self.now)
        with self.index.connect() as c:c.execute('UPDATE events SET timestamp=?',(self.now-h.WINDOW-1,))
        self.index.last_scan=time.time();self.assertEqual(self.index.payload()['sessions'],[])

    def test_log_filters_exec_exact_tool_search_and_pagination(self):
        records=[self.meta(),self.message('Discussion mentions exec but is not a call')]
        for i in range(302):
            records.append({'timestamp':h.iso(self.now-i),'type':'response_item','payload':{'type':'function_call','name':'functions.exec','call_id':str(i),'arguments':'DO NOT EXPORT'}})
        records.append({'timestamp':h.iso(self.now),'type':'response_item','payload':{'type':'function_call','name':'other_tool','call_id':'other'}})
        self.write(records);self.index.ingest(self.path,'Codex',self.now)
        all_rows=self.index.log('codex:sample');filtered=self.index.log('codex:sample','tool=@exec')
        self.assertEqual(all_rows['totalEvents'],304)
        self.assertEqual(filtered['matchingEvents'],302)
        self.assertEqual(filtered['eventCount'],300)
        self.assertEqual(self.index.log('codex:sample','tool=@exec&offset=300')['eventCount'],2)
        self.assertNotIn('DO NOT EXPORT',filtered['markdown'])
        self.assertNotIn('Discussion',filtered['markdown'].split('\n## ',1)[1])
        self.assertEqual(self.index.log('codex:sample','kind=progress&tool=@exec')['matchingEvents'],0)
        self.assertEqual(self.index.log('codex:sample','tool=other_tool')['matchingEvents'],1)
        self.assertEqual(self.index.log('codex:sample','q=mentions')['matchingEvents'],1)
        self.assertEqual(self.index.log('codex:sample',"q=%27+OR+1%3D1")['matchingEvents'],0)
        self.assertEqual(self.index.log('codex:sample')['totalEvents'],304)

if __name__=='__main__':unittest.main()


def test_real_loopback_server_and_assembled_browser_session_history(
    tmp_path, make_repo,
):
    from vizzer.cli import _make_serve_server, _read_graph, main
    from vizzer.config import Config

    chrome = next((candidate for candidate in (
        shutil.which('google-chrome'), shutil.which('chromium'),
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ) if candidate and Path(candidate).is_file()), None)
    if chrome is None:
        import pytest
        pytest.skip('Chrome is required for the assembled session-history smoke')

    repo = make_repo(tmp_path, 'mixed_proj')
    config_path = repo/'vizzer/vizzer.toml'
    config_path.write_text(config_path.read_text() + '''

[session_history]
enabled = true
''')
    assert main(['refresh', '--root', str(repo)]) == 0
    index = h.History(repo, tmp_path, tmp_path/'history-cache')
    transcript = tmp_path/'session.jsonl'
    now = time.time()
    transcript.write_text('\n'.join(json.dumps(record) for record in [
        {'type':'session_meta','payload':{'id':'browser-session','cwd':str(repo),
                                         'model':'gpt-6-astra'}},
        {'timestamp':h.iso(now-10),'type':'event_msg','payload':{
            'type':'user_message','message':'Work on story:snap-to-grid because the route was stale.'}},
        {'timestamp':h.iso(now-5),'type':'event_msg','payload':{
            'type':'agent_message','message':'Updated story:canvas-core and preserved the answer.'}},
    ])+'\n')
    index.ingest(transcript, 'Codex', now)
    index.last_scan = now
    h._instances[(str(repo), ())] = index

    cfg = Config.load(repo)
    graph = _read_graph(repo)
    views = repo/'vizzer/views'
    html_path = views/'constellation.html'
    original = html_path.read_text()
    browser_script = Path(__file__).with_name('browser_live_session_history.js')

    def run_browser(expected_failure=None):
        server = _make_serve_server(repo, graph, views, 0, cfg)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        connection = http.client.HTTPConnection(host, port, timeout=3)
        try:
            for route in (
                '/constellation.html', '/api/work-history?summary=1',
                '/api/work-history/event?id='+index.rows()[0]['id']
                if hasattr(index, 'rows') else '/api/work-history?summary=1',
                '/api/work-history/log?session=codex%3Abrowser-session',
            ):
                connection.request('GET', route)
                response = connection.getresponse(); response.read()
                assert response.status == 200, route
            result = subprocess.run(
                ['node', str(browser_script), chrome,
                 f'http://{host}:{port}/constellation.html'],
                capture_output=True, text=True, timeout=45,
            )
            if expected_failure is None:
                assert result.returncode == 0, result.stderr
            else:
                assert result.returncode != 0, result.stdout
                assert expected_failure in result.stderr, result.stderr
            return result
        finally:
            connection.close(); server.shutdown(); server.server_close()
            thread.join(timeout=2)

    # Obtain one real event id without reaching into private fixture helpers.
    with index.connect() as connection:
        event_id = connection.execute('SELECT id FROM events ORDER BY timestamp LIMIT 1').fetchone()[0]
    server = _make_serve_server(repo, graph, views, 0, cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        for route in ('/api/work-history?summary=1',
                      '/api/work-history/event?id='+event_id,
                      '/api/work-history/log?session=codex%3Abrowser-session'):
            connection.request('GET', route); response=connection.getresponse(); body=response.read()
            assert response.status == 200, (route, body)
    finally:
        connection.close(); server.shutdown(); server.server_close(); thread.join(timeout=2)

    run_browser()
    draw_mutation = original.replace(
        "if(typeof drawSessionHistory==='function')drawSessionHistory();",
        "if(false)drawSessionHistory();", 1,
    )
    assert draw_mutation != original
    assert draw_mutation.count("if(false)drawSessionHistory();") == 1
    html_path.write_text(draw_mutation)
    run_browser('timed out waiting for assembled canvas draw hook')
    double_click_mutation = original.replace(
        "if(typeof historyDoubleClick==='function'&&historyDoubleClick(e.clientX,e.clientY,hover))",
        "if(false&&historyDoubleClick(e.clientX,e.clientY,hover))", 1,
    )
    assert double_click_mutation != original
    assert double_click_mutation.count("if(false&&historyDoubleClick") == 1
    html_path.write_text(double_click_mutation)
    run_browser('timed out waiting for path isolation')
    duplicate_paint_mutation = original.replace(
        "for(const p of sessionHistory.points){const q=historyPoint(p);",
        "for(const p of sessionHistory.points.concat(sessionHistory.points)){const q=historyPoint(p);",
        1,
    )
    assert duplicate_paint_mutation != original
    assert duplicate_paint_mutation.count(
        "sessionHistory.points.concat(sessionHistory.points)"
    ) == 1
    html_path.write_text(duplicate_paint_mutation)
    run_browser('trail paint counts mismatch')
    html_path.write_text(original)

    disabled = Config(data={**cfg.data, 'session_history': {
        **cfg.data['session_history'], 'enabled': False,
    }})
    server = _make_serve_server(repo, graph, views, 0, disabled)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    host, port = server.server_address[:2]
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        for route in ('/api/work-history?summary=1',
                      '/api/work-history/event?id='+event_id,
                      '/api/work-history/log?session=codex%3Abrowser-session'):
            connection.request('GET', route)
            response=connection.getresponse(); response.read()
            assert response.status == 404, route
    finally:
        connection.close(); server.shutdown(); server.server_close(); thread.join(timeout=2)
        h._instances.pop((str(repo), ()), None)
