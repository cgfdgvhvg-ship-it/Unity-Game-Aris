#!/usr/bin/env python3
"""Bounded in-Codespace agent for the Actions-free Aaris Cloudflare relay.

Only executes an explicit set of reviewed actions. Does not use shell=True,
Git credentials, git reset/clean, arbitrary paths, or write Unity source.
This process MUST be started by a trusted Codespaces startup hook on each boot.
"""
from __future__ import annotations
import argparse
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

CODESPACE_PROJECT = Path('/workspaces/Unity-Game-Aris')
STAGE = Path('/workspaces/.aaris-world-bridge/ondemand')
STATE = Path('/workspaces/.aaris-world-bridge/relay-local-results')
ID_RE = re.compile(r'r[a-z0-9][a-z0-9-]{5,51}\Z')
ARG_RE = re.compile(r'[a-z][a-z0-9-]{3,55}\Z')
SUPPORTED = {
    'system_status': ('system', 0),
    'desktop_live_start': ('desktop_xterm', 0),
    'desktop_live_status': ('desktop_diagnose', 0),
    'unity_virtual_start': ('unity_virtual_gui_launch', 0),
    'unity_virtual_status': ('unity_virtual_gui_status', 0),
    'unity_camera_focus': ('unity_virtual_live', 3),
    'unity_status': ('unity_session_status', 0),
    'unity_recover': ('unity_session_recover', 0),
    'unity_gallery_start': ('unity_house_bridge_gallery_start', 0),
    'unity_gallery_diagnose': ('unity_house_bridge_gallery_diagnose', 1),
    'unity_gallery_partial_export': ('unity_house_bridge_gallery_partial_export', 1),
    'unity_frame_check': ('unity_virtual_frame', 1),
}


def validate_job(job):
    if not isinstance(job, dict) or set(job) != {'id','action','command','args'}:
        raise ValueError('Invalid relay job')
    if not isinstance(job['id'], str) or not ID_RE.fullmatch(job['id']):
        raise ValueError('Invalid job ID')
    if job['action'] != 'terminal' or job['command'] not in SUPPORTED:
        raise ValueError('Command not approved for Codespace relay')
    expected = SUPPORTED[job['command']][1]
    if not isinstance(job['args'], list) or len(job['args']) != expected:
        raise ValueError('Wrong argument count')
    if job['command'] == 'unity_camera_focus':
        if any(not isinstance(n,(int,float)) or isinstance(n,bool) or
               not math.isfinite(n) or abs(n)>20000 for n in job['args']):
            raise ValueError('Invalid camera coordinate')
    elif expected and (not isinstance(job['args'][0],str) or
                     not ARG_RE.fullmatch(job['args'][0])):
        raise ValueError('Invalid gallery/frame ID')
    return job


def read_config(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Relay config must be a private regular file (chmod 600)')
    if path.stat().st_size > 4000:
        raise ValueError('Oversized agent configuration')
    data=json.loads(path.read_text(encoding='utf-8'))
    if set(data) != {'url','agent_key'}:
        raise ValueError('Agent config needs exactly url and agent_key')
    u=urlparse(data['url'])
    if (u.scheme!='https' or not u.netloc or u.username or u.password or
         u.query or u.fragment or u.path not in ('','/')):
        raise ValueError('Relay URL must be an HTTPS origin')
    if not isinstance(data['agent_key'],str) or len(data['agent_key'])<32 or len(data['agent_key'])>256:
        raise ValueError('Invalid agent secret')
    return data


def exchange(config, method, route, payload=None):
    body=json.dumps(payload).encode('utf-8') if payload is not None else None
    request=Request(config['url'].rstrip('/')+route, data=body,method=method,
      headers={'Authorization':'Bearer '+config['agent_key'],
               'Accept':'application/json',
               'Content-Type':'application/json',
               'User-Agent':'aaris-codespace-agent/1'})
    with urlopen(request,timeout=25) as response:
        blob=response.read(20000)
    return json.loads(blob)


def _run(command, timeout=35, max_stdout=8500):
    try:
        p=subprocess.run(command, cwd=CODESPACE_PROJECT,
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,timeout=timeout,check=False)
        return {'status':'ok' if p.returncode==0 else 'error',
                'exit_code':p.returncode if p.returncode in (-1,0,1,2,3,124,127) else 1,
                'stdout':p.stdout[-max_stdout:], 'stderr':p.stderr[-2500:]}
    except subprocess.TimeoutExpired:
        return {'status':'error','exit_code':124,'stdout':'','stderr':'Reviewed command timed out'}
    except OSError:
        return {'status':'error','exit_code':127,'stdout':'','stderr':'Reviewed command unavailable'}


def stage_scratch_camera_bridge():
    """Update only the disposable scratch Editor bridge, never the owner's Git worktree."""
    approved=STAGE/'AarisLiveEditorBridge.reviewed.cs'
    target=Path('/tmp/aaris-unity-batch/project/Assets/AarisWorld/Editor/AarisLiveEditorBridge.cs')
    if not target.is_file():
        return False  # scratch may need safe native Unity recovery first
    if approved.is_symlink() or target.is_symlink() or not approved.is_file():
        raise ValueError('Unsafe scratch camera bridge file')
    source=approved.read_text(encoding='utf-8')
    old='private static readonly string Root = "/home/codespace/.aaris-desktop";'
    new='private static readonly string Root = "/tmp/aaris-unity-batch/control";'
    if old not in source or 'view.LookAtDirect(center, view.rotation, focusSize);' not in source:
        raise ValueError('Review-branch camera focus source verification failed')
    desired=source.replace(old,new,1)
    current=target.read_text(encoding='utf-8')
    if current==desired:
        return True
    if old not in current and new not in current:
        raise ValueError('Scratch bridge has unknown control root; refusing modification')
    # Keep a byte-perfect rollback of any scratch bridge before replacing it.
    backup=STAGE/('AarisLiveEditorBridge.pre-focus-'+hashlib.sha256(current.encode()).hexdigest()[:12]+'.cs')
    if backup.is_symlink():
        raise ValueError('Unsafe scratch bridge backup')
    if not backup.exists():
        with backup.open('x',encoding='utf-8') as f:
            f.write(current)
        backup.chmod(0o600)
    pending=target.with_name(target.name+'.ai-focus-pending')
    if pending.exists() or pending.is_symlink():
        raise ValueError('Unsafe pending scratch bridge')
    with pending.open('x',encoding='utf-8') as f:
        f.write(desired)
    os.replace(pending,target)
    return True


def execute(job):
    validate_job(job)
    if job['command']=='system_status':
        blocks=[]
        for argv in (['pwd'],['uname','-a'],['df','-h','/workspaces','/tmp']):
            r=_run(argv,timeout=15)
            blocks.append('$ '+' '.join(argv)+'\n'+r['stdout']+r['stderr'])
            if r['exit_code']!=0:
                return {'id':job['id'],**r}
        return {'id':job['id'],'status':'ok','exit_code':0,
                'stdout':'\n'.join(blocks)[-8500:],'stderr':''}
    if not STAGE.is_dir() or STAGE.is_symlink():
        return {'id':job['id'],'status':'error','exit_code':3,'stdout':'',
                'stderr':'Trusted Codespace stage missing'}
    executor=STAGE/'ai_codespace_executor.py'
    if not executor.is_file() or executor.is_symlink() or executor.stat().st_size>400000:
        return {'id':job['id'],'status':'error','exit_code':3,'stdout':'',
                'stderr':'Approved native Unity command runner not staged'}
    operation = SUPPORTED[job['command']][0]
    if job['command'] in ('unity_virtual_start','unity_camera_focus'):
        stage_scratch_camera_bridge()
    jobfile=STAGE/(job['id']+'.json')
    approved_args=job['args']
    if job['command']=='unity_camera_focus':
        v=dict(zip(('x','y','z'),job['args']))
        approved_args=[json.dumps({'action':'inspect','cameraTarget':v,'radius':20,'limit':12},separators=(',',':'))]
    payload={'id':job['id'],'operation':operation,'args':approved_args}
    # Keep job file append-only: do not run an overwritten or changed job.
    if jobfile.exists() or jobfile.is_symlink():
        if not jobfile.is_file() or json.loads(jobfile.read_text())!=payload:
            raise ValueError('Conflicting staged command; refusing execution')
    else:
        with jobfile.open('x',encoding='utf-8') as stream:
            json.dump(payload,stream)
    result=_run([sys.executable,str(executor),str(jobfile)],timeout=140,max_stdout=40000)
    if result['exit_code']!=0:
        return {'id':job['id'],**result}
    try:
        data=json.loads(result['stdout'])
        if data.get('id')!=job['id'] or data.get('operation')!=operation:
            raise ValueError('Result identity mismatch')
        code=int(data.get('exit_code',1))
        return {'id':job['id'],'status':'ok' if data.get('ok') and code==0 else 'error',
                'exit_code':code if code in (-1,0,1,2,3,124,127) else 1,
                'stdout':str(data.get('stdout',''))[-8500:],
                'stderr':str(data.get('stderr',''))[-2500:]}
    except (ValueError,KeyError,TypeError):
        return {'id':job['id'],'status':'error','exit_code':1,
                'stdout':'','stderr':'Unity runner returned invalid result'}


def store_once(job_id, payload,root=STATE):
    if not root.exists():root.mkdir(mode=0o700,parents=True)
    if root.is_symlink():raise ValueError('Unsafe local receipt store')
    path=root/(job_id+'.json')
    if path.exists():
        if path.is_symlink() or path.stat().st_size>18000:
            raise ValueError('Unsafe prior command receipt')
        return json.loads(path.read_text())
    with path.open('x',encoding='utf-8') as out:
        json.dump(payload,out,ensure_ascii=False)
    path.chmod(0o600)
    return payload


def once(config):
    response=exchange(config,'GET','/v1/next')
    job=response.get('job')
    if job is None:return 'idle'
    job=validate_job(job)
    path=STATE/(job['id']+'.json')
    if path.exists():
        stored=store_once(job['id'],None)
    else:
        try: result=execute(job)
        except Exception as error:
            result={'id':job['id'],'status':'error','exit_code':1,
                    'stdout':'','stderr':type(error).__name__+': '+str(error)[:200]}
        stored=store_once(job['id'],result)
    outcome=exchange(config,'POST','/v1/result',stored)
    if not outcome.get('stored') or outcome.get('id')!=job['id']:
        raise ValueError('Result not acknowledged by worker')
    return 'completed:'+job['id']


def setup_config(path):
    url=input('Cloudflare Worker HTTPS origin (https://...workers.dev): ').strip().rstrip('/')
    key=getpass.getpass('Agent shared secret (not echoed): ')
    cfg={'url':url,'agent_key':key}
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.netloc or parsed.path not in ('','/') or len(key)<32:
        raise ValueError('Invalid relay endpoint or shared secret')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    path.parent.chmod(0o700)
    if path.exists() or path.is_symlink():
        raise ValueError('Config already exists; refusing overwrite')
    fd=os.open(path,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(cfg,stream)
    read_config(path)
    print('Private relay configuration saved (credentials not displayed).')


def install_service(script, config):
    if not read_config(config):raise ValueError('Missing valid config')
    unit_dir=Path.home()/'.config/systemd/user'
    unit_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    unit=unit_dir/'aaris-codespace-relay.service'
    if unit.exists() or unit.is_symlink():
        raise ValueError('User service already exists; refusing overwrite')
    if ' ' in str(script) or ' ' in str(config):
        raise ValueError('Unsupported service path with spaces')
    unit.write_text('[Unit]\nDescription=Aaris bounded Codespace relay agent\n'
      'After=network-online.target\nWants=network-online.target\n'
      '[Service]\nType=simple\n'
      f'ExecStart={sys.executable} {script} --config {config}\n'
      'Restart=on-failure\nRestartSec=15\n'
      '[Install]\nWantedBy=default.target\n')
    for args in (['systemctl','--user','daemon-reload'],
                 ['systemctl','--user','enable','--now','aaris-codespace-relay.service']):
        result=subprocess.run(args,text=True,capture_output=True,timeout=25,check=False)
        if result.returncode:
            print('systemd user service unavailable; configure Codespaces postStartCommand instead.')
            print('Error type: service_not_started')
            return False
    print('User service enabled; verify it restarts after an actual Codespace restart.')
    return True


def main():
    parser=argparse.ArgumentParser(description='Run bounded Codespace relay agent')
    parser.add_argument('--config',type=Path,default=Path.home()/'.config/aaris-relay/config.json')
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--setup',action='store_true',help='Create 0600 config without echoing secrets')
    parser.add_argument('--install-service',action='store_true',help='Install optional systemd user startup')
    args=parser.parse_args()
    if args.setup:
        setup_config(args.config)
        return
    if args.install_service:
        if not install_service(Path(__file__).resolve(),args.config.resolve()):sys.exit(2)
        return
    config=read_config(args.config)
    if args.once:
        print(once(config))
        return
    while True:
        try:
            status=once(config)
            if status!='idle':print(status,flush=True)
        except (ValueError, HTTPError, URLError, OSError) as exc:
            # Never print tokens, Authorization headers, or request data.
            print('relay_poll_error:'+type(exc).__name__,flush=True)
        time.sleep(20)


if __name__=='__main__':main()
