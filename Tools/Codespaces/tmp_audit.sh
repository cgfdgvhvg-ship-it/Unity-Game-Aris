#!/usr/bin/env bash
# Read-only, bounded inspection of Aaris /tmp caches and private Unity logs.
# Never emit paths, raw stack traces, credential material or source bytes.
set -Eeuo pipefail
python3 - <<'PY'
import os
from pathlib import Path
import re
import subprocess

SOURCE=Path("/workspaces/Unity-Game-Aris")
BASE=Path("/tmp")
ROOTS={
 "UNITY_RUNTIME":BASE/"aaris-unity-runtime",
 "CODESPACE_DIAGNOSTICS":BASE/"aaris-codespaces",
 "ISOLATED_SCENES":BASE/"aaris-native-photo-worktrees",
 "LFS_CACHE":BASE/"aaris-preserved-lfs-cache",
 "MAP_TESTS":BASE/"aaris-map-expansion-worktrees",
}
LIMIT=35000
def run(cmd,timeout=25):
 try:
  proc=subprocess.run(cmd,capture_output=True,timeout=timeout,check=False)
  return proc.stdout if proc.returncode==0 else None
 except (OSError,subprocess.TimeoutExpired):
  return None
def summary(path):
 if not path.is_dir() or path.is_symlink():return 0,0,False
 todo=[path];n=mb=0
 while todo and n<LIMIT:
  d=todo.pop()
  try:
   for f in d.iterdir():
    n+=1
    if n>LIMIT:break
    try:
     if f.is_symlink():continue
     if f.is_dir():todo.append(f)
     elif f.is_file():mb+=f.stat().st_size
    except OSError:continue
  except OSError:pass
 return n,mb//(1024*1024),bool(todo) or n>LIMIT
for name,path in ROOTS.items():
 n,mb,limited=summary(path)
 print("TMP_"+name+"_PRESENT_"+("YES" if path.is_dir() else "NO"))
 print("TMP_"+name+"_ENTRIES_"+str(n))
 print("TMP_"+name+"_MEGABYTES_"+str(mb))
 if limited:print("TMP_"+name+"_SCAN_LIMIT_REACHED")
print("TMP_SCAN_READ_ONLY")
LOGS={
 "EDITOR":BASE/"aaris-codespaces/Editor.log",
 "EDITOR_STDERR":BASE/"aaris-codespaces/editor-launch-stderr.log",
 "SCENE_EDITOR":BASE/"aaris-codespaces/scene-probe/unity-probe-editor.log",
 "SCENE_STDERR":BASE/"aaris-codespaces/scene-probe/private-stderr.log",
 "MAP_EDITOR":BASE/"aaris-codespaces/map-expansion-probe/private-editor.log",
 "LFS_PULL":BASE/"aaris-codespaces/scene-probe/private-lfs-pull.log",
}
PATTERNS={
 "CRASH":r"segmentation fault|sigsegv|signal 11|fatal error|native crash",
 "SHADER":r"shader.*(error|unsupported|failed)|failed to compile shader|invalid shader",
 "ASSET_IMPORT":r"assetdatabase.*(error|fail)|failed to import|import worker.*(crash|fail)",
 "PACKAGE":r"failed to resolve package|package manager.*error|manifest.*(invalid|error)",
 "EDITOR_LICENSE":r"no valid.*license|license.*(expired|invalid|failed|missing)",
 "MEMORY":r"out of memory|std::bad_alloc|failed to allocate|oom.killed",
 "SHARED_LIB":r"error while loading shared libraries|shared object file|undefined symbol",
 "PROJECT_LOCK":r"project.*(already open|in use|locked)",
 "GRAPHICS":r"glx.*error|failed to create.*gl|vulkan.*(error|failed)|mesa.*(error|failed)",
 "CS_ERROR":r"error cs[0-9]{4}",
 "LFS_ERROR":r"smudge error|batch response.*error|object.*missing|cannot download|lfs.*(error|fail)"
}
for kind,path in LOGS.items():
 if not path.is_file() or path.is_symlink():
  print("TMP_PRIVATE_LOG_"+kind+"_ABSENT");continue
 try:
  raw=path.open("rb").read(4*1024*1024)
  size=path.stat().st_size
  snippet=raw.decode("utf-8","replace")
 except OSError:
  print("TMP_PRIVATE_LOG_"+kind+"_UNREADABLE");continue
 print("TMP_PRIVATE_LOG_"+kind+"_PRESENT")
 print("TMP_PRIVATE_LOG_"+kind+"_KILOBYTES_"+str(size//1024))
 for family,pattern in PATTERNS.items():
  if re.search(pattern,snippet,re.I):
   print("TMP_PRIVATE_LOG_"+kind+"_"+family)
witness=BASE/"aaris-codespaces/editor-exit-code.txt"
if witness.is_file() and not witness.is_symlink():
 try:
  c=int(witness.read_text().strip())
  if c in (0,1,127,134,137,139,143):print("TMP_EDITOR_LAST_EXIT_"+str(c))
 except (OSError,ValueError):pass
if SOURCE.is_dir():
 dirty=run(["git","-C",str(SOURCE),"status","--porcelain=v1","--untracked-files=no","-z"])
 if dirty is not None:print("TMP_ORIGINAL_TRACKED_DIRTY_"+str(sum(bool(p) for p in dirty.split(b"\0"))))
 tracked=run(["git","-C",str(SOURCE),"lfs","ls-files","--name-only"])
 if tracked:
  paths=[x for x in tracked.decode("utf-8","replace").splitlines() if x]
  ptr=missing=0
  for rel in paths:
   file=SOURCE/rel
   try:
    with file.open("rb") as f:
     if f.read(100).startswith(b"version https://git-lfs.github.com/spec/v1"):ptr+=1
   except OSError:missing+=1
  print("TMP_ORIGINAL_LFS_TRACKED_"+str(len(paths)))
  print("TMP_ORIGINAL_LFS_POINTERS_"+str(ptr))
  print("TMP_ORIGINAL_LFS_MISSING_"+str(missing))
 backup=run(["git","-C",str(SOURCE),"ls-remote","--exit-code","origin",
            "refs/heads/backup/codespace-local-changes-20261108"])
 print("TMP_GITHUB_SOURCE_BACKUP_"+("FOUND" if backup else "UNCONFIRMED"))
print("TMP_AUDIT_COMPLETE")
PY