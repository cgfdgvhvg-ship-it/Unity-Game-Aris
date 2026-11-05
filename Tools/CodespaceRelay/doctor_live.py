#!/usr/bin/env python3
"""Read-only Codespace/GitHub/Unity live viewer health report. Never prints secrets."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess

PROJECT = Path("/workspaces/Unity-Game-Aris")
STAGE = Path("/workspaces/.aaris-world-bridge/ondemand")
HOME = Path.home()
LINK = "https://aaris-codespace-relay.aaris-game-control-6f9c.workers.dev/live"

def tcp_open(port):
    try:
        with socket.create_connection(("127.0.0.1",port),timeout=1):return True
    except OSError:return False

def process(name):
    if not shutil.which("pgrep"):return False
    try:
        return subprocess.run(["pgrep","-u",str(os.getuid()),"-x",name],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                              timeout=3).returncode==0
    except (OSError,subprocess.TimeoutExpired):return False

def unit(name):
    if not shutil.which("systemctl"):return "unavailable"
    try:
        r=subprocess.run(["systemctl","--user","is-active",name+".service"],
                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                        text=True,timeout=5)
        return r.stdout.strip() if r.returncode==0 else "inactive"
    except (OSError,subprocess.TimeoutExpired):return "unavailable"

def report():
    valid=PROJECT.is_dir()
    return {
        "running_inside_codespace":valid,
        "codespace_name":os.environ.get("CODESPACE_NAME","not-set"),
        "project_exists":valid,
        "installer_staged":(STAGE/"bootstrap_live.py").is_file(),
        "queue_agent_staged":(STAGE/"github_queue_agent.py").is_file(),
        "github_agent_unit":unit("aaris-github-queue"),
        "desktop_unit":unit("aaris-live-desktop"),
        "vnc_password_configured":(HOME/".aaris-desktop/vnc.pass").is_file(),
        "xvfb_display_12":Path("/tmp/.X11-unix/X12").exists(),
        "x11vnc_process":process("x11vnc"),
        "novnc_websockify_process":process("websockify"),
        "vnc_local_5900":tcp_open(5900),
        "novnc_local_6080":tcp_open(6080),
        "unity_editor_process":process("Unity"),
        "scratch_map_exists":Path("/tmp/aaris-unity-batch/project/Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity").is_file(),
        "viewer_link":LINK,
        "interpretation":"Port 6080 must also be privately forwarded in GitHub Codespaces, with owner login. Codespace must be running. This status does not prove Unity camera rendering."
    }

if __name__=="__main__":
    print(json.dumps(report(),ensure_ascii=False,indent=2))
