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
    has_forest=(BATCH_ROOT/"project/Assets/AarisWorld/Editor/AarisForestCoreAuthoring.cs").is_file()
    log=BATCH_ROOT/("virtual-editor-forest.log" if has_forest else "virtual-editor.log")
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
    helper=BATCH_ROOT/"project/Assets/AarisWorld/Editor/AarisForestCoreAuthoring.cs"
    bridge=_virtual_bridge_path()
    data["forest_authoring_scratch_files"]={
        "helper_staged":helper.is_file(),"bridge_patched":
        bridge.is_file() and 'case "forest_plan":' in bridge.read_text(encoding="utf-8"),
        "helper_unity_meta_created":Path(str(helper)+".meta").is_file(),
    }
    data["x11_tools"]={name:bool(shutil.which(name)) for name in
        ("xwininfo","xprop","wmctrl","xdotool","xte")}
    # Search backward within bound, without exposing arbitrary Editor logs.
    if log.is_file():
        with log.open("rb") as file:
            file.seek(max(0,log.stat().st_size-600000))
            recent=file.read().decode("utf-8","replace")
        found=[line[-400:] for line in recent.splitlines()
               if any(key in line for key in
                 ("AarisForestCoreAuthoring.cs","AarisLiveEditorBridge.cs",
                  "error CS","Scripts have compiler errors",
                  "script compilation failed","Script compilation failed"))]
        data["forest_editor_compiler_evidence"]=found[-12:]
    # Foliage/URP shader triage: inspect only exact isolated Editor log,
    # do not print arbitrary files or change any materials, cache or owner source.
    shader_markers=("shader error", "shader unsupported", "shader is not supported",
                    "failed to compile shader", "failed to compile", "all subshaders removed",
                    "speedtreeurp", "error in shader", "shadergraph", "renderpipeline")
    if log.is_file() and not log.is_symlink() and log.stat().st_size < 32*1024**2:
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size-10*1024**2))
            material=stream.read().decode("utf-8","replace")
        evidence=[line[-500:] for line in material.splitlines()
                  if any(mark in line.lower() for mark in shader_markers)
                  and not line.startswith("[Worker")]
        data["shader_log_match_count"]=len(evidence)
        data["shader_log_evidence"]=[
            re.sub(r"(?i)(?:ghp_|ghu_|github_pat_|sk-)[A-Za-z0-9_-]{8,}",
                   "[REDACTED]", line) for line in evidence[-32:]]
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
          "-logFile",str(BATCH_ROOT/("virtual-editor-forest.log" if
              (target/"Assets/AarisWorld/Editor/AarisForestCoreAuthoring.cs").is_file()
              else "virtual-editor.log")),
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


def unity_forest_menu_snapshot():
    """Small read-only screenshot snippet to inspect Unity Editor menu placement."""
    import base64
    if not _scratch_unity_pids() or not Path("/tmp/.X11-unix/X12").exists() or not shutil.which("scrot"):
        return {"exit_code":3,"stdout":"","stderr":"Scratch Editor or screenshot tool unavailable"}
    path=BATCH_ROOT/"unity-forest-menubar-diagnostic.jpg"
    if path.exists() or path.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Existing menu capture needs review"}
    env=os.environ.copy()
    env["DISPLAY"]=":12"
    try:
        cmd=["scrot","-z","-q","12","-a","390,185,620,150",str(path)]
        r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=20,check=False)
        if r.returncode!=0 or not path.is_file():
            return {"exit_code":3,"stdout":"","stderr":"Xvfb menu capture failed"}
        b=path.read_bytes()
        if not 150<len(b)<11000:
            return {"exit_code":3,"stdout":json.dumps({"bytes":len(b)}),
                    "stderr":"Screenshot not bounded for private diagnostic"}
        return {"exit_code":0,"stdout":json.dumps({
            "status":"unity_top_menu_snapshot", "bytes":len(b),
            "jpeg_b64":base64.b64encode(b).decode("ascii")}),"stderr":""}
    finally:
        if path.exists() and not path.is_symlink(): path.unlink()


def unity_forest_editor_refresh():
    """One focused Assets > Refresh keyboard shortcut in PID-verified scratch Unity."""
    import ctypes
    import ctypes.util
    pids=set(_scratch_unity_pids())
    if not pids or not Path("/tmp/.X11-unix/X12").exists():
        return {"exit_code":3,"stdout":"","stderr":"No live scratch Editor"}
    helper=BATCH_ROOT/"project/Assets/AarisWorld/Editor/AarisForestCoreAuthoring.cs"
    bridge=_virtual_bridge_path()
    if not helper.is_file() or not bridge.is_file() or 'case "forest_plan":' not in bridge.read_text():
        return {"exit_code":3,"stdout":"","stderr":"Reviewed scratch forest authoring not staged"}
    x=subprocess.run(["xwininfo","-display",":12","-root","-tree"],
                     capture_output=True,text=True,timeout=12,check=False)
    if x.returncode:
        return {"exit_code":3,"stdout":"","stderr":"No X11 Unity window inventory"}
    eligible=[]
    for line in x.stdout.splitlines():
        if "Unity - project - TerrainDemoScene" not in line: continue
        match=re.search(r"0x[0-9a-fA-F]+",line)
        if not match: continue
        win=match.group(0)
        p=subprocess.run(["xprop","-display",":12","-id",win,
                          "_NET_WM_PID","WM_NAME"],capture_output=True,
                         text=True,timeout=8,check=False)
        pid=re.search(r"_NET_WM_PID\(CARDINAL\) = (\d+)",p.stdout)
        if p.returncode==0 and pid and int(pid.group(1)) in pids:
            eligible.append((win,int(pid.group(1))))
    if len(eligible)!=1:
        return {"exit_code":3,"stdout":json.dumps({"eligible":eligible}),
                "stderr":"Expected precisely one X11 Unity map window with scratch PID"}
    x11=ctypes.util.find_library("X11")
    xtst=ctypes.util.find_library("Xtst")
    if not x11 or not xtst: raise ValueError("XTest/X11 libraries not available")
    lib=ctypes.CDLL(x11)
    test=ctypes.CDLL(xtst)
    lib.XOpenDisplay.argtypes=[ctypes.c_char_p]
    lib.XOpenDisplay.restype=ctypes.c_void_p
    lib.XCloseDisplay.argtypes=[ctypes.c_void_p]
    lib.XSetInputFocus.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
    lib.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    lib.XKeysymToKeycode.restype=ctypes.c_uint
    lib.XFlush.argtypes=[ctypes.c_void_p]
    lib.XSync.argtypes=[ctypes.c_void_p,ctypes.c_int]
    test.XTestFakeKeyEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
    test.XTestFakeKeyEvent.restype=ctypes.c_int
    dpy=lib.XOpenDisplay(b":12")
    if not dpy: raise ValueError("Failed to open verified Unity display")
    try:
        window=int(eligible[0][0],16)
        ctrl=lib.XKeysymToKeycode(dpy,0xffe3)
        r=lib.XKeysymToKeycode(dpy,ord("r"))
        if not ctrl or not r: raise ValueError("Unity refresh shortcut keymaps unavailable")
        lib.XSetInputFocus(dpy,window,1,0)
        lib.XSync(dpy,0)
        try:
            if not test.XTestFakeKeyEvent(dpy,ctrl,1,0): raise ValueError("XTest control-down failed")
            if not test.XTestFakeKeyEvent(dpy,r,1,0): raise ValueError("XTest r-down failed")
            test.XTestFakeKeyEvent(dpy,r,0,0)
        finally:
            test.XTestFakeKeyEvent(dpy,ctrl,0,0)
        lib.XSync(dpy,0)
    finally:
        lib.XCloseDisplay(dpy)
    return {"exit_code":0,"stdout":json.dumps({
        "status":"unity_assets_refresh_shortcut_sent",
        "verified_scratch_pid":eligible[0][1],
        "scratch_only":True,
        "note":"Check Unity asset import and C# compiler before any forest core write"}),"stderr":""}


def unity_forest_treeonly_tune():
    """Replace only scratch one-time C# with confirmed broader tree silhouette plan."""
    if _scratch_unity_pids():
        return {"exit_code":3,"stdout":"","stderr":"Unity Editor currently running"}
    probe=json.loads(unity_forest_baseline_probe()["stdout"])
    if not probe["can_restore_tree_only_baseline"] or not all(
        x["scratch"].get("sha256")==x["main_expected_sha"]
        for x in probe["files"]
    ):
        return {"exit_code":3,"stdout":"","stderr":"Not at exact four-tile original baseline"}
    quarantine=BATCH_ROOT/"forest-treeonly-quarantine"
    proof=quarantine/"prepared.json"
    if not proof.is_file() or proof.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Verified tree-only restoration proof unavailable"}
    src=Path("/workspaces/.aaris-world-bridge/ondemand/AarisForestCoreAuthoring.cs")
    dst=BATCH_ROOT/"project/Assets/AarisWorld/Editor/AarisForestCoreAuthoring.cs"
    if not src.is_file() or src.is_symlink() or src.stat().st_size>40000 or not dst.is_file() or dst.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Tree-only C# staging identity invalid"}
    old=dst.read_text(encoding="utf-8")
    revised=src.read_text(encoding="utf-8")
    if "categories[i] != 1" not in old or "oldWidth * .61f" not in old:
        return {"exit_code":3,"stdout":"","stderr":"Unexpected current scratch tree-only source"}
    if ("widthFactor" not in revised or
        "report.widthIncreased" not in revised or
        "categories[i] != 1" not in revised or
        "float limit = report.projectedCanopyBefore * .99f;" not in revised):
        return {"exit_code":3,"stdout":"","stderr":"Not the approved species-aware broad-trunk scaling"}
    backup=quarantine/"AarisForestCoreAuthoring.pre-tuning.cs"
    if backup.exists() or backup.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Prior tuning attempt already present"}
    shutil.copy2(dst,backup)
    if backup.read_bytes()!=dst.read_bytes():
        raise ValueError("Unable to verify previous scratch helper backup")
    temp=dst.with_name(dst.name+".aaris-treeonly-tuned")
    if temp.exists() or temp.is_symlink():
        raise ValueError("Unexpected existing scratch tuning temp")
    shutil.copy2(src,temp)
    os.replace(temp,dst)
    if dst.read_bytes()!=src.read_bytes():
        shutil.copy2(backup,dst)
        raise ValueError("Tuned source readback mismatch; restored prior scratch helper")
    return {"exit_code":0,"stdout":json.dumps({
        "status":"treeonly_width_maturity_calibration_staged",
        "four_original_core_assets_unchanged":True,
        "scratch_only":True,"original_worktree_untouched":True
    }),"stderr":""}


def unity_forest_treeonly_prepare():
    """Quarantine incorrect 7508-instance edit and restore EXACT source core bytes.

    Never modify owner checkout, Git refs, GUIDs, user files outside isolated
    /tmp scratch. Stages reviewed tree-only authoring and retains rollback.
    """
    base=Path("Assets/TerrainDemoScene_URP/Terrain/Data")
    expected={
      "Terrain_1_1_4bf22c8f-eb55-436d-84e3-dedfa85665b1.asset":
        ("4798dfe0edf6cec43be1417e519271fbc4b98b99de553a981195e13c321714ae",
         "17522c8e230240894e76d08fd483992e63ebd06a2a767486ab1a91a404820857"),
      "Terrain_1_2_1694bb0f-cffe-402c-b6f9-cf47692fbb78.asset":
        ("9053935547655ccf39744e0b5ab475514598734bdffcf19f4f1760a452b559e4",
         "4a1c4577f690a0bfea4748e38b4049dec6c3d49137149b601fa3fd162e543d2c"),
      "Terrain_2_1_82fc4922-5564-4a18-858e-787f6d901556.asset":
        ("9aa00e637163f52f559683eb837e12799f39f499bcd16535d60838d49f8d5f65",
         "d10d4cb2a92f86ab8718c5f27cdfb1a750a90a0fcc9fdf1ad1e1897a5fe3631b"),
      "Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset":
        ("113c4b11ab5f7e6cba20f60a6b8bbc061d0f72d335827d48c98fff855a7faf07",
         "0a6c967a5bd1e0a73c05f759b1d599ec26d370759d399d5152f2180eab9051cc")
    }
    probe=json.loads(unity_forest_baseline_probe()["stdout"])
    if not probe["can_restore_tree_only_baseline"] or _scratch_unity_pids():
        return {"exit_code":3,"stdout":json.dumps(probe)[:2500],
                "stderr":"Source baseline SHA/metas not verified or scratch Editor running"}
    root=BATCH_ROOT/"project"
    directory=root/base
    staging=Path("/workspaces/.aaris-world-bridge/ondemand")
    helper=staging/"AarisForestCoreAuthoring.cs"
    one=staging/"AarisForestOneShot.cs"
    dest_helper=root/"Assets/AarisWorld/Editor/AarisForestCoreAuthoring.cs"
    dest_one=root/"Assets/AarisWorld/Editor/AarisForestOneShot.cs"
    for src in (helper,one):
        if not src.is_file() or src.is_symlink() or src.stat().st_size>40000:
            return {"exit_code":3,"stdout":"","stderr":"Reviewed one-shot C# source missing/unsafe"}
    if ("categories[i] != 1" not in helper.read_text() or
        "report.actualTrees" not in helper.read_text()):
        return {"exit_code":3,"stdout":"","stderr":"Tree-only corrected source not staged"}
    if "treeTotal != 1939" not in one.read_text():
        return {"exit_code":3,"stdout":"","stderr":"Tree-only one-shot audit missing"}
    for dest in (dest_helper,dest_one):
        if not dest.is_file() or dest.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Existing scratch C# script identity invalid"}
    queued=VIRTUAL_CONTROL/"unity-commands"
    if queued.is_dir() and any(x.is_file() and x.suffix==".json" for x in queued.iterdir()):
        return {"exit_code":3,"stdout":"","stderr":"Pending Unity command; cannot restore"}
    def digest(path):
        h=hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda:file.read(1024*1024),b""):h.update(chunk)
        return h.hexdigest()
    for name,(baseline,wrong) in expected.items():
        o=PROJECT/base/name
        w=directory/name
        if digest(o)!=baseline or digest(w)!=wrong:
            return {"exit_code":3,"stdout":"","stderr":"Unexpected native source/wrong bulk bytes: "+name}
        if digest(Path(str(o)+".meta"))!=digest(Path(str(w)+".meta")):
            return {"exit_code":3,"stdout":"","stderr":"Native metadata mismatch: "+name}
    quarantine=BATCH_ROOT/"forest-treeonly-quarantine"
    if quarantine.exists() or quarantine.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Existing quarantine requires review; refusing repeat"}
    if shutil.disk_usage(BATCH_ROOT).free<2*1024**3:
        return {"exit_code":3,"stdout":"","stderr":"Scratch cannot safely retain rollback"}
    quarantine.mkdir(mode=0o700)
    # Backup every incorrect asset and original scratch C# authoring before writes.
    for name,(_,wrong) in expected.items():
        backup=quarantine/name
        shutil.copy2(directory/name,backup)
        if digest(backup)!=wrong: raise ValueError("Quarantine SHA verification failed")
    for item in (dest_helper,dest_one):
        shutil.copy2(item,quarantine/item.name)
        if digest(item)!=digest(quarantine/item.name):
            raise ValueError("Editor script backup mismatch")
    written=[]
    try:
        for name,(baseline,_) in expected.items():
            original=PROJECT/base/name
            dest=directory/name
            temp=dest.with_name(name+".aaris-treeonly-new")
            if temp.exists() or temp.is_symlink():
                raise ValueError("Unsafe leftover TerrainData restore temp")
            shutil.copy2(original,temp)
            if digest(temp)!=baseline:
                raise ValueError("Source baseline copy digest mismatch")
            os.replace(temp,dest)
            written.append(dest)
            if digest(dest)!=baseline:
                raise ValueError("Native restored TerrainData SHA mismatch")
        for source,dest in ((helper,dest_helper),(one,dest_one)):
            temp=dest.with_suffix(".cs.aaris-treeonly-new")
            if temp.exists() or temp.is_symlink():
                raise ValueError("Scratch C# restore temp already exists")
            shutil.copy2(source,temp)
            os.replace(temp,dest)
            written.append(dest)
            if digest(dest)!=digest(source):
                raise ValueError("Staged tree-only C# readback mismatch")
    except Exception:
        for dest in reversed(written):
            backup=quarantine/dest.name
            if backup.is_file() and not backup.is_symlink():
                rollback=dest.with_name(dest.name+".aaris-treeonly-rollback")
                shutil.copy2(backup,rollback)
                os.replace(rollback,dest)
        raise
    details={
        "status":"baseline_restored_treeonly_corrected_authoring_staged",
        "scratch_only":True,"original_source_untouched":True,
        "bad_bulk_backed_up":list(expected),
        "restored_sha256":{name:sha for name,(sha,_) in expected.items()},
        "editor_scripts":["AarisForestCoreAuthoring.cs","AarisForestOneShot.cs"],
        "expected_counts":{"trees":1939,"rocks":5564,"shrubs":5},
        "note":"The next one-shot plan must show changedCount=actualTrees, non-trees preserved"
    }
    proof=quarantine/"prepared.json"
    proof.write_text(json.dumps(details,indent=2,sort_keys=True))
    return {"exit_code":0,"stdout":json.dumps(details),"stderr":""}


def unity_forest_baseline_probe():
    """Never write: compare source/main LFS-hydrated terrain assets with scratch."""
    base=Path("Assets/TerrainDemoScene_URP/Terrain/Data")
    expected={
        "Terrain_1_1_4bf22c8f-eb55-436d-84e3-dedfa85665b1.asset":
            "4798dfe0edf6cec43be1417e519271fbc4b98b99de553a981195e13c321714ae",
        "Terrain_1_2_1694bb0f-cffe-402c-b6f9-cf47692fbb78.asset":
            "9053935547655ccf39744e0b5ab475514598734bdffcf19f4f1760a452b559e4",
        "Terrain_2_1_82fc4922-5564-4a18-858e-787f6d901556.asset":
            "9aa00e637163f52f559683eb837e12799f39f499bcd16535d60838d49f8d5f65",
        "Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset":
            "113c4b11ab5f7e6cba20f60a6b8bbc061d0f72d335827d48c98fff855a7faf07",
    }
    active=_scratch_unity_pids()
    output={"scratch_editor_pids":active,
            "scratch_free_gib":round(shutil.disk_usage(BATCH_ROOT).free/2**30,2),
            "files":[]}
    for name,sha in expected.items():
        a=PROJECT/base/name
        b=BATCH_ROOT/"project"/base/name
        def read_digest(p):
            if not p.is_file() or p.is_symlink():
                return {"exists":False}
            h=hashlib.sha256()
            with p.open("rb") as file:
                for chunk in iter(lambda:file.read(1024*1024),b""):h.update(chunk)
            return {"exists":True,"bytes":p.stat().st_size,"sha256":h.hexdigest()}
        src=read_digest(a)
        cur=read_digest(b)
        src_meta=read_digest(Path(str(a)+".meta"))
        cur_meta=read_digest(Path(str(b)+".meta"))
        output["files"].append({
            "name":name,"main_expected_sha":sha,"source":src,"scratch":cur,
            "source_matches_main":src.get("sha256")==sha,
            "metas_match":src_meta.get("sha256") is not None
                          and src_meta.get("sha256")==cur_meta.get("sha256")
        })
    output["can_restore_tree_only_baseline"]=(not active and
        all(x["source_matches_main"] and x["metas_match"] for x in output["files"])
        and output["scratch_free_gib"]>12)
    return {"exit_code":0,"stdout":json.dumps(output,ensure_ascii=False),"stderr":""}


def unity_render_backend_probe():
    """Read-only software Vulkan/OpenGL capability probe for Unity screenshots."""
    info={"display_exists":Path("/tmp/.X11-unix/X12").exists(),
          "scratch_unity_pids":_scratch_unity_pids(),
          "binaries":{n:bool(shutil.which(n))
            for n in ("vulkaninfo","glxinfo","vkcube","eglinfo","scrot")}}
    for dir_name in ("/usr/share/vulkan/icd.d","/etc/vulkan/icd.d",
                     "/usr/share/glvnd/egl_vendor.d"):
        directory=Path(dir_name)
        info[dir_name]=[x.name for x in directory.iterdir()
                         if x.is_file() and not x.is_symlink()][:16] if directory.is_dir() else []
    env=os.environ.copy()
    env["DISPLAY"]=":12"
    env["VK_LOADER_DEBUG"]="error"
    for cmd in (("glxinfo","-B"),("vulkaninfo","--summary")):
        if not shutil.which(cmd[0]):continue
        try:
            ret=subprocess.run(list(cmd),env=env,capture_output=True,text=True,
                               timeout=15,check=False,stdin=subprocess.DEVNULL)
            info[cmd[0]]={"exit":ret.returncode,
                          "stdout":ret.stdout[-2200:],"stderr":ret.stderr[-600:]}
        except (OSError,subprocess.TimeoutExpired) as exc:
            info[cmd[0]]={"error":str(exc)[:300]}
    return {"exit_code":0,"stdout":json.dumps(info,ensure_ascii=False),"stderr":""}


def unity_map_camera_capture(job):
    """One-shot real Unity URP screenshot, saved ONLY as a short-lived artifact.

    Fail closed unless the four scratch TerrainData assets have the exact SHA256
    already merged to main. The owner worktree and game code are never edited.
    """
    ident=job["id"]
    zone=job["args"][0]
    if zone not in {"forest-west","forest-south","mountain-east"}:
        return {"exit_code":3,"stdout":"","stderr":"Unsupported camera location"}
    if _scratch_unity_pids():
        return {"exit_code":3,"stdout":"","stderr":"Existing scratch Unity Editor; cannot launch simultaneous renderer"}
    project=BATCH_ROOT/"project"
    source=Path("/workspaces/.aaris-world-bridge/ondemand/AarisMapCameraOneShot.cs")
    destination=project/"Assets/AarisWorld/Editor/AarisMapCameraOneShot.cs"
    if (not project.is_dir() or project.is_symlink() or not source.is_file()
        or source.is_symlink() or source.stat().st_size>15000
        or not EDITOR.is_file() or not Path("/tmp/.X11-unix/X12").exists()):
        return {"exit_code":3,"stdout":"","stderr":"Trusted scratch Unity camera environment unavailable"}
    expected={
      "Terrain_1_1_4bf22c8f-eb55-436d-84e3-dedfa85665b1.asset":
        "896b2d29b2d5b71afffe1f64a17863c8fa99cd06104c833b679ca117dd4d4609",
      "Terrain_1_2_1694bb0f-cffe-402c-b6f9-cf47692fbb78.asset":
        "b92e9099868cabd8040db632d0cfac3c38075b2e292519b0edd8629723edecf8",
      "Terrain_2_1_82fc4922-5564-4a18-858e-787f6d901556.asset":
        "d26aa11e1e6bb8edc65ca52c8c3210d477711b091e86e7ead42e75407dcc29a3",
      "Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset":
        "cfd96176947a1e75da285458ad6198ebf56a80195aa2138a5f202f5dc7f814e6",
    }
    root=project/"Assets/TerrainDemoScene_URP/Terrain/Data"
    for name,sha in expected.items():
        obj=root/name
        if not obj.is_file() or obj.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Merged native TerrainData missing: "+name}
        digest=hashlib.sha256()
        with obj.open("rb") as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b""):
                digest.update(chunk)
        if digest.hexdigest()!=sha:
            return {"exit_code":3,"stdout":"","stderr":"Scratch scene not from merged 1939-tree assets"}
    if shutil.disk_usage(project).free<14*1024**3 or shutil.disk_usage(PROJECT).free<250*1024**2:
        return {"exit_code":3,"stdout":"","stderr":"Not enough scratch or owner disk headroom"}
    if destination.is_symlink() or source.stat().st_size>15000:
        return {"exit_code":3,"stdout":"","stderr":"Unsafe scratch camera script"}
    content=source.read_bytes()
    if b"public static class AarisMapCameraOneShot" not in content or b"SubmitRenderRequest" not in content:
        return {"exit_code":3,"stdout":"","stderr":"Unreviewed native Unity camera script"}
    if destination.exists():
        if destination.read_bytes()!=content:
            return {"exit_code":3,"stdout":"","stderr":"Scratch screenshot source changed unexpectedly"}
    else:
        destination.write_bytes(content)
        if destination.read_bytes()!=content:
            return {"exit_code":3,"stdout":"","stderr":"Scratch capture staging failed"}
    result=VIRTUAL_CONTROL/"unity-results"/(ident+".json")
    image_path=VIRTUAL_CONTROL/"frames"/(ident+".jpg")
    log=BATCH_ROOT/("unity-real-camera-"+ident+".log")
    if any(x.exists() or x.is_symlink() for x in (result,image_path,log)):
        return {"exit_code":3,"stdout":"","stderr":"Existing capture result or frame ID; retry with a unique ID"}
    vulkan_icd=Path("/usr/share/vulkan/icd.d/lvp_icd.json")
    if not vulkan_icd.is_file() or vulkan_icd.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Software Vulkan driver not installed"}
    env=os.environ.copy()
    env["VK_ICD_FILENAMES"]=str(vulkan_icd)
    env["VK_DRIVER_FILES"]=str(vulkan_icd)
    env.update({"DISPLAY":":12","AARIS_SHOT_ID":ident,"AARIS_SHOT_ZONE":zone,
                "XDG_CACHE_HOME":str(BATCH_ROOT/"xdg-cache"),
                "TMPDIR":str(BATCH_ROOT/"temp"),
                "UPM_CACHE_ROOT":str(BATCH_ROOT/"upm-cache")})
    for name in ("xdg-cache","temp","upm-cache"):
        (BATCH_ROOT/name).mkdir(parents=True,exist_ok=True)
    cmd=[str(EDITOR),"-batchmode","-force-vulkan","-projectPath",str(project),
         "-executeMethod","Aaris.WorldAutomation.AarisMapCameraOneShot.Execute",
         "-logFile",str(log),"-job-worker-count","2"]
    with log.open("wb") as output:
        proc=subprocess.Popen(cmd,env=env,cwd=BATCH_ROOT,stdin=subprocess.DEVNULL,
                              stdout=output,stderr=output,start_new_session=True)
    deadline=time.monotonic()+120
    while time.monotonic()<deadline and not result.is_file():
        if proc.poll() is not None:
            break
        time.sleep(.7)
    if not result.is_file():
        with log.open("rb") as stream:
            stream.seek(max(0,log.stat().st_size-20000))
            logtext=stream.read().decode("utf-8","replace")
        errors=[x[-350:] for x in logtext.splitlines()
                if any(y in x for y in ("error CS","AARIS_UNITY_CAPTURE",
                    "Caught fatal signal","Segmentation fault","Exception"))]
        return {"exit_code":3,"stdout":json.dumps({
            "status":"unity_camera_no_capture","zone":zone,
            "unity_exit":proc.poll(),"diagnostics":errors[-12:],
            "last_log_lines":logtext[-850:]}),
            "stderr":"Unity could not render a verified authentic scene screenshot"}
    if result.is_symlink() or result.stat().st_size>11000:
        return {"exit_code":3,"stdout":"","stderr":"Invalid Unity capture metadata"}
    report=json.loads(result.read_text(encoding="utf-8"))
    if report.get("id")!=ident or report.get("zone")!=zone:
        return {"exit_code":3,"stdout":"","stderr":"Unity screenshot metadata identity mismatch"}
    if report.get("status")!="ok":
        return {"exit_code":3,"stdout":json.dumps(report)[:4000],
                "stderr":"Real Unity screenshot camera render failed"}
    if report.get("terrainComponents")!=4 or report.get("terrainInstances")!=7508:
        return {"exit_code":3,"stdout":"","stderr":"Screenshot does not show validated Unity terrain"}
    if not image_path.is_file() or image_path.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Unity-rendered JPEG not found"}
    data=image_path.read_bytes()
    if (len(data)!=report.get("jpegBytes") or len(data)<8000 or len(data)>1800000
        or hashlib.sha256(data).hexdigest()!=report.get("jpegSha256")
        or data[:3]!=bytes([255,216,255])):
        return {"exit_code":3,"stdout":"","stderr":"Unity JPEG bytes failed readback and SHA verification"}
    for _ in range(12):
        if proc.poll() is not None:break
        time.sleep(.4)
    return {"exit_code":0,"stdout":json.dumps({
        "status":"verified_real_unity_scene_capture","renderBackend":"software_vulkan",
        "zone":zone,"bytes":len(data),"sha256":report.get("jpegSha256"),
        "terrainInstances":report.get("terrainInstances"),
        "nativeAssetsMatchMergedMain":True,
        "imageFileName":image_path.name,"unityProcessExit":proc.poll()
    }),"stderr":""}


def unity_forest_one_shot(job):
    """Run one fully licensed real Unity Editor startup authoring transaction.

    Runs in isolated /tmp only, produces native .asset SHA256-backed output.
    Executes before rendering the heavy SceneView that crashes on this Xvfb GL.
    """
    op=job["operation"]
    ident=job["id"]
    apply=op=="unity_forest_one_shot_apply"
    args=job["args"]
    names={
        "1_1":"Terrain_1_1_4bf22c8f-eb55-436d-84e3-dedfa85665b1.asset",
        "1_2":"Terrain_1_2_1694bb0f-cffe-402c-b6f9-cf47692fbb78.asset",
        "2_1":"Terrain_2_1_82fc4922-5564-4a18-858e-787f6d901556.asset",
        "2_2":"Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset",
    }
    if apply:
        if len(args)!=2 or args[0] not in names or not re.fullmatch(r"[0-9a-f]{64}",args[1]):
            return {"exit_code":3,"stdout":"","stderr":"Exact tile key and SHA256 required"}
        target="Assets/TerrainDemoScene_URP/Terrain/Data/"+names[args[0]]
        digest=args[1]
    else:
        if args: return {"exit_code":3,"stdout":"","stderr":"Plan takes no args"}
        target="all"
        digest=""
    project=BATCH_ROOT/"project"
    source=Path("/workspaces/.aaris-world-bridge/ondemand/AarisForestOneShot.cs")
    destination=project/"Assets/AarisWorld/Editor/AarisForestOneShot.cs"
    helper=destination.with_name("AarisForestCoreAuthoring.cs")
    if not source.is_file() or source.is_symlink() or not helper.is_file() or helper.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Reviewed forest authoring and one-shot sources unavailable"}
    if not project.is_dir() or project.is_symlink() or not Path("/tmp/.X11-unix/X12").exists():
        return {"exit_code":3,"stdout":"","stderr":"Isolated Unity project or Xvfb unavailable"}
    if _scratch_unity_pids():
        return {"exit_code":3,"stdout":"","stderr":"Existing scratch Unity Editor must finish before one-shot"}
    if shutil.disk_usage(project).free<20*1024**3 or shutil.disk_usage(PROJECT).free<250*1024**2:
        return {"exit_code":3,"stdout":"","stderr":"Unsafe temporary or persistent disk headroom"}
    commands=VIRTUAL_CONTROL/"unity-commands"
    if commands.is_dir() and any(p.is_file() and p.suffix==".json" for p in commands.iterdir()):
        return {"exit_code":3,"stdout":"","stderr":"Unfinished Unity bridge command"}
    if apply:
        actual=hashlib.sha256((project/target).read_bytes()).hexdigest()
        if actual!=digest:
            return {"exit_code":3,"stdout":"","stderr":"Native TerrainData core SHA changed since plan"}
        original=PROJECT/target
        if not original.is_file() or original.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Owner core data identity cannot be checked"}
        for p in (original.with_suffix(".asset.meta"),(project/target).with_suffix(".asset.meta")):
            if not p.is_file() or p.is_symlink():
                return {"exit_code":3,"stdout":"","stderr":"Expected exact terrain GUID metadata missing"}
        if hashlib.sha256(original.with_suffix(".asset.meta").read_bytes()).hexdigest() != hashlib.sha256((project/target).with_suffix(".asset.meta").read_bytes()).hexdigest():
            return {"exit_code":3,"stdout":"","stderr":"TerrainData GUID metadata changed"}
    result=VIRTUAL_CONTROL/"unity-results"/(ident+".json")
    if result.exists() or result.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"One-shot result already exists"}
    if destination.is_symlink() or source.stat().st_size>10000:
        return {"exit_code":3,"stdout":"","stderr":"Untrusted one-shot scratch source"}
    content=source.read_bytes()
    if b"public static class AarisForestOneShot" not in content or b"EditorApplication.Exit" not in content:
        return {"exit_code":3,"stdout":"","stderr":"Unreviewed one-shot entrypoint"}
    if destination.exists():
        if destination.read_bytes()!=content:
            return {"exit_code":3,"stdout":"","stderr":"Scratch one-shot script differs, refuse overwrite"}
    else:
        destination.write_bytes(content)
        if destination.read_bytes()!=content:
            return {"exit_code":3,"stdout":"","stderr":"Scratch staging verification failed"}
    env=os.environ.copy()
    env.update({
        "DISPLAY":":12",
        "XDG_CACHE_HOME":str(BATCH_ROOT/"xdg-cache"),
        "TMPDIR":str(BATCH_ROOT/"temp"),
        "UPM_CACHE_ROOT":str(BATCH_ROOT/"upm-cache"),
        "AARIS_FOREST_JOB_ID":ident,
        "AARIS_FOREST_MODE":"apply" if apply else "plan",
        "AARIS_FOREST_TARGET":target,
        "AARIS_FOREST_SHA256":digest
    })
    for name in ("xdg-cache","temp","upm-cache"):
        (BATCH_ROOT/name).mkdir(parents=True,exist_ok=True)
    logfile=BATCH_ROOT/("forest-oneshot-"+ident+".log")
    if logfile.exists() or logfile.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"One-shot diagnostic log already exists"}
    argv=[str(EDITOR),"-projectPath",str(project),
          "-executeMethod","Aaris.WorldAutomation.AarisForestOneShot.Execute",
          "-logFile",str(logfile),"-job-worker-count","2"]
    with logfile.open("wb") as logfile_handle:
        proc=subprocess.Popen(argv,env=env,cwd=BATCH_ROOT,
                              stdin=subprocess.DEVNULL,
                              stdout=logfile_handle,stderr=logfile_handle,
                              start_new_session=True)
    end=time.monotonic()+105
    while time.monotonic()<end and not result.is_file():
        if proc.poll() is not None:
            break
        time.sleep(.75)
    if not result.is_file():
        with logfile.open("rb") as file:
            file.seek(max(0,logfile.stat().st_size-15000))
            raw=file.read().replace(bytes([0]),b"").decode("utf-8","replace")
        errors=[x[-350:] for x in raw.splitlines() if any(
            mark in x for mark in ("error CS","Exception","Caught fatal signal",
                                  "AARIS_FOREST","Compilation failed"))]
        return {"exit_code":3,"stdout":json.dumps({
            "status":"unity_oneshot_no_result",
            "pid":proc.pid,"process_exit":proc.poll(),
            "log_errors":errors[-10:],"log_tail":raw[-900:]}),
            "stderr":"Native Unity did not produce confirmed forest plan/save"}
    if result.is_symlink() or result.stat().st_size>120000:
        return {"exit_code":3,"stdout":"","stderr":"Unsafe native Unity one-shot result"}
    report=json.loads(result.read_text())
    if report.get("id")!=ident or report.get("action")!=("forest_apply" if apply else "forest_plan"):
        return {"exit_code":3,"stdout":"","stderr":"Native Unity result identity/action mismatch"}
    if report.get("status")!="ok":
        return {"exit_code":3,"stdout":json.dumps(report,ensure_ascii=False)[:11500],
                "stderr":"Unity refused native forest authoring"}
    if apply:
        if report.get("changedAsset")!=target or len(report.get("forestReports") or [])!=1:
            return {"exit_code":3,"stdout":"","stderr":"Invalid native changedAsset/readback report"}
        row=report["forestReports"][0]
        actual=hashlib.sha256((project/target).read_bytes()).hexdigest()
        if actual!=row.get("afterSha256") or digest!=row.get("beforeSha256"):
            return {"exit_code":3,"stdout":"","stderr":"Native .asset SHA256 after Unity save mismatch"}
        if row.get("changedCount",0)<1 or row.get("treeCount",0)<1:
            return {"exit_code":3,"stdout":"","stderr":"No changed trees on the native terrain tile"}
    else:
        if report.get("terrainTreeCount")!=7508 or len(report.get("forestReports") or [])!=4:
            return {"exit_code":3,"stdout":"","stderr":"Full-forest plan did not cover exactly 7508 trees"}
    for _ in range(15):
        if proc.poll() is not None: break
        time.sleep(.35)
    return {"exit_code":0,"stdout":json.dumps({
        "status":"native_unity_core_"+("saved" if apply else "planned"),
        "report":report,"process_exit":proc.poll(),"project_original_untouched":True,
        "unity_editor_pid":proc.pid},ensure_ascii=False)[:16500],"stderr":""}


def unity_forest_crash_report():
    """Read-only, redacted, bounded Unity compiler/crash and core-hash evidence."""
    data={"scratch_pids":_scratch_unity_pids(),
          "scene_readback":(BATCH_ROOT/"scene-readback.json").is_file(),
          "scratch_free_gib":round(shutil.disk_usage(BATCH_ROOT).free/2**30,2)}
    import hashlib
    import re
    import os
    markers=("error CS","AarisForestCoreAuthoring","AarisLiveEditorBridge",
             "Compilation failed","script compilation","Fatal","SIGSEGV",
             "Aborting batchmode","Asset Pipeline","Exception","crash","Exit")
    for leaf in ("virtual-editor.log","virtual-editor-forest.log","virtual-launch.log","xvfb.log"):
        p=BATCH_ROOT/leaf
        if not p.is_file() or p.is_symlink() or p.stat().st_size > 40*1024**2:
            data[leaf]={"available":False}
            continue
        with p.open("rb") as file:
            file.seek(max(0,p.stat().st_size-3*1024**2))
            fragment=file.read().replace(bytes([0]),b"")
        raw=fragment.decode("utf-8","replace")
        relevant=[line[-400:] for line in raw.splitlines() if any(x.lower() in line.lower() for x in markers)]
        data[leaf]={"bytes":p.stat().st_size,"markers":relevant[-35:],
                    "tail":raw[-1500:]}
    old=Path("/workspaces/.aaris-world-bridge/ondemand/unity-forest-recompile-proof.json")
    if old.is_file() and not old.is_symlink():
        proof=json.loads(old.read_text(encoding="utf-8"))
        data["recompile_phase"]=proof.get("phase")
        actual={}
        for name,sha in proof.get("tile_sha256",{}).items():
            p=BATCH_ROOT/"project/Assets/TerrainDemoScene_URP/Terrain/Data"/name
            if not p.is_file() or p.is_symlink():
                actual[name]="missing"
            else:
                h=hashlib.sha256()
                with p.open("rb") as file:
                    for part in iter(lambda:file.read(1024*1024),b""):h.update(part)
                actual[name]=h.hexdigest()==sha
        data["all_core_tiles_unchanged"]=all(actual.values()) if actual else False
        data["core_tile_sha_matches"]=actual
    # A GUI Editor can be terminated by the container OOM killer without a
    # useful Unity log. Inspect cgroup counters without mutating machine state.
    for name in ("memory.events","memory.max","memory.current","memory.peak"):
        for candidate in (Path("/sys/fs/cgroup")/name,
                          Path("/sys/fs/cgroup/memory")/name):
            if candidate.is_file() and not candidate.is_symlink():
                data["cgroup_"+name]=candidate.read_text(errors="replace")[:600]
                break
    for candidate in (
        Path("/home/codespace/.config/unity3d/Editor.log"),
        Path("/home/codespace/.local/share/unity3d/Editor.log"),
        Path("/home/codespace/.config/unity3d/Unity/Editor.log"),
    ):
        if not candidate.is_file() or candidate.is_symlink(): continue
        with candidate.open("rb") as stream:
            stream.seek(max(0,candidate.stat().st_size-200000))
            txt=stream.read().replace(bytes([0]),b"").decode("utf-8","replace")
        matches=[line[-420:] for line in txt.splitlines() if any(
            word in line.lower() for word in
            ("error cs","assembly reload","script compilation","fatal error",
             "exception","crash","segfault","out of memory"))]
        data["supplemental_unity_log"]={"file":candidate.name,
                   "hits":matches[-15:],"tail":txt[-550:]}
        break
    proc=subprocess.run(["free","-m"],capture_output=True,text=True,timeout=10)
    data["memory"]=proc.stdout[-900:]
    return {"exit_code":0,"stdout":json.dumps(data,ensure_ascii=False),"stderr":""}


def unity_forest_recompile():
    """Graceful restart only of the disposable scratch Unity GUI after verified save."""
    import signal
    from pathlib import Path
    target=BATCH_ROOT/"project"
    bridge=_virtual_bridge_path()
    helper=bridge.with_name("AarisForestCoreAuthoring.cs")
    if not all(x.is_file() and not x.is_symlink() for x in (bridge,helper)):
        return {"exit_code":3,"stdout":"","stderr":"Reviewed scratch forest sources missing"}
    source=bridge.read_text(encoding="utf-8")
    if 'case "forest_plan":' not in source or 'case "forest_apply":' not in source:
        return {"exit_code":3,"stdout":"","stderr":"Forest bridge not staged"}
    if not target.is_dir() or target.is_symlink() or not PROJECT.is_dir():
        return {"exit_code":3,"stdout":"","stderr":"Scratch and owner project identities missing"}
    if shutil.disk_usage(target).free < 20*1024**3:
        return {"exit_code":3,"stdout":"","stderr":"Scratch disk headroom below 20 GiB"}
    running=_scratch_unity_pids()
    if len(running)!=1:
        return {"exit_code":3,"stdout":json.dumps({"scratch_pids":running}),
                "stderr":"Exactly one running scratch GUI Unity process required"}
    pid=running[0]
    argv=[x.decode("utf-8","replace") for x in (Path("/proc")/str(pid)/"cmdline").read_bytes().split(b"\x00") if x]
    if "-projectPath" not in argv or argv[argv.index("-projectPath")+1]!=str(target):
        return {"exit_code":3,"stdout":"","stderr":"Scratch Unity process identity mismatch"}
    inbox=VIRTUAL_CONTROL/"unity-commands"
    if inbox.is_dir() and any(x.suffix==".json" and x.is_file() for x in inbox.iterdir()):
        return {"exit_code":3,"stdout":"","stderr":"Pending Unity commands; no relaunch"}
    autosync=Path("/workspaces/.aaris-world-bridge/ondemand/unity_batched_autosync.py")
    if not autosync.is_file() or autosync.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Autosync verifier unavailable"}
    audit=subprocess.run(["python3",str(autosync),"status"],text=True,capture_output=True,timeout=35)
    if audit.returncode:
        return {"exit_code":3,"stdout":"","stderr":"Autosync check failed"}
    status=json.loads(audit.stdout)
    if status.get("pending")!=0 or status.get("pending_unity_commands")!=0:
        return {"exit_code":3,"stdout":json.dumps(status)[:1000],
                "stderr":"Unsaved native edits present"}
    directory=target/"Assets/TerrainDemoScene_URP/Terrain/Data"
    tiles=[
        "Terrain_1_1_4bf22c8f-eb55-436d-84e3-dedfa85665b1.asset",
        "Terrain_1_2_1694bb0f-cffe-402c-b6f9-cf47692fbb78.asset",
        "Terrain_2_1_82fc4922-5564-4a18-858e-787f6d901556.asset",
        "Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset",
    ]
    hashes={}
    for name in tiles:
        src=directory/name
        if not src.is_file() or src.is_symlink() or src.stat().st_size < 1024*1024:
            return {"exit_code":3,"stdout":"","stderr":"Missing original native terrain asset: "+name}
        h=hashlib.sha256()
        with src.open("rb") as file:
            for chunk in iter(lambda:file.read(1024*1024),b""): h.update(chunk)
        hashes[name]=h.hexdigest()
    proof=Path("/workspaces/.aaris-world-bridge/ondemand/unity-forest-recompile-proof.json")
    if proof.exists() or proof.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Prior forest relaunch checkpoint requires review"}
    checkpoint={"scratch":str(target),"old_pid":pid,
                "tile_sha256":hashes,"phase":"before_graceful_stop"}
    proof.write_text(json.dumps(checkpoint,sort_keys=True),encoding="utf-8")
    os.kill(pid,signal.SIGTERM)
    for _ in range(85):
        if pid not in _scratch_unity_pids(): break
        time.sleep(.55)
    if pid in _scratch_unity_pids():
        return {"exit_code":3,"stdout":"","stderr":"Unity did not exit gracefully; no forced stop performed"}
    checkpoint["phase"]="scratch_editor_exited"
    proof.write_text(json.dumps(checkpoint,sort_keys=True),encoding="utf-8")
    launched=unity_virtual_gui_launch()
    checkpoint["phase"]="relaunch_called"
    checkpoint["relaunch_exit_code"]=launched["exit_code"]
    checkpoint["new_pids"]=_scratch_unity_pids()
    proof.write_text(json.dumps(checkpoint,sort_keys=True),encoding="utf-8")
    if launched["exit_code"]!=0: return launched
    return {"exit_code":0,"stdout":json.dumps({
        "status":"scratch_gui_unity_relaunched_for_compile",
        "old_pid":pid,"new_pids":_scratch_unity_pids(),
        "tile_sha256_before":hashes,"original_worktree_untouched":True,
        "note":"Check editor import and all tile hashes before full-forest plan"
    }),"stderr":""}


def unity_forest_x11_probe():
    if not _scratch_unity_pids() or not Path("/tmp/.X11-unix/X12").exists():
        return {"exit_code":3,"stdout":"","stderr":"No verified scratch Unity process/display"}
    import ctypes.util
    info={"scratch_pids":_scratch_unity_pids(),
          "x11_library_available":bool(ctypes.util.find_library("X11")),
          "xtest_library_available":bool(ctypes.util.find_library("Xtst"))}
    if not shutil.which("xwininfo"):
        return {"exit_code":3,"stdout":"","stderr":"No xwininfo"}
    x=subprocess.run(["xwininfo","-display",":12","-root","-tree"],
                     capture_output=True,text=True,timeout=12,check=False)
    info["xwininfo_exit"]=x.returncode
    interesting=[line.strip()[-400:] for line in x.stdout.splitlines()
                 if "Unity" in line or "unity" in line]
    info["possible_unity_windows"]=interesting[:15]
    info["window_count"]=len(x.stdout.splitlines())
    for line in interesting[:8]:
        match=re.search(r"0x[0-9a-fA-F]+",line)
        if not match or not shutil.which("xprop"): continue
        p=subprocess.run(["xprop","-display",":12","-id",match.group(0),
                          "_NET_WM_PID","WM_NAME"],capture_output=True,
                         text=True,timeout=8,check=False)
        info.setdefault("window_properties",[]).append({
            "id":match.group(0),"properties":p.stdout[-500:]})
    return {"exit_code":0,"stdout":json.dumps(info,ensure_ascii=False),"stderr":""}


def unity_forest_stage():
    """Stage reviewed one-time forest authoring into *scratch Unity Editor only*.

    Never write owner original or commit the editor helper as the map result.
    Checked exact bridge source and /tmp backup permit rollback on failed stage.
    """
    if not _scratch_unity_pids() or not (BATCH_ROOT/"scene-readback.json").is_file():
        return {"exit_code":3,"stdout":"","stderr":"Live scratch Unity scene not confirmed"}
    stage=Path("/workspaces/.aaris-world-bridge/ondemand")
    bridge_reference=stage/"AarisLiveEditorBridge.cs"
    helper=stage/"AarisForestCoreAuthoring.cs"
    target=_virtual_bridge_path()
    helper_target=target.with_name("AarisForestCoreAuthoring.cs")
    if not all(x.is_file() and not x.is_symlink() for x in (bridge_reference,helper,target)):
        return {"exit_code":3,"stdout":"","stderr":"Reviewed staging sources or scratch Unity bridge unavailable"}
    if helper_target.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Unsafe scratch helper symlink"}
    old_root='private static readonly string Root = "/home/codespace/.aaris-desktop";'
    scratch_root='private static readonly string Root = "/tmp/aaris-unity-batch/control";'
    baseline=bridge_reference.read_text(encoding="utf-8")
    if baseline.count(old_root)!=1:
        return {"exit_code":3,"stdout":"","stderr":"Unexpected reviewed bridge source"}
    expected=baseline.replace(old_root,scratch_root)
    saved=target.read_text(encoding="utf-8")
    patch=[
      ('public string id, action, target;','public string id, action, target, expectedDigest;'),
      ('public Item[] nearbyObjects, nearbyTerrainTrees;',
       'public Item[] nearbyObjects, nearbyTerrainTrees;\\n            public AarisForestCoreAuthoring.ForestReport[] forestReports;'),
      ('case "capture": Capture(request, result); break;',
       'case "forest_plan": AarisForestCoreAuthoring.Run(request, result, false); break;\\n'
       '                    case "forest_apply": AarisForestCoreAuthoring.Run(request, result, true); break;\\n'
       '                    case "capture": Capture(request, result); break;'),
    ]
    revised=expected
    for before,after in patch:
        if revised.count(before)!=1:
            return {"exit_code":3,"stdout":"","stderr":"Reviewed scratch bridge patch anchor mismatch"}
        revised=revised.replace(before,after.replace("\\n","\n"))
    desired=helper.read_bytes()
    if not desired.startswith(b"// One-time *Editor-only* forest core authoring.") or len(desired)>40000:
        return {"exit_code":3,"stdout":"","stderr":"Unreviewed forest authoring source"}
    if saved==revised and helper_target.is_file() and helper_target.read_bytes()==desired:
        return {"exit_code":0,"stdout":json.dumps({"status":"forest_helper_already_staged",
                "source_original_untouched":True,"scratch_only":True}),"stderr":""}
    if saved!=expected or helper_target.exists():
        return {"exit_code":3,"stdout":"","stderr":"Scratch Editor sources differ from approved baseline; refuse overwrite"}
    backup=BATCH_ROOT/"forest-native-authoring-backup"
    if backup.exists() or backup.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Prior forest stage backup needs inspection"}
    backup.mkdir(mode=0o700)
    backup_bridge=backup/target.name
    shutil.copy2(target,backup_bridge)
    updated=False
    try:
        fresh=target.with_suffix(".cs.aaris-forest-new")
        if fresh.exists() or fresh.is_symlink(): raise ValueError("Scratch temp already exists")
        fresh.write_text(revised,encoding="utf-8")
        os.replace(fresh,target)
        updated=True
        helper_target.write_bytes(desired)
        if target.read_text(encoding="utf-8")!=revised or helper_target.read_bytes()!=desired:
            raise ValueError("Staged Unity Editor source readback mismatch")
    except BaseException:
        if helper_target.exists(): helper_target.unlink()
        if updated: shutil.copy2(backup_bridge,target)
        raise
    return {"exit_code":0,"stdout":json.dumps({
        "status":"forest_authoring_staged_in_running_scratch_editor",
        "helper":"Assets/AarisWorld/Editor/AarisForestCoreAuthoring.cs",
        "source_original_untouched":True,"scratch_only":True,
        "note":"Unity auto compilation must complete before forest_plan"}),"stderr":""}


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



RECOVERY_SCRIPT=Path("/workspaces/.aaris-world-bridge/ondemand/unity_session_checkpoint.py")
RECOVERY_STATE=Path("/workspaces/.aaris-world-bridge/ondemand/unity-session-checkpoint.json")


def _session_plan(save=False):
    if RECOVERY_SCRIPT.is_symlink() or not RECOVERY_SCRIPT.is_file():
        raise ValueError("Reviewed restart checkpoint script not staged")
    cmd=["python3",str(RECOVERY_SCRIPT),"--original",str(PROJECT),
         "--scratch",str(BATCH_ROOT/"project"),
         "--editor",str(EDITOR),"--state-file",str(RECOVERY_STATE)]
    if save:
        cmd.append("--checkpoint")
    result=subprocess.run(cmd,text=True,capture_output=True,
                          timeout=40,check=False)
    if result.returncode:
        raise ValueError("Unity restart checkpoint failed: "+result.stdout[-300:])
    return json.loads(result.stdout)


def _stage_resume_camera(target):
    if not isinstance(target,dict) or set(target)!={"x","y","z"}:
        return None
    if not all(isinstance(target[k],(int,float)) and
               abs(target[k])<=10000 for k in ("x","y","z")):
        return None
    virtual_bridge_isolate()
    info={"action":"inspect","cameraTarget":target,"radius":20,"limit":12}
    validate_live_payload(info)
    ident="unity-resume-view-"+str(int(time.time()))
    file=VIRTUAL_CONTROL/"unity-commands"/(ident+".json")
    if file.exists():
        return None
    with file.open("x") as stream:
        stream.write(json.dumps(dict(info,id=ident),separators=(",",":")))
    return ident


def _restart_rebuild_worker():
    """Recreate only a lost /tmp scratch project; never run licensed headless mode."""
    try:
        if BATCH_ROOT.exists():
            raise RuntimeError("Existing scratch root could contain edits; do not overwrite")
        if shutil.disk_usage(PROJECT).free < 250*1024**2:
            raise RuntimeError("Original persistent disk below guarded free-space threshold")
        if shutil.disk_usage(Path("/tmp")).free < 20*1024**3:
            raise RuntimeError("Separate /tmp lacks safe reimport headroom")
        BATCH_ROOT.mkdir(mode=0o700)
        _batch_write("recreating_scratch_after_codespace_stop")
        target=BATCH_ROOT/"project"
        target.mkdir()
        for folder in ("Assets","Packages","ProjectSettings"):
            src=PROJECT/folder
            if src.is_symlink() or not src.is_dir():
                raise RuntimeError("Source directory unavailable or symlinked: "+folder)
            for base,dirs,files in os.walk(src,followlinks=False):
                for entry in dirs+files:
                    if (Path(base)/entry).is_symlink():
                        raise RuntimeError("Unexpected source symlink, refuse scratch copy")
            shutil.copytree(src,target/folder,symlinks=False)
        if shutil.disk_usage(BATCH_ROOT).free < 20*1024**3:
            raise RuntimeError("Insufficient scratch headroom after copying")
        probe=target/"Assets/Editor/AarisBatchProbe.cs"
        if not BATCH_CS.is_file() or BATCH_CS.is_symlink() or probe.exists():
            raise RuntimeError("Reviewed Unity scene probe unavailable or conflicting")
        probe.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(BATCH_CS,probe)
        virtual_bridge_isolate()  # BEFORE Editor compilation: never read original bridge queue
        preflight=_session_plan()
        if not preflight.get("scratch_core_matches"):
            raise RuntimeError("Scratch copy differs from original core; refusing launch")
        marker=BATCH_ROOT/".aaris-scratch-copy-complete.json"
        if marker.exists() or marker.is_symlink():
            raise RuntimeError("Unexpected scratch copy marker, refusing overwrite")
        # Only after every copytree and staged bridge succeeds, atomically mark
        # an isolated /tmp copy as complete. Never write in original Assets.
        proof={"schema":1,
               "scene":"Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity",
               "source_sha256":preflight["source_sha256"]}
        staged=marker.with_suffix(".new")
        if staged.exists() or staged.is_symlink():
            raise RuntimeError("Stale scratch completion marker staging")
        staged.write_text(json.dumps(proof,ensure_ascii=False))
        os.replace(staged,marker)
        snapshot=_session_plan()
        if snapshot["step"]!="reopen_existing_scratch":
            raise RuntimeError("Source fingerprint mismatch after scratch clone: "+snapshot["step"])
        view=_stage_resume_camera(snapshot.get("last_camera_target"))
        _batch_write("scratch_recreated",resume_view_job=view,
                     note="New Unity Library import required: Codespace cleared /tmp")
        launch=unity_virtual_gui_launch() # licensed normal GUI, hidden Xvfb, no noVNC
        if launch["exit_code"]!=0:
            raise RuntimeError("Unity virtual Editor restart refused: "+launch["stderr"][:400])
    except Exception as exc:
        _batch_write("recovery_failed",error=type(exc).__name__+": "+str(exc)[:450])
    return 0


def unity_session_recover():
    """Idempotent owner-only restore when a GitHub AI job wakes the Codespace."""
    snapshot=_session_plan()
    step=snapshot.get("step")
    if step=="already_running":
        try:
            updated=_session_plan(save=True)
        except ValueError as exc:
            return {"exit_code":3,"stdout":json.dumps(snapshot),
                    "stderr":"Live Editor exists but checkpoint failed: "+str(exc)}
        return {"exit_code":0,"stdout":json.dumps({
            "status":"already_running","checkpoint_saved":True,
            "original_untouched":True,"details":updated}),"stderr":""}
    if step=="reopen_existing_scratch":
        try:
            virtual_bridge_isolate()
            view=_stage_resume_camera(snapshot.get("last_camera_target"))
            result=unity_virtual_gui_launch()
            if result["exit_code"]!=0:
                return result
            return {"exit_code":0,"stdout":json.dumps({
                "status":"reopened_existing_scratch","resume_view_job":view,
                "original_untouched":True,"details":unity_virtual_gui_status()}),"stderr":""}
        except (OSError,ValueError) as exc:
            return {"exit_code":3,"stdout":json.dumps(snapshot),
                    "stderr":"Existing scratch restore blocked: "+str(exc)[:350]}
    if step=="recreate_scratch_and_reimport":
        if BATCH_ROOT.exists():
            return {"exit_code":3,"stdout":json.dumps(snapshot),
                    "stderr":"Partial scratch root exists; requires inspection, not deletion"}
        out=BATCH_META.parent/"unity-rebuild-worker.log"
        with out.open("a") as stream:
            worker=subprocess.Popen(
                [sys.executable,str(Path(__file__).resolve()),"--unity-rebuild-worker"],
                cwd=Path("/tmp"),stdin=subprocess.DEVNULL,
                stdout=stream,stderr=stream,start_new_session=True)
        return {"exit_code":0,"stdout":json.dumps({
            "status":"scratch_reimport_started","worker_pid":worker.pid,
            "reason":"Codespace /tmp cleared; old imported Library cannot be resumed",
            "original_untouched":True,
            "previous_checkpoint":snapshot.get("previous_checkpoint_at"),
            "last_camera_target":snapshot.get("last_camera_target")}),"stderr":""}
    return {"exit_code":3,"stdout":json.dumps(snapshot),
            "stderr":"Recovery guard refused to launch: "+str(step)}


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
        "forest_plan":{"target"},
        "forest_apply":{"target","expectedDigest"},
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
    if action=="forest_plan" and value.get("target")!="all":
        raise ValueError("Only whole-map native forest plan is allowed")
    if action=="forest_apply":
        asset=value.get("target")
        if not isinstance(asset,str) or not re.fullmatch(
            r"Assets/TerrainDemoScene_URP/Terrain/Data/Terrain_[a-zA-Z0-9_-]+\.asset", asset
        ):
            raise ValueError("Forest writes are restricted to existing TerrainData .asset")
        if not isinstance(value.get("expectedDigest"),str) or not re.fullmatch(
            r"[a-f0-9]{64}",value["expectedDigest"]
        ):
            raise ValueError("Exact fresh Unity SHA256 required for forest write")
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


def unity_house_gallery(job):
    """Native Editor-only screenshot survey; never write original Unity assets."""
    import zipfile
    import csv
    import io
    op=job["operation"]
    ident=job["id"]
    root=BATCH_ROOT/"project"
    stage=Path("/workspaces/.aaris-world-bridge/ondemand/AarisHousePhotoSurvey.cs")
    target=root/"Assets/AarisWorld/Editor/AarisHousePhotoSurvey.cs"
    requests=VIRTUAL_CONTROL/"house-requests"
    reports=VIRTUAL_CONTROL/"house-results"
    exports=VIRTUAL_CONTROL/"house-exports"
    if not root.is_dir() or root.is_symlink() or len(_scratch_unity_pids())!=1:
        return {"exit_code":3,"stdout":"","stderr":"Isolated live Unity Editor unavailable"}
    if op=="unity_house_gallery_diagnose":
        info=VIRTUAL_CONTROL/"house-results"/(job["args"][0]+".json")
        query=VIRTUAL_CONTROL/"house-requests"/(job["args"][0]+".json")
        log=BATCH_ROOT/"virtual-editor-forest.log"
        if not log.exists(): log=BATCH_ROOT/"virtual-editor.log"
        matched=[]
        if log.is_file() and not log.is_symlink():
            with log.open("rb") as stream:
                stream.seek(max(0,log.stat().st_size-18*1024*1024))
                data=stream.read().decode("utf-8","replace")
            matched=[x[:400] for x in data.splitlines() if
                     any(w in x for w in ("AarisHousePhotoSurvey","AARIS_HOUSE_","error CS","Compilation failed","Script Compilation"))][-30:]
        source=stage.read_bytes() if stage.is_file() else b""
        dest=target.read_bytes() if target.is_file() else b""
        return {"exit_code":0,"stdout":json.dumps({
            "queued_house_request":query.exists(),"house_result":info.exists(),
            "house_result_text":info.read_text()[:4500] if info.is_file() else None,
            "house_editor_source_installed":target.is_file(),"source_match":source==dest,
            "photos_dir_exists":(VIRTUAL_CONTROL/"house-photos"/job["args"][0]).is_dir(),
            "photos_so_far":len(list((VIRTUAL_CONTROL/"house-photos"/job["args"][0]).glob("*.jpg"))) if (VIRTUAL_CONTROL/"house-photos"/job["args"][0]).is_dir() else 0,
            "unity_pids":_scratch_unity_pids(),"editor_compiler_evidence":matched
        }),"stderr":""}
    if op=="unity_house_gallery_start":
        if job["args"]:
            raise ValueError("House gallery start takes no arguments")
        if not stage.is_file() or stage.is_symlink() or stage.stat().st_size>250000:
            return {"exit_code":3,"stdout":"","stderr":"Trusted staged house photo Editor helper missing"}
        data=stage.read_bytes()
        if b"public static class AarisHousePhotoSurvey" not in data or b"SubmitRenderRequest" not in data:
            return {"exit_code":3,"stdout":"","stderr":"Unreviewed house photo helper"}
        if not target.parent.is_dir() or target.parent.is_symlink() or target.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Unsafe scratch editor helper target"}
        if target.exists() and target.read_bytes()!=data:
            return {"exit_code":3,"stdout":"","stderr":"Existing different house helper; preserve and inspect"}
        if not target.exists():
            tmp=target.with_name(target.name+".aaris-staged")
            if tmp.exists() or tmp.is_symlink():
                return {"exit_code":3,"stdout":"","stderr":"House helper stage conflict"}
            tmp.write_bytes(data)
            if hashlib.sha256(tmp.read_bytes()).digest()!=hashlib.sha256(data).digest():
                raise ValueError("House helper SHA verification failed")
            os.replace(tmp,target)
        for directory in (requests,reports,exports):
            directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        req=requests/(ident+".json")
        answer=reports/(ident+".json")
        if req.exists() or req.is_symlink() or answer.exists() or answer.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"House photo job already submitted"}
        req.write_text(json.dumps({"id":ident})+"\n")
        return {"exit_code":0,"stdout":json.dumps({
            "job":ident,"queued":True,"isolated_unity_editor":True,
            "scratch_only":True,"game_source_unchanged":True,
            "expected_photos":15,"editor_helper_sha256":hashlib.sha256(data).hexdigest(),
            "note":"Unity compiles read-only editor helper and renders real houses asynchronously"
        }),"stderr":""}
    if op!="unity_house_gallery_export" or len(job["args"])!=1:
        raise ValueError("House photo export operation requires one job ID")
    survey=job["args"][0]
    if not re.fullmatch(r"[a-z][a-z0-9-]{3,55}",survey):
        raise ValueError("Invalid house survey identifier")
    info=reports/(survey+".json")
    if not info.is_file() or info.is_symlink():
        return {"exit_code":3,"stdout":json.dumps({"job":survey,"pending":True}),
                "stderr":"Unity house survey is still compiling or rendering"}
    if info.stat().st_size>300000:
        return {"exit_code":3,"stdout":"","stderr":"Oversized survey manifest"}
    result=json.loads(info.read_text())
    if result.get("id")!=survey or result.get("status")!="ok":
        return {"exit_code":3,"stdout":json.dumps({
            "id":survey,"status":result.get("status"),"found_houses":result.get("candidatesFound"),
            "error":result.get("error"),"pictures":result.get("picturesMade")}),
            "stderr":"Unity native house survey failed or returned no valid report"}
    houses=result.get("houses") or []
    photos=result.get("photos") or []
    if not 10<=len(photos)<=20 or not 1<=len(houses)<=3:
        return {"exit_code":3,"stdout":"","stderr":"Expected at least ten verified shots and 1-3 real houses"}
    gallery=VIRTUAL_CONTROL/"house-photos"/survey
    if gallery.is_symlink() or not gallery.is_dir():
        return {"exit_code":3,"stdout":"","stderr":"Missing house gallery photo folder"}
    archive=exports/(survey+".zip")
    if archive.exists() or archive.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Previous house gallery export needs review"}
    total=0
    seen=set()
    entries=[]
    for item in photos:
        leaf=item.get("file")
        if (not isinstance(leaf,str) or not re.fullmatch(r"[a-zA-Z0-9-]{6,100}\.jpg",leaf) or leaf in seen):
            return {"exit_code":3,"stdout":"","stderr":"Untrusted house photo filename"}
        seen.add(leaf)
        path=gallery/leaf
        if not path.is_file() or path.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"House photo missing"}
        data=path.read_bytes()
        digest=hashlib.sha256(data).hexdigest()
        if len(data)!=item.get("bytes") or digest!=item.get("sha256") or not data.startswith(b"\xff\xd8"):
            return {"exit_code":3,"stdout":"","stderr":"House photo hash/size validation failed"}
        total+=len(data)
        entries.append((leaf,data))
    if total>30*1024*1024:
        return {"exit_code":3,"stdout":"","stderr":"Unexpectedly large house survey images"}
    readme=[
        "UNITY GAME ARIS - REAL HOUSE PHOTOS",
        "Unity Editor version: "+str(result.get("unityVersion")),
        "Scene: "+str(result.get("scene")),
        "Measurements below are renderer world-axis AABB extents, in metres.",
        "They do not prove interior walkability or a finished furnished room.",
        "The 'inside-volume' camera is inside the model's external 3D bounds;",
        "walls/roof can obstruct the camera if interiors are not implemented.",
        "No source/game files were edited to create these screenshots.",
        "",
    ]
    for i,house in enumerate(houses,1):
        readme.append(f"House {i}: {house.get('name')}")
        for k in ("widthXMetres","lengthZMetres","heightMetres","bottomY","topY","prefabPath","renderers","colliders"):
            readme.append(f"  {k}: {house.get(k)}")
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        z.writestr("HOUSE_DIMENSIONS.txt","\n".join(readme)+"\n")
        z.writestr("HOUSE_SURVEY.json",json.dumps(result,indent=2))
        for leaf,data in entries:
            z.writestr("photos/"+leaf,data)
    return {"exit_code":0,"stdout":json.dumps({
      "survey_id":survey,"status":"ok","houses":houses,"views":[
          {"file":x["file"],"house":x["houseName"],"view":x["view"]} for x in photos],
      "pictures":len(photos),"bytes":archive.stat().st_size,
      "sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),
      "archive_path":str(archive),"game_source_untouched":True,
      "note":"Gallery ZIP contains real Unity JPGs, house measurements and JSON"
    },ensure_ascii=False),"stderr":""}


def unity_main_core_sync(job):
    """Import precisely reviewed merged source to disposable Unity Editor only.

    Actions stages files pinned to a single main commit; never run git in the
    owner's dirty checkout or overwrite anything under /workspaces/Unity-Game-Aris.
    Reject any unexpected scratch changes. SHA-verify inputs and final readback.
    """
    import tarfile
    from pathlib import PurePosixPath
    import io
    commit=job["args"][0]
    if not re.fullmatch(r"[0-9a-f]{40}",commit):
        raise ValueError("Expected reviewed main 40-character SHA")
    stage=Path("/workspaces/.aaris-world-bridge/ondemand")/("main-core-"+job["id"]+".tar")
    scratch=BATCH_ROOT/"project"
    backup=BATCH_ROOT/("main-core-backup-"+job["id"])
    source_root="Assets/TerrainDemoScene_URP/Prefabs/Trees/"
    leaves=tuple(
        source_root+folder+"/Materials/"+name+".mat"
        for folder,items in (
          ("Conifer",("Conifer_Branches","Conifer_Billboard")),
          ("Cypress",("Cypress_Forest_Desktop","Cypress_Forest_Desktop_Billboard")),
          *((f"Pines/Pine_{x}",(f"Pine_{x}",f"Pine_{x}_Billboard")) for x in "ABCD"),
        ) for name in items
    )
    prefabs=tuple(source_root+stem+".prefab" for stem in
        ("Conifer/Conifer","Cypress/Cypress_Forest_Desktop",
         *(f"Pines/Pine_{x}/Pine_{x}" for x in "ABCD")))
    player="Assets/AarisWorld/Scripts/AarisThirdPersonPlayer.cs"
    required=leaves+prefabs+(player,)
    checks=(
        "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity",
        "ProjectSettings/QualitySettings.asset",
        "ProjectSettings/GraphicsSettings.asset",
        "Packages/manifest.json",
    )
    original_prefab_sha={
      prefabs[0]:"fa9d9cc07822b938ef5ba29bfa20eab7ce25de10",
      prefabs[1]:"65c18f7e3449f24240f6a52a33182991eda3d80e",
      prefabs[2]:"f91d80bab50c2ef0cdc816fc0a5f0f30036b6f5f",
      prefabs[3]:"526af9d0f166ca774cfe61b0d6906c11483929fc",
      prefabs[4]:"959a20643bb07c39f9553623133eca7affa81ffb",
      prefabs[5]:"344363e72f13f909c3cca8ad036491484c2a7373",
      player:"c3f07233825b9ca94ef2f19b3a63f78c9e54e318",
    }
    old_shader=b"d4fdc026464a42041be7fe785babd90e"
    new_shader=b"9920c1f1781549a46ba081a2a15a16ec"
    def sha256(data): return hashlib.sha256(data).hexdigest()
    def blob(data):
        return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
    if not stage.is_file() or stage.is_symlink() or stage.stat().st_size>8*1024*1024:
        return {"exit_code":3,"stdout":"","stderr":"Trusted exact-main core bundle missing or oversized"}
    if not scratch.is_dir() or scratch.is_symlink() or backup.exists() or backup.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Scratch identity or backup conflict"}
    if len(_scratch_unity_pids())!=1 or not (BATCH_ROOT/"scene-readback.json").is_file():
        return {"exit_code":3,"stdout":"","stderr":"Exactly one live isolated Unity Editor and loaded scene required"}
    if shutil.disk_usage(scratch).free<12*1024**3:
        return {"exit_code":3,"stdout":"","stderr":"Insufficient temporary Unity disk headroom"}
    # Verify source files and all project-level snapshot checks before ANY write.
    files={}
    try:
        with tarfile.open(stage,"r") as tar:
            members=tar.getmembers()
            allowed={"manifest.json"}|{"source/"+p for p in required}
            if {m.name for m in members} != allowed or len(members)!=len(allowed):
                raise ValueError("Bundle contains unreviewed files")
            if any(not m.isfile() or m.size>8*1024*1024 or m.name.startswith("/")
                   or ".." in PurePosixPath(m.name).parts for m in members):
                raise ValueError("Invalid bundle member")
            manifest=json.load(tar.extractfile("manifest.json"))
            if manifest.get("commit")!=commit or set(manifest.get("files",{}))!=set(required) or set(manifest.get("checks",{}))!=set(checks):
                raise ValueError("Unexpected main core commit or path manifest")
            for rel in required:
                data=tar.extractfile("source/"+rel).read()
                if sha256(data)!=manifest["files"][rel]:
                    raise ValueError("Bundle hash mismatch: "+rel)
                files[rel]=data
    except (OSError,tarfile.TarError,ValueError,KeyError,TypeError) as e:
        return {"exit_code":3,"stdout":"","stderr":"Invalid approved main bundle: "+str(e)[:180]}
    mismatches=[]
    for rel in checks:
        candidate=scratch/rel
        if candidate.is_symlink() or not candidate.is_file():
            mismatches.append(rel+":missing")
        else:
            with candidate.open("rb") as stream:
                h=hashlib.sha256()
                for chunk in iter(lambda:stream.read(1024*1024),b""):h.update(chunk)
            if h.hexdigest()!=manifest["checks"][rel]:
                mismatches.append(rel+":snapshot-drift")
    # Do not overwrite pre-existing owner-authored scene/settings differences.
    # Report them, but permit the 19 independently verified source files to
    # reimport if each of those files matches its exact reviewed historical blob.
    expected_drift={
        "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity:snapshot-drift",
        "ProjectSettings/QualitySettings.asset:snapshot-drift",
        "ProjectSettings/GraphicsSettings.asset:snapshot-drift",
    }
    if not set(mismatches)<=expected_drift:
        return {"exit_code":3,"stdout":json.dumps({"read_only_snapshot_errors":mismatches}),
                "stderr":"Unexpected non-target baseline drift; no source writes"}
    changes=[]
    conflicts=[]
    for rel in required:
        dst=scratch/rel
        owner=PROJECT/rel
        if (not dst.is_file() or dst.is_symlink() or not owner.is_file() or owner.is_symlink()):
            return {"exit_code":3,"stdout":"","stderr":"Missing/symlinked core destination: "+rel}
        if rel.startswith("Assets/"):
            meta=rel+".meta"
            a=scratch/meta
            b=PROJECT/meta
            if not a.is_file() or a.is_symlink() or not b.is_file() or b.is_symlink() or a.read_bytes()!=b.read_bytes():
                return {"exit_code":3,"stdout":"","stderr":"Core GUID meta drift: "+rel}
        current=dst.read_bytes()
        desired=files[rel]
        if current==desired: continue
        if rel in leaves:
            expected=desired.replace(new_shader,old_shader)
            if desired.count(new_shader)!=1 or len(expected)!=len(desired) or current!=expected:
                return {"exit_code":3,"stdout":"","stderr":"Unreviewed tree material preview modification: "+rel}
        elif blob(current)!=original_prefab_sha[rel]:
            # Existing scratch Unity data is not an approved historical baseline.
            # Do not overwrite it and do not claim a full-main reimport.
            conflicts.append({"file":rel,"scratch_blob":blob(current),
                              "expected_historical_blob":original_prefab_sha[rel]})
            continue
        changes.append((rel,dst,current,desired))
    backup.mkdir(parents=True,mode=0o700)
    backup_manifest={"commit":commit,"paths":{},"read_only_checks":manifest["checks"]}
    for rel,dst,before,after in changes:
        output=backup/rel
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(before)
        if sha256(output.read_bytes())!=sha256(before):
            return {"exit_code":3,"stdout":"","stderr":"Backup verification failed: "+rel}
        backup_manifest["paths"][rel]={"old_sha256":sha256(before),"new_sha256":sha256(after)}
    (backup/"manifest.json").write_text(json.dumps(backup_manifest,indent=2))
    done=[]
    try:
        for rel,dst,old,updated in changes:
            tmp=dst.with_name(dst.name+".aaris-main-sync")
            if tmp.exists() or tmp.is_symlink():
                raise ValueError("Existing temp target: "+rel)
            tmp.write_bytes(updated)
            if sha256(tmp.read_bytes())!=sha256(updated):
                raise ValueError("Scratch staging readback mismatch: "+rel)
            os.replace(tmp,dst)
            done.append((dst,old))
        conflict_paths={row["file"] for row in conflicts}
        for rel in required:
            if rel in conflict_paths: continue
            if sha256((scratch/rel).read_bytes())!=manifest["files"][rel]:
                raise ValueError("Merged main sync readback mismatch: "+rel)
    except BaseException:
        for dst,previous in reversed(done):
            dst.write_bytes(previous)
        raise
    stage.unlink()
    return {"exit_code":0,"stdout":json.dumps({
      "source_main_commit":commit,"scratch_only":True,"owner_worktree_untouched":True,
      "total_reviewed_core_files":len(required),"changed_core_count":len(changes),
      "changed_paths":[rel for rel,_,_,_ in changes],
      "all_19_exact_main_bytes":not bool(conflicts),
      "all_12_foliage_materials_exact_main":all(
          sha256((scratch/p).read_bytes())==manifest["files"][p] for p in leaves),
      "conflicts_preserved_unchanged":conflicts,
      "verified_current_main_core_count":len(required)-len(conflicts),
      "scene_pipeline_unchanged":True,
      "scene_pipeline_preexisting_drift":mismatches,
      "full_project_matches_main":not bool(mismatches),
      "backup_path":str(backup),
      "next_gate":"Unity Editor asset reimport, shader material check and matched camera capture"
    },ensure_ascii=False),"stderr":""}


def unity_shader_ab_probe(operation):
    """Bounded A/B: change only twelve isolated scratch leaf material shader GUIDs.

    Never write owner source, scene, .meta, imported tree meshes, TerrainData or git.
    Exact material bytes and per-file SHA256 are retained for an atomic restore.
    """
    import hashlib
    if operation not in ("preflight", "apply", "restore"):
        raise ValueError("Unsupported shader A/B action")
    root = BATCH_ROOT/"project"
    stage = BATCH_ROOT/"shader-foliage-ab"
    prior = "m_Shader: {fileID: -6465566751694194690, guid: d4fdc026464a42041be7fe785babd90e, type: 3}"
    candidate = "m_Shader: {fileID: -6465566751694194690, guid: 9920c1f1781549a46ba081a2a15a16ec, type: 3}"
    groups = (
      ("Conifer", ("Conifer_Branches", "Conifer_Billboard")),
      ("Cypress", ("Cypress_Forest_Desktop", "Cypress_Forest_Desktop_Billboard")),
      ("Pines/Pine_A", ("Pine_A", "Pine_A_Billboard")),
      ("Pines/Pine_B", ("Pine_B", "Pine_B_Billboard")),
      ("Pines/Pine_C", ("Pine_C", "Pine_C_Billboard")),
      ("Pines/Pine_D", ("Pine_D", "Pine_D_Billboard")),
    )
    names = ["Assets/TerrainDemoScene_URP/Prefabs/Trees/" + folder +
             "/Materials/" + name + ".mat" for folder, leaves in groups for name in leaves]
    if len(names) != 12 or len(_scratch_unity_pids()) != 1 or not (BATCH_ROOT/"scene-readback.json").is_file():
        return {"exit_code":3, "stdout":"", "stderr":"One verified scratch Unity Editor/scene required"}
    if root.is_symlink() or not root.is_dir() or shutil.disk_usage(root).free < 10*1024**3:
        return {"exit_code":3, "stdout":"", "stderr":"Invalid scratch or less than 10 GiB temporary headroom"}
    def sha(b):
        return hashlib.sha256(b).hexdigest()
    pairs = []
    for rel in names:
        path, source = root/rel, PROJECT/rel
        if not path.is_file() or path.is_symlink() or not source.is_file() or source.is_symlink():
            return {"exit_code":3, "stdout":"", "stderr":"Missing/symlinked material: "+rel}
        a, b = path.read_bytes(), source.read_bytes()
        if not (a == b and a.count(prior.encode())==1 and b.count(prior.encode())==1) and operation=="preflight":
            return {"exit_code":3, "stdout":"", "stderr":"Scratch differs from approved original material: "+rel}
        if operation=="apply" and (a!=b or a.count(prior.encode())!=1):
            return {"exit_code":3, "stdout":"", "stderr":"Unreviewed material before A/B: "+rel}
        if not (root/(rel+".meta")).is_file() or (root/(rel+".meta")).read_bytes() != (PROJECT/(rel+".meta")).read_bytes():
            return {"exit_code":3, "stdout":"", "stderr":"Original material GUID mismatch: "+rel}
        pairs.append((rel,path,a,b))
    pkg = list((root/"Library/PackageCache").glob("com.unity.render-pipelines.universal@*/Shaders/Nature/SpeedTree8_PBRLit.shadergraph.meta"))
    candidate_meta = [x for x in pkg if x.is_file() and not x.is_symlink() and "guid: 9920c1f1781549a46ba081a2a15a16ec" in x.read_text(errors="replace")]
    details = {"operation":operation, "scratch_only":True, "original_untouched":True,
               "source_materials":len(pairs), "target":"URP17/SpeedTree8_PBRLit",
               "candidate_shader_guid_verified":bool(candidate_meta),
               "package_meta_matches":len(candidate_meta),
               "material_paths":names}
    if operation=="preflight":
        return {"exit_code":0,"stdout":json.dumps(details),"stderr":""}
    if operation=="apply":
        if not candidate_meta:
            return {"exit_code":3,"stdout":json.dumps(details),
                    "stderr":"Installed URP SpeedTree8 shader GUID not verified"}
        if stage.exists() or stage.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Prior shader A/B backup exists; restore first"}
        stage.mkdir(mode=0o700)
        manifest=[]
        written=[]
        try:
            for rel,path,original,src in pairs:
                backup=stage/rel
                backup.parent.mkdir(parents=True,exist_ok=True)
                backup.write_bytes(original)
                if sha(backup.read_bytes())!=sha(original):
                    raise ValueError("Unverified shader A/B backup: "+rel)
                after=original.replace(prior.encode(),candidate.encode())
                if len(after)!=len(original) or after.count(candidate.encode())!=1:
                    raise ValueError("Unexpected shader A/B replacement: "+rel)
                manifest.append({"path":rel,"before_sha256":sha(original),"after_sha256":sha(after)})
                tmp=path.with_suffix(".mat.aaris-shader-preview")
                if tmp.exists() or tmp.is_symlink():
                    raise ValueError("Existing shader temporary material: "+rel)
                tmp.write_bytes(after)
                os.replace(tmp,path)
                written.append((path,original))
                if sha(path.read_bytes())!=sha(after):
                    raise ValueError("Shader preview material readback mismatch: "+rel)
            (stage/"manifest.json").write_text(json.dumps(manifest,indent=2))
        except BaseException:
            for path,original in reversed(written):
                path.write_bytes(original)
            raise
        details["edited_scratch_materials"]=len(written)
        details["backup"]=str(stage)
        return {"exit_code":0,"stdout":json.dumps(details),"stderr":""}
    # restore operation verifies the exact backup and preview byte identities
    manifest_file=stage/"manifest.json"
    if not manifest_file.is_file() or manifest_file.is_symlink():
        return {"exit_code":3,"stdout":"","stderr":"Original A/B backup manifest unavailable"}
    records=json.loads(manifest_file.read_text())
    if [x.get("path") for x in records]!=names:
        return {"exit_code":3,"stdout":"","stderr":"Shader A/B backup path mismatch"}
    for rec in records:
        path=root/rec["path"]
        original=(stage/rec["path"]).read_bytes()
        if sha(original)!=rec["before_sha256"] or sha((PROJECT/rec["path"]).read_bytes())!=rec["before_sha256"]:
            return {"exit_code":3,"stdout":"","stderr":"Original shader A/B baseline drift"}
        if sha(path.read_bytes())!=rec["after_sha256"]:
            return {"exit_code":3,"stdout":"","stderr":"Scratch shader A/B material changed unexpectedly"}
    for rec in records:
        dst=root/rec["path"]
        before=(stage/rec["path"]).read_bytes()
        tmp=dst.with_suffix(".mat.aaris-shader-restore")
        if tmp.exists() or tmp.is_symlink():
            raise ValueError("Unexpected restore temp")
        tmp.write_bytes(before)
        os.replace(tmp,dst)
    details["restored_scratch_materials"]=len(records)
    details["all_restored"]=all((root/x["path"]).read_bytes()==(PROJECT/x["path"]).read_bytes() for x in records)
    return {"exit_code":0 if details["all_restored"] else 3,
            "stdout":json.dumps(details),"stderr":""}


def execute(job):
    # Validate independently from Actions, where an untrusted queue file travels.
    if set(job) != {"id", "operation", "args"}:
        raise ValueError("invalid job shape")
    ident, op, args = job["id"], job["operation"], job["args"]
    if not isinstance(ident, str) or not (4 <= len(ident) <= 56) or not ident.replace("-", "").isalnum():
        raise ValueError("invalid job id")
    if not isinstance(args, list):
        raise ValueError("invalid args")
    if op in {"unity_house_gallery_start","unity_house_gallery_export","unity_house_gallery_diagnose"}:
        return unity_house_gallery(job)
    if op == "unity_main_core_sync":
        if len(args)!=1 or not re.fullmatch(r"[0-9a-f]{40}",args[0]):
            raise ValueError("Exact-main sync requires one reviewed 40-hex main SHA")
        return unity_main_core_sync(job)
    if op in {"unity_shader_ab_preflight", "unity_shader_ab_apply", "unity_shader_ab_restore"}:
        if args: raise ValueError("Shader A/B operation takes no args")
        return unity_shader_ab_probe(op.removeprefix("unity_shader_ab_"))
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
    if op == "unity_session_stop_simulation":
        if args: raise ValueError("Stop simulation takes no arguments")
        if not RECOVERY_SCRIPT.is_file() or RECOVERY_SCRIPT.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Reviewed Unity checkpoint not staged"}
        result=subprocess.run(
            ["python3",str(RECOVERY_SCRIPT),
             "--original",str(PROJECT),"--editor",str(EDITOR),
             "--state-file",str(RECOVERY_STATE),"--simulate-stop"],
            text=True,capture_output=True,timeout=60,check=False
        )
        return {"exit_code":result.returncode,"stdout":result.stdout[-12000:],
                "stderr":result.stderr[-900:]}
    if op == "unity_sync_save_session":
        if args: raise ValueError("Save Session takes no extra arguments")
        return {"exit_code":0,"stdout":json.dumps({
            "status":"delegated_to_github_actions_writer",
            "note":"Separate owner-only workflow with contents:write performs Git LFS upload. This Codespace worker never pushes."}),"stderr":""}
    if op in {"unity_sync_auth","unity_sync_status","unity_sync_arm",
              "unity_sync_dry_run","unity_sync_save_session","unity_sync_watch_start"}:
        if args: raise ValueError("No extra arguments allowed for Unity Sync job")
        source=Path("/workspaces/.aaris-world-bridge/ondemand/unity_batched_autosync.py")
        if not source.is_file() or source.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Reviewed Unity batch sync engine not staged"}
        commands={"unity_sync_auth":"auth-check","unity_sync_status":"status",
                  "unity_sync_arm":"arm","unity_sync_dry_run":"dry-run",
                  "unity_sync_save_session":"flush"}
        if op=="unity_sync_watch_start":
            if not _scratch_unity_pids() or not (BATCH_ROOT/"scene-readback.json").is_file():
                return {"exit_code":3,"stdout":"","stderr":"Native Unity map Editor/scene not verified, cannot arm watcher"}
            current=subprocess.run(["python3",str(source),"arm"],
                                   capture_output=True,text=True,timeout=35,check=False)
            if current.returncode!=0:
                return {"exit_code":3,"stdout":current.stdout[-3000:],"stderr":"Autosync could not arm"}
            # Existing watchdog is identified by exact Python argv; no duplicate.
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit(): continue
                try:
                    cmd=[a.decode(errors="replace") for a in
                         (proc/"cmdline").read_bytes().split(b"\0") if a]
                    if len(cmd)==3 and cmd[1]==str(source) and cmd[2]=="watch":
                        return {"exit_code":0,"stdout":json.dumps({
                            "status":"watch_already_running","pid":int(proc.name),
                            "quiet_seconds":180,"max_unsaved_seconds":600}),"stderr":""}
                except OSError: pass
            target=BATCH_ROOT/"autosync-watch.log"
            with target.open("a") as stream:
                watch=subprocess.Popen(
                    ["python3",str(source),"watch"],
                    cwd=BATCH_ROOT,stdin=subprocess.DEVNULL,
                    stdout=stream,stderr=stream,start_new_session=True
                )
            return {"exit_code":0,"stdout":json.dumps({
                "status":"watcher_started","pid":watch.pid,"quiet_seconds":180,
                "max_unsaved_seconds":600,
                "note":"Best effort while Codespace runs; no guaranteed shutdown hook."}),
                "stderr":""}
        commandline=["python3",str(source),commands[op]]
        if op=="unity_sync_save_session": commandline.append("--force")
        audit=subprocess.run(commandline,text=True,capture_output=True,
                             timeout=300 if op=="unity_sync_save_session" else 75,
                             check=False)
        return {"exit_code":audit.returncode,"stdout":audit.stdout[-16000:],
                "stderr":audit.stderr[-1200:]}
    if op == "unity_session_status":
        if args: raise ValueError("Session status takes no arguments")
        return {"exit_code":0,"stdout":json.dumps(_session_plan(),
                                                  ensure_ascii=False),"stderr":""}
    if op == "unity_session_checkpoint":
        if args: raise ValueError("Session checkpoint takes no arguments")
        return {"exit_code":0,"stdout":json.dumps(_session_plan(save=True),
                                                  ensure_ascii=False),"stderr":""}
    if op == "unity_session_recover":
        if args: raise ValueError("Session recovery takes no arguments")
        return unity_session_recover()
    if op == "unity_tree_v2_preview":
        if args: raise ValueError("Tree-v2 scratch preview takes no arguments")
        if not _scratch_unity_pids() or not (BATCH_ROOT/"scene-readback.json").is_file():
            return {"exit_code":3,"stdout":"",
                    "stderr":"Native Unity Editor and Scene must be loaded before selective tree reimport"}
        source = Path("/workspaces/.aaris-world-bridge/ondemand/unity_tree_v2_preview.py")
        if not source.is_file() or source.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Reviewed selective scratch tree helper absent"}
        return run(["python3",str(source)],timeout=115)
    if op == "unity_scratch_reconcile":
        if args: raise ValueError("scratch reconciliation takes no arguments")
        source = Path("/workspaces/.aaris-world-bridge/ondemand/unity_scratch_reconcile.py")
        if not source.is_file() or source.is_symlink():
            return {"exit_code":3,"stdout":"","stderr":"Reviewed scratch reconciliation missing"}
        audit = subprocess.run(
            ["python3",str(source),"--original",str(PROJECT),
             "--scratch",str(BATCH_ROOT/"project")],
            text=True,capture_output=True,timeout=120,check=False)
        return {"exit_code":audit.returncode,"stdout":audit.stdout[-25000:],
                "stderr":audit.stderr[-1400:]}
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
    if op == "unity_forest_menu_snapshot":
        if args: raise ValueError("Snapshot takes no args")
        return unity_forest_menu_snapshot()
    if op == "unity_forest_editor_refresh":
        if args: raise ValueError("Unity refresh takes no arguments")
        return unity_forest_editor_refresh()
    if op == "unity_forest_treeonly_tune":
        if args: raise ValueError("Tree-only tuning takes no arguments")
        return unity_forest_treeonly_tune()
    if op == "unity_forest_treeonly_prepare":
        if args: raise ValueError("Tree-only correction preparation takes no args")
        return unity_forest_treeonly_prepare()
    if op == "unity_forest_baseline_probe":
        if args: raise ValueError("Baseline inspection takes no arguments")
        return unity_forest_baseline_probe()
    if op == "unity_render_backend_probe":
        if args: raise ValueError("Backend probe needs no args")
        return unity_render_backend_probe()
    if op == "unity_map_camera_capture":
        if len(args)!=1 or args[0] not in {"forest-west","forest-south","mountain-east"}:
            raise ValueError("Only reviewed Unity scene camera zones are allowed")
        return unity_map_camera_capture(job)
    if op in {"unity_forest_one_shot_plan","unity_forest_one_shot_apply"}:
        return unity_forest_one_shot(job)
    if op == "unity_forest_crash_report":
        if args: raise ValueError("Crash inspection takes no parameters")
        return unity_forest_crash_report()
    if op == "unity_forest_recompile":
        if args: raise ValueError("Forest recompile takes no args")
        return unity_forest_recompile()
    if op == "unity_forest_x11_probe":
        if args: raise ValueError("X11 probe takes no args")
        return unity_forest_x11_probe()
    if op == "unity_forest_stage":
        if args: raise ValueError("Forest stage does not accept parameters")
        return unity_forest_stage()
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


if len(sys.argv)==2 and sys.argv[1]=="--unity-rebuild-worker":
    sys.exit(_restart_rebuild_worker())

if len(sys.argv)==2 and sys.argv[1]=="--unity-batch-worker":
    sys.exit(unity_batch_worker())

if __name__ == "__main__":
    if len(sys.argv)==3 and sys.argv[1]=="--unity-watchdog" and sys.argv[2].isdigit():
        _monitor_unity(int(sys.argv[2]))
        sys.exit(0)
    sys.exit(main())