#!/usr/bin/env python3
"""One-time Codespace setup for GitHub job polling and private noVNC display.

Does NOT checkout, reset, merge, or modify Unity project files. The Cloudflare
Worker manages lifecycle; this agent runs commands INSIDE the Codespace.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = "Aaris-khan-don/Unity-Game-Aris"
BRANCH = "ai/codespace-jobs"
ROOT = Path("/workspaces/.aaris-world-bridge")
STAGE = ROOT / "ondemand"
PROJECT = Path("/workspaces/Unity-Game-Aris")
SOURCES = {
    "Tools/CodespaceRelay/agent.py": STAGE / "agent.py",
    "Tools/CodespaceRelay/github_queue_agent.py": STAGE / "github_queue_agent.py",
    "Tools/CodespaceRelay/bootstrap_live.py": STAGE / "bootstrap_live.py",
    "Tools/CodespaceRelay/doctor_live.py": STAGE / "doctor_live.py",
    "Tools/World/ai_codespace_executor.py": STAGE / "ai_codespace_executor.py",
    "Assets/AarisWorld/Editor/AarisLiveEditorBridge.cs": STAGE / "AarisLiveEditorBridge.reviewed.cs",
}
LIVE_URL = ("https://aaris-codespace-relay."
            "aaris-game-control-6f9c.workers.dev/live")


def command(args, *, timeout=45, input_text=None):
    return subprocess.run(args, cwd=PROJECT, text=True, input=input_text,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, check=False)


def fetch(path):
    from urllib.parse import quote
    url = ("repos/" + REPO + "/contents/" + quote(path, safe="/")
           + "?ref=" + quote(BRANCH, safe=""))
    r = command(["gh", "api", url])
    if r.returncode:
        raise RuntimeError("Cannot read private GitHub source: gh authentication or path invalid")
    doc = json.loads(r.stdout)
    if doc.get("path") != path or doc.get("encoding") != "base64":
        raise RuntimeError("GitHub source path or encoding mismatch")
    if doc.get("size", 999999) > 400000:
        raise RuntimeError("Unexpectedly large source")
    return base64.b64decode(doc["content"])


def install_sources():
    if not PROJECT.is_dir() or PROJECT.is_symlink():
        raise RuntimeError(
            "This is the PHONE/TERMUX terminal, not the GitHub Codespace. "
            "Open github.com/codespaces -> your Codespace -> Open in browser "
            "-> TERMINAL and run the installation there once. "
            "Do NOT install x11vnc into Termux.")
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI not installed inside Codespace")
    STAGE.mkdir(parents=True, exist_ok=True)
    if STAGE.is_symlink():
        raise RuntimeError("Unsafe staging directory")
    for path, target in SOURCES.items():
        incoming = fetch(path)
        if target.is_symlink():
            raise RuntimeError("Unsafe staged symlink: " + target.name)
        if target.exists() and target.read_bytes() == incoming:
            print("ALREADY_INSTALLED:", target.name)
            continue
        if target.suffix == ".py":
            compile(incoming, str(target), "exec")
        elif target.name == "AarisLiveEditorBridge.reviewed.cs" and (
            b"view.LookAtDirect(center, view.rotation, focusSize);" not in incoming or
            b'private static readonly string Root = "/home/codespace/.aaris-desktop";' not in incoming):
            raise RuntimeError("Unexpected Unity camera focus bridge source")
        if target.exists():
            # The native Unity runner may contain newer local recovery fixes.
            # Keep it untouched instead of silently replacing it.
            if target.name == "ai_codespace_executor.py":
                print("PRESERVED_LOCAL_NATIVE_EXECUTOR:", target.name)
                continue
            old = target.read_bytes()
            backup = target.with_name(target.name + ".backup-" +
                                      hashlib.sha256(old).hexdigest()[:12])
            if not backup.exists():
                with backup.open("xb") as stream:
                    stream.write(old)
                backup.chmod(0o600)
            print("BACKED_UP_OLD_AGENT:", target.name)
        staging = target.with_name(target.name + ".install-tmp")
        if staging.exists() or staging.is_symlink():
            raise RuntimeError("Unreviewed staging file: " + staging.name)
        with staging.open("xb") as out:
            out.write(incoming)
        staging.chmod(0o600)
        os.replace(staging, target)
        print("STAGED_CURRENT_AGENT:", target.name, len(incoming))
    issue = ROOT / "issue.txt"
    if issue.exists() and issue.read_text().strip() != "37":
        raise RuntimeError("Existing GitHub issue bridge target differs")
    ROOT.mkdir(parents=True, exist_ok=True)
    if not issue.exists():
        issue.write_text("37\n")


def ensure_vnc_password():
    """Ask exactly once inside Codespace; never echo or commit VNC credentials."""
    directory = Path.home() / ".aaris-desktop"
    passwd = directory / "vnc.pass"
    if directory.is_symlink() or passwd.is_symlink():
        raise RuntimeError("Unsafe VNC password location")
    if passwd.is_file() and passwd.stat().st_size:
        passwd.chmod(0o600)
        print("SAVED_VNC_PASSWORD_REUSED")
        return
    if not shutil.which("x11vnc"):
        raise RuntimeError("x11vnc is missing INSIDE Codespace; do not install it on the phone")
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    directory.chmod(0o700)
    print("ONE_TIME_VNC_PASSWORD: enter a private password at the prompt.",flush=True)
    print("The VNC protocol uses at most 8 password characters; choose 8 strong characters.",flush=True)
    try:
        with open("/dev/tty","r+") as terminal:
            task = subprocess.run(
                ["x11vnc","-storepasswd",str(passwd)],stdin=terminal,
                stdout=terminal,stderr=terminal,timeout=100,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise RuntimeError(
            "Cannot prompt for a password here. Run the installer in the actual Codespace "
            "integrated Terminal, not Termux or a noninteractive runner.")
    if task.returncode != 0 or not passwd.is_file() or passwd.stat().st_size == 0:
        raise RuntimeError("VNC password was not saved")
    passwd.chmod(0o600)
    print("VNC_PASSWORD_SAVED_ONCE; keep it private",flush=True)


def unit_file(name, body):
    folder = Path.home() / ".config/systemd/user"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + ".service")
    if path.is_symlink():
        raise RuntimeError("Unsafe systemd symlink")
    if path.exists() and path.read_text() != body:
        print("PRESERVED_EXISTING_SERVICE:", name)
        return
    if not path.exists():
        path.write_text(body)
        path.chmod(0o600)


def setup_units():
    py = sys.executable
    agent = STAGE / "github_queue_agent.py"
    bootstrap = STAGE / "bootstrap_live.py"
    agent_unit = (
        "[Unit]\nDescription=Aaris GitHub-driven Codespace terminal control\n"
        "After=network-online.target\nWants=network-online.target\n\n"
        "[Service]\nType=simple\nWorkingDirectory=" + str(PROJECT) + "\n"
        "ExecStart=" + py + " -u " + str(agent) + "\n"
        "Restart=always\nRestartSec=15\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    desktop_unit = (
        "[Unit]\nDescription=Aaris authenticated noVNC live desktop\n"
        "After=network-online.target\nWants=network-online.target\n\n"
        "[Service]\nType=oneshot\nWorkingDirectory=" + str(PROJECT) + "\n"
        "ExecStart=" + py + " " + str(bootstrap) + " --desktop-once\n"
        "RemainAfterExit=yes\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    unit_file("aaris-github-queue", agent_unit)
    unit_file("aaris-live-desktop", desktop_unit)
    result = command(["systemctl", "--user", "daemon-reload"], timeout=18)
    if result.returncode:
        print("USER_SYSTEMD_UNAVAILABLE: startup automatic only after shell bootstrap")
        return False
    for name in ("aaris-github-queue", "aaris-live-desktop"):
        result = command(["systemctl", "--user", "enable", "--now", name + ".service"], timeout=45)
        print("UNIT", name, "enabled" if result.returncode == 0 else "NOT_ENABLED")
    check = command(["systemctl", "--user", "is-active", "aaris-github-queue.service"])
    return check.stdout.strip() == "active"


def fallback_shell_hook():
    # A fallback, not a guaranteed Codespace boot hook. Shell start invokes it.
    bashrc = Path.home() / ".bashrc"
    marker = "# AARIS_GITHUB_RELAY_SHELL_FALLBACK"
    if bashrc.exists() and marker in bashrc.read_text(errors="replace"):
        return
    with bashrc.open("a", encoding="utf-8") as out:
        out.write("\n" + marker + "\n")
        out.write("pgrep -f '^" + sys.executable + " -u "
                  + str(STAGE / "github_queue_agent.py")
                  + "$' >/dev/null || (nohup " + sys.executable + " -u "
                  + str(STAGE / "github_queue_agent.py")
                  + " >>" + str(ROOT / "github-queue.log")
                  + " 2>&1 </dev/null &)\n")
        out.write("python3 " + str(STAGE / "bootstrap_live.py")
                  + " --desktop-once >/dev/null 2>&1 || true\n")
    print("SHELL_FALLBACK_INSTALLED: automatic after opening Codespace terminal")


def run_desktop():
    executor = STAGE / "ai_codespace_executor.py"
    if not executor.is_file() or executor.is_symlink():
        print("DESKTOP_NOT_READY: native executor missing")
        return 3
    passwd = Path.home() / ".aaris-desktop/vnc.pass"
    if not passwd.is_file() or passwd.is_symlink():
        print("DESKTOP_NOT_READY: saved VNC password missing")
        print('ONE_TIME: mkdir -p "$HOME/.aaris-desktop" && chmod 700 "$HOME/.aaris-desktop" && x11vnc -storepasswd "$HOME/.aaris-desktop/vnc.pass"')
        return 3
    pid = "rdesktopbootstrap20261105"
    job = STAGE / (pid + ".json")
    payload = {"id": pid, "operation": "desktop_xterm", "args": []}
    if job.is_symlink():
        raise RuntimeError("Unsafe desktop job file")
    if job.exists() and json.loads(job.read_text()) != payload:
        raise RuntimeError("Conflicting desktop command")
    if not job.exists():
        job.write_text(json.dumps(payload))
    result = command([sys.executable, str(executor), str(job)], timeout=180)
    try:
        info = json.loads(result.stdout)
    except ValueError:
        print("DESKTOP_NOT_READY: native Unity runner failed")
        return 3
    if info.get("ok") and info.get("exit_code") == 0:
        print("DESKTOP_READY: noVNC port 6080, private GitHub login required")
        print("LIVE_LINK:", LIVE_URL)
        print("LIVE_LOCAL_TEST: http://127.0.0.1:6080/vnc.html")
        return 0
    print("DESKTOP_NOT_READY:", str(info.get("stderr", "unknown"))[:250])
    return 3


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--install", action="store_true")
    p.add_argument("--desktop-once", action="store_true")
    args = p.parse_args()
    if args.desktop_once:
        raise SystemExit(run_desktop())
    install_sources()
    ensure_vnc_password()
    if not setup_units():
        fallback_shell_hook()
        subprocess.Popen([sys.executable, "-u", str(STAGE / "github_queue_agent.py")],
                         cwd=PROJECT, stdin=subprocess.DEVNULL,
                         stdout=(ROOT / "github-queue.log").open("a"),
                         stderr=subprocess.STDOUT, start_new_session=True)
    # Desktop is started by systemd service when possible; otherwise try once.
    print("LIVE_LINK:", LIVE_URL)
    if not (Path.home() / ".aaris-desktop/vnc.pass").exists():
        print("NEXT: configure VNC password privately in Codespace terminal.")
    else:
        run_desktop()
    print("NOTE: In the Codespace PORTS tab, forward 6080 as PRIVATE (never Public).")
    print("SINGLE_LINK:", LIVE_URL)
    print("Port 6080 must be running AND privately forwarded, otherwise GitHub displays HTTP 404.")
    print("INSTALL_FINISHED: inspect service and port status before claiming live video.")
    doctor = STAGE / "doctor_live.py"
    if doctor.is_file():
        health = command([sys.executable,str(doctor)],timeout=15)
        if health.returncode==0:
            print("LIVE_HEALTH_REPORT:",health.stdout.strip())
        else:
            print("LIVE_HEALTH_REPORT_UNAVAILABLE")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        print("SETUP_BLOCKED:", str(exc), file=sys.stderr)
        raise SystemExit(2)
