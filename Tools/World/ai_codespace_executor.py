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


def system_storage_audit():
    """Bounded, read-only storage accounting. Never delete system or project files.

    Du of a read-only base-image path does NOT establish recoverable bytes
    because a Codespace can use overlay/layered filesystems.
    """
    import time
    sources = (
        ("lfs_objects", PROJECT/".git/lfs/objects"),
        ("git_directory", PROJECT/".git"),
        ("assets", PROJECT/"Assets"),
        ("unity_library", PROJECT/"Library"),
        ("project_temp", PROJECT/"Temp"),
        ("codespace_cache", Path("/home/codespace/.cache")),
        ("codespace_local", Path("/home/codespace/.local")),
        ("npm_cache", Path("/home/codespace/.npm")),
        ("opt_conda", Path("/opt/conda")),
        ("opt_ghc", Path("/opt/ghc")),
        ("opt_total", Path("/opt")),
        ("usr_local_nvm", Path("/usr/local/share/nvm")),
        ("usr_local_android", Path("/usr/local/lib/android")),
        ("usr_local_rvm", Path("/usr/local/rvm")),
        ("usr_local_total", Path("/usr/local")),
        ("usr_lib_jvm", Path("/usr/lib/jvm")),
        ("apt_archives", Path("/var/cache/apt/archives")),
        ("apt_lists", Path("/var/lib/apt/lists")),
        ("unity_editor", Path("/home/codespace/Unity/Hub/Editor/6000.3.26f1")),
        ("world_bridge", Path("/workspaces/.aaris-world-bridge")),
        ("conda_package_cache", Path("/opt/conda/pkgs")),
        ("conda_environments", Path("/opt/conda/envs")),
        ("usr_local_share", Path("/usr/local/share")),
        ("usr_local_lib", Path("/usr/local/lib")),
        ("usr_local_go", Path("/usr/local/go")),
        ("usr_local_swift", Path("/usr/local/swift")),
        ("usr_share_dotnet", Path("/usr/share/dotnet")),
        ("usr_local_bin", Path("/usr/local/bin")),
        ("home_local_share", Path("/home/codespace/.local/share")),
        ("home_local_lib", Path("/home/codespace/.local/lib")),
    )
    deadline=time.monotonic()+90
    sizes={}
    for label,path in sources:
        if time.monotonic()>deadline:
            sizes[label]={"status":"time_budget_exceeded"}
            continue
        if path.is_symlink():
            sizes[label]={"status":"symlink_refused"}
            continue
        if not path.exists():
            sizes[label]={"status":"absent","bytes":0}
            continue
        remaining=max(1,min(8,int(deadline-time.monotonic())))
        try:
            process=subprocess.run(["du","-sx","-B1","--",str(path)],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                   text=True,timeout=remaining,check=False)
            if process.returncode:
                sizes[label]={"status":"unknown","reason":"du_error",
                              "detail":process.stderr[-120:]}
            else:
                sizes[label]={"status":"ok","bytes":int(process.stdout.split()[0])}
        except (subprocess.TimeoutExpired,OSError,ValueError,IndexError):
            sizes[label]={"status":"unknown","reason":"timeout_or_parse"}
    free=shutil.disk_usage(PROJECT)
    try:
        mount_table=Path("/proc/self/mountinfo").read_text()
        overlay=any(" - overlay " in row and row.split()[4]=="/"
                    for row in mount_table.splitlines())
    except OSError:
        overlay=None
    commands={name:shutil.which(name) for name in (
        "python3","node","npm","conda","php","java","dotnet","git","gh"
    )}
    ps=run(["ps","-o","pid,stat,comm","-C","Unity"],timeout=5)
    return {"free_disk_gib":round(free.free/2**30,3),
            "total_disk_gib":round(free.total/2**30,3),
            "unity_process":ps["stdout"][-250:],
            "root_overlay":overlay,"command_paths":commands,"sizes":sizes,
            "note":"Sizes overlap. In layered/overlay filesystems, du size is NOT reclaimable space. No files changed; measure df before and after any separately reviewed cleanup."}



def runtime_mount_probe():
    """Pure read-only tmpfs and Unity recovery feasibility inspection."""
    pkg=Path("/home/codespace/Unity/Hub/Editor/6000.3.26f1/Editor/Data/Resources/PackageManager")
    paths={"/dev/shm":Path("/dev/shm"),"project":PROJECT,
           "editor_package_manager":pkg,"editor":EDITOR,"home":Path("/home/codespace"),
           "temporary":Path("/tmp")}
    disks={}
    for label,path in paths.items():
        try:
            if not path.exists() or path.is_symlink():
                disks[label]={"status":"absent_or_symlink"}
                continue
            disk=shutil.disk_usage(path)
            fs=os.statvfs(path)
            disks[label]={"status":"ok","total_gib":round(disk.total/2**30,3),
                          "free_gib":round(disk.free/2**30,3),
                          "device_id":os.stat(path).st_dev,
                          "f_bavail":fs.f_bavail,"f_frsize":fs.f_frsize}
        except OSError as ex:
            disks[label]={"status":"error","reason":type(ex).__name__}
    try:
        mountinfo=Path("/proc/self/mountinfo").read_text()
        mountnames={}
        for line in mountinfo.splitlines():
            parts=line.split(" - ",1)
            if len(parts)!=2:
                continue
            front=parts[0].split()
            if len(front)<5:
                continue
            path=front[4].replace("\\040"," ")
            if path in ("/","/dev/shm","/workspaces","/tmp","/home","/home/codespace"):
                fields=parts[1].split()
                mountnames[path]={"filesystem":fields[0] if fields else None,
                                  "source":fields[1] if len(fields)>1 else None}
    except OSError:
        mountnames={}
    mem={}
    try:
        content=Path("/proc/meminfo").read_text()
        for field in ("MemTotal","MemAvailable","Shmem","SwapTotal","SwapFree"):
            import re
            m=re.search(r"^"+field+r":\s+(\d+) kB$",content,re.MULTILINE)
            if m: mem[field+"_gib"]=round(int(m.group(1))/1024**2,3)
    except OSError:
        pass
    process_states={}
    for pid in _unity_pids():
        try:
            raw=(Path("/proc")/str(pid)/"status").read_text()
            rows={}
            for key in ("State","VmRSS","VmSize"):
                import re
                m=re.search(r"^"+key+r":\s+(.+)$",raw,re.MULTILINE)
                if m: rows[key]=m.group(1)
            process_states[str(pid)]=rows
        except OSError:
            process_states[str(pid)]={"status":"unreadable"}
    pkg_bytes=_du_bytes(pkg)
    return {"paths":disks,"mounts":mountnames,"memory":mem,
            "unity_processes":process_states,"unity_package_manager_bytes":pkg_bytes,
            "warning":"A /dev/shm tmpfs copy is VOLATILE across Codespace stop and shares RAM; a persistent symlink to it would strand Unity Editor on restart. This operation did not move, delete, symlink or resume anything."}


def safe_archive_cleanroom(*, delete=False):
    """Review only re-downloadable package archives, never installed programs.

    Explicit fixed-directory allowlist; does not follow symlinks, run a shell,
    touch Git/LFS/Assets/Library, or call apt/conda uninstall commands.
    """
    import stat
    roots = (
        ("conda_archives", Path("/opt/conda/pkgs"), (".conda",".tar.bz2")),
        ("apt_archives", Path("/var/cache/apt/archives"), (".deb",)),
    )
    targets=[]
    data={}
    total_bytes=0
    for label,root,suffixes in roots:
        if root.is_symlink() or not root.is_dir():
            data[label]={"status":"missing_or_unsafe"}
            continue
        files=[]
        try:
            for path in root.iterdir():
                if not path.name.endswith(suffixes) or path.is_symlink():
                    continue
                st=path.stat(follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode) or st.st_size<=0:
                    continue
                files.append((path,st.st_size))
        except OSError as exc:
            data[label]={"status":"not_readable","reason":type(exc).__name__}
            continue
        files.sort(key=lambda v:v[0].name)
        this_size=sum(size for _,size in files)
        total_bytes+=this_size
        data[label]={"status":"ok","count":len(files),
                     "archive_bytes":this_size,
                     "directory_writable":os.access(root,os.W_OK)}
        targets.extend((label,path,size) for path,size in files)
    free_before=shutil.disk_usage(PROJECT).free
    if not delete:
        return {"mode":"audit","candidates":data,"total_archive_bytes":total_bytes,
                "free_disk_gib":round(free_before/2**30,3),"deleted":False}
    if len(targets)>4000 or total_bytes>2*1024**3:
        raise ValueError("Archive cleanup budget exceeded; manual review required")
    active=run(["ps","-eo","comm="],timeout=5)
    if active["exit_code"]!=0:
        raise ValueError("Cannot check active package managers")
    procs={p.strip() for p in active["stdout"].splitlines()}
    if procs.intersection({"conda","mamba","apt","apt-get","dpkg","dpkg-deb"}):
        raise ValueError("Package manager running; refuse archive cleanup")
    before=run(["git","status","--porcelain","--untracked-files=all"],timeout=30)
    if before["exit_code"]!=0:
        raise ValueError("Cannot verify protected Git worktree")
    freed_count=0
    freed_nominal=0
    denied=0
    for label,path,size in targets:
        # Fail closed: only direct regular file entries at fixed roots.
        root = dict((x[0],x[1]) for x in roots)[label]
        if path.parent!=root or path.is_symlink() or not path.is_file():
            raise ValueError("Archive path changed during cleanup")
        if not os.access(root,os.W_OK) or not os.access(path,os.W_OK):
            denied+=1
            continue
        try:
            path.unlink()
            freed_count+=1
            freed_nominal+=size
        except PermissionError:
            denied+=1
    after=run(["git","status","--porcelain","--untracked-files=all"],timeout=30)
    if before["stdout"]!=after["stdout"] or after["exit_code"]!=0:
        raise ValueError("Git worktree changed unexpectedly; stop")
    free_after=shutil.disk_usage(PROJECT).free
    return {"mode":"cleanup","candidates":data,"deleted_files":freed_count,
            "nominal_deleted_bytes":freed_nominal,"permission_denied":denied,
            "recovered_mib":round((free_after-free_before)/2**20,2),
            "free_disk_gib":round(free_after/2**30,3),
            "git_worktree_unchanged":True,
            "note":"Deleting archives does not remove installed Conda or APT packages; on OverlayFS lower-layer bytes may not be recovered."}



# Headless Unity scene import: all expensive writes and imported assets go to
# the separate /tmp ext4 volume. The existing original project/Library and
# dirty Core Files are never modified by this experimental test.
BATCH_ROOT=Path("/tmp/aaris-unity-batch")
BATCH_META=Path("/workspaces/.aaris-world-bridge/ondemand/unity-batch-status.json")
BATCH_CS=Path("/workspaces/.aaris-world-bridge/ondemand/AarisBatchProbe.cs")


def _batch_write(state, **fields):
    data={"state":state,"timestamp_utc":__import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(),
        "workspace_source_untouched":True,"no_vnc_used":True,**fields}
    BATCH_META.parent.mkdir(parents=True,exist_ok=True)
    path=BATCH_META.with_suffix(".new")
    path.write_text(json.dumps(data,ensure_ascii=False))
    os.replace(path,BATCH_META)
    return data


def unity_batch_status():
    try:
        data=json.loads(BATCH_META.read_text()) if BATCH_META.is_file() else {"state":"not_started"}
    except (OSError,ValueError):
        data={"state":"unreadable"}
    logfile=BATCH_ROOT/"editor.log"
    if logfile.is_file() and not logfile.is_symlink():
        try:
            tail=logfile.read_text(encoding="utf-8",errors="replace")[-3200:]
            data["unity_log_tail"]=re.sub(
                r"(?i)(?:ghp_|github_pat_|sk-)[A-Za-z0-9_-]{8,}",
                "[REDACTED]",tail)
        except OSError:
            pass
    report=BATCH_ROOT/"scene-readback.json"
    if report.is_file() and not report.is_symlink():
        try:
            data["scene_readback"]=json.loads(report.read_text())
        except (ValueError,OSError):
            data["scene_readback_error"]="invalid or unavailable scene report"
    try:
        data["scratch_free_gib"]=round(shutil.disk_usage(BATCH_ROOT if BATCH_ROOT.exists() else Path("/tmp")).free/2**30,3)
        data["persistent_free_gib"]=round(shutil.disk_usage(PROJECT).free/2**30,3)
    except OSError:
        pass
    root=BATCH_ROOT/"project"
    if root.is_dir():
        try:
            size=subprocess.run(
                ["du","-s","-B1","--",str(root)],capture_output=True,
                text=True,timeout=15,check=False
            )
            if size.returncode==0:
                data["scratch_project_gib"]=round(int(size.stdout.split()[0])/2**30,3)
        except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):
            pass
    try:
        data["worker_running"] = bool(data.get("worker_pid") and
                                      Path("/proc",str(data["worker_pid"])).exists())
        unity=run(["ps","-eo","pid,stat,comm"],timeout=5)
        data["unity_processes"]=[
            item.strip() for item in unity["stdout"].splitlines()
            if item.strip().endswith(" Unity")
        ][:6]
    except OSError:
        pass
    return data


def unity_batch_launch():
    if not EDITOR.is_file() or not os.access(EDITOR,os.X_OK):
        return {"exit_code":3,"stdout":"","stderr":"Unity Editor not installed or executable"}
    if not BATCH_CS.is_file() or BATCH_CS.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Reviewed headless C# probe not staged"}
    if BATCH_ROOT.exists():
        return {"exit_code":3,"stdout":json.dumps(unity_batch_status()),
                "stderr":"Existing scratch run present; inspect status instead of overwriting it"}
    if shutil.disk_usage(Path("/tmp")).free < 20*1024**3:
        return {"exit_code":3,"stdout":"","stderr":"Not enough separate /tmp free disk for safe project import"}
    if shutil.disk_usage(PROJECT).free < 240*1024**2:
        return {"exit_code":3,"stdout":"","stderr":"Original persistent project disk critically full"}
    for path in ("Assets","Packages","ProjectSettings"):
        if not (PROJECT/path).is_dir() or (PROJECT/path).is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Missing original project folder: "+path}
    _batch_write("launching",original_project=str(PROJECT),
                 scratch_project=str(BATCH_ROOT/"project"),
                 note="Separate throwaway /tmp test; original paused GUI is untouched")
    env=os.environ.copy()
    out=BATCH_META.parent/"unity-batch-worker.log"
    with out.open("a") as log:
        proc=subprocess.Popen(
            [sys.executable,str(Path(__file__).resolve()),"--unity-batch-worker"],
            cwd=Path("/tmp"),env=env,stdin=subprocess.DEVNULL,
            stdout=log,stderr=log,start_new_session=True)
    _batch_write("worker_started",worker_pid=proc.pid,
                 scratch_project=str(BATCH_ROOT/"project"))
    return {"exit_code":0,"stdout":json.dumps(unity_batch_status()),"stderr":""}


def _headless_mem_available():
    try:
        m=re.search(r"^MemAvailable:\s*(\d+)\s+kB",Path("/proc/meminfo").read_text(),re.M)
        return int(m.group(1))*1024 if m else 0
    except OSError:
        return 0


def unity_batch_worker():
    """Non-destructive separate project clone, then REAL Unity Editor CLI open."""
    try:
        BATCH_ROOT.mkdir(mode=0o700)
        _batch_write("copying_original_to_scratch",scratch_project=str(BATCH_ROOT/"project"))
        target=BATCH_ROOT/"project"
        target.mkdir()
        for folder in ("Assets","Packages","ProjectSettings"):
            src=PROJECT/folder
            # Refuse symlinks so a project copy cannot reach outside original.
            for base,dirs,files in os.walk(src,followlinks=False):
                for entry in dirs+files:
                    if (Path(base)/entry).is_symlink():
                        raise RuntimeError("Symlink detected; abort scratch copy safely")
            shutil.copytree(src,target/folder,symlinks=True)
        if shutil.disk_usage(BATCH_ROOT).free < 12*1024**3:
            raise RuntimeError("Scratch filesystem too full after source copy")
        probe=target/"Assets/Editor/AarisBatchProbe.cs"
        probe.parent.mkdir(parents=True,exist_ok=True)
        if probe.exists():
            raise RuntimeError("Refuse to overwrite an existing Editor script in test copy")
        shutil.copy2(BATCH_CS,probe)
        (BATCH_ROOT/"xdg-cache").mkdir()
        (BATCH_ROOT/"xdg-config").mkdir()
        (BATCH_ROOT/"xdg-data").mkdir()
        (BATCH_ROOT/"xdg-state").mkdir()
        (BATCH_ROOT/"home").mkdir(mode=0o700)
        (BATCH_ROOT/"temp").mkdir()
        _batch_write("unity_importing",scratch_project=str(target),
                     note="Unity CLI -batchmode -nographics -executeMethod; no screen/VNC")
        env=os.environ.copy()
        env["HOME"]=str(BATCH_ROOT/"home")
        env["XDG_CACHE_HOME"]=str(BATCH_ROOT/"xdg-cache")
        env["XDG_CONFIG_HOME"]=str(BATCH_ROOT/"xdg-config")
        env["XDG_DATA_HOME"]=str(BATCH_ROOT/"xdg-data")
        env["XDG_STATE_HOME"]=str(BATCH_ROOT/"xdg-state")
        env["TMPDIR"]=str(BATCH_ROOT/"temp")
        env["AARIS_BATCH_REPORT"]=str(BATCH_ROOT/"scene-readback.json")
        args=[str(EDITOR),"-batchmode","-nographics","-quit",
              "-projectPath",str(target),
              "-executeMethod","AarisBatchProbe.OpenMapAndAudit",
              "-logFile",str(BATCH_ROOT/"editor.log")]
        with (BATCH_ROOT/"stdout.log").open("w") as output:
            proc=subprocess.Popen(args,cwd=BATCH_ROOT,env=env,
                                  stdin=subprocess.DEVNULL,stdout=output,
                                  stderr=subprocess.STDOUT,start_new_session=True)
            start=time.monotonic()
            while proc.poll() is None:
                time.sleep(8)
                original_free=shutil.disk_usage(PROJECT).free
                scratch_free=shutil.disk_usage(BATCH_ROOT).free
                mem=_headless_mem_available()
                elapsed=round(time.monotonic()-start)
                if (original_free < 200*1024**2 or
                    scratch_free < 5*1024**3 or
                    (mem and mem < 1200*1024**2) or elapsed>2600):
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=15)
                    raise RuntimeError(
                        "Safe scratch Unity stop: persistent_free_mib="+
                        str(original_free//2**20)+" scratch_free_gib="+
                        str(round(scratch_free/2**30,2))+
                        " mem_available_mib="+str(mem//2**20)+
                        " elapsed_seconds="+str(elapsed))
                if elapsed%40<8:
                    _batch_write("unity_importing",unity_pid=proc.pid,
                                 elapsed_seconds=elapsed,
                                 scratch_free_gib=round(scratch_free/2**30,3),
                                 persistent_free_gib=round(original_free/2**30,3))
            exitcode=proc.returncode
        report=BATCH_ROOT/"scene-readback.json"
        if exitcode!=0 or not report.is_file():
            raise RuntimeError("Unity batch incomplete: exit="+str(exitcode)+
                               " report_present="+str(report.is_file()))
        obj=json.loads(report.read_text())
        if obj.get("sceneLoaded") is not True:
            raise RuntimeError("Scene audit did not confirm Unity scene loaded")
        _batch_write("unity_scene_opened_and_audited",
                     unity_exit_code=exitcode,scene=obj,
                     note="ONLY scratch-copy loaded, no persistent source mutation")
    except Exception as err:
        _batch_write("failed",error=type(err).__name__+": "+str(err)[:600])
    return 0



def _scratch_unity_pids():
    """Only match Editor processes opening the isolated scratch copy."""
    target=str(BATCH_ROOT/"project")
    found=[]
    for child in Path("/proc").iterdir():
        if not child.name.isdigit():
            continue
        try:
            argv=[a.decode("utf-8","replace") for a in
                  (child/"cmdline").read_bytes().split(b"\x00") if a]
            if len(argv)<4 or argv[0]!=str(EDITOR):
                continue
            ix=argv.index("-projectPath")
            if ix+1<len(argv) and argv[ix+1]==target:
                found.append(int(child.name))
        except (OSError,ValueError,IndexError):
            pass
    return sorted(found)


def unity_virtual_gui_status():
    data=unity_batch_status()
    data["scratch_unity_pids"]=_scratch_unity_pids()
    log=BATCH_ROOT/"virtual-editor.log"
    if log.is_file() and not log.is_symlink():
        try:
            with log.open("rb") as stream:
                stream.seek(0,2)
                size=stream.tell()
                stream.seek(max(0,size-128*1024))
                tail=stream.read().decode("utf-8","replace")
            data["virtual_unity_log_bytes"]=size
            data["virtual_unity_log_tail"]=re.sub(
                r"(?i)(?:ghp_|github_pat_|sk-)[A-Za-z0-9_-]{8,}",
                "[REDACTED]",tail[-4500:])
            markers=("AARIS_LIVE_EDITOR_READY","AARIS_LIVE_RESTORE_FAILED",
                     "AARIS_LIVE_POLL_ERROR","error CS","Compilation failed",
                     "Application.AssetDatabase Initial Refresh Start",
                     "AssetDatabase Initial Refresh Done","AARIS_BATCH_MAP_OPENED")
            data["import_log_markers"]={m:tail.count(m) for m in markers if m in tail}
        except OSError:
            pass
    control=BATCH_ROOT/"control"
    for folder,key in (("unity-commands","queued_virtual_commands"),
                       ("unity-results","virtual_completed_results")):
        p=control/folder
        if p.is_dir():
            data[key]=sum(1 for f in p.iterdir() if f.is_file() and f.suffix==".json")
    data["display_socket"]=Path("/tmp/.X11-unix/X12").exists()
    data["novnc_required"]=False
    return data


def unity_virtual_gui_launch():
    """Run the REAL Unity graphical Editor on isolated Xvfb; NO VNC transport."""
    target=BATCH_ROOT/"project"
    scene=target/"Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
    if not EDITOR.is_file() or not os.access(EDITOR,os.X_OK):
        return {"exit_code":3,"stdout":"","stderr":"Native Unity Editor unavailable"}
    if not target.is_dir() or not scene.is_file():
        return {"exit_code":3,"stdout":json.dumps(unity_virtual_gui_status()),
                "stderr":"Isolated scratch project/scene missing"}
    if _scratch_unity_pids():
        return {"exit_code":0,"stdout":json.dumps(unity_virtual_gui_status()),
                "stderr":""}
    if shutil.disk_usage(PROJECT).free < 250*1024**2:
        return {"exit_code":3,"stdout":"","stderr":"Less than 250 MiB protected original disk headroom"}
    if shutil.disk_usage(BATCH_ROOT).free < 20*1024**3:
        return {"exit_code":3,"stdout":"","stderr":"Scratch disk lacks 20 GiB headroom"}
    if not shutil.which("Xvfb"):
        return {"exit_code":3,"stdout":"","stderr":"Xvfb virtual display not installed"}
    BATCH_ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    env=os.environ.copy()
    env["DISPLAY"]=":12"
    env["XDG_CACHE_HOME"]=str(BATCH_ROOT/"xdg-cache")
    env["TMPDIR"]=str(BATCH_ROOT/"temp")
    env["UPM_CACHE_ROOT"]=str(BATCH_ROOT/"upm-cache")
    env["AARIS_BATCH_REPORT"]=str(BATCH_ROOT/"scene-readback.json")
    # Keep the genuine user's HOME & Unity Hub licensing state for Personal
    # authorization; redirect only disposable cache and temporary writes.
    for dirname in ("xdg-cache","temp","upm-cache"):
        (BATCH_ROOT/dirname).mkdir(mode=0o700,exist_ok=True)
    socket=Path("/tmp/.X11-unix/X12")
    if not socket.exists():
        with (BATCH_ROOT/"xvfb.log").open("a") as out:
            subprocess.Popen(
                ["Xvfb",":12","-screen","0","1600x900x24",
                 "-nolisten","tcp","-noreset"],
                cwd=BATCH_ROOT,stdin=subprocess.DEVNULL,stdout=out,
                stderr=out,start_new_session=True)
    for _ in range(25):
        if socket.exists():
            break
        time.sleep(0.2)
    if not socket.exists():
        return {"exit_code":3,"stdout":"","stderr":"Xvfb :12 did not open; see scratch xvfb.log"}
    # Normal Unity Editor on virtual display, not batch/headless entitlement.
    # The Editor remains alive for the existing file-based AI bridge.
    args=[str(EDITOR),"-projectPath",str(target),
          "-executeMethod","AarisBatchProbe.OpenMapAndAudit",
          "-logFile",str(BATCH_ROOT/"virtual-editor.log"),
          "-job-worker-count","2"]
    with (BATCH_ROOT/"virtual-launch.log").open("a") as out:
        proc=subprocess.Popen(args,cwd=BATCH_ROOT,env=env,
                              stdin=subprocess.DEVNULL,stdout=out,
                              stderr=out,start_new_session=True)
    _batch_write("virtual_unity_started",unity_pid=proc.pid,
                 scratch_project=str(target),display=":12",
                 note="Virtual-only Xvfb; no noVNC launched; original assets unchanged")
    return {"exit_code":0,"stdout":json.dumps(unity_virtual_gui_status(),
                                              ensure_ascii=False),"stderr":""}



VIRTUAL_CONTROL=BATCH_ROOT/"control"


def _virtual_bridge_path():
    return BATCH_ROOT/"project/Assets/AarisWorld/Editor/AarisLiveEditorBridge.cs"


def virtual_bridge_isolate():
    """The scratch Unity Editor must NEVER consume original Editor's jobs."""
    source=_virtual_bridge_path()
    if not source.is_file() or source.is_symlink():
        raise ValueError("Native Unity live bridge missing from scratch project")
    old='private static readonly string Root = "/home/codespace/.aaris-desktop";'
    new='private static readonly string Root = "/tmp/aaris-unity-batch/control";'
    code=source.read_text(encoding="utf-8")
    if new not in code:
        if code.count(old)!=1:
            raise ValueError("Live bridge root differs; refuse scratch-only patch")
        backup=BATCH_ROOT/"original-scratch-bridge.cs"
        if backup.exists():
            raise ValueError("Scratch bridge backup already exists; inspect manually")
        shutil.copy2(source,backup)
        temp=source.with_suffix(".cs.aaris-tmp")
        temp.write_text(code.replace(old,new),encoding="utf-8")
        os.replace(temp,source)
    for dirname in ("unity-commands","unity-results","frames"):
        (VIRTUAL_CONTROL/dirname).mkdir(mode=0o700,parents=True,exist_ok=True)
    return str(VIRTUAL_CONTROL)


def _virtual_response(ident,seconds=0):
    if not re.fullmatch(r"[a-z][a-z0-9-]{3,55}",ident):
        raise ValueError("Bad virtual Unity result ID")
    file=VIRTUAL_CONTROL/"unity-results"/(ident+".json")
    until=time.monotonic()+seconds
    while time.monotonic()<until and not file.is_file():
        time.sleep(0.6)
    if not file.is_file():
        return {"exit_code":0,"stdout":json.dumps({
            "job":ident,"pending":True,
            "virtual_unity_running":bool(_scratch_unity_pids()),
            "scratch_scene_readback":(BATCH_ROOT/"scene-readback.json").is_file(),
            "note":"Awaiting native Unity AssetDatabase and bridge compilation"
        }),"stderr":""}
    if file.is_symlink() or file.stat().st_size>150000:
        return {"exit_code":3,"stdout":"","stderr":"Unsafe virtual response"}
    obj=json.loads(file.read_text())
    if obj.get("id")!=ident:
        return {"exit_code":3,"stdout":"","stderr":"Virtual result ID mismatch"}
    return {"exit_code":0 if obj.get("status")=="ok" else 3,
            "stdout":json.dumps(obj,ensure_ascii=False)[:16000],
            "stderr":(obj.get("error") or "")[:350]}


def unity_virtual_live_job(job):
    if len(job["args"])!=1 or len(job["args"][0])>550:
        raise ValueError("One bounded JSON action required")
    payload=validate_live_payload(json.loads(job["args"][0]))
    if not _scratch_unity_pids():
        return {"exit_code":3,"stdout":json.dumps(unity_virtual_gui_status()),
                "stderr":"Scratch Unity GUI Editor not running"}
    root=virtual_bridge_isolate()
    ident=job["id"]
    command=VIRTUAL_CONTROL/"unity-commands"/(ident+".json")
    result=VIRTUAL_CONTROL/"unity-results"/(ident+".json")
    if not command.exists() and not result.exists():
        info=dict(payload,id=ident)
        if payload["action"] in ("move_tree","scale_tree"):
            info["hasExpectedPosition"]=True
        tmp=command.with_suffix(".new")
        if tmp.exists() or command.is_symlink():
            raise ValueError("Unsafe virtual command staging")
        tmp.write_text(json.dumps(info,separators=(",",":"),allow_nan=False))
        os.replace(tmp,command)
    return _virtual_response(ident,seconds=17)


def unity_virtual_frame(ident):
    if not re.fullmatch(r"[a-z][a-z0-9-]{3,55}",ident):
        raise ValueError("Invalid frame command")
    frame=VIRTUAL_CONTROL/"frames"/(ident+".jpg")
    if not frame.is_file() or frame.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Virtual Unity screenshot not yet generated"}
    size=frame.stat().st_size
    if not 100 <= size <= 3*1024*1024:
        return {"exit_code":3,"stdout":"","stderr":"Unexpected screenshot size"}
    return {"exit_code":0,"stdout":json.dumps({
        "frame_job":ident,"bytes":size,"sha256":hashlib.sha256(frame.read_bytes()).hexdigest(),
        "format":"jpg","retention":"temporary 1 day GitHub Actions artifact"
    }),"stderr":""}


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
        "scale_tree":{"target","scale","expectedPosition"},
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
    if action in ("move","scale","move_tree","scale_tree") and not value.get("target"):
        raise ValueError("target required")
    if action in ("move","move_tree") and "delta" not in value:
        raise ValueError("move delta required")
    if action in ("scale","scale_tree") and "scale" not in value:
        raise ValueError("scale vector required")
    if action in ("move_tree","scale_tree") and "expectedPosition" not in value:
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
        if params["action"] in ("move_tree","scale_tree"):
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



def unity_diagnostics():
    """Read-only X11/Unity state, with no secrets, new imports or asset changes."""
    pidlist=_unity_pids()
    rawlogs={}
    for filename in ("unity-editor.log","unity-launch.log","unity-storage-watchdog.log"):
        path=DESKTOP/filename
        if path.is_file() and not path.is_symlink() and path.stat().st_size < 20*1024*1024:
            data=path.read_text(encoding="utf-8",errors="replace")[-6000:]
            rawlogs[filename]=re.sub(
                r"(?i)(?:ghp_|ghu_|gho_|ghs_|ghr_|github_pat_|sk-)[A-Za-z0-9_-]{8,}",
                "[REDACTED]", data
            )
        else:
            rawlogs[filename]="missing_or_unavailable"
    x11={}
    env=os.environ.copy()
    env["DISPLAY"]=":12"
    for app,args in (
        ("xwininfo",["xwininfo","-display",":12","-root","-tree"]),
        ("wmctrl",["wmctrl","-l"]),
        ("xdpyinfo",["xdpyinfo","-display",":12"]),
    ):
        x11[app]={"installed":bool(shutil.which(app))}
        if not x11[app]["installed"]: continue
        try:
            p=subprocess.run(args,env=env,capture_output=True,text=True,
                             timeout=12,check=False)
            x11[app].update({"exit_code":p.returncode,
                              "stdout":p.stdout[:7000],
                              "stderr":p.stderr[-500:]})
        except (OSError,subprocess.TimeoutExpired) as err:
            x11[app]["error"]=str(err)[:300]
    process=[]
    for pid in pidlist:
        proc=Path("/proc")/str(pid)
        try:
            line=(proc/"stat").read_text()
            fields=line.rsplit(")",1)[1].split()
            state=fields[0]
            threads=len(list((proc/"task").iterdir()))
            process.append({"pid":pid,"state":state,"threads":threads})
        except OSError:
            process.append({"pid":pid,"state":"unavailable"})
    folder=PROJECT/"Library"
    return {"gui":_unity_gui_status(),
            "process":process,
            "x11":x11,
            "screenshot_tools":{k:bool(shutil.which(k)) for k in
                                ("xwd","import","scrot","ffmpeg","python3")},
            "project_library_entries":sorted(p.name for p in folder.iterdir())[:30] if folder.is_dir() else [],
            "pending_commands":len(list((DESKTOP/"unity-commands").glob("*.json"))) if (DESKTOP/"unity-commands").is_dir() else 0,
            "completed_responses":len(list((DESKTOP/"unity-results").glob("*.json"))) if (DESKTOP/"unity-results").is_dir() else 0,
            "logs":rawlogs}




def ensure_desktop_tools():
    """Install only screenshot/window-inspection utilities; leave Unity and assets intact."""
    required=("xwininfo","scrot")
    if all(shutil.which(x) for x in required):
        return {"installed":True,"installed_before":True,
                "free_disk_gib":round(shutil.disk_usage(PROJECT).free/2**30,3)}
    if shutil.disk_usage(PROJECT).free < 2*1024**3:
        raise ValueError("Less than 2 GiB free, refusing even small GUI package install")
    env=os.environ.copy()
    env["DEBIAN_FRONTEND"]="noninteractive"
    argv=["sudo","-n","apt-get","install","-y","--no-install-recommends",
          "x11-utils","scrot"]
    proc=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=105,check=False)
    result={
        "installed":proc.returncode==0 and all(shutil.which(x) for x in required),
        "installed_before":False,
        "exit_code":proc.returncode,
        "stdout_tail":proc.stdout[-1700:],
        "stderr_tail":proc.stderr[-800:],
        "free_disk_gib":round(shutil.disk_usage(PROJECT).free/2**30,3),
    }
    return result



def unity_terms_accept():
    """Owner-authorized, single-purpose click for the exact Unity 6000 Terms dialog.

    This is deliberately NOT a generic GUI command executor. Never accept
    untrusted coordinates, window names, commands or arguments.
    """
    import ctypes
    import ctypes.util

    if not _unity_pids() or not Path("/tmp/.X11-unix/X12").exists():
        return {"exit_code": 3, "stdout": "", "stderr": "Unity GUI/display not running"}
    env = os.environ.copy()
    env["DISPLAY"] = ":12"
    command = ["xwininfo", "-display", ":12", "-name",
               "Unity Editor Software Terms", "-stats"]
    probe = subprocess.run(command, env=env, capture_output=True, text=True,
                           timeout=12, check=False)
    info = probe.stdout
    if probe.returncode != 0 or '"Unity Editor Software Terms"' not in info:
        return {"exit_code": 3, "stdout": "",
                "stderr": "Exact Unity Editor Software Terms window not found"}
    def value(pattern):
        match = re.search(pattern, info, re.MULTILINE)
        if not match:
            raise ValueError("Unexpected Unity Terms window geometry")
        return int(match.group(1))
    x = value(r"^\s*Absolute upper-left X:\s*(-?\d+)\s*$")
    y = value(r"^\s*Absolute upper-left Y:\s*(-?\d+)\s*$")
    w = value(r"^\s*Width:\s*(\d+)\s*$")
    h = value(r"^\s*Height:\s*(\d+)\s*$")
    if (w, h) != (640, 480) or not (0 <= x <= 960 and 0 <= y <= 420):
        return {"exit_code": 3, "stdout": "",
                "stderr": "Terms window geometry differs from verified screenshot"}
    if not re.search(r"Map State:\s+IsViewable", info):
        return {"exit_code": 3, "stdout": "",
                "stderr": "Terms window is not viewable"}
    x11_name, xtst_name = ctypes.util.find_library("X11"), ctypes.util.find_library("Xtst")
    if not x11_name or not xtst_name:
        return {"exit_code": 3, "stdout": "", "stderr": "X11 XTest libraries unavailable"}
    x11, xtst = ctypes.CDLL(x11_name), ctypes.CDLL(xtst_name)
    ptr = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ptr
    x11.XRootWindow.argtypes = [ptr, ctypes.c_int]
    x11.XRootWindow.restype = ctypes.c_ulong
    x11.XWarpPointer.argtypes = [ptr, ctypes.c_ulong, ctypes.c_ulong,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                                ctypes.c_uint, ctypes.c_int, ctypes.c_int]
    x11.XWarpPointer.restype = ctypes.c_int
    x11.XSync.argtypes = [ptr, ctypes.c_int]
    x11.XSync.restype = ctypes.c_int
    x11.XCloseDisplay.argtypes = [ptr]
    x11.XCloseDisplay.restype = ctypes.c_int
    xtst.XTestFakeButtonEvent.argtypes = [ptr, ctypes.c_uint, ctypes.c_int,
                                         ctypes.c_ulong]
    xtst.XTestFakeButtonEvent.restype = ctypes.c_int
    display = x11.XOpenDisplay(b":12")
    if not display:
        return {"exit_code": 3, "stdout": "", "stderr": "Cannot open local X11 display"}
    def press(xx, yy):
        root = x11.XRootWindow(display, 0)
        if x11.XWarpPointer(display, 0, root, 0, 0, 0, 0, xx, yy) == 0:
            raise RuntimeError("X11 pointer movement failed")
        x11.XSync(display, 0)
        if xtst.XTestFakeButtonEvent(display, 1, 1, 0) == 0:
            raise RuntimeError("XTest button press failed")
        if xtst.XTestFakeButtonEvent(display, 1, 0, 0) == 0:
            raise RuntimeError("XTest button release failed")
        x11.XSync(display, 0)
    try:
        # Coordinates relative to the verified 640x480 Unity terms CLIENT
        # window, not the 1600x900 screenshot or an arbitrary desktop window.
        press(x + 32, y + 395)  # unchecked "I have read and agree"
        time.sleep(0.7)
        # Refuse the second click if the expected dialog disappeared.
        midway = subprocess.run(command, env=env, capture_output=True,
                                text=True, timeout=12, check=False)
        if midway.returncode != 0 or '"Unity Editor Software Terms"' not in midway.stdout:
            return {"exit_code": 3, "stdout": "",
                    "stderr": "Terms window changed after checkbox; no confirm click sent"}
        press(x + 350, y + 443)  # "Accept and Continue"
        time.sleep(2.5)
    finally:
        x11.XCloseDisplay(display)
    after = subprocess.run(command, env=env, capture_output=True,
                           text=True, timeout=12, check=False)
    closed = after.returncode != 0
    outcome = {"terms_window_closed": closed, "editor_pids": _unity_pids(),
               "project_library_exists": (PROJECT / "Library").is_dir(),
               "free_disk_gib": round(shutil.disk_usage(PROJECT).free / 2**30, 3)}
    return {"exit_code": 0 if closed else 3, "stdout": json.dumps(outcome),
            "stderr": "" if closed else "Terms window is still visible; inspect new screenshot"}


def unity_low_disk_stop():
    """Gracefully protect this exact Unity project from disk exhaustion.

    No assets or Library files are deleted, and no unrelated process is touched.
    The action is deliberately not a generic process killer.
    """
    free=shutil.disk_usage(PROJECT).free
    running=_unity_pids()
    limit=int(1.3 * 1024**3)
    if free >= limit:
        return {"exit_code":0,"stdout":json.dumps({
            "action":"no_stop_disk_above_guard","free_disk_gib":round(free/2**30,3),
            "unity_pids":running}),"stderr":""}
    if not running:
        return {"exit_code":0,"stdout":json.dumps({
            "action":"already_stopped","free_disk_gib":round(free/2**30,3),
            "library_retained":(PROJECT/"Library").is_dir()}),"stderr":""}
    for pid in running:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(24):
        if not _unity_pids():
            break
        time.sleep(0.5)
    remaining=_unity_pids()
    return {"exit_code":0 if not remaining else 3,
            "stdout":json.dumps({
                "action":"graceful_SIGTERM_for_low_disk",
                "free_disk_gib":round(shutil.disk_usage(PROJECT).free/2**30,3),
                "pids_before":running,"pids_remaining":remaining,
                "library_retained":(PROJECT/"Library").is_dir()}),
            "stderr":"" if not remaining else "Unity has not exited yet; no SIGKILL issued"}


def unity_import_pause_or_resume(resume=False):
    """Pause only the Unity Editor's own verified process group on low disk.

    A paused process retains RAM only while the Codespace stays running.
    The persistent Library and all source assets are never rewritten here.
    """
    free=shutil.disk_usage(PROJECT).free
    pids=_unity_pids()
    if resume:
        if free < 4*1024**3:
            return {"exit_code":3,"stdout":"","stderr":"Resume denied: 4 GiB persistent free disk required"}
    elif free >= int(1.3*1024**3):
        return {"exit_code":0,"stdout":json.dumps({
            "action":"not_needed","free_disk_gib":round(free/2**30,3),
            "unity_pids":pids}),"stderr":""}
    if not pids:
        return {"exit_code":0,"stdout":json.dumps({
            "action":"no_unity_process","free_disk_gib":round(free/2**30,3),
            "library_preserved":(PROJECT/"Library").is_dir()}),"stderr":""}
    groups=[]
    for pid in pids:
        pgid=os.getpgid(pid)
        # The reviewed launcher uses start_new_session=True. Refuse to signal
        # any group that could include unrelated SSH or Codespace programs.
        if pgid!=pid:
            return {"exit_code":3,"stdout":"","stderr":"Unity PID is not its own process-group leader"}
        groups.append(pgid)
    for pgid in groups:
        os.killpg(pgid, signal.SIGCONT if resume else signal.SIGSTOP)
    result={"action":"resume" if resume else "pause",
            "groups":groups,"free_disk_gib":round(shutil.disk_usage(PROJECT).free/2**30,3),
            "library_preserved":(PROJECT/"Library").is_dir()}
    return {"exit_code":0,"stdout":json.dumps(result),"stderr":""}

def desktop_snapshot(job_id):
    """Capture current Xvfb desktop, never commit it into repository history."""
    import re
    if not re.fullmatch(r"[a-z][a-z0-9-]{3,55}",job_id):
        raise ValueError("Bad snapshot ID")
    if not shutil.which("scrot"):
        return {"exit_code":3,"stdout":"","stderr":"scrot unavailable: run desktop_tools first"}
    if not Path("/tmp/.X11-unix/X12").exists():
        return {"exit_code":3,"stdout":"","stderr":"Virtual display :12 unavailable"}
    folder=DESKTOP/"frames"
    folder.mkdir(parents=True,exist_ok=True)
    folder.chmod(0o700)
    target=folder/(job_id+".jpg")
    if target.exists() or target.is_symlink():
        raise ValueError("Snapshot path already exists; use a new job ID")
    env=os.environ.copy()
    env["DISPLAY"]=":12"
    result=subprocess.run(["scrot","-z","-q","65",str(target)],env=env,
                          capture_output=True,text=True,timeout=18,check=False)
    if result.returncode!=0 or not target.is_file() or target.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"scrot failed: "+result.stderr[-300:]}
    size=target.stat().st_size
    if size<100 or size>3*1024*1024:
        target.unlink(missing_ok=True)
        return {"exit_code":3,"stdout":"","stderr":"Screen capture out of permitted size"}
    info={"frame_job":job_id,"bytes":size,"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
          "format":"jpg","retention":"1-day GitHub Actions artifact, remote copy deleted after upload"}
    return {"exit_code":0,"stdout":json.dumps(info),"stderr":""}


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
    if op == "safe_archives_audit":
        if args: raise ValueError("archive audit takes no arguments")
        return {"exit_code":0,"stdout":json.dumps(safe_archive_cleanroom(delete=False)),"stderr":""}
    if op == "safe_archives_cleanup":
        if args: raise ValueError("archive cleanup takes no arguments")
        return {"exit_code":0,"stdout":json.dumps(safe_archive_cleanroom(delete=True)),"stderr":""}
    if op == "runtime_mount_probe":
        if args: raise ValueError("runtime mount probe accepts no arguments")
        return {"exit_code":0,"stdout":json.dumps(runtime_mount_probe(),ensure_ascii=False),"stderr":""}
    if op == "system_storage_audit":
        if args: raise ValueError("system storage audit takes no arguments")
        return {"exit_code":0,"stdout":json.dumps(system_storage_audit(),ensure_ascii=False),"stderr":""}
    if op == "unity_lfs_preflight":
        if args: raise ValueError("read-only LFS preflight takes no arguments")
        source = Path("/workspaces/.aaris-world-bridge/ondemand/unity_lfs_preflight.py")
        if not source.is_file() or source.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Reviewed LFS preflight not staged"}
        audit = subprocess.run(
            ["python3",str(source),"--project",str(PROJECT),"--editor",str(EDITOR)],
            text=True,capture_output=True,timeout=90,check=False
        )
        return {"exit_code":audit.returncode,"stdout":audit.stdout[-16000:],
                "stderr":audit.stderr[-1400:]}
    if op == "unity_virtual_live":
        return unity_virtual_live_job(job)
    if op == "unity_virtual_result":
        if len(args)!=1: raise ValueError("Expected virtual Unity result ID")
        return _virtual_response(args[0],seconds=5)
    if op == "unity_virtual_frame":
        if len(args)!=1: raise ValueError("Expected virtual screenshot job ID")
        return unity_virtual_frame(args[0])
    if op == "unity_virtual_gui_launch":
        if args: raise ValueError("virtual Editor start accepts no arguments")
        return unity_virtual_gui_launch()
    if op == "unity_virtual_gui_status":
        if args: raise ValueError("virtual Editor status accepts no arguments")
        return {"exit_code":0,"stdout":json.dumps(unity_virtual_gui_status(),ensure_ascii=False),"stderr":""}
    if op == "unity_batch_launch":
        if args: raise ValueError("headless launch takes no args")
        return unity_batch_launch()
    if op == "unity_batch_status":
        if args: raise ValueError("headless status takes no args")
        return {"exit_code":0,"stdout":json.dumps(unity_batch_status(),ensure_ascii=False),"stderr":""}
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
    if op == "unity_frame":
        if len(args)!=1 or not re.fullmatch(r"[a-z][a-z0-9-]{3,55}",args[0]):
            raise ValueError("frame job ID required")
        name=args[0]+".jpg"
        path=DESKTOP/"frames"/name
        if not path.is_file() or path.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Unity screenshot not ready or already expired"}
        size=path.stat().st_size
        if size<100 or size>3*1024*1024:
            return {"exit_code":3,"stdout":"","stderr":"Invalid screenshot size"}
        return {"exit_code":0,"stdout":json.dumps({"frame_job":args[0],"bytes":size,
                         "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                         "format":"jpg","retention":"temporary, not committed to Git"}),"stderr":""}
    if op == "world_site":
        import math
        if len(args)!=3 or any(not s.replace(".","",1).replace("-","",1).isdigit() for s in args):
            raise ValueError("world_site requires x z radius")
        x,z,radius=map(float,args)
        if not all(math.isfinite(v) for v in (x,z,radius)) or max(abs(x),abs(z))>10000 or not 1<=radius<=150:
            raise ValueError("world_site coordinates/radius out of range")
        source=PROJECT/"Tools/World/ai_world_observe.py"
        if not source.is_file():
            source=Path("/workspaces/.aaris-world-bridge/ondemand/ai_world_observe.py")
        if not source.is_file() or source.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Reviewed world sensor missing from both project and private staging"}
        python=Path("/workspaces/.aaris-world-bridge/venv/bin/python")
        return run([str(python) if python.is_file() else "python3",str(source),
                    "site","--x",str(x),"--z",str(z),"--radius",str(radius),
                    "--limit","12"],timeout=100)
    if op == "unity_live":
        if len(args)!=1 or len(args[0])>500: raise ValueError("one short Unity command required")
        return unity_live_job(job)
    if op == "unity_result":
        if len(args)!=1: raise ValueError("Unity result ID required")
        return _read_unity_result(args[0],wait_seconds=8)
    if op == "desktop_tools":
        if args: raise ValueError("unexpected arguments")
        info=ensure_desktop_tools()
        return {"exit_code":0 if info.get("installed") else 3,
                "stdout":json.dumps(info,ensure_ascii=False),
                "stderr":"" if info.get("installed") else "GUI tools install failed"}
    if op == "desktop_snapshot":
        if args: raise ValueError("unexpected arguments")
        return desktop_snapshot(job["id"])
    if op == "unity_terms_accept":
        if args: raise ValueError("Unity terms acceptance takes no arguments")
        return unity_terms_accept()
    if op == "unity_low_disk_pause":
        if args: raise ValueError("no arguments accepted")
        return unity_import_pause_or_resume(False)
    if op == "unity_resume_paused":
        if args: raise ValueError("no arguments accepted")
        return unity_import_pause_or_resume(True)
    if op == "unity_low_disk_stop":
        if args: raise ValueError("low disk safety stop takes no arguments")
        return unity_low_disk_stop()
    if op == "unity_diagnostics":
        if args: raise ValueError("unexpected args")
        return {"exit_code":0,"stdout":json.dumps(unity_diagnostics(),ensure_ascii=False),"stderr":""}
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
            path = Path("/workspaces/.aaris-world-bridge/ondemand/ai_world_observe.py")
        if not path.is_file() or path.is_symlink():
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


if len(sys.argv)==2 and sys.argv[1]=="--unity-batch-worker":
    sys.exit(unity_batch_worker())

if __name__ == "__main__":
    if len(sys.argv)==3 and sys.argv[1]=="--unity-watchdog" and sys.argv[2].isdigit():
        _monitor_unity(int(sys.argv[2]))
        sys.exit(0)
    sys.exit(main())