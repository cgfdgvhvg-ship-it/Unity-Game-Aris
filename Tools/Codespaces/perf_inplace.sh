#!/usr/bin/env bash
# Owner-only GitHub Issue control: tune the SAME Codespace project in place.
# No checkout, new worktree, scene rewrite, LFS reset, APK build or Git push.
set -Eeuo pipefail
MODE="${1:-audit}"
case "$MODE" in audit|tune) ;; *) echo 'AARIS_PERF_INVALID_MODE'; exit 2;; esac
RUN=/tmp/aaris-codespaces
mkdir -p "$RUN"
exec 9>"$RUN/perf-inplace.lock"
flock -n 9 || { echo 'AARIS_PERF_OTHER_SESSION_BUSY'; exit 28; }
python3 - "$MODE" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

mode=sys.argv[1]
root=Path("/workspaces/Unity-Game-Aris")
if not (root/".git").exists():
    raise SystemExit("AARIS_PERF_ORIGINAL_PROJECT_MISSING")
edits={
    "Assets/AarisWorld/Scripts/AarisWeaponLootWorld.cs":[
        ("private const int StreamFramesPerRefresh = 3;",
         "private const int StreamFramesPerRefresh = 5;"),
        ("private const int MaximumBuildAttemptsPerFrame = 2;",
         "private const int MaximumBuildAttemptsPerFrame = 1;"),
        ("private const int MaximumCandidateProbesPerFrame = 6;",
         "private const int MaximumCandidateProbesPerFrame = 4;"),
    ],
    "Assets/AarisWorld/Scripts/AarisVehicleWorld.cs":[
        ("if (active >= MaximumNearbyVehicles || built >= 2) break;",
         "if (active >= MaximumNearbyVehicles || built >= 1) break;"),
    ],
    "Assets/AarisWorld/Scripts/AarisNearbyColliders.cs":[
        ("nextCheck = Time.unscaledTime + .25f;",
         "nextCheck = Time.unscaledTime + .75f;"),
    ],
}
def sha(data):
    return hashlib.sha256(data).hexdigest()
planned={}
changed=0
for name,replacements in edits.items():
    p=root/name
    if p.is_symlink() or not p.is_file() or p.stat().st_size>2_000_000:
        raise SystemExit("AARIS_PERF_SOURCE_FILE_UNSAFE")
    original=p.read_bytes()
    if original.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise SystemExit("AARIS_PERF_SOURCE_IS_LFS_POINTER")
    try:
        before=original.decode("utf-8")
    except UnicodeDecodeError:
        raise SystemExit("AARIS_PERF_SOURCE_NOT_UTF8")
    after=before
    for old,new in replacements:
        old_count=after.count(old)
        new_count=after.count(new)
        if old_count==1 and new_count==0:
            after=after.replace(old,new,1)
        elif old_count==0 and new_count==1:
            pass
        else:
            raise SystemExit("AARIS_PERF_ANCHOR_UNEXPECTED_NO_FILES_WRITTEN")
    planned[name]=(p,original,after.encode("utf-8"))
    changed+=int(original != after.encode("utf-8"))
print("AARIS_PERF_SOURCE_PREFLIGHT_PASSED")
print("AARIS_PERF_SOURCE_COUNT_3")
print("AARIS_PERF_EXPECTED_EDITS_"+str(changed))
renderer=root/"Assets/TerrainDemoScene_URP/Settings/URP/Universal Render Pipeline Asset_Renderer.asset"
if renderer.is_file() and not renderer.read_bytes()[:110].startswith(b"version https://git-lfs.github.com/spec/v1"):
    print("AARIS_PERF_RENDERER_HYDRATED")
else:
    print("AARIS_PERF_RENDERER_UNVERIFIED")
# None of these edits changes source meshes, materials, terrain, native scene, shaders or draw distance.
print("AARIS_PERF_NATIVE_WORLD_UNCHANGED")
if mode=="audit":
    print("AARIS_PERF_AUDIT_COMPLETE")
    raise SystemExit(0)
if not changed:
    print("AARIS_PERF_TUNE_ALREADY_APPLIED")
    raise SystemExit(0)
backup_root=Path("/tmp/aaris-codespaces/perf-source-backups")
backup=backup_root/("tune-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
backup.mkdir(parents=True,exist_ok=False)
manifest=[]
for name,(p,original,after) in planned.items():
    target=backup/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(original)
    manifest.append(dict(file=name,before_sha256=sha(original),after_sha256=sha(after)))
(backup/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
written=[]
try:
    for name,(p,original,after) in planned.items():
        if original==after: continue
        if p.read_bytes()!=original:
            raise RuntimeError("source_modified_concurrently")
        descriptor,tmp=tempfile.mkstemp(prefix=".aaris-perf-",suffix=".tmp",dir=str(p.parent))
        try:
            with os.fdopen(descriptor,"wb") as handle:
                handle.write(after)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp,p.stat().st_mode & 0o777)
            if p.read_bytes()!=original:
                raise RuntimeError("source_modified_before_replace")
            os.replace(tmp,p)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        written.append(name)
    for name,(p,original,after) in planned.items():
        if p.read_bytes()!=after:
            raise RuntimeError("postwrite_hash_mismatch")
    git=subprocess.run(["git","-C",str(root),"diff","--check","--",
                        *edits.keys()],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if git.returncode!=0:
        raise RuntimeError("diff_check_failed")
except Exception:
    for name in reversed(written):
        p,original,after=planned[name]
        if p.read_bytes()==after:
            p.write_bytes(original)
    raise SystemExit("AARIS_PERF_TUNE_ABORTED_WITH_SAFE_ROLLBACK")
print("AARIS_PERF_TUNED_FILES_"+str(len(written)))
print("AARIS_PERF_TUNE_APPLIED_IN_ORIGINAL_CODESPACE")
print("AARIS_PERF_NO_GIT_PUSH_NO_WORKTREE")
PY
