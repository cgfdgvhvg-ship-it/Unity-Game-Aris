#!/usr/bin/env bash
# Owner-only GitHub Actions command. Compile the reviewed HUD/parachute PR
# in a disposable /tmp worktree without touching the current Codespace checkout.
set -Eeuo pipefail
umask 077
SOURCE=/workspaces/Unity-Game-Aris
FEATURE=fix/android-ugui-shader-parachute-20261110
ROOT=/tmp/aaris-hud-review
RUN=/tmp/aaris-codespaces/hud-review
EDITOR="$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity"
for fallback in /workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity /tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity; do
  if ! test -x "$EDITOR" && test -x "$fallback"; then EDITOR="$fallback"; fi
done
test -x "$EDITOR" || { echo HUD_REVIEW_EDITOR_MISSING; exit 11; }
test -d "$SOURCE/.git" || { echo HUD_REVIEW_SOURCE_MISSING; exit 12; }
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo HUD_REVIEW_EDITOR_BUSY
  exit 13
fi
mkdir -p "$ROOT" "$RUN/UnityTemp"
# Fetch only the published reviewed branch. No checkout, stash or reset in SOURCE.
if ! git -C "$SOURCE" fetch --quiet origin "+refs/heads/$FEATURE:refs/remotes/origin/$FEATURE"; then
  echo HUD_REVIEW_FETCH_FAILED
  exit 14
fi
SHA="$(git -C "$SOURCE" rev-parse --verify "refs/remotes/origin/$FEATURE^{commit}")"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo HUD_REVIEW_REF_INVALID; exit 15; }
PROJECT="$ROOT/$SHA"
if test ! -d "$PROJECT"; then
  GIT_LFS_SKIP_SMUDGE=1 git -C "$SOURCE" \
    -c filter.lfs.process= -c filter.lfs.smudge=cat -c filter.lfs.required=false \
    worktree add --detach "$PROJECT" "$SHA" >/dev/null 2>&1 || {
      echo HUD_REVIEW_WORKTREE_CREATE_FAILED; exit 16;
    }
fi
test "$(git -C "$PROJECT" rev-parse HEAD)" = "$SHA" || {
  echo HUD_REVIEW_WORKTREE_REF_MISMATCH; exit 17;
}
# Confirm exact original LFS bytes using the source machine and authenticated
# historical native-tree archive, not mock models or Git LFS pointers.
if python3 "$PROJECT/Tools/Codespaces/restore_preserved_source_lfs.py" "$PROJECT" >/dev/null 2>&1; then
  echo HUD_REVIEW_LFS_793_VERIFIED
elif git -C "$PROJECT" lfs pull > "$RUN/lfs-private.log" 2>&1; then
  echo HUD_REVIEW_LFS_PULL_COMPLETED
else
  echo HUD_REVIEW_LFS_NOT_HYDRATED
  exit 18
fi
SCENE="$PROJECT/Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
test -s "$SCENE" || { echo HUD_REVIEW_SCENE_MISSING; exit 19; }
if head -c 110 "$SCENE" | grep -q 'version https://git-lfs.github.com/spec/v1'; then
  echo HUD_REVIEW_SCENE_IS_POINTER
  exit 20
fi
test -s "$PROJECT/Assets/Resources/AarisHUDOverlay.shader" || {
  echo HUD_REVIEW_SHADER_MISSING; exit 21;
}
bash "$PROJECT/.devcontainer/start_screen.sh" >/dev/null 2>&1 || {
  echo HUD_REVIEW_DISPLAY_START_FAILED; exit 22;
}
DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || { echo HUD_REVIEW_DISPLAY_MISSING; exit 23; }
echo HUD_REVIEW_NATIVE_UNITY_IMPORT_STARTED
set +e
timeout --signal=TERM 1500 env DISPLAY=:99 TMPDIR="$RUN/UnityTemp" \
  LIBGL_ALWAYS_SOFTWARE=1 "$EDITOR" -batchmode -quit -force-glcore \
  -projectPath "$PROJECT" \
  -executeMethod Aaris.MapReview.Editor.AarisBattleHudValidation.Run \
  -logFile "$RUN/unity-private.log" > "$RUN/stdout-private.log" 2> "$RUN/stderr-private.log"
RC=$?
set -e
if test "$RC" -eq 0 && grep -q 'AARIS_BATTLE_HUD_IMPORT_PASS' "$RUN/unity-private.log" 2>/dev/null; then
  echo HUD_REVIEW_UNITY_IMPORT_AND_SHADER_PASS
  echo HUD_REVIEW_ANDROID_APK_STILL_UNVERIFIED
  exit 0
fi
if grep -Eq 'error CS[0-9]{4}' "$RUN/unity-private.log" 2>/dev/null; then
  echo HUD_REVIEW_CSHARP_COMPILATION_FAILED
elif grep -Eqi 'shader.*(error|unsupported|failed)|failed to compile shader' "$RUN/unity-private.log" 2>/dev/null; then
  echo HUD_REVIEW_SHADER_IMPORT_FAILED
elif grep -Eqi 'licen[sc]e.*(invalid|missing|failed|expired)' "$RUN/unity-private.log" 2>/dev/null; then
  echo HUD_REVIEW_LICENSE_REJECTED
elif test "$RC" -eq 124 || test "$RC" -eq 143; then
  echo HUD_REVIEW_EDITOR_TIMED_OUT
else
  echo HUD_REVIEW_NATIVE_IMPORT_NOT_CONFIRMED
fi
echo HUD_REVIEW_EXIT_NONZERO
exit 24
