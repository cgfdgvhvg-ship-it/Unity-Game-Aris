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
import signal
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
              "dirty_protected": 0, "unreadable": 0, "hash_deferred": 0}
    suffixes = {}
    samples = {"lfs_pointer":[], "file_missing":[], "dirty_protected":[],
               "hash_mismatch":[]}
    checked_bytes = 0
    existing_bytes = 0
    skipped_hash_bytes = 0
    hash_budget_bytes = 128 * 1024 * 1024
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
                    # Exact SHA check in a bounded sample, not the entire
                    # multi-GB Unity project in one SSH call.
                    if checked_bytes + size > hash_budget_bytes:
                        result["hash_deferred"] += 1
                        skipped_hash_bytes += size
                        continue
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
            "hash_budget_bytes":hash_budget_bytes,
            "hash_deferred_bytes":skipped_hash_bytes,
            "present_lfs_bytes_excluding_dirty":existing_bytes,
            "file_extensions":dict(sorted(suffixes.items(),key=lambda x:-x[1])[:20]),
            "examples":samples, "protected_dirty_tracked_count":len(dirty),
            "git_status":run(["git","status","--short","--untracked-files=all"],timeout=30)}

def lfs_verify_chunk(cursor):
    """One bounded, strictly read-only verification of LFS checkout bytes.

    Each run reports the next cursor and keeps all dirty core assets intact.
    Multiple queued jobs can cover the complete 764-file checkout.
    """
    import re
    if not isinstance(cursor, int) or cursor < 0 or cursor > 20000:
        raise ValueError("invalid LFS cursor")
    command = subprocess.run(["git", "lfs", "ls-files", "--long"],
                             cwd=PROJECT, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=45, check=False)
    if command.returncode:
        raise ValueError("cannot enumerate LFS files: " + command.stderr.decode("utf-8", "replace")[-250:])
    records = []
    for line in command.stdout.decode("utf-8", "surrogateescape").splitlines():
        found = re.fullmatch(r"([0-9a-f]{64})\s+[*-]\s+(.+)", line)
        if not found:
            raise ValueError("unrecognized LFS entry format")
        if found.group(2).startswith("Assets/"):
            records.append((found.group(2), found.group(1)))
    if not records or cursor > len(records):
        raise ValueError("no LFS entries or invalid cursor")
    modified = subprocess.run(["git", "diff", "--name-only", "-z", "HEAD", "--"],
                              cwd=PROJECT, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=30, check=False)
    if modified.returncode:
        raise ValueError("cannot enumerate protected changed files")
    protected = {x.decode("utf-8", "surrogateescape")
                 for x in modified.stdout.split(b"\0") if x}
    head = run(["git", "rev-parse", "HEAD"], timeout=10)
    if head["exit_code"]:
        raise ValueError("cannot read Git HEAD")
    max_bytes = 480 * 1024 * 1024
    max_items = 145
    max_elapsed = 75
    deadline = time.monotonic() + max_elapsed
    count = dict(hash_matches=0, hash_mismatch=0, dirty_protected=0,
                 pointer=0, missing=0, unreadable=0, changed_during_check=0,
                 large_deferred=0)
    samples = {"hash_mismatch": [], "dirty_protected": [], "pointer": [],
               "missing": [], "large_deferred": []}
    i = cursor
    read_bytes = 0
    while i < len(records):
        if i > cursor and (i-cursor >= max_items or
                           read_bytes >= max_bytes or time.monotonic() >= deadline):
            break
        name, oid = records[i]
        target = PROJECT / name
        if ".." in Path(name).parts:
            raise ValueError("invalid LFS path")
        category = None
        if name in protected:
            category = "dirty_protected"
        elif target.is_symlink() or not target.is_file():
            category = "missing"
        else:
            try:
                stat_before = target.stat()
                with target.open("rb") as stream:
                    is_pointer = stream.read(100).startswith(
                        b"version https://git-lfs.github.com/spec/v1")
                if is_pointer:
                    category = "pointer"
                elif stat_before.st_size > 1024 * 1024 * 1024:
                    category = "large_deferred"
                elif read_bytes + stat_before.st_size > max_bytes and i > cursor:
                    # Do not consume this file; resume at the same index next job.
                    break
                else:
                    checksum = hashlib.sha256()
                    with target.open("rb") as stream:
                        for part in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                            checksum.update(part)
                    stat_after = target.stat()
                    read_bytes += stat_before.st_size
                    if (stat_before.st_size != stat_after.st_size or
                            stat_before.st_mtime_ns != stat_after.st_mtime_ns):
                        category = "changed_during_check"
                    elif checksum.hexdigest() == oid:
                        category = "hash_matches"
                    else:
                        category = "hash_mismatch"
            except OSError:
                category = "unreadable"
        count[category] += 1
        if category in samples and len(samples[category]) < 6:
            samples[category].append(name)
        i += 1
    return {"head_sha": head["stdout"].strip(), "cursor": cursor,
            "next_cursor": i, "total": len(records),
            "processed": i-cursor, "hash_checked_bytes": read_bytes,
            "all_done": i == len(records), "categories": count, "examples": samples}


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

def prune_caches(home=Path("/home/codespace")):
    """Delete only two named re-downloadable caches, never project or Unity."""
    paths=[home/".cache"/"copilot"/"pkg", home/".npm"/"_cacache"]
    initial=shutil.disk_usage(PROJECT).free
    git_before=run(["git","status","--porcelain","--untracked-files=all"],timeout=20)
    if git_before["exit_code"] != 0:
        raise ValueError("cannot verify git status before cleanup")
    removed={}
    for target in paths:
        # Don't follow symlinks or remove anything other than an exact cache root.
        if target.is_symlink() or target.parent.is_symlink() or not target.is_dir():
            removed[str(target)]="not_present_or_unsafe"
            continue
        if not target.resolve().is_relative_to(home.resolve()):
            raise ValueError("cache path escapes home directory")
        estimate=_du_bytes(target)
        shutil.rmtree(target)
        removed[str(target)]=estimate
    git_after=run(["git","status","--porcelain","--untracked-files=all"],timeout=20)
    if git_before["stdout"] != git_after["stdout"] or git_after["exit_code"] != 0:
        raise ValueError("git status changed unexpectedly; stop")
    final=shutil.disk_usage(PROJECT).free
    return {"deleted_only_allowlisted_cache_paths":removed,
            "free_disk_gib_before":round(initial/2**30,3),
            "free_disk_gib_after":round(final/2**30,3),
            "recovered_mib":round((final-initial)/2**20,1),
            "git_worktree_unchanged":True}



def _install_live_bridge():
    """Install only new reviewed files; fail closed on any existing content mismatch."""
    stage=Path("/workspaces/.aaris-world-bridge/ondemand")
    dest=PROJECT/"Assets/AarisWorld/Editor"
    names=("AarisLiveEditorBridge.cs","AarisLiveEditorBridge.cs.meta")
    dest.mkdir(parents=True,exist_ok=True)
    installed=[]
    for leaf in names:
        src=stage/leaf
        target=dest/leaf
        if not src.is_file() or src.is_symlink() or src.stat().st_size>100000:
            raise ValueError("Reviewed Unity bridge source not staged")
        if target.is_symlink():
            raise ValueError("Refusing to overwrite symlinked Unity source")
        expected=hashlib.sha256(src.read_bytes()).hexdigest()
        if target.exists():
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
                raise ValueError("Existing locally changed Unity bridge: never overwrite "+leaf)
        else:
            tmp=dest/(leaf+".aaris-new")
            if tmp.exists(): raise ValueError("Stale staging file needs review")
            tmp.write_bytes(src.read_bytes())
            os.replace(tmp,target)
            installed.append(leaf)
    return installed


def _monitor_unity(pid):
    """Emergency protection for low-capacity Codespaces. Never delete Library/Assets."""
    note=DESKTOP/"unity-storage-watchdog.log"
    while True:
        path=Path("/proc")/str(pid)/"cmdline"
        try:
            argv=path.read_bytes().replace(b"\0",b" ").decode("utf-8","replace")
        except OSError:
            break
        if not argv.startswith(str(EDITOR)+" ") or "-projectPath "+str(PROJECT) not in argv:
            break
        free=shutil.disk_usage(PROJECT).free
        if free < 1024**3:
            with note.open("a") as file:
                file.write("Low disk below 1 GiB: requesting safe Unity process shutdown; Library retained\n")
            try:
                os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
            break
        time.sleep(10)

def _unity_pids():
    """Match actual argv via /proc; never mistake process table snippets for Unity."""
    found=[]
    proc=Path("/proc")
    try:
        entries=list(proc.iterdir())
    except OSError:
        return found
    for entry in entries:
        if not entry.name.isdigit(): continue
        try:
            raw=(entry/"cmdline").read_bytes()
            argv=[p.decode("utf-8","replace") for p in raw.split(b"\0") if p]
        except (OSError,PermissionError):
            continue
        if len(argv)>=3 and argv[0]==str(EDITOR):
            try:
                i=argv.index("-projectPath")
            except ValueError:
                continue
            if i+1<len(argv) and argv[i+1]==str(PROJECT):
                found.append(int(entry.name))
    return sorted(found)


def _unity_log_tail():
    logfile=DESKTOP/"unity-editor.log"
    if logfile.is_file() and not logfile.is_symlink():
        with logfile.open("rb") as f:
            f.seek(max(0, logfile.stat().st_size-3000))
            raw=f.read().decode("utf-8","replace")
        return re.sub(r"(?i)\b(?:ghp_|ghu_|gho_|ghs_|ghr_|github_pat_|sk-)[A-Za-z0-9_-]{8,}",
                      "[REDACTED]",raw)[-2200:]
    return "Unity log does not exist"


def _unity_gui_status():
    free=shutil.disk_usage(PROJECT).free
    lib=PROJECT/"Library"
    return {
        "editor_version":"6000.3.26f1",
        "editor_present":EDITOR.is_file() and os.access(EDITOR,os.X_OK),
        "project_version_present":(PROJECT/"ProjectSettings/ProjectVersion.txt").is_file(),
        "map_scene_present":(PROJECT/"Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity").is_file(),
        "pid":_unity_pids(),
        "display_12":Path("/tmp/.X11-unix/X12").exists(),
        "novnc_6080":_port_ready(6080),
        "library_exists":lib.is_dir(),
        "library_bytes":_du_bytes(lib),
        "free_disk_gib":round(free/2**30,3),
        "last_log":_unity_log_tail(),
    }


def ensure_unity_gui(*, launch=True):
    """Resume saved project using existing Library, without checkout or re-import cleanup."""
    status=_unity_gui_status()
    if not launch or status["pid"]:
        return {"exit_code":0,"stdout":json.dumps(status,ensure_ascii=False),"stderr":""}
    if not status["editor_present"] or not status["project_version_present"] or not status["map_scene_present"]:
        return {"exit_code":3,"stdout":json.dumps(status),"stderr":"Unity Editor or saved project missing"}
    if shutil.disk_usage(PROJECT).free < 3*1024**3:
        return {"exit_code":3,"stdout":json.dumps(status),"stderr":"Less than 3 GiB available; refusing unsafe first import"}
    error=ensure_desktop()
    if error:
        return {"exit_code":3,"stdout":json.dumps(status),"stderr":error}
    import fcntl
    DESKTOP.mkdir(parents=True,exist_ok=True)
    DESKTOP.chmod(0o700)
    lock=DESKTOP/"unity-launch.lock"
    with lock.open("a+") as lockfile:
        fcntl.flock(lockfile.fileno(),fcntl.LOCK_EX)
        if not _unity_pids():
            installed=_install_live_bridge()
            env=os.environ.copy()
            env["DISPLAY"]=":12"
            env.setdefault("XDG_RUNTIME_DIR",str(DESKTOP/"runtime"))
            runtime=Path(env["XDG_RUNTIME_DIR"])
            runtime.mkdir(parents=True,exist_ok=True)
            runtime.chmod(0o700)
            args=[str(EDITOR),"-projectPath",str(PROJECT),
                  "-logFile",str(DESKTOP/"unity-editor.log"),
                  "-job-worker-count","2"]
            with (DESKTOP/"unity-launch.log").open("a") as output:
                proc=subprocess.Popen(args,cwd=PROJECT,stdin=subprocess.DEVNULL,
                                      stdout=output,stderr=output,env=env,start_new_session=True)
            (DESKTOP/"unity-last-pid.txt").write_text(str(proc.pid)+"\n")
            watchdog=[sys.executable,str(Path(__file__).resolve()),"--unity-watchdog",str(proc.pid)]
            with (DESKTOP/"unity-watchdog-launch.log").open("a") as watcher:
                subprocess.Popen(watchdog, cwd=PROJECT,stdin=subprocess.DEVNULL,
                                 stdout=watcher,stderr=watcher,start_new_session=True)

    # Non-blocking: big first import is checked by later status jobs.
    time.sleep(4)
    info=_unity_gui_status()
    info["launch_attempted"]=True
    if not info["pid"]:
        return {"exit_code":3,"stdout":json.dumps(info),"stderr":"Unity process exited; inspect last_log and unity-launch.log"}
    return {"exit_code":0,"stdout":json.dumps(info,ensure_ascii=False),"stderr":""}



def validate_live_payload(value):
    """Minimal reviewed Unity commands only. No shell, paths or arbitrary code."""
    import math
    if not isinstance(value,dict) or "action" not in value:
        raise ValueError("Unity request must be a JSON object with action")
    action=value["action"]
    allowed={
        "status":set(),
        "inspect":{"target","cameraTarget","radius","limit"},
        "move":{"target","delta"},
        "scale":{"target","scale"},
        "move_tree":{"target","delta","expectedPosition"},
        "capture":{"cameraPosition","cameraTarget"},
    }
    if action not in allowed or set(value)-({"action"}|allowed[action]):
        raise ValueError("unsupported Unity request action or fields")
    for field in ("target",):
        if field in value and (not isinstance(value[field],str) or not (1 <= len(value[field]) <= 210)):
            raise ValueError("invalid target name")
    for field in ("delta","scale","cameraPosition","cameraTarget","expectedPosition"):
        if field not in value: continue
        vec=value[field]
        if not isinstance(vec,dict) or set(vec)!={"x","y","z"} or any(
            not isinstance(n,(int,float)) or isinstance(n,bool) or not math.isfinite(n)
            or abs(n)>20000 for n in vec.values()
        ):
            raise ValueError("invalid vector "+field)
    if action in ("move","scale","move_tree") and not value.get("target"):
        raise ValueError("target required")
    if action in ("move","move_tree") and "delta" not in value:
        raise ValueError("move delta required")
    if action=="scale" and "scale" not in value:
        raise ValueError("scale vector required")
    if action=="move_tree" and "expectedPosition" not in value:
        raise ValueError("expected terrain tree position required")
    if action=="capture" and not {"cameraPosition","cameraTarget"}<=set(value):
        raise ValueError("camera position and target required")
    if action=="inspect" and not value.get("target") and "cameraTarget" not in value:
        raise ValueError("inspect requires target or cameraTarget")
    if "radius" in value and (not isinstance(value["radius"],(int,float)) or
                               not 1<=value["radius"]<=200):
        raise ValueError("radius outside 1..200")
    if "limit" in value and (not isinstance(value["limit"],int) or not 1<=value["limit"]<=80):
        raise ValueError("limit outside 1..80")
    return value


def unity_live_job(job):
    params=validate_live_payload(json.loads(job["args"][0]))
    _install_live_bridge()
    started=ensure_unity_gui()
    if started["exit_code"]:
        return started
    commands=DESKTOP/"unity-commands"
    results=DESKTOP/"unity-results"
    commands.mkdir(parents=True,exist_ok=True)
    results.mkdir(parents=True,exist_ok=True)
    ident=job["id"]
    output=results/(ident+".json")
    command=commands/(ident+".json")
    if not output.is_file():
        payload=dict(params,id=ident)
        if params["action"]=="move_tree":
            payload["hasExpectedPosition"]=True
        if not command.exists():
            temp=commands/(ident+".writing")
            if temp.exists() or command.is_symlink():
                raise ValueError("unsafe Unity command staging")
            temp.write_text(json.dumps(payload,separators=(",",":"),allow_nan=False))
            os.replace(temp,command)
    return _read_unity_result(ident,wait_seconds=30)


def _read_unity_result(ident,*,wait_seconds=0):
    import re
    if not re.fullmatch(r"[a-z][a-z0-9-]{3,55}",ident):
        raise ValueError("invalid Unity result ID")
    file=DESKTOP/"unity-results"/(ident+".json")
    deadline=time.monotonic()+wait_seconds
    while time.monotonic()<deadline and not file.is_file():
        time.sleep(.7)
    if not file.is_file() and not _unity_pids():
        # A cold Codespace cannot process an earlier queued Unity command.
        _install_live_bridge()
        result=ensure_unity_gui()
        if result["exit_code"]!=0:
            return result
    if not file.is_file():
        return {"exit_code":0,"stdout":json.dumps({
            "job":ident,"pending":True,"unity_running":bool(_unity_pids()),
            "note":"Accepted, awaiting Editor import/domain compilation; poll unity_result by job ID."
        }),"stderr":""}
    if file.is_symlink() or file.stat().st_size>150000:
        return {"exit_code":3,"stdout":"","stderr":"Invalid Unity response"}
    result=json.loads(file.read_text(encoding="utf-8"))
    if result.get("id")!=ident:
        return {"exit_code":3,"stdout":"","stderr":"Unity response identity mismatch"}
    # Output can contain relative saved scene paths, never VNC credentials.
    return {"exit_code":0 if result.get("status")=="ok" else 3,
            "stdout":json.dumps(result,ensure_ascii=False)[:16000],
            "stderr":result.get("error","")[:300] if result.get("status")!="ok" else ""}


def execute(job):
    # Validate independently from Actions, where an untrusted queue file travels.
    if set(job) != {"id", "operation", "args"}:
        raise ValueError("invalid job shape")
    ident, op, args = job["id"], job["operation"], job["args"]
    if not isinstance(ident, str) or not (4 <= len(ident) <= 56) or not ident.replace("-", "").isalnum():
        raise ValueError("invalid job id")
    if not isinstance(args, list):
        raise ValueError("invalid args")
    if op == "prune_caches":
        if args: raise ValueError("unexpected arguments")
        return {"exit_code":0,"stdout":json.dumps(prune_caches(),ensure_ascii=False),"stderr":""}
    if op == "lfs_verify_chunk":
        if len(args) != 1 or not args[0].isdigit():
            raise ValueError("expected one numeric LFS cursor")
        return {"exit_code":0,"stdout":json.dumps(lfs_verify_chunk(int(args[0])),ensure_ascii=False),"stderr":""}
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
    if op == "unity_live":
        if len(args)!=1 or len(args[0])>500: raise ValueError("one short Unity command required")
        return unity_live_job(job)
    if op == "unity_result":
        if len(args)!=1: raise ValueError("Unity result ID required")
        return _read_unity_result(args[0],wait_seconds=8)
    if op == "unity_gui":
        if args: raise ValueError("unity_gui takes no arguments")
        return ensure_unity_gui()
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
    if len(sys.argv)==3 and sys.argv[1]=="--unity-watchdog" and sys.argv[2].isdigit():
        _monitor_unity(int(sys.argv[2]))
        sys.exit(0)
    sys.exit(main())