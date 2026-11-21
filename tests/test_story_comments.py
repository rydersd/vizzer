"""Owner comments on story text: validation, atomic store, HTTP verbs, refresh view."""
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_question_story import Cfg  # noqa: E402
from vizzer import cli, story_comments as story_comments_module, story_files
from vizzer.model import Graph
from vizzer.story_comments import (StoryCommentError, add_comment, delete_comment,
                                   list_comments, render_comments_markdown)
from vizzer.render import story_comments as render_story_comments

STORY_REL = 'prod_spec/shared/capabilities/c/epics/e/stories/live-wet-x.md'


def good(**over):
    body = {'storyId': 'story:live-wet-x', 'path': STORY_REL, 'questionId': 'question:q1',
            'quote': 'the quoted passage', 'heading': 'Acceptance criteria',
            'comment': 'Is this bound too loose?', 'clientTime': '2026-11-21T10:00:00Z'}
    body.update(over)
    return body


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        story = self.root / STORY_REL
        story.parent.mkdir(parents=True)
        story.write_text('# Live wet X\n\n## Acceptance criteria\nthe quoted passage\n')
        (self.root / 'prod_spec/story-id-crosswalk.json').write_text('{"aliases":{}}')
        (self.root / 'vizzer').mkdir()
        self.store = self.root / 'vizzer' / 'story-comments.json'

    def tearDown(self):
        self._tmp.cleanup()


class Store(Fixture):
    def test_add_appends_entry_with_id_time_and_open_status(self):
        entry = add_comment(self.root, Cfg(), good())
        self.assertEqual(entry['status'], 'open')
        self.assertEqual(len(entry['id']), 36)
        self.assertTrue(entry['createdAt'])
        stored = json.loads(self.store.read_text())
        self.assertIsInstance(stored, list)
        self.assertEqual(stored[0]['quote'], 'the quoted passage')
        self.assertEqual(stored[0]['path'], STORY_REL)
        self.assertEqual([p.name for p in self.store.parent.iterdir() if p.name.startswith('.')], [])

    def test_unknown_story_is_refused_and_nothing_written(self):
        with self.assertRaises(StoryCommentError):
            add_comment(self.root, Cfg(), good(storyId='story:nope'))
        self.assertFalse(self.store.exists())

    def test_path_must_match_the_resolved_story(self):
        with self.assertRaises(StoryCommentError):
            add_comment(self.root, Cfg(), good(path='prod_spec/other.md'))

    def test_length_caps_and_required_text(self):
        with self.assertRaises(StoryCommentError):
            add_comment(self.root, Cfg(), good(comment='x' * 4001))
        with self.assertRaises(StoryCommentError):
            add_comment(self.root, Cfg(), good(quote='y' * 2001))
        with self.assertRaises(StoryCommentError):
            add_comment(self.root, Cfg(), good(comment='   '))
        add_comment(self.root, Cfg(), good(comment='x' * 4000, quote='y' * 2000))

    def test_unknown_fields_and_non_strings_are_refused(self):
        with self.assertRaises(StoryCommentError):
            add_comment(self.root, Cfg(), good(status='resolved'))
        with self.assertRaises(StoryCommentError):
            add_comment(self.root, Cfg(), good(comment=['a']))

    def test_html_is_stored_as_text_unchanged(self):
        add_comment(self.root, Cfg(), good(comment='<img src=x onerror=alert(1)>'))
        self.assertEqual(list_comments(self.root, 'story:live-wet-x')[0]['comment'],
                         '<img src=x onerror=alert(1)>')

    def test_delete_removes_only_open_entries_by_id(self):
        a = add_comment(self.root, Cfg(), good())
        b = add_comment(self.root, Cfg(), good(comment='second'))
        delete_comment(self.root, a['id'])
        self.assertEqual([c['id'] for c in list_comments(self.root, 'story:live-wet-x')], [b['id']])
        with self.assertRaises(StoryCommentError) as caught:
            delete_comment(self.root, 'no-such-id')
        self.assertEqual(caught.exception.status, 404)
        stored = json.loads(self.store.read_text())
        stored[0]['status'] = 'resolved'
        self.store.write_text(json.dumps(stored))
        with self.assertRaises(StoryCommentError) as caught:
            delete_comment(self.root, b['id'])
        self.assertEqual(caught.exception.status, 409)

    def test_corrupt_store_is_never_overwritten(self):
        self.store.write_text('{not json')
        with self.assertRaises(StoryCommentError):
            add_comment(self.root, Cfg(), good())
        self.assertEqual(self.store.read_text(), '{not json')


class Caps(Fixture):
    def test_comment_count_cap_is_409_and_store_unchanged(self):
        with patch.object(story_comments_module, 'MAX_COMMENTS', 2):
            add_comment(self.root, Cfg(), good())
            add_comment(self.root, Cfg(), good())
            with self.assertRaises(StoryCommentError) as caught:
                add_comment(self.root, Cfg(), good())
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(len(json.loads(self.store.read_text())), 2)

    def test_store_byte_cap_is_413_and_store_unchanged(self):
        first = add_comment(self.root, Cfg(), good())
        before = self.store.read_bytes()
        with patch.object(story_comments_module, 'MAX_STORE_BYTES', len(before) + 10):
            with self.assertRaises(StoryCommentError) as caught:
                add_comment(self.root, Cfg(), good())
        self.assertEqual(caught.exception.status, 413)
        self.assertEqual(self.store.read_bytes(), before)
        self.assertEqual(json.loads(before)[0]['id'], first['id'])

    def test_oversized_existing_store_is_refused_not_loaded(self):
        self.store.write_text(' ' * (story_comments_module.MAX_STORE_BYTES + 1))
        with self.assertRaises(StoryCommentError) as caught:
            list_comments(self.root, 'story:live-wet-x')
        self.assertEqual(caught.exception.status, 413)


class RefreshView(Fixture):
    def test_dangling_store_symlink_renders_unreadable_not_empty(self):
        self.store.symlink_to(self.root / 'vizzer' / 'missing-target.json')
        text = render_story_comments.render(None, Cfg(), self.root)['story-comments.md']
        self.assertIn('could not be read', text)
        self.assertNotIn('No open story comments', text)

    def test_store_over_the_count_cap_renders_over_limit_without_listing(self):
        with patch.object(story_comments_module, 'MAX_COMMENTS', 2):
            self.store.write_text(json.dumps([{'id': str(i), 'status': 'open', 'storyId': 's',
                                               'quote': 'q', 'comment': 'c'} for i in range(3)]))
            text = render_story_comments.render(None, Cfg(), self.root)['story-comments.md']
            with self.assertRaises(StoryCommentError) as caught:
                list_comments(self.root, 's')
        self.assertIn('store over limit', text)
        self.assertNotIn('### ', text)
        self.assertEqual(caught.exception.status, 413)

    def test_store_over_the_byte_cap_renders_over_limit_and_reads_at_most_cap_plus_one(self):
        counted = []
        real = story_files._read_fd

        def counting(fd, n):
            data = real(fd, n)
            counted.append(len(data))
            return data
        with patch.object(story_comments_module, 'MAX_STORE_BYTES', 100):
            self.store.write_text(' ' * 5000)
            with patch.object(story_files, '_read_fd', counting):
                text = render_story_comments.render(None, Cfg(), self.root)['story-comments.md']
                with self.assertRaises(StoryCommentError) as caught:
                    list_comments(self.root, 's')
        self.assertIn('store over limit', text)
        self.assertEqual(caught.exception.status, 413)
        self.assertLessEqual(sum(counted), 2 * 101)

    def test_store_growing_past_the_cap_after_the_size_check_is_still_bounded(self):
        counted = []
        real = story_files._read_fd

        def counting(fd, n):
            data = real(fd, n)
            counted.append(len(data))
            return data
        with patch.object(story_comments_module, 'MAX_STORE_BYTES', 100), \
                patch.object(story_comments_module, '_size_check', lambda size: None):
            self.store.write_text(' ' * 5000)
            with patch.object(story_files, '_read_fd', counting):
                with self.assertRaises(StoryCommentError) as caught:
                    list_comments(self.root, 's')
        self.assertEqual(caught.exception.status, 413)
        self.assertEqual(sum(counted), 101)

    def test_corrupt_store_renders_an_explicit_error_not_an_empty_state(self):
        self.store.write_text('{not json')
        text = render_story_comments.render(None, Cfg(), self.root)['story-comments.md']
        self.assertIn('could not be read', text)
        self.assertNotIn('No open story comments', text)

    def test_markdown_groups_open_comments_by_story_with_quote_heading_comment(self):
        add_comment(self.root, Cfg(), good())
        add_comment(self.root, Cfg(), good(comment='line one\nline two', quote='multi\nline'))
        text = render_comments_markdown(json.loads(self.store.read_text()))
        self.assertIn('story:live-wet-x', text)
        self.assertEqual(text.count('### '), 2)
        self.assertIn('> the quoted passage', text)
        self.assertIn('Acceptance criteria', text)
        self.assertIn('Is this bound too loose?', text)
        self.assertIn('> multi\n> line', text)

    def test_resolved_comments_are_left_out_and_empty_state_is_stated(self):
        self.assertIn('No open story comments', render_comments_markdown([]))
        entry = add_comment(self.root, Cfg(), good())
        entry['status'] = 'resolved'
        self.assertIn('No open story comments', render_comments_markdown([entry]))

    def test_refresh_renderer_emits_story_comments_md(self):
        add_comment(self.root, Cfg(), good())
        out = render_story_comments.render(None, Cfg(), self.root)
        self.assertEqual(list(out), ['story-comments.md'])
        self.assertIn('Is this bound too loose?', out['story-comments.md'])


class Http(Fixture):
    def setUp(self):
        super().setUp()
        views = self.root / 'vizzer' / 'views'
        views.mkdir()
        self.server = cli._make_serve_server(self.root, Graph(), views, 0, Cfg(), 'tok')
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, method, path, body=None, csrf=True, host=None, skip_host=False):
        conn = http.client.HTTPConnection('127.0.0.1', self.port)
        headers = {'Origin': f'http://127.0.0.1:{self.port}'}
        if host:
            headers['Host'] = host
        if skip_host:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.endheaders()
            response = conn.getresponse()
            return response.status, json.loads(response.read() or b'{}')
        if csrf:
            headers['X-Vizzer-CSRF'] = 'tok'
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, data, headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read() or b'{}')

    def test_post_get_delete_round_trip_leaves_store_clean(self):
        with patch.object(cli, '_serve_version_error', return_value=None):
            status, created = self.call('POST', '/api/story-comments', good())
            self.assertEqual(status, 201, created)
            status, listed = self.call('GET', '/api/story-comments?storyId=story%3Alive-wet-x')
            self.assertEqual(status, 200)
            self.assertEqual([c['id'] for c in listed['comments']], [created['comment']['id']])
            self.assertEqual(listed['csrfToken'], 'tok')
            self.assertIn('Is this bound too loose?', (self.root / 'vizzer/views/story-comments.md').read_text())
            status, _ = self.call('DELETE', '/api/story-comments/' + created['comment']['id'])
            self.assertEqual(status, 200)
        self.assertEqual(json.loads(self.store.read_text()), [])
        self.assertIn('No open story comments', (self.root / 'vizzer/views/story-comments.md').read_text())

    def test_writes_need_the_csrf_token_and_bad_input_is_400(self):
        with patch.object(cli, '_serve_version_error', return_value=None):
            self.assertEqual(self.call('POST', '/api/story-comments', good(), csrf=False)[0], 403)
            self.assertEqual(self.call('DELETE', '/api/story-comments/x', csrf=False)[0], 403)
            self.assertEqual(self.call('POST', '/api/story-comments', good(comment='x' * 4001))[0], 400)
            self.assertEqual(self.call('POST', '/api/story-comments', good(storyId='story:nope'))[0], 404)
            self.assertFalse(self.store.exists())


    def test_hostile_host_gets_421_on_both_story_reads(self):
        with patch.object(cli, '_serve_version_error', return_value=None):
            for path in ('/api/story-comments?storyId=story%3Alive-wet-x',
                         '/api/question-story/story%3Alive-wet-x'):
                status, body = self.call('GET', path, host='evil.example:%d' % self.port)
                self.assertEqual(status, 421, path)
                self.assertNotIn('csrfToken', body)
                self.assertNotIn('markdown', body)
                self.assertEqual(self.call('GET', path)[0], 200, path)

    def test_host_forms(self):
        path = '/api/story-comments?storyId=story%3Alive-wet-x'
        with patch.object(cli, '_serve_version_error', return_value=None):
            self.assertEqual(self.call('GET', path, skip_host=True)[0], 421)
            for host in ('localhost', 'localhost.', f'localhost:{self.port}', f'localhost.:{self.port}',
                         f'127.0.0.1:{self.port}', f'[::1]:{self.port}'):
                self.assertEqual(self.call('GET', path, host=host)[0], 200, host)
            self.assertEqual(self.call('GET', path, host='evil.example')[0], 421)

    def test_view_write_failure_after_store_write_still_succeeds(self):
        with patch.object(cli, '_serve_version_error', return_value=None), \
                patch.object(cli, '_atomic_text', side_effect=OSError('disk full')):
            status, created = self.call('POST', '/api/story-comments', good())
        self.assertEqual(status, 201, created)
        self.assertEqual(len(json.loads(self.store.read_text())), 1)

    def test_caps_surface_as_http_errors(self):
        with patch.object(cli, '_serve_version_error', return_value=None), \
                patch.object(story_comments_module, 'MAX_COMMENTS', 1):
            self.assertEqual(self.call('POST', '/api/story-comments', good())[0], 201)
            status, body = self.call('POST', '/api/story-comments', good())
            self.assertEqual(status, 409)
            self.assertIn('limit', body['error'])


class Reader(unittest.TestCase):
    def test_node_reader_comment_logic(self):
        node = subprocess.run(['node', str(Path(__file__).with_name('story_comments_reader.cjs'))],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(node.returncode, 0, node.stdout + node.stderr)


if __name__ == '__main__':
    unittest.main()
