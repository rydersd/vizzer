"""Install project-scoped macOS login services for Vizzer and progress pathing."""
import argparse
import hashlib
from pathlib import Path
import os
import plistlib
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args()
    if sys.platform!='darwin':parser.error('Login services require macOS')
    if not 1<=args.port<=65535:parser.error('port must be 1..65535')
    root=args.root.resolve();engine=root/'vizzer/engine'
    if not (engine/'vizzer/evolution.py').is_file():parser.error('Install the current engine in this project first')
    identity=hashlib.sha256(str(root).encode()).hexdigest()[:12]
    prefix=f'com.vizzer.project.{identity}'
    agents=Path.home()/'Library/LaunchAgents';logs=Path.home()/'Library/Logs/Vizzer'/identity
    agents.mkdir(parents=True,exist_ok=True);logs.mkdir(parents=True,exist_ok=True)
    jobs={'server':[str(engine),'serve','--root',str(root),'--port',str(args.port)],
          'pathing':[str(engine/'vizzer/evolution.py'),'--root',str(root),'watch']}
    domain=f'gui/{os.getuid()}'
    for job,arguments in jobs.items():
        label=f'{prefix}.{job}';path=agents/f'{label}.plist'
        config=dict(Label=label,ProgramArguments=[sys.executable,'-u',*arguments],WorkingDirectory=str(root),
                    RunAtLoad=True,KeepAlive=True,ThrottleInterval=10,ProcessType='Background',
                    StandardOutPath=str(logs/f'{job}.stdout.log'),StandardErrorPath=str(logs/f'{job}.stderr.log'))
        if path.exists() and plistlib.loads(path.read_bytes()).get('WorkingDirectory')!=str(root):
            raise SystemExit(f'Refusing to replace another project service: {path}')
        subprocess.run(['launchctl','bootout',f'{domain}/{label}'],capture_output=True)
        path.write_bytes(plistlib.dumps(config))
        subprocess.run(['plutil','-lint',str(path)],check=True)
        subprocess.run(['launchctl','enable',f'{domain}/{label}'],check=True)
        subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
        print(f'Installed {label}: {path}')
    print(f'Vizzer: http://127.0.0.1:{args.port}/constellation.html')

if __name__=='__main__':main()
