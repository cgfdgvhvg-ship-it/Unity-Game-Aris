#!/usr/bin/env python3
"""Runs one owner-approved Actions job inside the existing dirty Codespace.

No repo checkout or git cleanup. Never access secrets or publish credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
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



def _port_ready(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _wait_ready(ready, attempts=65):
    # Heavy Xvfb/x11vnc startup can exceed 8 seconds on a resumed Codespace.
    # Poll a bounded ~26 seconds, rather than reporting a false service failure.
    for _ in range(attempts):
        if ready():
            return True
        time.sleep(0.4)
    return False


def _spawn_desktop(command, logname, *, env=None):
    DESKTOP.mkdir(parents=True, exist_ok=True)
    with (DESKTOP / logname).open("a", encoding="utf-8") as output:
        subprocess.Popen(command, cwd=PROJECT, env=env, stdin=subprocess.DEVNULL,
                         stdout=output, stderr=output, start_new_session=True)


def _process_running(name):
    return run(["pgrep", "-u", str(os.getuid()), "-x", name], timeout=5)["exit_code"] == 0


def ensure_desktop():
    """Revive trusted GUI processes after Codespace auto-start, without touching assets."""
    required = ("Xvfb", "openbox", "x11vnc", "websockify", "xterm")
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        return "Missing GUI packages: " + ", ".join(missing)
    password = DESKTOP / "vnc.pass"
    if not password.is_file() or password.is_symlink() or password.stat().st_size == 0:
        return "Existing VNC password missing; refusing to start unprotected VNC"
    DESKTOP.mkdir(parents=True, exist_ok=True)
    DESKTOP.chmod(0o700)
    password.chmod(0o600)
    env = os.environ.copy()
    env["DISPLAY"] = ":12"
    display_socket = Path("/tmp/.X11-unix/X12")
    if not display_socket.exists():
        _spawn_desktop(["Xvfb", ":12", "-screen", "0", "1600x900x24",
                        "-nolisten", "tcp", "-noreset"], "xvfb.log")
    if not _wait_ready(display_socket.exists):
        return "Xvfb :12 did not start; inspect ~/.aaris-desktop/xvfb.log"
    if not _process_running("openbox"):
        _spawn_desktop(["openbox"], "openbox.log", env=env)
        if not _wait_ready(lambda: _process_running("openbox")):
            return "Openbox did not start; inspect ~/.aaris-desktop/openbox.log"
    if not _port_ready(5900):
        _spawn_desktop(["x11vnc", "-display", ":12", "-rfbauth", str(password),
                        "-rfbport", "5900", "-localhost", "-forever", "-shared"],
                       "vnc.log")
        if not _wait_ready(lambda: _port_ready(5900)):
            return "x11vnc did not listen on localhost:5900; inspect ~/.aaris-desktop/vnc.log"
    if not _port_ready(6080):
        _spawn_desktop(["websockify", "--web=/usr/share/novnc", "0.0.0.0:6080",
                        "127.0.0.1:5900"], "novnc.log")
        if not _wait_ready(lambda: _port_ready(6080)):
            return "noVNC did not listen on port 6080; inspect ~/.aaris-desktop/novnc.log"
    return None



def _du_bytes(path):
    if not path.exists():
        return 0
    value = run(["du", "-sb", str(path)], timeout=30)
    if value["exit_code"] != 0:
        return None
    try:
        return int(value["stdout"].split()[0])
    except (ValueError, IndexError):
        return None


def _lfs_inventory():
    """Compare original LFS OIDs with clean checked-out asset bytes.

    Read-only and dirty-aware. Modified core geometry is NEVER hashed as if
    it were unchanged; dirty paths are separately protected and reported.
    """
    cmd = subprocess.run(["git", "lfs", "ls-files", "--long"],
                         cwd=PROJECT, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, timeout=45, check=False)
    if cmd.returncode:
        return {"error": "git lfs ls-files --long failed",
                "detail": cmd.stderr.decode("utf-8", "replace")[-400:]}
    # Output: '<64 hex OID> * Assets/...'; - means not checked out.
    import re
    records = []
    for line in cmd.stdout.decode("utf-8", "surrogateescape").splitlines():
        match = re.match(r"^([0-9a-f]{64})\s+[*-]\s+(.+)$", line)
        if match:
            records.append((match.group(2), match.group(1)))
    # Fail closed: do not mistake a CLI output-format change for zero LFS.
    if not records and cmd.stdout.strip():
        return {"error": "unrecognized git lfs ls-files --long format",
                "sample": cmd.stdout[:100].decode("utf-8", "replace")}
    tracked = subprocess.run(["git", "diff", "--name-only", "-z", "HEAD", "--"],
                             cwd=PROJECT, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=35, check=False)
    if tracked.returncode:
        return {"error": "could not list dirty tracked paths"}
    dirty = set(x.decode("utf-8", "surrogateescape") for x in tracked.stdout.split(b"\0") if x)
    result = {"checked_sha256": 0, "hash_matches": 0, "hash_mismatch": 0,
              "lfs_pointer": 0, "file_missing": 0,
              "dirty_protected": 0, "unreadable": 0}
    suffixes = {}
    samples = {"lfs_pointer":[], "file_missing":[], "dirty_protected":[],
               "hash_mismatch":[]}
    checked_bytes = 0
    existing_bytes = 0
    for name, expected in records:
        if not name.startswith("Assets/") or ".." in Path(name).parts:
            continue
        target = PROJECT / name
        suffix = target.suffix.lower()
        suffixes[suffix] = suffixes.get(suffix, 0) + 1
        if name in dirty:
            result["dirty_protected"] += 1
            if len(samples["dirty_protected"]) < 10: samples["dirty_protected"].append(name)
            continue
        if not target.is_file() or target.is_symlink():
            kind = "file_missing"
        else:
            try:
                size = target.stat().st_size
                existing_bytes += size
                with target.open("rb") as stream:
                    pointer = stream.read(100).startswith(b"version https://git-lfs.github.com/spec/v1")
                if pointer:
                    kind = "lfs_pointer"
                else:
                    digest = hashlib.sha256()
                    with target.open("rb") as stream:
                        for part in iter(lambda: stream.read(1024*1024), b""):
                            digest.update(part)
                    checked_bytes += size
                    result["checked_sha256"] += 1
                    if digest.hexdigest() == expected:
                        result["hash_matches"] += 1
                    else:
                        result["hash_mismatch"] += 1
                        if len(samples["hash_mismatch"]) < 10: samples["hash_mismatch"].append(name)
                    continue
            except OSError:
                kind = "unreadable"
        result[kind] += 1
        if kind in samples and len(samples[kind]) < 10:
            samples[kind].append(name)
    return {"all_lfs_paths":len(records), "lfs_assets":sum(suffixes.values()),
            "lfs_status": result, "checked_bytes":checked_bytes,
            "present_lfs_bytes_excluding_dirty":existing_bytes,
            "file_extensions":dict(sorted(suffixes.items(),key=lambda x:-x[1])[:20]),
            "examples":samples, "protected_dirty_tracked_count":len(dirty),
            "git_status":run(["git","status","--short","--untracked-files=all"],timeout=30)}

def storage_audit():
    home=Path("/home/codespace")
    parts=[PROJECT/"Library", PROJECT/"Temp",PROJECT/".git",PROJECT/"Assets",
           home/".cache",home/".cache"/"pip",home/".cache"/"uv",
           home/".npm"/"_cacache",home/".local",home/"Unity",
           Path("/tmp"),Path("/var/cache/apt/archives")]
    sizes={str(p):_du_bytes(p) for p in parts}
    disk=shutil.disk_usage(PROJECT)
    inventory=_lfs_inventory()
    return {"free_disk_gib":round(disk.free/2**30,3),
            "total_disk_gib":round(disk.total/2**30,3),
            "disk_directory_bytes":sizes,
            "lfs_inventory":inventory}

def execute(job):
    # Validate independently from Actions, where an untrusted queue file travels.
    if set(job) != {"id", "operation", "args"}:
        raise ValueError("invalid job shape")
    ident, op, args = job["id"], job["operation"], job["args"]
    if not isinstance(ident, str) or not (4 <= len(ident) <= 56) or not ident.replace("-", "").isalnum():
        raise ValueError("invalid job id")
    if not isinstance(args, list):
        raise ValueError("invalid args")
    if op == "storage_audit":
        if args: raise ValueError("unexpected args")
        return {"exit_code":0,"stdout":json.dumps(storage_audit(),ensure_ascii=False),"stderr":""}
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
    if op == "desktop_diagnose":
        if args: raise ValueError("unexpected args")
        logs = {}
        for name in ("xvfb.log", "openbox.log", "vnc.log", "novnc.log", "ai-xterm.log"):
            logfile = DESKTOP / name
            if logfile.is_file() and not logfile.is_symlink():
                excerpt = logfile.read_text(encoding="utf-8", errors="replace")[-1800:]
                excerpt = re.sub(r"(?i)\b(?:ghp_|ghu_|gho_|ghs_|ghr_|github_pat_|sk-)[A-Za-z0-9_-]{8,}",
                                 "[REDACTED]", excerpt)
                logs[name] = excerpt
            else:
                logs[name] = "MISSING"
        status = {"display_socket": Path("/tmp/.X11-unix/X12").exists(),
                  "vnc_local_5900": _port_ready(5900),
                  "novnc_6080": _port_ready(6080),
                  "xvfb_process": _process_running("Xvfb"),
                  "openbox_process": _process_running("openbox"),
                  "x11vnc_process": _process_running("x11vnc"),
                  "websockify_process": _process_running("websockify"),
                  "saved_vnc_password_exists": (DESKTOP/"vnc.pass").is_file(),
                  "logs": logs}
        return {"exit_code": 0, "stdout": json.dumps(status, ensure_ascii=False), "stderr": ""}
    if op == "desktop_xterm":
        if args: raise ValueError("unexpected args")
        error = ensure_desktop()
        if error:
            return {"exit_code": 3, "stdout": "", "stderr": error}
        env = os.environ.copy()
        env["DISPLAY"] = ":12"
        if not _process_running("xterm"):
            _spawn_desktop(["xterm", "-title", "Aaris Unity Desktop",
                            "-geometry", "105x35+80+80"], "ai-xterm.log", env=env)
        if not _wait_ready(lambda: _process_running("xterm")):
            return {"exit_code": 3, "stdout": "", "stderr": "xterm not running; inspect ~/.aaris-desktop/ai-xterm.log"}
        state = {"display_12": True, "vnc_local_5900": _port_ready(5900),
                 "novnc_6080": _port_ready(6080), "xterm_running": True}
        return {"exit_code": 0, "stdout": json.dumps(state), "stderr": ""}
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