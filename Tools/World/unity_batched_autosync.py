#!/usr/bin/env python3
"""AI Unity edits -> debounced, verified, isolated Git LFS branch.

No changes are made to the original /workspaces Git checkout. The editor
saves into /tmp. Only successful native Unity mutation responses count as
candidate source assets, never import noise or screenshots. Default status
and dry-run are read-only. Explicit flush / watch requires configured Git
authentication; errors leave scratch assets intact and report UNSAVED.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

REPO="Aaris-khan-don/Unity-Game-Aris"
URL="https://github.com/"+REPO+".git"
ORIGINAL=Path("/workspaces/Unity-Game-Aris")
SCRATCH=Path("/tmp/aaris-unity-batch/project")
CONTROL=Path("/tmp/aaris-unity-batch/control")
STATE=Path("/workspaces/.aaris-world-bridge/ondemand/unity-autosync-state.json")
ALLOW_EXT={".asset",".unity",".prefab",".mat"}
MUTATIONS={"move","scale","move_tree","scale_tree","forest_apply"}
QUIET_SECONDS=180
MAX_UNSAVED_SECONDS=600
MAX_FILES=12
MAX_BYTES=600*1024**2
MIN_SCRATCH_FREE=5*1024**3
MIN_ORIGINAL_FREE=160*1024**2
ID_PATTERN=re.compile(r"^[a-z][a-z0-9-]{3,55}$")
POINTER=re.compile(rb"^version https://git-lfs.github.com/spec/v1\r?\noid sha256:([0-9a-f]{64})\r?\nsize (\d+)\r?\n?")
VERSION=1


class SyncError(Exception):
    pass


def sha(path: Path, cap=MAX_BYTES):
    if path.is_symlink() or not path.is_file():
        raise SyncError("Unsafe or absent expected file: "+path.name)
    if path.stat().st_size>cap:
        raise SyncError("File exceeds safe batch size: "+path.name)
    h=hashlib.sha256()
    with path.open("rb") as file:
        for part in iter(lambda:file.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()


def relative_asset(name):
    if not isinstance(name,str) or not name.startswith("Assets/") or "\x00" in name or "\\" in name:
        raise SyncError("Untrusted Unity changedAsset path")
    p=PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or p.suffix not in ALLOW_EXT:
        raise SyncError("Unsupported Unity asset for automatic sync")
    if name.startswith("Assets/Editor/") or name.startswith("Assets/AarisWorld/Editor/"):
        raise SyncError("Editor automation source is not a map content edit")
    return str(p)


def command(argv,cwd=None,timeout=100,env=None,check=True):
    safeenv=os.environ.copy()
    safeenv.update({"GIT_TERMINAL_PROMPT":"0","GIT_LFS_SKIP_SMUDGE":"1",
                    "GCM_INTERACTIVE":"never"})
    if env:
        safeenv.update(env)
    try:
        p=subprocess.run(argv,cwd=cwd,stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=timeout,env=safeenv,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise SyncError("Git operation failed or timed out: "+argv[0]) from exc
    if check and p.returncode:
        # NEVER expose Git credential helper errors, URLs, tokens, or stdout.
        raise SyncError("Git command unsuccessful: "+argv[1] if len(argv)>1 else "Git command unsuccessful")
    return p


def load_state(path=STATE):
    if path.is_symlink():
        raise SyncError("Autosync state path is symlinked")
    if not path.is_file():
        return None
    if path.stat().st_size>80000:
        raise SyncError("Autosync state too large")
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or data.get("schema")!=VERSION:
        raise SyncError("Unrecognized autosync schema")
    return data


def store_state(data,path=STATE):
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise SyncError("Persistent autosync state directory missing")
    if path.exists() and path.is_symlink():
        raise SyncError("Persistent autosync state symlink")
    if shutil.disk_usage(path.parent).free<80*1024**2:
        raise SyncError("Too little original persistent disk to checkpoint autosync")
    blob=json.dumps(data,indent=2,sort_keys=True)+"\n"
    if len(blob)>80000:
        raise SyncError("Autosync state too large")
    temp=path.with_name(path.name+".new")
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"w") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():
            temp.unlink()


def scratch_identity(scratch=SCRATCH):
    scene=scratch/"Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
    if not scratch.is_dir() or scratch.is_symlink() or not scene.is_file():
        raise SyncError("Live Unity scratch scene is missing")
    st=scratch.stat()
    return f"{st.st_dev}:{st.st_ino}"


def arm(original=ORIGINAL,scratch=SCRATCH,statefile=STATE,clock=time.time):
    ident=scratch_identity(scratch)
    previous=load_state(statefile)
    if previous is not None:
        if previous.get("scratch_identity")!=ident:
            if previous.get("pending_assets"):
                raise SyncError("Prior Unity scratch vanished with UNSAVED changes; manual review")
            if previous.get("pushed") and previous.get("last_restored_identity")!=ident:
                raise SyncError("Previous Git LFS session edits must be restored before rearming new scratch")
        else:
            return previous
    if not (original/".git").exists():
        raise SyncError("Original Git checkout unavailable")
    now=clock()
    state={"schema":VERSION,"scratch_identity":ident,"armed_at":now,
           "branch":previous.get("branch") if previous else None,
           "pushed":previous.get("pushed",{}) if previous else {},
           "pending_assets":{},"last_restored_identity":None,
           "last_success":previous.get("last_success") if previous else None,
           "last_error":None,"last_attempt":None}
    store_state(state,statefile)
    return state


def scan(state,scratch=SCRATCH,control=CONTROL):
    if state is None:
        return {"ready":False,"reason":"autosync_not_armed",
                "candidates":{},"pending_commands":0}
    if scratch_identity(scratch)!=state.get("scratch_identity"):
        raise SyncError("Unity scratch identity changed; no automatic replay")
    results=control/"unity-results"
    commands=control/"unity-commands"
    if not results.is_dir() or results.is_symlink():
        raise SyncError("Unity bridge result directory missing")
    pending_count=0
    if commands.is_dir():
        pending_count=sum(1 for p in commands.iterdir()
                          if p.is_file() and p.suffix==".json")
    candidates={}
    for file in results.iterdir():
        if not file.is_file() or file.is_symlink() or file.suffix!=".json":
            continue
        if not ID_PATTERN.fullmatch(file.stem) or file.stat().st_size>120000:
            continue
        if file.stat().st_mtime<=state["armed_at"]:
            continue
        try:
            reply=json.loads(file.read_text())
        except (OSError,ValueError):
            continue
        if not isinstance(reply,dict) or reply.get("id")!=file.stem:
            continue
        if reply.get("status")!="ok" or reply.get("action") not in MUTATIONS:
            continue
        if not reply.get("changedAsset"):
            continue
        name=relative_asset(reply["changedAsset"])
        item=candidates.setdefault(name,{"latest":0.0,"first":float("inf"),
                                          "commands":0})
        item["latest"]=max(item["latest"],file.stat().st_mtime)
        item["first"]=min(item["first"],file.stat().st_mtime)
        item["commands"]+=1
    if len(candidates)>MAX_FILES:
        raise SyncError("Too many different core assets in a single auto-batch")
    changed={}
    for name,info in candidates.items():
        path=scratch/name
        if path.is_symlink() or not path.is_file():
            raise SyncError("Unity changedAsset missing or symlinked: "+name)
        digest=sha(path)
        if state["pushed"].get(name)!=digest:
            changed[name]={**info,"sha256":digest,"bytes":path.stat().st_size}
    return {"ready":True,"candidates":changed,
            "pending_commands":pending_count}


def status(original=ORIGINAL,scratch=SCRATCH,control=CONTROL,
           statefile=STATE,now=None):
    now=time.time() if now is None else now
    state=load_state(statefile)
    if not state:
        return {"status":"not_armed","pending":0,"safe_to_push":False}
    info=scan(state,scratch,control)
    files=info["candidates"]
    last=max((x["latest"] for x in files.values()),default=None)
    first=min((x["first"] for x in files.values()),default=None)
    idle=(now-last) if last is not None else None
    wait=(idle is not None and idle>=QUIET_SECONDS) or (
        first is not None and now-first>=MAX_UNSAVED_SECONDS)
    safe=(bool(files) and info["pending_commands"]==0 and
          wait and shutil.disk_usage(scratch).free>MIN_SCRATCH_FREE and
          shutil.disk_usage(original).free>MIN_ORIGINAL_FREE)
    return {"status":"changes_pending" if files else "clean_or_saved",
            "pending":len(files),"changed_assets":list(files),
            "pending_unity_commands":info["pending_commands"],
            "seconds_since_last_edit":round(idle,1) if idle is not None else None,
            "quiet_seconds":QUIET_SECONDS,
            "max_unsaved_seconds":MAX_UNSAVED_SECONDS,
            "safe_to_push":safe,"branch":state["branch"],
            "last_success":state.get("last_success"),
            "last_error":state.get("last_error")}


def match_remote_blob(blob,digest):
    pointer=POINTER.match(blob)
    if pointer:
        return pointer.group(1).decode()==digest
    return hashlib.sha256(blob).hexdigest()==digest


def current_git_branch(repo_path):
    p=command(["git","-C",str(repo_path),"branch","--show-current"])
    return p.stdout.decode("utf-8","replace").strip()


def ensure_original_clean(original,files):
    if not (original/".git").exists():
        raise SyncError("No original checkout metadata")
    for name in files:
        p=original/name
        if p.is_symlink() or not p.is_file():
            raise SyncError("Original tracked asset unavailable")
        src=command(["git","-C",str(original),"status","--porcelain","--",name])
        if src.stdout.strip():
            raise SyncError("Owner has unsaved original changes to selected Unity asset")
        meta=original/(name+".meta")
        if meta.is_symlink() or not meta.is_file():
            raise SyncError("Original .meta missing")
    return True


def check_meta(original,scratch,files):
    for name in files:
        before=original/(name+".meta")
        after=scratch/(name+".meta")
        if sha(before,2*1024**2)!=sha(after,2*1024**2):
            raise SyncError("Unity .meta GUID/config differs; needs explicit review")


def clone_branch(path,state,files):
    branch=state.get("branch")
    ref=branch or "main"
    command(["git","clone","--no-checkout","--depth=1",
             "--filter=blob:none","--branch",ref,URL,str(path)],
            timeout=200)
    patterns=[".gitattributes"]+list(files)+[f+".meta" for f in files]
    command(["git","-C",str(path),"sparse-checkout","init","--no-cone"],timeout=90)
    command(["git","-C",str(path),"sparse-checkout","set","--no-cone",
             "--",*patterns],timeout=150)
    command(["git","-C",str(path),"checkout",ref],timeout=150)
    if not branch:
        branch="ai/unity-batched-"+datetime.now(timezone.utc).strftime("%Y%m%d")+"-"+hashlib.sha256(os.urandom(16)).hexdigest()[:10]
        command(["git","-C",str(path),"checkout","-b",branch])
    return branch


def flush(*,force=False,original=ORIGINAL,scratch=SCRATCH,
          control=CONTROL,statefile=STATE,now=None,dry_run=False):
    now=time.time() if now is None else now
    state=load_state(statefile)
    if not state:
        raise SyncError("Autosync not armed; first arm after reviewing old edits")
    scaninfo=scan(state,scratch,control)
    candidates=scaninfo["candidates"]
    if not candidates:
        return {"status":"no_changes","pushed":False,"branch":state["branch"]}
    if scaninfo["pending_commands"]:
        raise SyncError("Unity has pending commands; cannot snapshot mid-edit")
    files=sorted(candidates)
    first=min(x["first"] for x in candidates.values())
    last=max(x["latest"] for x in candidates.values())
    if not force and now-last<QUIET_SECONDS and now-first<MAX_UNSAVED_SECONDS:
        return {"status":"debouncing","files":files,
                "seconds_to_quiet":round(QUIET_SECONDS-(now-last),1),"pushed":False}
    if sum(x["bytes"] for x in candidates.values())>MAX_BYTES:
        raise SyncError("Total modified Unity core assets exceed 600MiB guarded batch budget")
    if shutil.disk_usage(scratch).free<MIN_SCRATCH_FREE:
        raise SyncError("Scratch disk critically full")
    if shutil.disk_usage(original).free<MIN_ORIGINAL_FREE:
        raise SyncError("Original workspace disk critically full")
    ensure_original_clean(original,files)
    check_meta(original,scratch,files)
    if dry_run:
        return {"status":"dry_run_validated","files":files,"bytes":sum(x["bytes"] for x in candidates.values()),
                "pushed":False,"original_untouched":True,"branch":state["branch"]}
    with tempfile.TemporaryDirectory(prefix="aaris-verified-lfs-",dir="/tmp") as root:
        checkout=Path(root)/"repo"
        branch=clone_branch(checkout,state,files)
        # LFS/regular assets in remote branch must match original snapshot
        # (first push) or previously verified uploaded content (later pushes).
        for name in files:
            prior=state["pushed"].get(name) or sha(original/name)
            current=command(["git","-C",str(checkout),"show","HEAD:"+name],timeout=100).stdout
            if not match_remote_blob(current,prior):
                raise SyncError("Remote branch version conflicts with original/saved asset")
            remote_meta=command(["git","-C",str(checkout),"show","HEAD:"+name+".meta"],timeout=30).stdout
            if hashlib.sha256(remote_meta).hexdigest()!=sha(original/(name+".meta"),2*1024**2):
                raise SyncError("Remote .meta mismatch: "+name)
        # Source stays on /tmp; this copy is the only checkout written.
        for name in files:
            dest=checkout/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            original_digest=candidates[name]["sha256"]
            shutil.copyfile(scratch/name,dest,follow_symlinks=False)
            if sha(dest)!=original_digest or sha(scratch/name)!=original_digest:
                raise SyncError("Unity changed asset while snapshot was copying")
        command(["git","-C",str(checkout),"config","user.name","Aaris Unity AI Session"])
        command(["git","-C",str(checkout),"config","user.email","aaris-unity-ai@users.noreply.github.com"])
        command(["git","-C",str(checkout),"lfs","install","--local"])
        command(["git","-C",str(checkout),"add","--",*files])
        staged=command(["git","-C",str(checkout),"diff","--cached","--name-only","-z"]).stdout
        staged_names={p.decode("utf-8","replace") for p in staged.split(b"\0") if p}
        if not staged_names or not staged_names.issubset(set(files)):
            raise SyncError("Unexpected staged file or no real Unity data change")
        # Verify Git LFS filter generated a pointer for every LFS-tracked asset.
        for name in staged_names:
            attrs=command(["git","-C",str(checkout),"check-attr","filter","--",name]).stdout
            if b": lfs" in attrs:
                ptr=command(["git","-C",str(checkout),"show",":"+name]).stdout
                p=POINTER.match(ptr)
                if not p or p.group(1).decode()!=candidates[name]["sha256"]:
                    raise SyncError("Git LFS index did not record expected Unity asset SHA")
        command(["git","-C",str(checkout),"diff","--cached","--check"])
        command(["git","-C",str(checkout),"commit","-m",
                 "Unity AI verified batch: "+str(len(staged_names))+" map assets"],timeout=150)
        # LFS upload comes before Git ref, avoiding dangling pointers in Git.
        command(["git","-C",str(checkout),"lfs","push","origin",branch],timeout=240)
        command(["git","-C",str(checkout),"push","origin",
                 "HEAD:refs/heads/"+branch],timeout=240)
        expected=command(["git","-C",str(checkout),"rev-parse","HEAD"]).stdout.strip()
        remote=command(["git","-C",str(checkout),"ls-remote","origin",
                        "refs/heads/"+branch],timeout=60).stdout
        if not remote.startswith(expected+b"\t"):
            raise SyncError("Remote Git branch did not verify against pushed commit")
        # Validate current source after network upload. Any later mutations
        # remain pending in the NEXT batch; never claim them pushed.
        pushed={name:val["sha256"] for name,val in candidates.items()}
        state["pushed"].update(pushed)
        state["branch"]=branch
        state["last_success"]=datetime.now(timezone.utc).isoformat()
        state["pending_assets"]={}
        state["last_error"]=None
        state["last_attempt"]=now
        store_state(state,statefile)
        return {"status":"verified_pushed_to_review_branch",
                "branch":branch,"pushed":True,
                "files":files,"bytes":sum(x["bytes"] for x in candidates.values()),
                "commit":expected.decode(),"repository":REPO,
                "original_untouched":True,
                "note":"Main is NOT overwritten. Review/merge session branch after CI."}


def restore_synced_scratch(*,original=ORIGINAL,scratch=SCRATCH,
                           statefile=STATE):
    """Reapply ONLY already remote-verified LFS source edits to a new /tmp copy.

    The game source in /workspaces is never written. This is used before Unity
    starts after the Codespace wiped /tmp, not while an Editor is editing.
    The previous unpushed changes CANNOT be restored and are reported.
    """
    state=load_state(statefile)
    if not state or not state.get("branch") or not state.get("pushed"):
        return {"status":"no_verified_session_edits_to_restore",
                "restored":[], "unsaved_was_lost":bool(state and state.get("pending_assets"))}
    if not scratch.is_dir() or scratch.is_symlink():
        raise SyncError("Scratch copy must be completely recreated before restore")
    if shutil.disk_usage(scratch).free<MIN_SCRATCH_FREE:
        raise SyncError("Insufficient scratch disk for verified session replay")
    files=sorted(state["pushed"])
    if len(files)>MAX_FILES or any(relative_asset(n)!=n for n in files):
        raise SyncError("Unsafe previously saved asset inventory")
    ensure_original_clean(original,files)
    check_meta(original,scratch,files)
    if state.get("pending_assets"):
        # A saved batch is durable, but pending changes at stop were not.
        # Do not silently present the restored scene as the latest edit.
        raise SyncError("Unpushed mutations are recorded in persistent journal; manual conflict review required")
    with tempfile.TemporaryDirectory(prefix="aaris-restore-verified-",dir="/tmp") as root:
        clone=Path(root)/"repo"
        branch=state["branch"]
        if not re.fullmatch(r"ai/unity-batched-[a-zA-Z0-9-]+",branch):
            raise SyncError("Unsafe saved Git branch")
        command(["git","clone","--no-checkout","--depth=1","--filter=blob:none",
                 "--branch",branch,URL,str(clone)],timeout=200)
        patterns=[".gitattributes"]+files+[n+".meta" for n in files]
        command(["git","-C",str(clone),"sparse-checkout","init","--no-cone"])
        command(["git","-C",str(clone),"sparse-checkout","set","--no-cone",
                 "--",*patterns],timeout=180)
        command(["git","-C",str(clone),"checkout",branch],timeout=150)
        for name in files:
            pointer=command(["git","-C",str(clone),"show","HEAD:"+name],timeout=60).stdout
            if not match_remote_blob(pointer,state["pushed"][name]):
                raise SyncError("Saved remote branch has been changed: "+name)
            remote_meta=command(["git","-C",str(clone),"show","HEAD:"+name+".meta"]).stdout
            if hashlib.sha256(remote_meta).hexdigest()!=sha(original/(name+".meta"),2*1024**2):
                raise SyncError("Saved .meta GUID conflicts with original: "+name)
        includes=",".join(files)
        # This touches only /tmp checkout; never Git LFS sources in /workspaces.
        command(["git","-C",str(clone),"lfs","pull","--include="+includes,
                 "--exclude="],timeout=300)
        staging=[]
        for name in files:
            hydrated=clone/name
            if sha(hydrated)!=state["pushed"][name]:
                raise SyncError("Hydrated saved Git LFS content mismatch: "+name)
            destination=scratch/name
            if destination.is_symlink() or sha(destination)!=sha(original/name):
                raise SyncError("Scratch already has unsaved or conflicting native content")
            temp=destination.with_name(destination.name+".aaris-sync-new")
            if temp.exists() or temp.is_symlink():
                raise SyncError("Unsafe preexisting scratch restore temp path")
            shutil.copy2(hydrated,temp)
            if sha(temp)!=state["pushed"][name]:
                raise SyncError("Temporary restore hash mismatch")
            staging.append((temp,destination))
        # Commit validated copies into the *scratch* tree. Original untouched.
        for temp,destination in staging:
            os.replace(temp,destination)
    state["last_restored_identity"]=scratch_identity(scratch)
    state["pending_assets"]={}
    store_state(state,statefile)
    return {"status":"verified_synced_edits_restored_to_scratch",
            "restored":files,"branch":branch,"original_untouched":True,
            "note":"Only prior Git LFS committed data was restored; latest AI edits must be independently inspected."}


def export_for_actions(*,force=False,original=ORIGINAL,scratch=SCRATCH,
                       control=CONTROL,statefile=STATE,now=None):
    """Prepare validated scratch files for GitHub Actions; NO Git credentials."""
    import tarfile
    now=time.time() if now is None else now
    state=load_state(statefile)
    if not state:
        raise SyncError("Autosync not armed")
    data=scan(state,scratch,control)
    candidates=data["candidates"]
    if not candidates:
        return {"status":"no_changes","exported":False}
    if data["pending_commands"]:
        return {"status":"unity_busy","exported":False}
    first=min(item["first"] for item in candidates.values())
    last=max(item["latest"] for item in candidates.values())
    if not force and (now-last)<QUIET_SECONDS and (now-first)<MAX_UNSAVED_SECONDS:
        return {"status":"debouncing","exported":False,
                "seconds_to_quiet":round(QUIET_SECONDS-(now-last),1)}
    paths=sorted(candidates)
    size=sum(x["bytes"] for x in candidates.values())
    if len(paths)>MAX_FILES or size>MAX_BYTES:
        raise SyncError("Unity batch exceeds guarded size/file limits")
    if shutil.disk_usage(original).free<MIN_ORIGINAL_FREE or (
        shutil.disk_usage(scratch).free<MIN_SCRATCH_FREE):
        raise SyncError("Insufficient disk for safe export")
    ensure_original_clean(original,paths)
    check_meta(original,scratch,paths)
    identity=scratch_identity(scratch)
    result_dir=scratch.parent/"sync-export"
    result_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    manifest={"schema":1,"repo":REPO,"scratch_identity":identity,
              "branch":state["branch"],"created_at":now,
              "files":[{
                  "path":name,"sha256":candidates[name]["sha256"],
                  "original_sha256":sha(original/name),
                  "meta_sha256":sha(original/(name+".meta"),2*1024**2),
                  "bytes":candidates[name]["bytes"],
                  "previously_pushed_sha256":state["pushed"].get(name)
              } for name in paths]}
    label=hashlib.sha256(os.urandom(16)).hexdigest()[:14]
    filename=result_dir/("batch-"+label+".tar")
    manifest_file=result_dir/("batch-"+label+".json")
    with tarfile.open(filename,"w") as archive:
        for entry in manifest["files"]:
            current=entry["path"]
            source=scratch/current
            if source.is_symlink() or not source.is_file():
                raise SyncError("Unsafe Unity asset during transfer packaging")
            archive.add(source,arcname=current,recursive=False)
            if sha(source)!=entry["sha256"]:
                raise SyncError("Unity changed asset while package was being prepared")
    manifest_file.write_text(json.dumps(manifest,sort_keys=True,indent=2))
    if manifest_file.stat().st_size>18000:
        raise SyncError("Transfer manifest exceeded cap")
    return {"status":"ready_for_actions_upload","exported":True,
            "tar":str(filename),"manifest":str(manifest_file),
            "bytes":size,"count":len(paths),"branch":state["branch"]}


def acknowledge_actions_receipt(receipt_path: Path,*,statefile=STATE,scratch=SCRATCH):
    """Acknowledge ONLY after runner verified both Git LFS and Git remote ref."""
    if receipt_path.is_symlink() or not receipt_path.is_file() or (
        receipt_path.stat().st_size>16000):
        raise SyncError("Unsafe Actions receipt")
    obj=json.loads(receipt_path.read_text())
    state=load_state(statefile)
    if not state or obj.get("schema")!=1 or obj.get("repo")!=REPO:
        raise SyncError("Unrecognized GitHub Actions sync receipt")
    if obj.get("scratch_identity")!=state.get("scratch_identity"):
        raise SyncError("Receipt is from another Unity scratch session")
    branch=obj.get("branch")
    if not isinstance(branch,str) or not re.fullmatch(r"ai/unity-batched-[A-Za-z0-9-]+",branch):
        raise SyncError("Untrusted Git branch in receipt")
    if state.get("branch") and state["branch"]!=branch:
        raise SyncError("GitHub Actions receipt branch differs from existing AI session")
    commit=obj.get("commit")
    if not isinstance(commit,str) or not re.fullmatch(r"[0-9a-f]{40}",commit):
        raise SyncError("Invalid Git commit in sync receipt")
    hashes=obj.get("pushed")
    if not isinstance(hashes,dict) or not hashes or len(hashes)>MAX_FILES:
        raise SyncError("No validated Unity assets in receipt")
    for name,value in hashes.items():
        relative_asset(name)
        if not isinstance(value,str) or not re.fullmatch(r"[0-9a-f]{64}",value):
            raise SyncError("Invalid native file checksum in receipt")
    state["branch"]=branch
    state["pushed"].update(hashes)
    # Any newer Unity edits remain candidates on the next scan.
    state["pending_assets"]={}
    state["last_success"]=datetime.now(timezone.utc).isoformat()
    state["last_error"]=None
    state["last_attempt"]=time.time()
    store_state(state,statefile)
    return {"status":"actions_remote_verified_and_acknowledged",
            "branch":branch,"commit":commit,"files":sorted(hashes),
            "original_untouched":True}


def watch(poll_seconds=15,*,max_cycles=None):
    """Poll while this Codespace is running; leave durable UNSAVED markers."""
    cycles=0
    while max_cycles is None or cycles<max_cycles:
        cycles+=1
        try:
            state=load_state()
            if not state:
                raise SyncError("Sync not armed; run arm after original project review")
            files=scan(state)["candidates"]
            pending={name:{"sha256":item["sha256"],"first":item["first"]}
                     for name,item in files.items()}
            if state.get("pending_assets")!=pending:
                state["pending_assets"]=pending
                store_state(state)
            # GitHub Actions is the only automatic uploader: the Codespace
            # does not have private-repository Git Push credentials. The
            # watcher journals changed assets, never performs uploads.
            snapshot=status()
        except (SyncError,OSError,ValueError) as exc:
            state=load_state()
            if state:
                state["last_error"]=str(exc)[:300]
                state["last_attempt"]=time.time()
                try:
                    store_state(state)
                except (SyncError,OSError):
                    pass
        if max_cycles is None or cycles<max_cycles:
            time.sleep(poll_seconds)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=["status","arm","flush","dry-run","watch","auth-check","restore","export","ack"])
    parser.add_argument("--force",action="store_true",help="Explicit Save Session; never omit conflict checks")
    parser.add_argument("--cycles",type=int,default=None)
    parser.add_argument("--receipt",type=Path,help="Trusted GitHub Actions remote push receipt path")
    opts=parser.parse_args(argv)
    try:
        if opts.operation=="status":
            result=status()
        elif opts.operation=="arm":
            state=arm()
            result={"status":"armed","branch":state["branch"],
                    "armed_at":state["armed_at"],"pending":0}
        elif opts.operation=="dry-run":
            result=flush(force=True,dry_run=True)
        elif opts.operation=="flush":
            result=flush(force=opts.force)
        elif opts.operation=="export":
            result=export_for_actions(force=opts.force)
        elif opts.operation=="ack":
            if opts.receipt is None:
                raise SyncError("GitHub Actions receipt path required")
            result=acknowledge_actions_receipt(opts.receipt)
        elif opts.operation=="restore":
            result=restore_synced_scratch()
        elif opts.operation=="watch":
            watch(max_cycles=opts.cycles)
            result={"status":"watch_exited"}
        else:
            p=command(["git","-C",str(ORIGINAL),"ls-remote","--heads",URL],
                      timeout=45,check=False)
            result={"status":"git_credentials_usable" if p.returncode==0
                    else "git_credentials_unavailable","no_tokens_exposed":True}
        print(json.dumps(result,ensure_ascii=False))
        return 0 if result.get("status") not in ("git_credentials_unavailable",) else 3
    except (SyncError,OSError,ValueError,json.JSONDecodeError) as exc:
        print(json.dumps({"status":"blocked","reason":str(exc)[:330],
                          "original_untouched":True,"pushed":False}))
        return 3


if __name__=="__main__":
    sys.exit(main())
