#!/usr/bin/env python3
"""Unity session restart planner and compact durable checkpoint.

Default mode is READ ONLY; --checkpoint writes only one small JSON under
/workspaces/.aaris-world-bridge. Never touches Unity Assets, Git, LFS, or Library.
The imported scratch Library in /tmp is LOST on Codespace stop. No checkpoint
can make temporary files durable; reimport is required unless a separately
verified persistent cache is available.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

ORIGINAL=Path("/workspaces/Unity-Game-Aris")
SCRATCH=Path("/tmp/aaris-unity-batch/project")
EDITOR=Path("/home/codespace/Unity/Hub/Editor/6000.3.26f1/Editor/Unity")
CHECKPOINT=Path("/workspaces/.aaris-world-bridge/ondemand/unity-session-checkpoint.json")
VERSION="6000.3.26f1"
SCENE="Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
SOURCES=("ProjectSettings/ProjectVersion.txt","Packages/manifest.json",SCENE,SCENE+".meta")
TERRAIN="Assets/TerrainDemoScene_URP/Terrain/Data/Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset"
MIN_ORIGINAL_FREE=250*1024**2
MIN_SCRATCH_FREE=20*1024**3
SCHEMA=1


def digest(path: Path, max_bytes=8*1024**2):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>max_bytes:
        return None
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024**2),b""):
            h.update(block)
    return h.hexdigest()


def small_sources(root: Path):
    return {name:digest(root/name) for name in SOURCES}


def scratch_unity_pids(editor: Path, scratch: Path, proc=Path("/proc")):
    result=[]
    if not proc.is_dir():
        return result
    for pid in proc.iterdir():
        if not pid.name.isdigit():
            continue
        try:
            args=[x.decode("utf-8","replace") for x in
                  (pid/"cmdline").read_bytes().split(b"\0") if x]
            if not args or args[0]!=str(editor):
                continue
            pos=args.index("-projectPath")
            if pos+1<len(args) and args[pos+1]==str(scratch):
                result.append(int(pid.name))
        except (OSError,ValueError,IndexError):
            pass
    return sorted(result)


def load_checkpoint(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>16000:
        return None
    try:
        obj=json.loads(path.read_text())
    except (ValueError,OSError):
        return None
    if not isinstance(obj,dict) or obj.get("schema")!=SCHEMA:
        return None
    return obj


def disk_free(path: Path):
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def last_camera_target(scratch: Path):
    """Read only the last SUCCESSFUL Unity inspect/capture view; no replay."""
    root=scratch.parent/"control"
    commands=root/"unity-commands"
    results=root/"unity-results"
    if not commands.is_dir() or not results.is_dir():
        return None
    try:
        options=sorted(
            (p for p in commands.iterdir()
             if p.suffix==".json" and not p.is_symlink() and p.is_file()),
            key=lambda p:p.stat().st_mtime,reverse=True
        )[:64]
    except OSError:
        return None
    for command in options:
        response=results/command.name
        if response.is_symlink() or not response.is_file():
            continue
        try:
            if command.stat().st_size>2400 or response.stat().st_size>150000:
                continue
            request=json.loads(command.read_text())
            result=json.loads(response.read_text())
            if result.get("status")!="ok" or request.get("action") not in ("inspect","capture"):
                continue
            target=request.get("cameraTarget")
            if not isinstance(target,dict) or set(target)!={"x","y","z"}:
                continue
            import math
            if not all(isinstance(target[k],(int,float)) and
                       math.isfinite(target[k]) and abs(target[k])<=10000
                       for k in ("x","y","z")):
                continue
            return {k:float(target[k]) for k in ("x","y","z")}
        except (OSError,ValueError,TypeError,AttributeError):
            continue
    try:
        finished=sorted(
            (p for p in results.iterdir() if p.is_file() and
             not p.is_symlink() and p.suffix==".json"),
            key=lambda p:p.stat().st_mtime,reverse=True
        )[:64]
        for item in finished:
            if item.stat().st_size>150000:
                continue
            obj=json.loads(item.read_text())
            if obj.get("status")!="ok" or obj.get("action")!="inspect":
                continue
            point=obj.get("position")
            if not isinstance(point,dict) or not all(k in point for k in ("x","y","z")):
                continue
            import math
            if all(isinstance(point[k],(int,float)) and math.isfinite(point[k])
                   and abs(point[k])<=10000 for k in ("x","y","z")):
                return {k:float(point[k]) for k in ("x","y","z")}
    except (OSError,ValueError,TypeError):
        pass
    return None


def plan(original=ORIGINAL,scratch=SCRATCH,editor=EDITOR,checkpoint=CHECKPOINT,
         proc=Path("/proc")):
    """Never returns 'exact_resume' if /tmp is missing."""
    core_ok=original.is_dir() and not original.is_symlink()
    original_hashes=small_sources(original) if core_ok else {}
    source_ok=bool(core_ok and all(original_hashes.values()))
    editor_ok=editor.is_file() and not editor.is_symlink()
    scratch_ok=(scratch.is_dir() and not scratch.is_symlink() and
                (scratch/SCENE).is_file() and
                not (scratch/SCENE).is_symlink())
    scratch_hashes=small_sources(scratch) if scratch_ok else {}
    source_matches=bool(scratch_ok and source_ok and
                        all(scratch_hashes.get(name)==value
                            for name,value in original_hashes.items()))
    loaded=False
    report=scratch.parent/"scene-readback.json"
    if report.is_file() and not report.is_symlink() and report.stat().st_size<=100000:
        try:
            data=json.loads(report.read_text())
            loaded=(data.get("sceneLoaded") is True and
                    data.get("scenePath")==SCENE)
        except (ValueError,OSError,AttributeError):
            loaded=False
    pids=scratch_unity_pids(editor,scratch,proc)
    saved=load_checkpoint(checkpoint)
    origfree=disk_free(original) if core_ok else None
    scratchfree=disk_free(scratch if scratch_ok else Path("/tmp"))
    terrain_sha=digest(scratch/TERRAIN, max_bytes=96*1024**2) if scratch_ok else None
    origin_terrain_sha=digest(original/TERRAIN,max_bytes=96*1024**2) if core_ok else None
    scratch_diff=bool(terrain_sha and origin_terrain_sha and terrain_sha!=origin_terrain_sha)
    warnings=[]
    if saved and saved.get("source_sha256")!=original_hashes:
        warnings.append("Original project core hashes changed since prior checkpoint; do not reuse stale scratch without review.")
    if not scratch_ok and saved and saved.get("scratch_loaded"):
        warnings.append("Previous imported /tmp Unity Library and any unpromoted scratch-only edits may have been lost at Codespace stop.")
    if scratch_diff:
        warnings.append("Scratch TerrainData bytes differ from original; never copy back automatically, even if tree transforms were restored.")
    mismatched=[name for name,value in original_hashes.items()
                if scratch_ok and value != scratch_hashes.get(name)]
    if mismatched:
        warnings.append("Unity scratch core differs from original: "+
                        ", ".join(mismatched)+". Never overwrite owner source.")
    if pids and source_ok and editor_ok:
        step="already_running"
    elif not source_ok or not editor_ok:
        step="blocked_missing_core_or_editor"
    elif origfree is None or origfree<MIN_ORIGINAL_FREE:
        step="blocked_low_persistent_disk"
    elif scratchfree is None or scratchfree<MIN_SCRATCH_FREE:
        step="blocked_low_temporary_disk"
    elif scratch_ok and saved and saved.get("source_sha256")!=original_hashes:
        step="blocked_original_changed_since_checkpoint"
    elif scratch_ok and not source_matches and not saved:
        step="blocked_scratch_core_mismatch"
    elif scratch_ok:
        step="reopen_existing_scratch"
    else:
        step="recreate_scratch_and_reimport"
    return {
        "schema":SCHEMA,"step":step,"project":str(original),"scratch":str(scratch),
        "editor_present":editor_ok,"scene":SCENE,"source_sha256":original_hashes,
        "scratch_core_matches":source_matches,"scratch_core_differences":mismatched,
        "scratch_source_sha256":scratch_hashes,"scratch_loaded":loaded,
        "scratch_exists":scratch_ok,"scratch_unity_pids":pids,
        "scratch_terrain_differs":scratch_diff,
        "last_camera_target":(last_camera_target(scratch) if scratch_ok else None) or (saved.get("last_camera_target") if saved else None),
        "original_free_mib":round(origfree/1024**2,1) if origfree is not None else None,
        "scratch_free_gib":round(scratchfree/1024**3,2) if scratchfree is not None else None,
        "previous_checkpoint_present":bool(saved),
        "previous_checkpoint_at":saved.get("captured_utc") if saved else None,
        "warnings":warnings,
        "restart_policy":"Reuse scratch Library only while /tmp exists; /tmp cleared on Codespace stop, requiring a fresh import. Never claim instant exact restoration.",
        "no_vnc_required":False,
        "writes_performed":0,
    }


def write_checkpoint(report, path=CHECKPOINT):
    if any(w.startswith("Original project core hashes changed") for w in report.get("warnings",[])):
        raise ValueError("Refuse to overwrite checkpoint after original source changed")
    if report["step"] not in {"already_running","reopen_existing_scratch"}:
        raise ValueError("Cannot checkpoint absent or incompatible scratch Editor session")
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ValueError("Checkpoint path is unsafe")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("Persistent bridge directory unavailable")
    if shutil.disk_usage(path.parent).free<100*1024**2:
        raise ValueError("Persistent disk critically full; refuse checkpoint write")
    output={
        "schema":SCHEMA,
        "captured_utc":datetime.now(timezone.utc).isoformat(),
        "original_project":report["project"],
        "scratch_project":report["scratch"],
        "scene":SCENE,
        "editor_version":VERSION,
        "source_sha256":report["source_sha256"],
        "scratch_source_sha256":report["scratch_source_sha256"],
        "scratch_loaded":report["scratch_loaded"],
        "scratch_terrain_differs":report["scratch_terrain_differs"],
        "last_camera_target":report.get("last_camera_target"),
        "recovery_note":"This is a durable state manifest, NOT a backup of /tmp Library or edited Assets.",
    }
    data=json.dumps(output,sort_keys=True,ensure_ascii=False,indent=2)+"\n"
    if len(data)>8000:
        raise ValueError("Checkpoint unexpectedly large")
    tmp=path.with_name(path.name+".new")
    if tmp.exists():
        raise ValueError("Checkpoint temp file already exists")
    descriptor=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(descriptor,"w") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp,path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return output


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint",action="store_true",help="Write small durable session manifest (does NOT copy Library)")
    p.add_argument("--original",type=Path,default=ORIGINAL)
    p.add_argument("--scratch",type=Path,default=SCRATCH)
    p.add_argument("--editor",type=Path,default=EDITOR)
    p.add_argument("--state-file",type=Path,default=CHECKPOINT)
    args=p.parse_args(argv)
    try:
        data=plan(args.original,args.scratch,args.editor,args.state_file)
        if args.checkpoint:
            data["checkpoint"]=write_checkpoint(data,args.state_file)
            data["writes_performed"]=1
    except (OSError,ValueError) as exc:
        print(json.dumps({"state":"error","error":str(exc)[:250]}))
        return 2
    print(json.dumps(data,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    sys.exit(main())
