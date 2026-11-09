#!/usr/bin/env bash
# Reclaim ONLY ignored Unity Library caches in two inactive /tmp review worktrees.
# No Git worktree, source, scene, prefab, terrain or LFS object is removed.
set -Eeuo pipefail
python3 - <<'PY'
import os,pathlib,re,shutil,subprocess,sys
ROOT=pathlib.Path("/tmp/aaris-native-photo-worktrees")
SOURCE=pathlib.Path("/workspaces/Unity-Game-Aris")
OLD_PREFIXES=("8bb6a4be31",)
def fail(reason):
    print("FOREST_SCRATCH_LIBRARY_REFUSED_"+reason)
    raise SystemExit(1)
if not ROOT.is_dir() or not SOURCE.is_dir():fail("SOURCE_MISSING")
running=subprocess.run(["pgrep","-f","[E]ditor/Unity.*-projectPath"],capture_output=True)
if running.returncode==0:fail("EDITOR_RUNNING")
registered=subprocess.run(["git","-C",str(SOURCE),"worktree","list","--porcelain"],
 capture_output=True,text=True,timeout=30)
if registered.returncode:fail("GIT_WORKTREE_REGISTRY_ERROR")
approved=[]
for prefix in OLD_PREFIXES:
    entries=[q for q in ROOT.iterdir() if q.is_dir() and not q.is_symlink()
             and q.name.startswith(prefix)]
    if len(entries)!=1:fail("REVIEW_WORKTREE_UNAVAILABLE")
    target=entries[0]
    if target.resolve().parent!=ROOT.resolve() or not re.fullmatch("[a-f0-9]{40}",target.name):
        fail("REVIEW_WORKTREE_INVALID_PATH")
    head=subprocess.run(["git","-C",str(target),"rev-parse","HEAD"],
          capture_output=True,text=True,timeout=30)
    if head.returncode or head.stdout.strip()!=target.name:fail("REVIEW_COMMIT_MISMATCH")
    if "worktree "+str(target)+"\n" not in registered.stdout:
        fail("REVIEW_NOT_REGISTERED")
    library=target/"Library"
    if library.is_symlink() or not library.is_dir() or library.resolve().parent!=target.resolve():
        fail("LIBRARY_NOT_ISOLATED")
    ignored=subprocess.run(["git","-C",str(target),"check-ignore","-q","--","Library"],
                 capture_output=True,timeout=30)
    if ignored.returncode:fail("LIBRARY_NOT_GIT_IGNORED")
    tracked=subprocess.run(["git","-C",str(target),"ls-files","--","Library"],
                 capture_output=True,text=True,timeout=30)
    if tracked.returncode or tracked.stdout.strip():fail("LIBRARY_CONTAINS_TRACKED_ASSETS")
    approved.append((prefix,library))
before=os.statvfs("/tmp")
free_before=before.f_bavail*before.f_frsize//1048576
for prefix,library in approved:
    shutil.rmtree(library)
    print("FOREST_SCRATCH_IGNORED_LIBRARY_RECLAIMED="+prefix)
after=os.statvfs("/tmp")
free_after=after.f_bavail*after.f_frsize//1048576
print("FOREST_SCRATCH_FREE_MIB_BEFORE="+str(free_before))
print("FOREST_SCRATCH_FREE_MIB_AFTER="+str(free_after))
if free_after<7500:fail("STILL_BELOW_SAFE_UNITY_DISK_BUDGET")
print("FOREST_SCRATCH_READONLY_SOURCE_PRESERVED=yes")
PY
