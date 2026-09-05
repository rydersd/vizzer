import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import vizzer.story_edits as edits

class StoryEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'prod_spec/stories/example.md'
        self.source.parent.mkdir(parents=True);self.source.write_text('# Example\n\nOriginal.\n')
        self.story='story:example'
    def request(self):
        state=edits.read_edit(self.root,self.story,self.source)
        return dict(storyId=self.story,expectedSourceHash=state['sourceHash'],expectedRevision=state['revision'],text='# Example\n\n**Owner edit**.\n')
    def test_exact_diff_durable_without_replacing_source(self):
        original=self.source.read_bytes();result=edits.save_edit(self.root,self.story,self.source,self.request())
        ledger=json.loads((self.root/result['path']).read_text());entry=ledger['revisions'][0]
        self.assertEqual(self.source.read_bytes(),original)
        self.assertEqual(entry['original'],original.decode());self.assertIn('+**Owner edit**.',entry['diff'])
        self.assertEqual(entry['status'],'pending-review')
        self.assertEqual(edits.read_edit(self.root,self.story,self.source)['latest']['editedHash'],edits.digest(entry['edited']))
    def test_concurrent_editor_conflict_keeps_first(self):
        request=self.request();edits.save_edit(self.root,self.story,self.source,request)
        request['text']='Another edit'
        with self.assertRaises(edits.StoryEditConflict):edits.save_edit(self.root,self.story,self.source,request)
        self.assertEqual(edits.read_edit(self.root,self.story,self.source)['revision'],1)
    def test_changed_source_conflict(self):
        request=self.request();self.source.write_text('Changed outside browser')
        with self.assertRaises(edits.StoryEditConflict):edits.save_edit(self.root,self.story,self.source,request)
    def test_path_and_symlink_rejection(self):
        other=tempfile.TemporaryDirectory();self.addCleanup(other.cleanup)
        outside=Path(other.name)/'outside.md';outside.write_text('outside')
        with self.assertRaises(ValueError):edits.read_edit(self.root,self.story,outside)
        (self.root/'vizzer').mkdir();(self.root/'vizzer/story-edits').symlink_to(self.source.parent,target_is_directory=True)
        with self.assertRaises(ValueError):edits.save_edit(self.root,self.story,self.source,self.request())
    def test_empty_and_oversized_rejected(self):
        for text in ('  ','x'*200001):
            request=self.request();request['text']=text
            with self.assertRaises(ValueError):edits.save_edit(self.root,self.story,self.source,request)
