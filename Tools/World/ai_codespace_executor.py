#!/usr/bin/env python3
"""Runs one owner-approved Actions job inside the existing dirty Codespace.

No repo checkout or git cleanup. Never access secrets or publish credentials.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

PROJECT = Path("/workspaces/Unity-Game-Aris")
EDITOR = Path("/home/codespace/Unity/Hub/Editor/6000.3.26f1/Editor/Unity")
DESKTOP = Path("/home/codespace/.aaris-desktop")


def run(cmd, timeout=45, env=None):
    try:
        p = subprocess.run(cmd, cwd=PROJECT, timeout=timeout, text=True,
                           capture_output=True, env=env, stdin=subprocess.DEVNULL)
        return {"exit_code": p.returncode, "stdout": p.stdout[-9000:], "stderr": p.stderr[-3000:]}
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "stdout": "", "stderr": "TIMEOUT"}
    except OSError as exc:
        return {"exit_code": 127, "stdout": "", "stderr": str(exc)}


def execute(job):
    # Validate independently from Actions, where an untrusted queue file travels.
    if set(job) != {"id", "operation", "args"}:
        raise ValueError("invalid job shape")
    ident, op, args = job["id"], job["operation"], job["args"]
    if not isinstance(ident, str) or not (4 <= len(ident) <= 56) or not ident.replace("-", "").isalnum():
        raise ValueError("invalid job id")
    if not isinstance(args, list):
        raise ValueError("invalid args")
    if op == "diagnose":
        if args: raise ValueError("unexpected args")
        free = shutil.disk_usage(PROJECT).free
        result = {
            "unity_editor_present": EDITOR.is_file(),
            "unity_editor_executable": os.access(EDITOR, os.X_OK),
            "free_disk_gib": round(free / 2**30, 3),
            "display_12_present": Path("/tmp/.X11-unix/X12").exists(),
            "xterm_executable": shutil.which("xterm"),
            "gui_processes": [name for name in run(["ps", "-eo", "comm="], timeout=5)["stdout"].splitlines()
                              if name.lower() in {"xvfb", "x11vnc", "websockify", "openbox", "xterm", "unity"}],
            "git_status": run(["git", "status", "--short"], timeout=15),
        }
        return {"exit_code": 0, "stdout": json.dumps(result, ensure_ascii=False), "stderr": ""}
    if op == "desktop_xterm":
        if args: raise ValueError("unexpected args")
        if not Path("/tmp/.X11-unix/X12").exists():
            return {"exit_code": 3, "stdout": "", "stderr": "X display :12 is missing"}
        if not shutil.which("xterm"):
            return {"exit_code": 3, "stdout": "", "stderr": "xterm is not installed"}
        DESKTOP.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy(); env["DISPLAY"] = ":12"
        output = (DESKTOP / "ai-xterm.log").open("a", encoding="utf-8")
        try:
            subprocess.Popen(["xterm", "-title", "Aaris Unity Desktop", "-geometry", "105x35+80+80"],
                             env=env, stdout=output, stderr=output, stdin=subprocess.DEVNULL,
                             start_new_session=True, cwd=PROJECT)
        finally:
            output.close()
        time.sleep(2)
        process = run(["pgrep", "-u", str(os.getuid()), "-x", "xterm"], timeout=5)
        return {"exit_code": process["exit_code"],
                "stdout": "XTERM_WINDOW_OPENED" if process["exit_code"] == 0 else "",
                "stderr": "" if process["exit_code"] == 0 else "xterm exited: inspect ~/.aaris-desktop/ai-xterm.log"}
    if op == "unity_version":
        if args: raise ValueError("unexpected args")
        if not EDITOR.is_file():
            return {"exit_code": 3, "stdout": "", "stderr": "Unity Editor missing"}
        return run([str(EDITOR), "-version"], timeout=90)
    if op == "world_doctor":
        if args: raise ValueError("unexpected args")
        path = PROJECT / "Tools/World/ai_world_observe.py"
        if not path.is_file():
            return {"exit_code": 3, "stdout": "", "stderr": "World observer not present"}
        python = Path("/workspaces/.aaris-world-bridge/venv/bin/python")
        return run([str(python) if python.is_file() else "python3", str(path), "doctor"], timeout=90)
    if op == "terminal_readonly":
        if not isinstance(args, list) or not 1 <= len(args) <= 16 or not all(isinstance(a, str) and 0 < len(a) < 500 for a in args):
            raise ValueError("invalid terminal arguments")
        if args[0] not in {"pwd", "df", "free", "ps", "stat", "ls", "du", "glxinfo", "pgrep"}:
            raise ValueError("unsupported terminal program")
        if any(x in {";", "&&", "|", ">", "<", "`", "$("} for x in args[1:]):
            raise ValueError("shell syntax rejected")
        if any(a.startswith("-") and ("exec" in a or "delete" in a) for a in args[1:]):
            raise ValueError("option rejected")
        if any(a.startswith("/") and not (a.startswith("/workspaces/") or a.startswith("/home/codespace/")) for a in args[1:]):
            raise ValueError("unapproved path")
        return run(args, timeout=40)
    raise ValueError("unknown operation")


def main():
    if len(sys.argv) != 2: raise SystemExit("usage: ai_codespace_executor.py job.json")
    f = Path(sys.argv[1]).resolve()
    allowed = Path("/workspaces/.aaris-world-bridge/ondemand").resolve()
    if f.parent != allowed or not f.name.endswith(".json") or not f.is_file() or f.is_symlink():
        raise SystemExit("job path denied")
    job = json.loads(f.read_text(encoding="utf-8"))
    try:
        data = execute(job)
        result = {"id": job["id"], "operation": job["operation"], "ok": data["exit_code"] == 0, **data}
    except Exception as exc:
        result = {"id": job.get("id"), "operation": job.get("operation"), "ok": False, "exit_code": 1, "stdout": "", "stderr": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())