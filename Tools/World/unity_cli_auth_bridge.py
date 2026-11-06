#!/usr/bin/env python3
"""Owner-scoped Unity CLI installation and status bridge for a single Codespace.

Only official Unity-supplied installation and named Unity authentication/license
subcommands are invoked. No account credentials enter Git, Actions or chat.
The user must authorize the Unity OAuth prompt on Unity's official website.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.parse

STAGE=Path("/workspaces/.aaris-world-bridge/ondemand")
STATUS=STAGE/"unity-cli-install-status.json"
INSTALL_LOG=STAGE/"unity-cli-install.log"
LOGIN_LOG=STAGE/"unity-cli-login.log"
LOGIN_PID=STAGE/"unity-cli-login.pid"
CLI=Path.home()/".local/bin/unity"
INSTALL_SCRIPT=STAGE/"unity-cli-vendor-install.sh"
OFFICIAL="https://public-cdn.cloud.unity3d.com/hub/prod/cli/install.sh"
LOCK=STAGE/"unity-cli-install.lock"


def run(argv, timeout=24, env=None):
    return subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout, check=False, env=env)


def put(state, **kw):
    STAGE.mkdir(mode=0o700,parents=True,exist_ok=True)
    f=STATUS.with_suffix(".next")
    if f.is_symlink(): raise RuntimeError("unsafe status symlink")
    f.write_text(json.dumps(dict(state=state,when=int(time.time()),**kw)))
    f.chmod(0o600)
    os.replace(f,STATUS)


def read():
    if STATUS.is_symlink() or not STATUS.is_file() or STATUS.stat().st_size>4096:return {}
    try:return json.loads(STATUS.read_text())
    except (ValueError,OSError):return {}


def installed():
    return CLI.is_file() and not CLI.is_symlink() and os.access(CLI,os.X_OK)


def process_alive(pidpath, expected):
    if pidpath.is_symlink() or not pidpath.is_file():return False
    try:
        pid=int(pidpath.read_text().strip())
        raw=Path("/proc")/str(pid)/"cmdline"
        return expected in raw.read_bytes().decode("utf-8","replace")
    except (ValueError,OSError):return False


def installer_running():
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():continue
        try:
            cmd=(item/"cmdline").read_bytes().decode("utf-8","replace")
            if "unity_cli_auth_bridge.py" in cmd and "--install-worker" in cmd:
                return True
        except OSError:pass
    return False


def install_worker():
    STAGE.mkdir(mode=0o700,parents=True,exist_ok=True)
    with LOCK.open("a+") as file:
        fcntl.flock(file.fileno(),fcntl.LOCK_EX)
        if installed():put("installed");return
        try:
            put("downloading")
            if INSTALL_SCRIPT.is_symlink():raise RuntimeError("unsafe install script path")
            download=run(["curl","--fail","--location","--show-error","--silent",
                         "--retry","3","--max-time","120","--output",str(INSTALL_SCRIPT),OFFICIAL],timeout=200)
            if download.returncode or not INSTALL_SCRIPT.is_file() or not 200<INSTALL_SCRIPT.stat().st_size<1000000:
                raise RuntimeError("Official Unity CLI bootstrap download failed")
            INSTALL_SCRIPT.chmod(0o600)
            env=os.environ.copy()
            env["UNITY_CLI_CHANNEL"]="beta"
            env["PATH"]=str(CLI.parent)+os.pathsep+env.get("PATH","")
            put("installing")
            with INSTALL_LOG.open("a",encoding="utf-8") as output:
                proc=subprocess.run(["bash",str(INSTALL_SCRIPT)],cwd=STAGE,env=env,
                                    stdin=subprocess.DEVNULL,stdout=output,stderr=output,
                                    timeout=1200,check=False)
            if proc.returncode or not installed():
                raise RuntimeError("Unity CLI installation incomplete (exit "+str(proc.returncode)+")")
            put("installed")
        except Exception as exc:
            put("failed",error=type(exc).__name__+": "+str(exc)[:200])


def install_start():
    if installed():return {"status":"already_installed"}
    if installer_running():return {"status":"already_running"}
    STAGE.mkdir(mode=0o700,parents=True,exist_ok=True)
    with INSTALL_LOG.open("a",encoding="utf-8") as log:
        p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--install-worker"],
                           cwd=STAGE,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                           start_new_session=True)
    return {"status":"install_worker_started","pid":p.pid}


def install_status():
    r=read()
    return {"cli_present":installed(),"installer_running":installer_running(),
            "installer_state":r.get("state","not_started"),
            "install_error":r.get("error")}


def unity_cmd(*args,timeout=30):
    if not installed():return {"ok":False,"error":"Unity CLI not installed"}
    env=os.environ.copy()
    env["PATH"]=str(CLI.parent)+os.pathsep+env.get("PATH","")
    try:
        proc=run([str(CLI),*args],timeout=timeout,env=env)
        # Do not disclose the CLI's raw auth contents; only status, not tokens.
        return {"ok":proc.returncode==0,"exit_code":proc.returncode}
    except subprocess.TimeoutExpired:
        return {"ok":False,"error":"Unity CLI status command timed out"}


def login_start():
    if not installed():return {"status":"cli_not_installed"}
    if process_alive(LOGIN_PID,"unity"):
        return {"status":"login_already_running"}
    STAGE.mkdir(mode=0o700,parents=True,exist_ok=True)
    if LOGIN_LOG.is_symlink() or LOGIN_PID.is_symlink():
        raise RuntimeError("unsafe login state symlink")
    env=os.environ.copy()
    env["PATH"]=str(CLI.parent)+os.pathsep+env.get("PATH","")
    # Headless environment prints an authorization URL for owner browser.
    env.pop("DISPLAY",None)
    env["BROWSER"]="/bin/false"
    with LOGIN_LOG.open("w",encoding="utf-8") as log:
        proc=subprocess.Popen([str(CLI),"auth","login"],cwd=STAGE,env=env,
                              stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                              start_new_session=True)
    LOGIN_LOG.chmod(0o600)
    LOGIN_PID.write_text(str(proc.pid))
    LOGIN_PID.chmod(0o600)
    return {"status":"login_started","pid":proc.pid}


def auth_status():
    # Only return Unity-owned HTTPS auth links, never raw CLI stdout or secrets.
    url=None
    if LOGIN_LOG.is_file() and not LOGIN_LOG.is_symlink() and LOGIN_LOG.stat().st_size<160000:
        text=LOGIN_LOG.read_text(encoding="utf-8",errors="replace")
        links=re.findall(r"https://[^\\s<>\"']+",text)
        for cand in links:
            cand=cand.rstrip("),.;")
            try:
                u=urllib.parse.urlsplit(cand)
                host=u.hostname or ""
                if u.scheme=="https" and (host=="unity.com" or host.endswith(".unity.com") or host=="unity3d.com" or host.endswith(".unity3d.com")):
                    url=cand
                    break
            except ValueError:
                pass
    return {"cli_present":installed(),"login_process_running":process_alive(LOGIN_PID,"unity"),
            "sign_in_url":url,"auth_checked":unity_cmd("auth","status",timeout=18)}


def license_status():
    return {"cli_present":installed(),"license_check":unity_cmd("license","status",timeout=26)}


if __name__=="__main__":
    mapping={
      "--install-start":install_start,"--install-status":install_status,
      "--auth-start":login_start,"--auth-status":auth_status,
      "--license-status":license_status
    }
    if sys.argv[1:]==["--install-worker"]:
        install_worker()
    elif len(sys.argv)==2 and sys.argv[1] in mapping:
        print(json.dumps(mapping[sys.argv[1]](),ensure_ascii=False))
    else:
        raise SystemExit("Unsupported operation")
