#!/usr/bin/env bash
# Fresh independent GitHub checkout in /tmp on the EXACT owner-selected
# Codespace. Retain original dirty /workspaces, Unity license, and LFS caches.
set -Eeuo pipefail
umask 077
export GIT_TERMINAL_PROMPT=0
export GIT_LFS_SKIP_SMUDGE=1
SOURCE=/workspaces/Unity-Game-Aris
ROOT=/tmp/aaris-native-photo-worktrees
REPOSITORY=https://github.com/sundamunda289-art/Unity-Game-Aris.git
test -d "$SOURCE/.git" || { echo AARIS_TMP_SOURCE_MISSING; exit 10; }
test "$(git -C "$SOURCE" rev-parse --show-toplevel)" = "$SOURCE" || {
  echo AARIS_TMP_SOURCE_NOT_CANONICAL; exit 11;
}
if pgrep -f '[E]ditor/Unity.*-projectPath|[s]cene_probe.sh|[o]ffline_drop_probe.sh|[o]ffline_drop_collect.sh' >/dev/null 2>&1; then
  echo AARIS_TMP_EDITOR_OR_TEST_BUSY
  exit 12
fi
# Do not erase existing work, license credentials, other users' files, or
# unrecognized /tmp directories. Clean ONLY named disposable test output.
for obsolete in /tmp/aaris-offline-drop-worktrees /tmp/aaris-map-expansion-worktrees \
                /tmp/aaris-codespaces/offline-drop-probe \
                /tmp/aaris-codespaces/map-expansion-probe; do
  if test -L "$obsolete"; then echo AARIS_TMP_CLEAN_BLOCKED_SYMLINK; exit 13; fi
  if test -d "$obsolete"; then
    case "$(realpath -e "$obsolete")" in
      /tmp/aaris-offline-drop-worktrees|/tmp/aaris-map-expansion-worktrees|/tmp/aaris-codespaces/offline-drop-probe|/tmp/aaris-codespaces/map-expansion-probe) ;;
      *) echo AARIS_TMP_CLEAN_UNEXPECTED_PATH; exit 14 ;;
    esac
  fi
done
# Original tracked changes are deliberately retained; they may not be
# present in GitHub main and must never be discarded during a refresh.
echo AARIS_TMP_ORIGINAL_DIRTY_PROJECT_PRESERVED
BEFORE="$(df -Pk /tmp | awk 'NR==2 {print $4}')"
echo "TMP_REFRESH_FREE_KB_BEFORE=$BEFORE"
# Never unlink a directory still registered as a Git worktree of the
# owner's original repository; such paths need a separately reviewed removal.
REGISTERED="$(git -C "$SOURCE" worktree list --porcelain)"
for obsolete in /tmp/aaris-offline-drop-worktrees /tmp/aaris-map-expansion-worktrees \
                /tmp/aaris-codespaces/offline-drop-probe \
                /tmp/aaris-codespaces/map-expansion-probe; do
  if test ! -d "$obsolete"; then continue; fi
  if grep -Fq "worktree $obsolete/" <<< "$REGISTERED" ||
     grep -Fxq "worktree $obsolete" <<< "$REGISTERED"; then
    echo AARIS_TMP_REGISTERED_WORKTREE_PRESERVED
    continue
  fi
  rm -rf --one-file-system -- "$obsolete"
done
mkdir -p "$ROOT"
test -d "$ROOT" && test ! -L "$ROOT" && \
  test "$(realpath -e "$ROOT")" = "$ROOT" || {
  echo AARIS_TMP_ROOT_UNSAFE; exit 15;
}
STAGE="$(mktemp -d "$ROOT/.fresh-XXXXXX")"
PROJECT=""
cleanup() {
  if test -n "$STAGE" && test -d "$STAGE"; then rm -rf --one-file-system -- "$STAGE"; fi
}
trap cleanup EXIT
# New independent clone, not a new Codespace or a linked Git worktree.
if ! timeout 480 git clone --quiet --no-checkout --branch main \
    "$REPOSITORY" "$STAGE/repo" >/dev/null 2>&1; then
  echo AARIS_TMP_GITHUB_CLONE_FAILED; exit 16;
fi
SHA="$(git -C "$STAGE/repo" rev-parse HEAD)"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo AARIS_TMP_BAD_MAIN_SHA; exit 17; }
if test -e "$ROOT/$SHA"; then
  echo AARIS_TMP_TARGET_COMMIT_ALREADY_EXISTS_NO_OVERWRITE
  exit 18
fi
if ! git -C "$STAGE/repo" -c advice.detachedHead=false checkout --quiet --detach "$SHA" >/dev/null 2>&1; then
  echo AARIS_TMP_CHECKOUT_FAILED; exit 19
fi
mv -- "$STAGE/repo" "$ROOT/$SHA"
PROJECT="$ROOT/$SHA"
echo AARIS_TMP_CLEAN_GITHUB_MAIN_CHECKOUT_CREATED
echo "TMP_REFRESH_MAIN_COMMIT=$SHA"
# Verified LFS recovery first reuses byte-identical originals from the
# preserved source and authentic cached objects; remaining OIDs use origin.
# An existing signed-off 18-mesh archive is independently hash verified.
if ! timeout 1800 python3 "$PROJECT/Tools/Codespaces/restore_preserved_source_lfs.py" \
  "$PROJECT" 2>/dev/null; then
  echo AARIS_TMP_LFS_LOCAL_RECOVERY_INCOMPLETE
  if ! timeout 1500 git -C "$PROJECT" lfs pull origin >/dev/null 2>&1; then
    echo AARIS_TMP_LFS_REMOTE_PULL_FAILED; exit 20
  fi
fi
# Reverify EVERY checked-out LFS object's HEAD SHA-256 and size, not merely
# the absence of pointer text. This rejects corrupt, partial, or fake assets.
if ! python3 - "$PROJECT" <<'PY'
from pathlib import Path
import importlib.util, sys
repo=Path(sys.argv[1])
sys.path.insert(0,str(repo/"Tools/Codespaces"))
from restore_preserved_source_lfs import audit_pointers, candidate_matches
try:
    expected=audit_pointers(repo)
    ok=sum(candidate_matches(repo/name,oid,size) for name,(oid,size) in expected.items())
except Exception:
    print("AARIS_TMP_LFS_HASH_VERIFICATION_FAILED")
    sys.exit(22)
print("TMP_REFRESH_LFS_TRACKED="+str(len(expected)))
print("TMP_REFRESH_LFS_HASH_VERIFIED="+str(ok))
if ok != 793: sys.exit(23)
print("AARIS_TMP_ALL_LFS_REAL_ASSETS_VERIFIED")
PY
then
  echo AARIS_TMP_LFS_HASH_VERIFICATION_FAILED; exit 24
fi
test -s "$PROJECT/Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity" || {
  echo AARIS_TMP_SCENE_MISSING; exit 25
}
test "$(git -C "$PROJECT" status --porcelain --untracked-files=no | wc -l)" -eq 0 || {
  echo AARIS_TMP_NEW_CLONE_DIRTY; exit 26;
}
AFTER="$(df -Pk /tmp | awk 'NR==2 {print $4}')"
echo "TMP_REFRESH_FREE_KB_AFTER=$AFTER"
echo AARIS_TMP_GITHUB_PROJECT_READY
echo AARIS_TMP_ORIGINAL_WORKSPACE_UNCHANGED
