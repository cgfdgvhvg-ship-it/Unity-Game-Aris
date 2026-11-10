#!/usr/bin/env bash
# Reclaim only verified disposable native-photo test worktrees. Never touch
# the original /workspaces/Unity-Game-Aris tree, Git LFS cache, Editor, or licenses.
set -Eeuo pipefail
SOURCE=/workspaces/Unity-Game-Aris
ROOT=/tmp/aaris-native-photo-worktrees
test -d "$SOURCE/.git" || { echo AARIS_TMP_RECLAIM_SOURCE_MISSING; exit 2; }
if pgrep -f '[E]ditor/Unity.*-projectPath|[s]cene_probe.sh|[o]ffline_drop_probe.sh' >/dev/null 2>&1; then
  echo AARIS_TMP_RECLAIM_BLOCKED_LIVE_UNITY
  exit 3
fi
if test ! -e "$ROOT"; then
  echo AARIS_TMP_RECLAIM_NO_DISPOSABLE_WORKTREES
  exit 0
fi
if test -L "$ROOT" || test ! -d "$ROOT" || test "$(realpath -e "$ROOT")" != "$ROOT"; then
  echo AARIS_TMP_RECLAIM_UNSAFE_ROOT
  exit 4
fi
# Worktree list is read only. The sole removal targets must be detached
# Git worktrees with commit-hash basenames directly below this fixed root.
python3 - "$SOURCE" "$ROOT" <<'PY'
from pathlib import Path
import os, re, subprocess, sys
source = Path(sys.argv[1])
root = Path(sys.argv[2])
def free_kb():
    st = os.statvfs("/tmp")
    return st.f_bavail * st.f_frsize // 1024
print("TMP_RECLAIM_FREE_KB_BEFORE=" + str(free_kb()))
info = subprocess.check_output(
    ["git", "-C", str(source), "worktree", "list", "--porcelain"],
    timeout=30, text=True)
records = []
for record in info.strip().split("\n\n"):
    lines = record.splitlines()
    if not lines or not lines[0].startswith("worktree "):
        continue
    p = Path(lines[0][9:])
    if p.parent != root:
        continue
    if not re.fullmatch(r"[0-9a-f]{40}", p.name):
        print("AARIS_TMP_RECLAIM_UNEXPECTED_WORKTREE_NAME")
        raise SystemExit(5)
    if "detached" not in lines or any(x.startswith("locked") for x in lines):
        print("AARIS_TMP_RECLAIM_PROTECTED_WORKTREE")
        raise SystemExit(6)
    if not p.is_dir() or p.is_symlink() or p.resolve() != p:
        print("AARIS_TMP_RECLAIM_INVALID_WORKTREE_PATH")
        raise SystemExit(7)
    records.append(p)
# Refuse to touch unknown files in the designated directory rather than
# assuming all of /tmp is disposable.
listed = {p.name for p in records}
if any(p.name not in listed for p in root.iterdir()):
    print("AARIS_TMP_RECLAIM_UNKNOWN_ENTRIES_NO_DELETION")
    raise SystemExit(8)
print("TMP_RECLAIM_VERIFIED_WORKTREES=" + str(len(records)))
for path in records:
    result = subprocess.run(
        ["git", "-C", str(source), "worktree", "remove", "--force", str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=420)
    if result.returncode != 0:
        print("AARIS_TMP_RECLAIM_GIT_WORKTREE_REMOVE_FAILED")
        raise SystemExit(9)
print("TMP_RECLAIM_REMOVED_WORKTREES=" + str(len(records)))
print("TMP_RECLAIM_FREE_KB_AFTER=" + str(free_kb()))
print("AARIS_TMP_RECLAIM_ORIGINAL_PROJECT_PRESERVED")
PY
