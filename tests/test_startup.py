import plistlib
from pathlib import Path
import vizzer.startup as startup


def test_login_jobs_are_project_scoped_and_use_installed_engine(tmp_path,monkeypatch):
    root=tmp_path/'project';engine=root/'vizzer/engine/vizzer'
    engine.mkdir(parents=True);(engine/'evolution.py').write_text('')
    home=tmp_path/'home';calls=[]
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:home))
    monkeypatch.setattr(startup.sys,'platform','darwin')
    monkeypatch.setattr(startup.sys,'argv',['startup','--root',str(root),'--port','57727'])
    monkeypatch.setattr(startup.subprocess,'run',lambda *args,**kwargs:calls.append(args[0]))
    startup.main()
    paths=list((home/'Library/LaunchAgents').glob('*.plist'));assert len(paths)==2
    jobs=[plistlib.loads(p.read_bytes()) for p in paths]
    assert all(job['WorkingDirectory']==str(root) and job['RunAtLoad'] and job['KeepAlive'] for job in jobs)
    assert any('watch' in job['ProgramArguments'] for job in jobs)
    assert any('57727' in job['ProgramArguments'] for job in jobs)
    assert sum(call[1]=='bootstrap' for call in calls if call[0]=='launchctl')==2
