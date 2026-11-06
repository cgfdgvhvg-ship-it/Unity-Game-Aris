#!/usr/bin/env python3
"""Install the exact official Unity Linux Editor into disposable /tmp on one Codespace.

All writes are confined to /tmp/aaris-unity-editor and a small persistent
status/log under /workspaces/.aaris-world-bridge/ondemand. No Unity map,
Library, Git checkout, Git LFS or account credentials are modified.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

VERSION = "6000.3.26f1"
CHANGESET = "de8167e7440c"
URL = ("https://download.unity3d.com/download_unity/" + CHANGESET +
       "/LinuxEditorInstaller/Unity-" + VERSION + ".tar.xz")
ROOT = Path("/tmp/aaris-unity-editor")
TARGET = ROOT / VERSION
EXE = TARGET / "Editor/Unity"
ARCHIVE = ROOT / ("Unity-" + VERSION + ".tar.xz")
STAGE = Path("/workspaces/.aaris-world-bridge/ondemand")
STATE = STAGE / "unity-tmp-install-status.json"
LOG = STAGE / "unity-tmp-install.log"
LOCK = STAGE / "unity-tmp-install.lock"
MIN_GIB = 32


def write_state(state: str, **info):
    STAGE.mkdir(parents=True, exist_ok=True)
    payload = {"version": VERSION, "state": state, "timestamp": int(time.time()), **info}
    partial = STAGE / "unity-tmp-install-status.next"
    if partial.is_symlink():
        raise RuntimeError("unsafe installation status path")
    partial.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    partial.chmod(0o600)
    os.replace(partial, STATE)


def status():
    stored = {}
    if STATE.is_file() and not STATE.is_symlink() and STATE.stat().st_size < 8000:
        try:
            stored = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    free = shutil.disk_usage("/tmp").free / (1024**3)
    running = False
    for child in Path("/proc").iterdir():
        if not child.name.isdigit():
            continue
        try:
            raw = (child / "cmdline").read_bytes().decode("utf-8", "replace")
            if "unity_tmp_editor_installer.py" in raw and "--worker" in raw:
                running = True
                break
        except OSError:
            continue
    return {"version": VERSION,
            "editor_path": str(EXE),
            "editor_present": EXE.is_file() and os.access(EXE, os.X_OK),
            "temporary_free_gib": round(free, 2),
            "download_bytes": ARCHIVE.stat().st_size if ARCHIVE.is_file() else 0,
            "installer_running": running,
            "last_state": stored.get("state", "not_started"),
            "last_error": stored.get("error"),
            "temporary_files_lost_on_codespace_stop": True}


def worker():
    STAGE.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as guard:
        fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        if EXE.is_file() and os.access(EXE, os.X_OK):
            write_state("already_installed")
            return
        try:
            if ROOT.is_symlink() or TARGET.is_symlink() or ARCHIVE.is_symlink():
                raise RuntimeError("unsafe symlink under Unity temporary install root")
            if TARGET.exists():
                raise RuntimeError("incomplete editor directory exists; preserve and inspect rather than overwrite")
            if shutil.disk_usage("/tmp").free < MIN_GIB * 1024**3:
                raise RuntimeError("insufficient free temporary storage for Editor plus later Unity map import")
            ROOT.mkdir(parents=True, exist_ok=True)
            write_state("downloading", destination=str(TARGET))
            # Official Unity archive, TLS-verified; curl resumes an interrupted download.
            with LOG.open("a", encoding="utf-8") as log:
                r = subprocess.run(
                    ["curl", "--fail", "--location", "--silent", "--show-error",
                     "--retry", "3", "--retry-delay", "10", "--continue-at", "-",
                     "--output", str(ARCHIVE), URL],
                    stdout=log, stderr=log, timeout=2700, check=False)
            if r.returncode != 0:
                raise RuntimeError("official Unity archive download failed, curl exit " + str(r.returncode))
            if ARCHIVE.stat().st_size < 1024**3 or ARCHIVE.stat().st_size > 8 * 1024**3:
                raise RuntimeError("unexpected Unity archive size")
            write_state("extracting", archive_bytes=ARCHIVE.stat().st_size)
            # Official signed-domain payload; tar cannot elevate archive owners.
            TARGET.mkdir(mode=0o700)
            with LOG.open("a", encoding="utf-8") as log:
                r = subprocess.run(
                    ["tar", "--no-same-owner", "--no-same-permissions",
                     "-xJf", str(ARCHIVE), "-C", str(TARGET)],
                    stdout=log, stderr=log, timeout=2400, check=False)
            if r.returncode != 0 or not EXE.is_file():
                raise RuntimeError("Unity Editor extraction incomplete; tar exit " + str(r.returncode))
            EXE.chmod(EXE.stat().st_mode | 0o100)
            write_state("installed", editor_path=str(EXE))
        except Exception as exc:
            write_state("failed", error=type(exc).__name__ + ": " + str(exc)[:300])


def start():
    if EXE.is_file() and os.access(EXE, os.X_OK):
        return {"status": "already_installed", **status()}
    if status()["installer_running"]:
        return {"status": "already_running", **status()}
    if shutil.disk_usage("/tmp").free < MIN_GIB * 1024**3:
        return {"status":"blocked_low_tmp_storage", **status()}
    STAGE.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--worker"],
            cwd="/tmp", stdin=subprocess.DEVNULL,
            stdout=log, stderr=log, start_new_session=True)
    return {"status": "started", "pid": proc.pid, **status()}



# GUI dependencies are provisioned separately so a failed apt action never
# triggers a destructive /tmp scene recreation or Unity download.
DEPS = ("xvfb", "openbox", "xterm", "x11vnc", "websockify", "novnc", "x11-utils",
        "xdotool", "wmctrl", "xauth")
EXECUTABLES = ("Xvfb", "openbox", "xterm", "x11vnc", "websockify")
DEPS_STATE = STAGE / "unity-desktop-deps-status.json"
DEPS_LOG = STAGE / "unity-desktop-deps.log"
DEPS_LOCK = STAGE / "unity-desktop-deps.lock"


def dependencies_status():
    state = {}
    if DEPS_STATE.is_file() and not DEPS_STATE.is_symlink() and DEPS_STATE.stat().st_size < 3000:
        try:
            state = json.loads(DEPS_STATE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    running = False
    for item in Path("/proc").iterdir():
        if not item.name.isdigit(): continue
        try:
            cmd = (item / "cmdline").read_bytes().decode("utf-8","replace")
            if "unity_tmp_editor_installer.py" in cmd and "--deps-worker" in cmd:
                running = True
                break
        except OSError: pass
    present = {name: bool(shutil.which(name)) for name in EXECUTABLES}
    return {"required_commands": present, "ready": all(present.values()),
            "worker_running": running, "last_state": state.get("state", "not_started"),
            "last_error": state.get("error")}


def dependencies_worker():
    STAGE.mkdir(parents=True, exist_ok=True)
    with DEPS_LOCK.open("a+") as guard:
        fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        if dependencies_status()["ready"]: return
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        env["APT_LISTCHANGES_FRONTEND"] = "none"
        try:
            if not shutil.which("sudo") or not shutil.which("apt-get"):
                raise RuntimeError("Codespace sudo/apt-get missing")
            for kind, cmd, limit in (
                ("apt_update", ["sudo", "-n", "apt-get", "update", "-qq"], 900),
                ("apt_install", ["sudo", "-n", "apt-get", "install", "-y", "-qq",
                                 "--no-install-recommends", *DEPS], 1200),
            ):
                DEPS_STATE.write_text(json.dumps({"state": kind}), encoding="utf-8")
                with DEPS_LOG.open("a", encoding="utf-8") as log:
                    result = subprocess.run(cmd, env=env, cwd="/tmp", stdin=subprocess.DEVNULL,
                                            stdout=log, stderr=log, timeout=limit, check=False)
                if result.returncode != 0:
                    raise RuntimeError(kind + " failed, exit " + str(result.returncode))
            if not dependencies_status()["ready"]:
                raise RuntimeError("GUI dependencies missing after apt install")
            DEPS_STATE.write_text(json.dumps({"state":"installed"}), encoding="utf-8")
        except Exception as exc:
            DEPS_STATE.write_text(json.dumps({"state":"failed",
                         "error":type(exc).__name__ + ": " + str(exc)[:200]}), encoding="utf-8")


def dependencies_start():
    d=dependencies_status()
    if d["ready"]: return {"status":"already_installed", **d}
    if d["worker_running"]: return {"status":"already_running", **d}
    STAGE.mkdir(parents=True, exist_ok=True)
    with DEPS_LOG.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--deps-worker"],
              stdin=subprocess.DEVNULL, cwd="/tmp", stdout=log, stderr=log, start_new_session=True)
    return {"status":"started", "pid":proc.pid, **dependencies_status()}


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        worker()
    elif sys.argv[1:] == ["--status"]:
        print(json.dumps(status(), sort_keys=True))
    elif sys.argv[1:] == ["--start"]:
        print(json.dumps(start(), sort_keys=True))
    elif sys.argv[1:] == ["--deps-start"]:
        print(json.dumps(dependencies_start(), sort_keys=True))
    elif sys.argv[1:] == ["--deps-status"]:
        print(json.dumps(dependencies_status(), sort_keys=True))
    elif sys.argv[1:] == ["--deps-worker"]:
        dependencies_worker()
    else:
        raise SystemExit("Use --start, --status, --deps-start, --deps-status or worker modes")
