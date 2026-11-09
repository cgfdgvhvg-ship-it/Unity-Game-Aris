#!/usr/bin/env bash
# Reclaim ONLY Unity's ignored import Library cache in ONE inactive /tmp review.
# Never remove any Git worktree, prefab, TerrainData, LFS object, or user file.
set -Eeuo pipefail
python3 - <<'PY'
import os,pathlib,re,shutil,subprocess,sys
ROOT=pathlib.Path("/tmp/aaris-native-photo-worktrees")
SOURCE=pathlib.Path("/workspaces/Unity-Game-Aris")
OLD_PREFIX="06dca6ce3a"
def fail(msg):
  print("FOREST_TEMP_LIBRARY_REFUSED_"+msg)
  raise SystemExit(1)
if not ROOT.is_dir() or not SOURCE.is_dir():fail("SOURCE_MISSING")
if subprocess.run(["pgrep","-f","[E]ditor/Unity.*-projectPath"],stdout=subprocess.DEVNULL).returncode==0:
  fail("EDITOR_ACTIVE")
matches=[p for p in ROOT.iterdir() if p.is_dir() and not p.is_symlink() and p.name.startswith(OLD_PREFIX)]
if len(matches)!=1:fail("OLD_REVIEW_NOT_UNIQUE")
target=matches[0]
if not re.fullmatch(r"[a-f0-9]{40}",target.name) or target.resolve().parent!=ROOT.resolve():
  fail("REVIEW_PATH_NOT_VERIFIED")
head=subprocess.run(["git","-C",str(target),"rev-parse","HEAD"],capture_output=True,text=True,timeout=30)
if head.returncode or head.stdout.strip()!=target.name:fail("REVIEW_HEAD_CHANGED")
worktrees=subprocess.run(["git","-C",str(SOURCE),"worktree","list","--porcelain"],
  capture_output=True,text=True,timeout=30)
if worktrees.returncode or "worktree "+str(target)+"\n" not in worktrees.stdout:
  fail("TEMP_GIT_WORKTREE_NOT_REGISTERED")
library=target/"Library"
if library.is_symlink() or not library.is_dir() or library.resolve().parent!=target.resolve():
  fail("NO_SAFE_LIBRARY_FOLDER")
check=subprocess.run(["git","-C",str(target),"check-ignore","-q","--","Library"],
  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
if check.returncode:fail("LIBRARY_NOT_GIT_IGNORED")
tracked=subprocess.run(["git","-C",str(target),"ls-files","--","Library"],
  capture_output=True,text=True,timeout=30)
if tracked.returncode or tracked.stdout.strip():fail("LIBRARY_HAS_TRACKED_FILES")
before=os.statvfs("/tmp");free_before=before.f_bavail*before.f_frsize//1048576
# The exact ignored Unity import cache is disposable by design; the review
# source checkout and all its untracked/modified *non-Library* files remain.
shutil.rmtree(library)
after=os.statvfs("/tmp");free_after=after.f_bavail*after.f_frsize//1048576
print("FOREST_TEMP_OLD_REVIEW_HEAD="+target.name[:10])
print("FOREST_TEMP_LIBRARY_FREE_MIB_BEFORE="+str(free_before))
print("FOREST_TEMP_LIBRARY_FREE_MIB_AFTER="+str(free_after))
if free_after<5500:fail("INSUFFICIENT_FREE_AFTER_CLEAN")
print("FOREST_TEMP_IGNORED_LIBRARY_RECLAIM_PASSED")
PY
