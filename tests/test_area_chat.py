import json
import http.client
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from vizzer.area_chat import BASE, append_message, read_area

@pytest.fixture
def root(tmp_path):
    base=tmp_path / BASE
    base.mkdir(parents=True)
    (base/'index.json').write_text(json.dumps([{'id':'foundation','title':'Foundation'}]))
    return tmp_path

def test_retry_and_concurrent_writers_preserve_messages(root):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: append_message(root,'foundation',f'q-{i}','Question'), range(8)))
    first=append_message(root,'foundation','q-0','Question')
    assert len(read_area(root,'foundation')['messages'])==8
    assert first['author']=='Owner'
    with pytest.raises(ValueError,match='different content'):
        append_message(root,'foundation','q-0','Changed')

def test_reply_is_bound_to_owner_and_rejects_duplicates(root):
    owner=append_message(root,'foundation','q-1','What is v0?')
    reply=append_message(root,'foundation','r-1','Define the outcome first.',author='Codex',reply_to='q-1',expected_parent_hash=owner['sha256'])
    assert reply['replyToHash']==owner['sha256']
    assert read_area(root,'foundation')['pending']==0
    with pytest.raises(ValueError,match='already answered'):
        append_message(root,'foundation','r-2','Another answer',author='Claude',reply_to='q-1',expected_parent_hash=owner['sha256'])
    with pytest.raises(ValueError,match='owner message'):
        append_message(root,'foundation','r-3','Wrong parent',author='Codex',reply_to='missing',expected_parent_hash=owner['sha256'])

def test_unknown_paths_and_symlinks_rejected(root,tmp_path):
    for area in ('../escape','unknown','/tmp/x'):
        with pytest.raises(ValueError): append_message(root,area,'q-1','Hello')
    (root/BASE/'foundation').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):
        append_message(root,'foundation','q-1','Hello')

def test_http_csrf_persistence_and_no_author_spoof(root):
    import http.server
    from vizzer.cli import _serve_handler
    from vizzer.config import Config,DEFAULTS
    handler=_serve_handler(root,None,root,Config(data=DEFAULTS),'test-token')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    host=f'127.0.0.1:{server.server_port}'
    def request(method,path,body=None,headers=None):
        connection=http.client.HTTPConnection(host)
        connection.request(method,path,body=body,headers=headers or {})
        response=connection.getresponse(); result=(response.status,json.loads(response.read()));connection.close();return result
    try:
        payload=json.dumps({'id':'q-1','text':'<img src=x onerror=alert(1)>','author':'Codex'})
        assert request('POST','/api/area-chat/foundation',payload,{'Content-Type':'application/json'})[0]==403
        status,data=request('POST','/api/area-chat/foundation',payload,{'Content-Type':'application/json','Origin':f'http://{host}','X-Vizzer-CSRF':'test-token'})
        assert status==200 and data['pending']==1
        assert data['messages'][0]['author']=='Owner'
        assert request('GET','/api/area-chat/foundation')[1]['messages']==data['messages']
        assert request('GET','/api/area-chat/foundation',headers={'Host':'evil.example'})[0]==421
    finally:
        server.shutdown();server.server_close();thread.join()


def test_revised_question_reopens_and_rejects_stale_reasoning(root):
    import hashlib
    owner=append_message(root,'foundation','q-1','Plan local storage')
    reply=append_message(root,'foundation','r-1','Use local files',author='Codex',
                         reply_to=owner['id'],expected_parent_hash=owner['sha256'])
    path=root/BASE/'foundation/messages.json'
    rows=json.loads(path.read_text())
    rows[0]['text']='Plan shared multiuser storage'
    # Even a manual edit that forgets to update sha256 must invalidate the answer.
    path.write_text(json.dumps(rows))
    assert read_area(root,'foundation')['pending']==1
    with pytest.raises(ValueError,match='changed'):
        append_message(root,'foundation','r-stale','Still use local files',author='Codex',
                       reply_to=owner['id'],expected_parent_hash=owner['sha256'])
    current_hash=hashlib.sha256(rows[0]['text'].encode()).hexdigest()
    fresh=append_message(root,'foundation','r-2','Discuss shared storage',author='Codex',
                         reply_to=owner['id'],expected_parent_hash=current_hash)
    assert fresh['replyToHash']==current_hash
    assert read_area(root,'foundation')['pending']==0
    assert read_area(root,'foundation')['messages'][1]==reply
    assert append_message(root,'foundation','r-2','Discuss shared storage',author='Codex',
                          reply_to=owner['id'],expected_parent_hash=current_hash)==fresh
    with pytest.raises(ValueError,match='expected parent hash'):
        append_message(root,'foundation','r-unbound','Unbound',author='Codex',reply_to=owner['id'])
