"""Owner question -> story markdown: disk resolution, endpoint payload, inline reader.

Isolated fixtures only; stories are plain files on disk (never read through git).
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ENGINE = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ENGINE))
from unittest.mock import patch
from vizzer import story_files
from vizzer.story_files import resolve_story_file, story_payload
from vizzer.render.constellation import _frontend_text


class Cfg:
    def get(self, key, default=None):
        return {'render.story_aliases': 'prod_spec/story-id-crosswalk.json',
                'sources.spec_tree.glob': 'prod_spec/*/capabilities/*/epics/*/stories/*.md'}.get(key, default)


class StoryFileResolution(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        stories = self.root / 'prod_spec/shared/capabilities/c/epics/e/stories'
        stories.mkdir(parents=True)
        (stories / 'live-wet-x.md').write_text(
            '---\nstatus: proposed\nsummary: A story.\n---\n# Live wet X\n\n## Acceptance criteria\n- one\n')
        (stories / 'canonical-y.md').write_text('# Canonical Y\n')
        (self.root / 'prod_spec/story-id-crosswalk.json').write_text(
            json.dumps({'aliases': {'story:old-y': 'story:canonical-y'}}))
        # Untracked: this directory is not a git repository at all.

    def tearDown(self):
        self._tmp.cleanup()

    def test_untracked_story_resolves_from_disk(self):
        path, reason = resolve_story_file(self.root, Cfg(), 'story:live-wet-x')
        self.assertEqual(reason, '')
        self.assertEqual(path.name, 'live-wet-x.md')

    def test_alias_follows_the_crosswalk(self):
        path, _ = resolve_story_file(self.root, Cfg(), 'story:old-y')
        self.assertEqual(path.name, 'canonical-y.md')

    def test_unresolvable_story_says_why(self):
        path, reason = resolve_story_file(self.root, Cfg(), 'story:nope')
        self.assertIsNone(path)
        self.assertIn('story:nope', reason)

    def test_unconfigured_story_tree_says_so(self):
        class NoTree:
            def get(self, key, default=None):
                return default
        path, reason = resolve_story_file(self.root, NoTree(), 'story:live-wet-x')
        self.assertIsNone(path)
        self.assertIn('sources.spec_tree', reason)

    def test_story_tree_follows_the_configured_glob(self):
        class Wiki:
            def get(self, key, default=None):
                return {'sources.spec_tree.glob': 'wiki/specs/*/stories/*.md'}.get(key, default)
        stories = self.root / 'wiki/specs/area/stories'
        stories.mkdir(parents=True)
        (stories / 'elsewhere.md').write_text('# Elsewhere\n')
        path, _ = resolve_story_file(self.root, Wiki(), 'story:elsewhere')
        self.assertEqual(path.name, 'elsewhere.md')
        path, _ = resolve_story_file(self.root, Wiki(), 'story:live-wet-x')
        self.assertIsNone(path)

    def test_in_repo_symlink_to_a_non_story_file_is_refused(self):
        (self.root / 'NOTES.md').write_text('# repo notes, not a story\n')
        (self.root / 'config.txt').write_text('secret\n')
        stories = self.root / 'prod_spec/shared/capabilities/c/epics/e/stories'
        (stories / 'leak.md').symlink_to(self.root / 'NOTES.md')
        (stories / 'leaktxt.md').symlink_to(self.root / 'config.txt')
        for slug in ('leak', 'leaktxt'):
            path, _ = resolve_story_file(self.root, Cfg(), 'story:' + slug)
            self.assertIsNone(path, slug)

    def test_symlinked_ancestor_directory_is_refused(self):
        real = self.root / 'elsewhere/stories'
        real.mkdir(parents=True)
        (real / 'viaparent.md').write_text('# via parent\n')
        link = self.root / 'prod_spec/linked'
        link.symlink_to(self.root / 'elsewhere')
        class Linked:
            def get(self, key, default=None):
                return {'sources.spec_tree.glob': 'prod_spec/linked/stories/*.md'}.get(key, default)
        path, _ = resolve_story_file(self.root, Linked(), 'story:viaparent')
        self.assertIsNone(path)

    def test_glob_is_not_broadened_to_other_stories(self):
        stories = self.root / 'wiki/stories'
        stories.mkdir(parents=True)
        (stories / 'public-a.md').write_text('# a\n')
        (stories / 'secret.md').write_text('# secret\n')
        class Public:
            def get(self, key, default=None):
                return {'sources.spec_tree.glob': 'wiki/stories/public-*.md'}.get(key, default)
        self.assertEqual(resolve_story_file(self.root, Public(), 'story:public-a')[0].name, 'public-a.md')
        path, _ = resolve_story_file(self.root, Public(), 'story:secret')
        self.assertIsNone(path)

    def test_oversized_story_is_413_not_read(self):
        big = self.root / 'prod_spec/shared/capabilities/c/epics/e/stories/big.md'
        big.write_text('x' * (1024 * 1024 + 1))
        status, body = story_payload(self.root, Cfg(), 'story:big')
        self.assertEqual(status, 413)
        self.assertNotIn('markdown', body)

    def test_swap_for_symlink_between_resolve_and_open_is_refused(self):
        stories = self.root / 'prod_spec/shared/capabilities/c/epics/e/stories'
        (self.root / 'NOTES.md').write_text('# repo notes, not a story\n')
        target = stories / 'live-wet-x.md'

        def swap(path):
            path.unlink()
            path.symlink_to(self.root / 'NOTES.md')
        with patch.object(story_files, '_before_open', swap):
            status, body = story_payload(self.root, Cfg(), 'story:live-wet-x')
        self.assertNotEqual(status, 200)
        self.assertNotIn('repo notes', json.dumps(body))
        self.assertTrue(target.is_symlink())

    def test_swap_of_an_ancestor_directory_is_refused(self):
        stories = self.root / 'prod_spec/shared/capabilities/c/epics/e/stories'
        moved = self.root / 'stories-moved'

        def swap(path):
            stories.rename(moved)
            (self.root / 'outside').mkdir()
            (self.root / 'outside' / 'live-wet-x.md').write_text('# planted\n')
            stories.symlink_to(self.root / 'outside')
        with patch.object(story_files, '_before_open', swap):
            status, body = story_payload(self.root, Cfg(), 'story:live-wet-x')
        self.assertNotEqual(status, 200)
        self.assertNotIn('planted', json.dumps(body))

    def test_story_read_never_exceeds_cap_plus_one_byte(self):
        big = self.root / 'prod_spec/shared/capabilities/c/epics/e/stories/big.md'
        big.write_text('x' * (3 * story_files.MAX_STORY_BYTES))
        counted = []
        real = story_files._read_fd

        def counting(fd, n):
            data = real(fd, n)
            counted.append(len(data))
            return data
        with patch.object(story_files, '_read_fd', counting):
            status, _ = story_payload(self.root, Cfg(), 'story:big')
            self.assertEqual(status, 413)
            with open(big, 'rb') as handle:
                data = story_files.read_capped(handle.fileno(), story_files.MAX_STORY_BYTES)
        self.assertEqual(len(data), story_files.MAX_STORY_BYTES + 1)
        self.assertLessEqual(sum(counted), story_files.MAX_STORY_BYTES + 1)

    def test_hostile_ids_are_refused(self):
        for bad in ('story:../../etc/passwd', 'story:a/b', 'story:', '../x', 'story:.hidden'):
            path, reason = resolve_story_file(self.root, Cfg(), bad)
            self.assertIsNone(path, bad)
            self.assertTrue(reason, bad)

    def test_ambiguous_slug_is_reported_not_guessed(self):
        other = self.root / 'prod_spec/mac/capabilities/c/epics/e/stories'
        other.mkdir(parents=True)
        (other / 'live-wet-x.md').write_text('# dup\n')
        path, reason = resolve_story_file(self.root, Cfg(), 'story:live-wet-x')
        self.assertIsNone(path)
        self.assertIn('more than one', reason)

    def test_symlink_leaving_the_project_is_refused(self):
        outside = tempfile.TemporaryDirectory()
        try:
            target = Path(outside.name) / 'secret.md'
            target.write_text('# secret\n')
            link = self.root / 'prod_spec/shared/capabilities/c/epics/e/stories/leak.md'
            link.symlink_to(target)
            path, _ = resolve_story_file(self.root, Cfg(), 'story:leak')
            self.assertIsNone(path)
        finally:
            outside.cleanup()

    def test_payload_carries_markdown_and_relative_path(self):
        status, body = story_payload(self.root, Cfg(), 'story:live-wet-x')
        self.assertEqual(status, 200)
        self.assertTrue(body['path'].endswith('stories/live-wet-x.md'))
        self.assertIn('Acceptance criteria', body['markdown'])
        self.assertEqual(body['storyId'], 'story:live-wet-x')

    def test_payload_for_missing_story_is_404_with_reason(self):
        status, body = story_payload(self.root, Cfg(), 'story:nope')
        self.assertEqual(status, 404)
        self.assertIn('story:nope', body['error'])


class InlineReaderFrontend(unittest.TestCase):
    """The question card links to the story; the reader renders it with a back link."""

    def test_question_card_markup_names_the_story_link(self):
        self.assertIn("typeof questionStoryLinkMarkup==='function'?questionStoryLinkMarkup(q):''",
                      _frontend_text('questions.js'))
        reader = _frontend_text('story_reader.js')
        for needle in ('data-open-question-story', '/api/question-story/', 'Back to question'):
            self.assertIn(needle, reader)
        self.assertIn('__VIZZER_STORY_READER_JS__', _frontend_text('shell.html'))

    def test_reader_renders_front_matter_headings_and_back(self):
        node = subprocess.run(['node', str(Path(__file__).with_name('question_story_reader.cjs'))],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(node.returncode, 0, node.stdout + node.stderr)


if __name__ == '__main__':
    unittest.main()
