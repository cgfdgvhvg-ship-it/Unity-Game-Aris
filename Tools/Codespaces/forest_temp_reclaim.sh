#!/usr/bin/env bash
# Reclaim ONE older /tmp-only Git review worktree; protect real owner workspace.
# Never delete /workspaces, active PR worktrees, or unverifiable local edits.
set -Eeuo pipefail
python3 - <<'PY'
import hashlib,os,pathlib,re,subprocess,sys
SOURCE=pathlib.Path("/workspaces/Unity-Game-Aris")
ROOT=pathlib.Path("/tmp/aaris-native-photo-worktrees")
PREFIX="02bed58cac"
def fail(msg):
 print("FOREST_TEMP_CLEAN_REFUSED_"+msg)
 raise SystemExit(1)
def git(*args):
 p=subprocess.run(["git",*args],capture_output=True,timeout=120)
 if p.returncode:fail("GIT_CHECK")
 return p.stdout
if not SOURCE.is_dir() or not ROOT.is_dir():fail("ROOT_MISSING")
running=subprocess.run(["pgrep","-f","[E]ditor/Unity.*-projectPath"],stdout=subprocess.DEVNULL)
if running.returncode==0:fail("EDITOR_RUNNING")
matches=[p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(PREFIX)]
if len(matches)!=1:fail("WORKTREE_NOT_UNIQUE")
target=matches[0]
if target.is_symlink() or target.resolve().parent!=ROOT.resolve():fail("WRONG_PATH")
if not re.fullmatch(r"[0-9a-f]{40}",target.name):fail("INVALID_REVISION")
head=git("-C",str(target),"rev-parse","HEAD").decode().strip()
if head!=target.name:fail("REVISION_CHANGED")
registered=git("-C",str(SOURCE),"worktree","list","--porcelain").decode(errors="replace")
if "worktree "+str(target)+"\n" not in registered:fail("WORKTREE_NOT_REGISTERED")
raw=git("-C",str(target),"status","--porcelain=v1","-z","--untracked-files=all")
items=[z for z in raw.decode("utf-8","surrogateescape").split("\x00") if z]
if len(items)>24:fail("TOO_MANY_CHANGED_FILES")
verified=0
for item in items:
 if len(item)<4 or item[:2] not in (" M","M ","MM"):
  fail("NON_LFS_OR_UNTRACKED_STATUS")
 rel=item[3:]
 if not rel.startswith("Assets/") or rel.startswith("Assets/Resources/"):
  fail("UNEXPECTED_MODIFIED_PATH")
 attr=git("-C",str(target),"check-attr","filter","--",rel).decode().strip()
 if not attr.endswith(": filter: lfs"):fail("UNEXPECTED_NON_LFS_PATH")
 pointer=git("-C",str(target),"show","HEAD:"+rel)
 m=re.fullmatch(rb"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?",pointer)
 if m is None:fail("NON_POINTER_MODIFICATION")
 file=target/rel
 if not file.is_file() or file.is_symlink():fail("MISSING_HYDRATED_ASSET")
 h=hashlib.sha256()
 with file.open("rb") as f:
  for part in iter(lambda:f.read(1024*1024),b""):h.update(part)
 if h.hexdigest()!=m.group(1).decode() or file.stat().st_size!=int(m.group(2)):
  fail("UNVERIFIED_ASSET_CONTENT")
 verified+=1
before=os.statvfs("/tmp");before_mb=before.f_bavail*before.f_frsize//1048576
# Git's own worktree remove performs the path/registry mutation. Force is safe
# only after every modified file has been proven byte-identical to HEAD LFS OID.
r=subprocess.run(["git","-C",str(SOURCE),"worktree","remove","--force",str(target)],
 capture_output=True,timeout=450)
if r.returncode:fail("GIT_WORKTREE_REMOVE")
after=os.statvfs("/tmp");after_mb=after.f_bavail*after.f_frsize//1048576
print("FOREST_TEMP_VERIFIED_LFS_HYDRATED_FILES="+str(verified))
print("FOREST_TEMP_RECLAIMED_WORKTREE="+PREFIX)
print("FOREST_TEMP_FREE_MIB_BEFORE="+str(before_mb))
print("FOREST_TEMP_FREE_MIB_AFTER="+str(after_mb))
if after_mb<3000:raise SystemExit("FOREST_TEMP_CAPACITY_STILL_LOW")
print("FOREST_TEMP_SCRATCH_RECLAIM_PASSED")
PY
