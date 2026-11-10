#!/usr/bin/env python3
"""Strict last-resort recovery of ONE invisible hung Unity Editor in approved Codespace.

Do not run while a Unity window exists. No project-file, Git, cache or asset edits.
Only one same-UID Unity Editor with exact -projectPath may be signaled.
"""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PROJECT="/workspaces/Unity-Game-Aris"
BASE=Path("/tmp/aaris-codespaces")
BASE.mkdir(parents=True,exist_ok=True)
lock=(BASE/"guarded-unity-process-recovery.lock").open("a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
    print("UNITY_GUARDED_RECOVERY_ALREADY_RUNNING")
    raise SystemExit(20)

def editor_processes():
    found=[]
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid != os.getuid():
                continue
            cmd=[x.decode("utf-8","replace") for x in (p/"cmdline").read_bytes().split(b"\0") if x]
            if not cmd or not cmd[0].endswith("/Editor/Unity"):
                continue
            if "-projectPath" not in cmd:
                continue
            idx=cmd.index("-projectPath")
            if idx+1>=len(cmd) or cmd[idx+1]!=PROJECT:
                continue
            stat=(p/"stat").read_text()
            starttime=stat.rsplit(")",1)[1].split()[19]
            state=next((x.split()[1] for x in (p/"status").read_text().splitlines()
                        if x.startswith("State:")),"?")
            if state!="Z":
                found.append((int(p.name),starttime,state))
        except (OSError,IndexError,ValueError):
            continue
    return found

def visible_unity_windows():
    env=dict(os.environ,DISPLAY=":99")
    try:
        p=subprocess.run(["xdotool","search","--onlyvisible","--name","Unity"],
                         env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                         text=True,timeout=5)
    except (OSError,subprocess.TimeoutExpired):
        print("UNITY_GUARDED_RECOVERY_DISPLAY_CHECK_FAILED")
        raise SystemExit(21)
    # No matching windows is acceptable; a command error other than normal
    # 'no matches' is not.
    if p.returncode not in (0,1):
        print("UNITY_GUARDED_RECOVERY_WINDOW_CHECK_FAILED")
        raise SystemExit(22)
    return [x for x in p.stdout.splitlines() if x.isdecimal()]

def verify_same(pid,start):
    return any(x==pid and st==start for x,st,_ in editor_processes())

if not os.path.isdir(PROJECT+"/.git"):
    print("UNITY_GUARDED_RECOVERY_PROJECT_MISSING")
    raise SystemExit(23)
if visible_unity_windows():
    print("UNITY_GUARDED_RECOVERY_BLOCKED_VISIBLE_WINDOW")
    raise SystemExit(24)
procs=editor_processes()
if not procs:
    print("UNITY_GUARDED_RECOVERY_ALREADY_STOPPED")
    raise SystemExit(0)
if len(procs)!=1:
    print("UNITY_GUARDED_RECOVERY_BLOCKED_MULTIPLE_EDITORS")
    raise SystemExit(25)
pid,start,state=procs[0]
print("UNITY_GUARDED_RECOVERY_TARGET_VERIFIED")
if state in ("D","T","t"):
    print("UNITY_GUARDED_RECOVERY_UNSAFE_PROCESS_STATE")
    raise SystemExit(26)
# First try normal graceful termination. No broad kill, no pidfile trust.
os.kill(pid,signal.SIGTERM)
for i in range(16):
    time.sleep(1)
    if not verify_same(pid,start):
        print("UNITY_GUARDED_RECOVERY_SIGTERM_SUCCEEDED")
        raise SystemExit(0)
# SIGTERM was proven ineffective and window is still absent; before escalation
# revalidate the exact PID identity, project, caller UID and lack of GUI.
if visible_unity_windows():
    print("UNITY_GUARDED_RECOVERY_ESCALATION_BLOCKED_WINDOW_APPEARED")
    raise SystemExit(27)
if editor_processes()!=[(pid,start,state)]:
    # State can change from S->R; compare verified identity instead below.
    procs2=editor_processes()
    if len(procs2)!=1 or procs2[0][:2]!=(pid,start):
        print("UNITY_GUARDED_RECOVERY_ESCALATION_BLOCKED_IDENTITY_CHANGED")
        raise SystemExit(28)
if not verify_same(pid,start):
    print("UNITY_GUARDED_RECOVERY_COMPLETED_BEFORE_ESCALATION")
    raise SystemExit(0)
os.kill(pid,signal.SIGKILL)
print("UNITY_GUARDED_RECOVERY_EXACT_PID_ESCALATED_AFTER_SIGTERM")
for i in range(10):
    time.sleep(1)
    if not verify_same(pid,start):
        print("UNITY_GUARDED_RECOVERY_EDITOR_TERMINATED")
        raise SystemExit(0)
print("UNITY_GUARDED_RECOVERY_PROCESS_UNINTERRUPTIBLE")
raise SystemExit(29)
