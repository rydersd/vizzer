from test_question_http import _prepare_repo, _request, _start, _stop
import json

def test_story_revision_http_roundtrip_and_guards(tmp_path, make_repo):
    repo=_prepare_repo(tmp_path,make_repo)
    server,thread,connection,headers=_start(repo)
    try:
        status,state=_request(connection,'GET','/api/story-edits/story%3Acanvas-core')
        assert status==200
        source=repo/state['sourcePath'];original=source.read_bytes()
        request=dict(storyId=state['storyId'],expectedSourceHash=state['sourceHash'],expectedRevision=state['revision'],text=state['source']+'\n## Owner direction\n\n**Changed in browser**\n')
        status,_=_request(connection,'POST','/api/story-edits',request)
        assert status==403
        status,result=_request(connection,'POST','/api/story-edits',request,headers)
        assert status==200 and result['status']=='pending-review'
        assert source.read_bytes()==original
        entry=json.loads((repo/result['path']).read_text())['revisions'][0]
        assert entry['edited']==request['text'] and '+**Changed in browser**' in entry['diff']
        status,_=_request(connection,'POST','/api/story-edits',request,headers)
        assert status==409
        status,_=_request(connection,'GET','/api/story-edits/story%3A..%2F..%2Fetc%2Fpasswd')
        assert status==404
    finally:_stop(server,thread,connection)


def test_story_revision_reads_refreshed_graph_without_server_restart(tmp_path, make_repo):
    from vizzer.cli import main
    repo = _prepare_repo(tmp_path, make_repo)
    server, thread, connection, headers = _start(repo)
    try:
        # Existing Story is the same-server control before adding a new one.
        assert _request(connection, 'GET', '/api/story-edits/story%3Acanvas-core')[0] == 200
        source = repo / 'spec/drawing/epics/tools/stories/new-import.md'
        source.write_text('# Story: New import\n\n> Status: ready\n> Deps: []\n')
        assert main(['refresh', '--root', str(repo)]) == 0
        status, state = _request(connection, 'GET', '/api/story-edits/story%3Anew-import')
        assert status == 200
        original = source.read_bytes()
        request = dict(storyId=state['storyId'], expectedSourceHash=state['sourceHash'],
                       expectedRevision=state['revision'], text=state['source']+'\nOwner revision.\n')
        status, result = _request(connection, 'POST', '/api/story-edits', request, headers)
        assert status == 200 and result['revision'] == 1
        assert source.read_bytes() == original
        ledger = json.loads((repo / result['path']).read_text())
        assert ledger['revisions'][-1]['edited'] == request['text']
        source.unlink()
        assert main(['refresh', '--root', str(repo)]) == 0
        assert _request(connection, 'GET', '/api/story-edits/story%3Anew-import')[0] == 404
        (repo / 'vizzer/vizzer-graph.json').unlink()
        assert _request(connection, 'GET', '/api/story-edits/story%3Acanvas-core')[0] == 409
    finally:
        _stop(server, thread, connection)
