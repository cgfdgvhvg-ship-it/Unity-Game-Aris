#!/usr/bin/env bash
# Build Aaris Android APK inside an existing owner's Codespace only.
# No original dirty GUI workspace/reset/commit, no tokens/license files exported.
set -Eeuo pipefail
MODE="${1:-preflight}"
case "$MODE" in preflight|build) ;; *) echo APK_UNSUPPORTED_MODE; exit 2 ;; esac
SOURCE=/workspaces/Unity-Game-Aris
BASE=/tmp/aaris-codespaces/android-apk
VERSION=6000.3.26f1
mkdir -p "$BASE"
EDITOR="$HOME/.local/share/aaris-unity-editors/$VERSION/Editor/Unity"
for candidate in "$EDITOR" "/workspaces/.aaris-unity-editors/$VERSION/Editor/Unity" \
  "/tmp/aaris-unity-runtime/editors/$VERSION/Editor/Unity"; do
  if test -x "$candidate"; then EDITOR="$candidate"; break; fi
done
if ! test -x "$EDITOR"; then echo APK_EDITOR_MISSING; exit 11; fi
E_ROOT="$(dirname "$EDITOR")"
ANDROID="$E_ROOT/Data/PlaybackEngines/AndroidPlayer"
AUTH_HOME="$(getent passwd "$(id -u)" | cut -d: -f6)"
if ! test -d "$AUTH_HOME"; then AUTH_HOME="$HOME"; fi
CLI=""
for tool in "$AUTH_HOME/.local/bin/unity" \
            "$AUTH_HOME/.local/share/aaris-unity-cli/bin/unity" \
            "$HOME/.local/bin/unity" \
            "/tmp/aaris-unity-runtime/cli/bin/unity"; do
  if test -x "$tool"; then CLI="$tool"; break; fi
done
if test -z "$CLI"; then CLI="$(command -v unity || true)"; fi
if test -n "$CLI" && env HOME="$AUTH_HOME" \
    UNITY_CLI_HOME="$AUTH_HOME/.local/share/aaris-unity-cli" \
    "$CLI" license status --format json --non-interactive >/dev/null 2>&1; then
  echo APK_LICENSE_ACTIVE
else
  echo APK_LICENSE_NOT_VERIFIED
  if test "$MODE" = build; then exit 12; fi
fi
test -s "$SOURCE/ProjectSettings/EditorBuildSettings.asset" || {
  echo APK_BUILD_SETTINGS_MISSING; exit 13;
}
if grep -q 'path: Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity' \
  "$SOURCE/ProjectSettings/EditorBuildSettings.asset"; then
  echo APK_MAIN_SCENE_REGISTERED
else
  echo APK_MAIN_SCENE_NOT_REGISTERED; exit 14
fi
if test -e "$SOURCE/.git"; then echo APK_SOURCE_WORKSPACE_PRESENT;
else echo APK_SOURCE_WORKSPACE_NOT_FOUND; exit 15; fi
APK_MODULE=missing
if test -d "$ANDROID/Variations"; then APK_MODULE=present; fi
SDK=missing
if test -d "$ANDROID/SDK/platform-tools" && test -d "$ANDROID/SDK/build-tools"; then
  SDK=present
fi
NDK=missing
if test -d "$ANDROID/NDK" && test -d "$ANDROID/NDK/toolchains"; then
  NDK=present
fi
JDK=missing
if test -x "$ANDROID/OpenJDK/bin/java"; then JDK=present; fi
echo "apk_android_module=$APK_MODULE"
echo "apk_android_sdk=$SDK"
echo "apk_android_ndk=$NDK"
echo "apk_android_jdk=$JDK"
if test -n "$CLI"; then echo APK_UNITY_CLI_PRESENT
else echo APK_UNITY_CLI_MISSING; fi
echo "apk_tmp_free_gb=$(df -BG /tmp | awk 'END {gsub(/G/,"",$4);print $4}')"
echo APK_PREFLIGHT_RECORDED
if test "$MODE" = preflight; then exit 0; fi

# Use only Unity's supported Android modules, never an arbitrary Android SDK.
if test "$APK_MODULE" != present || test "$SDK" != present ||
   test "$NDK" != present || test "$JDK" != present; then
  if test -z "$CLI"; then echo APK_MODULE_INSTALL_CLI_MISSING; exit 16; fi
  echo APK_MODULE_INSTALL_START
  # Unity CLI can manage Editors installed via Hub/CLI. Keep download output private.
  if ! timeout 5700 env HOME="$AUTH_HOME" \
       UNITY_CLI_HOME="$AUTH_HOME/.local/share/aaris-unity-cli" \
       "$CLI" install-modules -e "$VERSION" -m android --cm \
       >"$BASE/private-module-install.log" 2>&1; then
    echo APK_MODULE_INSTALL_FAILED_NEEDS_HUB_MANAGED_EDITOR
    exit 17
  fi
  # The CLI can install its own managed copy; re-detect exact version, never use
  # a different Unity version and never overwrite original Editor.
  for candidate in "$EDITOR" "$AUTH_HOME/.local/share/unity3d/Hub/Editor/$VERSION/Editor/Unity" \
    "$AUTH_HOME/Unity/Hub/Editor/$VERSION/Editor/Unity" \
    "$AUTH_HOME/.local/share/aaris-unity-editors/$VERSION/Editor/Unity"; do
    if test -x "$candidate" && test -d "$(dirname "$candidate")/Data/PlaybackEngines/AndroidPlayer/Variations"; then
      EDITOR="$candidate"; break
    fi
  done
  E_ROOT="$(dirname "$EDITOR")"
  ANDROID="$E_ROOT/Data/PlaybackEngines/AndroidPlayer"
  if ! test -d "$ANDROID/Variations" ||
     ! test -d "$ANDROID/SDK/build-tools" ||
     ! test -d "$ANDROID/NDK/toolchains" ||
     ! test -x "$ANDROID/OpenJDK/bin/java"; then
    echo APK_MODULE_INSTALL_INCOMPLETE; exit 18
  fi
  echo APK_ANDROID_MODULES_INSTALLED
fi
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo APK_EXISTING_EDITOR_BUSY_NO_FORCE_KILL; exit 19
fi
git -C "$SOURCE" fetch --quiet origin main || {
  echo APK_MAIN_FETCH_FAILED; exit 20; }
SHA="$(git -C "$SOURCE" rev-parse --verify 'origin/main^{commit}')"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo APK_MAIN_SHA_INVALID; exit 21; }
ROOT=/tmp/aaris-native-android-build-worktrees
PROJECT="$ROOT/$SHA"
mkdir -p "$ROOT"
if test ! -d "$PROJECT"; then
  # Repair only a stale, missing, *exact* temporary worktree registration.
  if git -C "$SOURCE" worktree list --porcelain | grep -Fx "worktree $PROJECT" >/dev/null; then
    git -C "$SOURCE" worktree remove --force "$PROJECT" >/dev/null 2>&1 || {
      echo APK_STALE_TEMP_WORKTREE_REGISTRATION_FAILED; exit 22; }
  fi
  GIT_LFS_SKIP_SMUDGE=1 git -C "$SOURCE" -c filter.lfs.process= \
    -c filter.lfs.smudge=cat -c filter.lfs.required=false \
    worktree add --detach "$PROJECT" "$SHA" >/dev/null 2>&1 || {
    echo APK_ISOLATED_WORKTREE_FAILED; exit 23; }
fi
test "$(git -C "$PROJECT" rev-parse HEAD)" = "$SHA" || {
  echo APK_WORKTREE_SHA_MISMATCH; exit 24; }
cd "$PROJECT"
# Preserve exact 793 original LFS objects, with authentic SHA verification.
if python3 Tools/Codespaces/restore_preserved_source_lfs.py "$PROJECT" \
    >"$BASE/private-lfs.log" 2>&1; then
  echo APK_AUTHENTIC_LOCAL_LFS_VERIFIED
elif git lfs pull >"$BASE/private-lfs.log" 2>&1; then
  echo APK_REMOTE_LFS_HYDRATED
else
  echo APK_LFS_HYDRATION_FAILED; exit 25
fi
if head -c 110 Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity |
    grep -q 'git-lfs.github.com/spec'; then
  echo APK_NATIVE_SCENE_LFS_POINTER; exit 26
fi
test -s Assets/AarisWorld/Editor/AarisCodespaceAndroidBuild.cs || {
  echo APK_BUILD_SCRIPT_MISSING; exit 27; }
bash .devcontainer/start_screen.sh >"$BASE/private-screen.log" 2>&1 || {
  echo APK_DISPLAY_START_FAILED; exit 28
}
DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || {
  echo APK_DISPLAY_MISSING; exit 29; }
mkdir -p "$BASE/UnityTemp" "$BASE/Build"
rm -f "$BASE/Build/AarisGame.apk" "$BASE/build-report.json"
echo APK_NATIVE_UNITY_BUILD_STARTED
# -buildTarget Android is required BEFORE executeMethod to avoid broken
# batchmode domain reload/scripting target switches.
set +e
timeout --signal=TERM 12000 env DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1 \
  TMPDIR="$BASE/UnityTemp" "$EDITOR" -batchmode -quit -force-glcore \
  -projectPath "$PROJECT" -buildTarget Android \
  -executeMethod Aaris.MapReview.Editor.AarisCodespaceAndroidBuild.BuildTestApk \
  -logFile "$BASE/private-editor.log" \
  >"$BASE/private-stdout.log" 2>"$BASE/private-stderr.log"
RC=$?
set -e
if test "$RC" -ne 0; then
  if grep -Eq 'error CS[0-9]{4}' "$BASE/private-editor.log" 2>/dev/null; then
    echo APK_CSHARP_COMPILE_FAILED
  elif grep -Eqi 'licen[sc]e.*(invalid|expired|missing|failed)' "$BASE/private-editor.log" 2>/dev/null; then
    echo APK_EDITOR_LICENSE_FAILED
  elif test "$RC" = 124; then
    echo APK_EDITOR_TIMEOUT
  else
    echo APK_EDITOR_BUILD_FAILED
  fi
  exit 30
fi
python3 - "$BASE" <<'PY'
import json,pathlib,sys,hashlib,zipfile
root=pathlib.Path(sys.argv[1])
p=root/"Build/AarisGame.apk"
j=root/"build-report.json"
try:
    d=json.loads(j.read_text())
    assert d["status"]=="passed" and d["terrainTiles"]==4
    assert d["buildTarget"]=="Android" and d["sceneCount"]==1
    assert p.is_file() and 100000<p.stat().st_size<2_000_000_000
    assert p.read_bytes()[:2]==b'PK'
    with zipfile.ZipFile(p) as z:
        names=set(z.namelist())
        assert "AndroidManifest.xml" in names
        assert any(s.endswith(".dex") for s in names)
    sha=hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
    (root/"apk-sha256.txt").write_text(sha+"  AarisGame.apk\n")
except Exception:
    raise SystemExit("APK_ARCHIVE_OR_NATIVE_REPORT_INVALID")
print("APK_BUILD_SUCCESS_VALID_ZIP")
print("apk_bytes="+str(p.stat().st_size))
PY
echo "apk_commit=$SHA"
echo APK_UPLOAD_READY
