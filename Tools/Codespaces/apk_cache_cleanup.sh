#!/usr/bin/env bash
# Emergency bounded disk recovery WHILE a separate Unity Android build runs.
# Deletes ONLY regenerable Unity Library/Temp/obj caches of two finished,
# SHA-verified /tmp worktrees. Original /workspaces and LFS never modified.
set -Eeuo pipefail
CURRENT=93ee9c452785741aff302d425ef315f664b13f5f
ROOT_ANDROID=/tmp/aaris-native-android-build-worktrees
ROOT_PHOTO=/tmp/aaris-native-photo-worktrees
test -d "$ROOT_ANDROID/$CURRENT" || { echo APK_CACHE_ACTIVE_SNAPSHOT_NOT_PRESENT; exit 11; }
test "$(git -C "$ROOT_ANDROID/$CURRENT" rev-parse HEAD)" = "$CURRENT" || {
  echo APK_CACHE_ACTIVE_SOURCE_MISMATCH; exit 12;
}
# We never touch the current Android worktree or its import/IL2CPP intermediates.
before="$(df -BG /tmp | awk 'END {gsub(/G/,"",$4);print $4}')"
echo "apk_cache_tmp_free_gb_before=$before"
clean_one() {
  local root="$1" sha="$2" old="$1/$2" folder path
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || return 10
  [[ "$root" = "$ROOT_ANDROID" || "$root" = "$ROOT_PHOTO" ]] || return 11
  test -d "$old" || return 0
  test ! -L "$old" || return 12
  test "$(realpath -e "$old")" = "$old" || return 13
  test "$(git -C "$old" rev-parse HEAD 2>/dev/null)" = "$sha" || return 14
  # A running editor may not be interrupted, even if it is not the APK builder.
  if ps -eo args= | grep -F -- "$old" | grep -E '[/]Editor/Unity|[U]nity.*-projectPath' >/dev/null; then
    echo APK_CACHE_OLD_WORKTREE_STILL_ACTIVE
    return 15
  fi
  for folder in Library Temp obj; do
    path="$old/$folder"
    if test -d "$path" && test ! -L "$path"; then
      test "$(realpath -e "$path")" = "$path" || return 16
      rm -rf --one-file-system -- "$path"
    fi
  done
  echo APK_CACHE_FINISHED_WORKTREE_CACHES_RELEASED
}
# Both are proven, completed snapshots: old Android APK is already GitHub
# released, and the native fog A/B review completed in run 42619957981.
clean_one "$ROOT_ANDROID" 42d06ff89c30d41d5f0213cd8df9911b4ee00bbd
clean_one "$ROOT_PHOTO" d749cff3593d3da4842dd642c1ff779e884dfaa9
after="$(df -BG /tmp | awk 'END {gsub(/G/,"",$4);print $4}')"
echo "apk_cache_tmp_free_gb_after=$after"
echo APK_CACHE_OLD_ISOLATED_CACHES_SAFE_CLEAN_COMPLETE
