#!/usr/bin/env python3
"""Owner-only, read-only terminal-like diagnostics for an ephemeral Actions runner.

Commands are selected from a fixed allowlist. NEVER interpret GitHub issue
comments as shell, Python, paths, URLs or Docker arguments. Public issue replies
must contain only bounded machine facts or fixed classification labels, not
Unity/Hub OAuth logs, tokens, passwords, license bytes or raw process arguments.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

from editor_runtime_diagnostics import ROOT, STATE, LOGS, snapshot

ALLOWED = ("PING", "HELP", "STATUS", "DISK", "PROCESSES",
           "EDITOR", "LICENSE", "ERRORS", "NETWORK", "LFS", "HISTORY", "ALL")
COMMAND = re.compile(r"TERM (PING|HELP|STATUS|DISK|PROCESSES|EDITOR|LICENSE|ERRORS|NETWORK|LFS|HISTORY|ALL)\Z")
TIMELINE = STATE / "terminal-timeline-safe.jsonl"
SCENE = ROOT / "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
SAFE_ERRORS = {
    "CS0103": "Undefined C# name",
    "CS0117": "C# type is missing a member",
    "CS0246": "Missing C# type/namespace or assembly",
    "CS1002": "C# syntax error: semicolon expected",
    "CS1061": "C# object missing member/extension method",
    "CS1503": "C# argument type mismatch",
    "CS1525": "C# invalid expression",
    "CS2001": "C# source file not found",
}
SAFE_EXCEPTIONS = (
    "NullReferenceException", "UnityException", "MissingReferenceException",
    "TypeLoadException", "FileNotFoundException", "OutOfMemoryException",
    "IOException", "InvalidOperationException", "DllNotFoundException",
    "StackOverflowException",
)

def parse(body):
    """Reject arbitrary shell syntax, options, filenames, args and newlines."""
    if not isinstance(body, str) or len(body) > 24:
        raise ValueError("Invalid terminal command")
    match = COMMAND.fullmatch(body.strip())
    if not match:
        raise ValueError("Unknown terminal command; use TERM HELP")
    return match.group(1)

def read_tail(path, limit=1_000_000):
    """Keep log text private; caller may extract ONLY fixed identifiers."""
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - limit))
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""

def errors():
    outputs = {}
    for name in ("live-unity.log", "unity-initial-activation.log", "unity-activate-retry.log"):
        source = read_tail(LOGS / name)
        if not source:
            continue
        codes = sorted(set(re.findall(r"\berror\s+(CS\d{4})\b", source, re.I)))[:15]
        kinds = [item for item in SAFE_EXCEPTIONS if item in source]
        outputs[name] = {
            "compiler_codes": codes,
            "compiler_explanations": {c: SAFE_ERRORS[c] for c in codes if c in SAFE_ERRORS},
            "exception_classes": kinds[:10],
        }
    return outputs

def disk():
    disks = {}
    for label, path in (("workspace", ROOT), ("tmp", Path("/tmp")), ("root", Path("/"))):
        try:
            space = shutil.disk_usage(path)
            disks[label] = {"total_gb": round(space.total / 2**30, 2),
                            "free_gb": round(space.free / 2**30, 2)}
        except OSError:
            disks[label] = {"available": False}
    return {"disks": disks, "cpu_logical": os.cpu_count()}

def memory():
    limit = Path("/sys/fs/cgroup/memory.max")
    usage = Path("/sys/fs/cgroup/memory.current")
    try:
        total = limit.read_text().strip()
        used = usage.read_text().strip()
        if total.isdigit() and used.isdigit():
            return {"limit_gb": round(int(total) / 2**30, 2),
                    "used_gb": round(int(used) / 2**30, 2)}
    except OSError:
        pass
    try:
        info = Path("/proc/meminfo").read_text()
        vals = dict((name, int(value)) for name, value in
                    re.findall(r"^(MemTotal|MemAvailable):\s+(\d+)\s+kB", info, re.M))
        return {"total_gb": round(vals["MemTotal"] / 2**20, 2),
                "available_gb": round(vals["MemAvailable"] / 2**20, 2)}
    except (OSError, KeyError, ValueError):
        return {"available": False}

def processes(info):
    allowed_names = {"Unity": "unity_editor", "python3": "python_workers",
                     "nginx": "nginx", "Xvfb": "virtual_screen",
                     "x11vnc": "vnc_server", "websockify": "vnc_proxy",
                     "cloudflared": "cloudflare_tunnel", "openbox": "window_manager",
                     "dockerd": "docker_service"}
    counts = Counter()
    try:
        proc = subprocess.run(["ps", "-eo", "comm="], text=True, capture_output=True,
                              timeout=5, check=False)
        if proc.returncode == 0:
            for raw in proc.stdout.splitlines():
                label = allowed_names.get(raw.strip())
                if label:
                    counts[label] += 1
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"known_process_counts": dict(sorted(counts.items())),
            "docker_running": info["unity_container_running"],
            "unity_editor_process_in_container": info["editor_process_detected"],
            "editor_exited": info["editor_exit_recorded"],
            "editor_exit_code": info["editor_exit_code"],
            "docker_oom_killed": info["unity_container_oom_killed"]}

def network():
    ports = {"local_api": 8765, "nginx_proxy": 8080, "web_vnc": 6080, "vnc_backend": 5900}
    results = {}
    for name, port in ports.items():
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                results[name] = True
        except (OSError, TimeoutError):
            results[name] = False
    return {"local_services_reachable": results,
            "cloudflare_url_created": Path("/tmp/aaris-tunnel-url").is_file()}

def lfs():
    try:
        with SCENE.open("rb") as handle:
            head = handle.read(110)
        native = b"git-lfs.github.com/spec" not in head
        scene_bytes = SCENE.stat().st_size
    except OSError:
        native = False
        scene_bytes = 0
    try:
        proc = subprocess.run(["git", "lfs", "ls-files", "--name-only"],
                              cwd=ROOT, capture_output=True, text=True,
                              timeout=15, check=False)
        tracked = len(proc.stdout.splitlines()) if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        tracked = None
    return {"native_scene_file_exists": SCENE.is_file(),
            "scene_lfs_pointer_hydrated": native if scene_bytes else False,
            "scene_bytes": scene_bytes,
            "tracked_lfs_file_count": tracked}

def history():
    try:
        lines = TIMELINE.read_text(encoding="utf-8").splitlines()[-8:]
        result = []
        for line in lines:
            entry = json.loads(line)
            if isinstance(entry, dict):
                result.append({k: entry[k] for k in ("time", "stage", "docker",
                    "editor", "photo", "free_gb") if k in entry})
        return result
    except (OSError, UnicodeError, ValueError, TypeError):
        return []

def license(info):
    return {"stage": info["stage"],
            "failure_code": info["license_failure_code"],
            "editor_start_recorded": info["editor_start_recorded"],
            "editor_exit_recorded": info["editor_exit_recorded"],
            "editor_exit_code": info["editor_exit_code"],
            "unity_editor_responding": info["unity_editor_confirmed"],
            "next_step": ("Protected /api/license shows the private Unity sign-in"
                          " if activation is waiting; never post OAuth URL publicly.")}

def editor(info):
    keys = ("stage", "license_failure_code", "unity_container_running", "editor_process_detected",
            "editor_start_recorded", "editor_exit_recorded", "editor_exit_code",
            "editor_heartbeat_recent", "editor_heartbeat_age_sec",
            "editor_graphics_backend", "unity_editor_confirmed",
            "native_scene_open", "real_camera_photo_confirmed",
            "last_world_command_success", "unity_container_oom_killed")
    return {k: info[k] for k in keys}

def execute(op):
    """All commands are bounded read-only inquiries; no arbitrary subprocess args."""
    if op not in ALLOWED:
        raise ValueError("Invalid terminal command")
    if op == "HELP":
        return {"commands": ["TERM " + s for s in ALLOWED],
                "editor_retry": "ACTIVATE_UNITY (owner only, separate command)",
                "camera_test": "CAMERA -420 22 -210 0 20 22",
                "note": "No arbitrary shell, script execution, paths, or secrets."}
    if op == "PING":
        return {"responding": True}
    info = snapshot()
    if op == "STATUS":
        return {"editor": editor(info), "disk_free_gb": info["free_disk_gb"],
                "error_categories": {name: details.get("error_categories", {})
                                    for name, details in info["logs"].items()}}
    if op == "EDITOR":
        return editor(info)
    if op == "LICENSE":
        return license(info)
    if op == "ERRORS":
        return {"categories": info["logs"], "identifiers": errors()}
    if op == "DISK":
        return {"storage": disk(), "memory": memory()}
    if op == "PROCESSES":
        return processes(info)
    if op == "NETWORK":
        return network()
    if op == "LFS":
        return lfs()
    if op == "HISTORY":
        return {"recent": history()}
    if op == "ALL":
        return {"editor": editor(info), "storage": disk(), "memory": memory(),
                "processes": processes(info), "network": network(),
                "lfs": lfs(), "errors": errors(), "recent": history()}
    raise ValueError("Unsupported terminal command")

def safe_reply(op):
    """JSON within the issue comment size budget; no login URLs or raw logs."""
    value = {"schema": 1, "run_id": os.environ.get("GITHUB_RUN_ID", "")
             if os.environ.get("GITHUB_RUN_ID", "").isdigit() else "",
             "command": "TERM " + op, "result": execute(op)}
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)[:8500]

def monitor(seconds, interval=30):
    STATE.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(1, min(seconds, 18000))
    while time.monotonic() < deadline:
        info = snapshot()
        item = {"time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "stage": info["stage"], "docker": info["unity_container_running"],
                "editor": info["unity_editor_confirmed"],
                "photo": info["real_camera_photo_confirmed"],
                "free_gb": info["free_disk_gb"]}
        with TIMELINE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=True, separators=(",", ":")) + "\n")
        time.sleep(max(5, interval))

def selftest():
    assert parse("TERM STATUS") == "STATUS"
    assert parse("TERM ALL") == "ALL"
    for unsafe in ("TERM cat /etc/passwd", "TERM DISK; rm -rf /", "TERM STATUS\nSHELL echo", 
                   "TERM STATUS --path=/", "TERM UNKNOWN", "TERM LOGS", "TERM"):
        try:
            parse(unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe terminal command was accepted")
    assert execute("HELP")["commands"][0] == "TERM PING"
    assert "private_token_here" not in safe_reply("HELP")
    assert "private_token_here" not in json.dumps(errors())
    print("Owner-only fixed-command terminal and safe outputs: PASS")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--seconds", type=int, default=900)
    args = parser.parse_args()
    if args.selftest:
        selftest()
    elif args.monitor:
        monitor(args.seconds)
    else:
        print(safe_reply("ALL"))
