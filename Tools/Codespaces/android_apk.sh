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

# Official Unity CLI/Hub installations are the only supported source of
# Android SDK/NDK/JDK modules. If the original Unity Editor was installed
# manually, install the exact *same version* to isolated /tmp. Never touch the
# original Editor binary, its cache, the original GUI project or license files.
if test "$APK_MODULE" != present || test "$SDK" != present ||
   test "$NDK" != present || test "$JDK" != present; then
  if test -z "$CLI"; then echo APK_MODULE_INSTALL_CLI_MISSING; exit 16; fi
  echo APK_MODULE_INSTALL_START
  MODULE_OK=no
  if timeout 1200 env HOME="$AUTH_HOME" \
       UNITY_CLI_HOME="$AUTH_HOME/.local/share/aaris-unity-cli" \
       "$CLI" install-modules -e "$VERSION" -m android --cm \
       >"$BASE/private-module-install.log" 2>&1; then
    MODULE_OK=yes
    echo APK_EXISTING_CLI_MANAGED_EDITOR_MODULES_INSTALLED
  else
    echo APK_EDITOR_NOT_CLI_MANAGED_USING_ISOLATED_INSTALL
  fi
  if test "$MODULE_OK" = no; then
    test "$(df -BG /tmp | awk 'END {gsub(/G/,"",$4);print $4}')" -ge 25 || {
      echo APK_ISOLATED_INSTALL_INSUFFICIENT_TMP_DISK; exit 17;
    }
    MANAGED="$BASE/managed-editors"
    mkdir -p "$MANAGED"
    # The CLI install-path preference is user-local configuration. Save and
    # restore it on exit; do NOT reconfigure or move original Unity installs.
    PREV_INSTALL_PATH="$(env HOME="$AUTH_HOME" \
       UNITY_CLI_HOME="$AUTH_HOME/.local/share/aaris-unity-cli" \
       "$CLI" install-path --get 2>/dev/null | tail -n1 || true)"
    restore_install_path() {
      if test -n "$PREV_INSTALL_PATH" && test -d "$PREV_INSTALL_PATH"; then
        env HOME="$AUTH_HOME" \
           UNITY_CLI_HOME="$AUTH_HOME/.local/share/aaris-unity-cli" \
           "$CLI" install-path --set "$PREV_INSTALL_PATH" \
           >"$BASE/private-install-path-restore.log" 2>&1 || true
      fi
    }
    trap restore_install_path EXIT
    if ! env HOME="$AUTH_HOME" \
       UNITY_CLI_HOME="$AUTH_HOME/.local/share/aaris-unity-cli" \
       "$CLI" install-path --set "$MANAGED" \
       >"$BASE/private-install-path-setup.log" 2>&1; then
      echo APK_UNITY_CLI_TEMP_INSTALL_PATH_FAILED
      exit 18
    fi
    echo APK_ISOLATED_MANAGED_EDITOR_DOWNLOAD_STARTED
    if ! timeout 10500 env HOME="$AUTH_HOME" \
       UNITY_CLI_HOME="$AUTH_HOME/.local/share/aaris-unity-cli" \
       "$CLI" install "$VERSION" -c de8167e7440c -m android --cm --yes --accept-eula \
       >"$BASE/private-isolated-install.log" 2>&1; then
      echo APK_MANAGED_EDITOR_INSTALL_FAILED
      exit 19
    fi
    restore_install_path
    trap - EXIT
    echo APK_ISOLATED_MANAGED_EDITOR_INSTALLED
  fi
  # A CLI-managed copy might be in its own versioned parent directory.
  # Never silently build with an incompatible Unity version.
  LOOKUP=("$EDITOR"
    "$BASE/managed-editors/$VERSION/Editor/Unity"
    "$AUTH_HOME/Unity/Hub/Editor/$VERSION/Editor/Unity"
    "$AUTH_HOME/.local/share/unity3d/Hub/Editor/$VERSION/Editor/Unity")
  if test -d "$BASE/managed-editors"; then
    while IFS= read -r candidate; do LOOKUP+=("$candidate"); done < <(
      find "$BASE/managed-editors" -maxdepth 7 -path '*/Editor/Unity' -print
    )
  fi
  MATCH=""
  for candidate in "${LOOKUP[@]}"; do
    mod="$(dirname "$candidate")/Data/PlaybackEngines/AndroidPlayer"
    if test -x "$candidate" && test -d "$mod/Variations" &&
       test -d "$mod/SDK/platform-tools" && test -d "$mod/SDK/build-tools" &&
       test -d "$mod/NDK/toolchains" && test -x "$mod/OpenJDK/bin/java"; then
      MATCH="$candidate"
      break
    fi
  done
  if test -z "$MATCH"; then
    echo APK_ANDROID_MODULES_NOT_DISCOVERED; exit 20
  fi
  EDITOR="$MATCH"
  echo APK_ANDROID_MODULES_INSTALLED_AND_VERIFIED
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
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    (root/"apk-sha256.txt").write_text(sha+"  AarisGame.apk\n")
except Exception:
    raise SystemExit("APK_ARCHIVE_OR_NATIVE_REPORT_INVALID")
print("APK_BUILD_SUCCESS_VALID_ZIP")
print("apk_bytes="+str(p.stat().st_size))
PY
# Validate actual Android installation metadata before exposing an APK.
# The prior build was a valid ZIP, but did not check signing/API compatibility.
bash Tools/Codespaces/apk_install_diagnostic.sh \
  > "$BASE/private-native-installability-report.log" 2>&1 || {
    echo APK_INSTALLABILITY_TOOLS_FAILED; exit 32;
  }
CHECK="$BASE/private-native-installability-report.log"
grep -qxF APK_INSTALL_DIAG_APKSIGNER_VERIFY_PASS "$CHECK" || {
  echo APK_SIGNER_VERIFICATION_FAILED; exit 33;
}
grep -qxF APK_INSTALL_DIAG_ZIPALIGN_PASS "$CHECK" || {
  echo APK_ZIPALIGN_VERIFICATION_FAILED; exit 34;
}
grep -qxF apk_signature_v2=true "$CHECK" || {
  echo APK_V2_SIGNATURE_MISSING; exit 35;
}
grep -qxF apk_signer_count=1 "$CHECK" || {
  echo APK_SIGNER_COUNT_INVALID; exit 36;
}
grep -qxF apk_android_manifest=yes "$CHECK"
grep -qxF apk_classes_dex=yes "$CHECK"
grep -qxF apk_arm64_unity_lib=yes "$CHECK"
grep -qxF apk_min_sdk=26 "$CHECK"
grep -qxF apk_target_sdk=33 "$CHECK" || {
  echo APK_ANDROID_API_TARGET_UNEXPECTED; exit 37;
}
# New standalone Aaris Game package must not conflict with mapexplorer.
AAPT="$(find "$BASE/managed-editors" -type f -name aapt -print -quit 2>/dev/null || true)"
if ! test -x "$AAPT"; then echo APK_AAPT_MISSING; exit 38; fi
timeout 120 "$AAPT" dump badging "$BASE/Build/AarisGame.apk" \
  > "$BASE/private-package-id-report.log" 2>&1 || exit 39
grep -Eq "^package: name='com[.]aaris[.]game' versionCode='7'" \
  "$BASE/private-package-id-report.log" || {
    echo APK_PACKAGE_ID_OR_VERSION_INVALID; exit 40;
  }
echo APK_INSTALLABILITY_SIGNATURE_MANIFEST_API33_VERIFIED
echo "apk_commit=$SHA"
echo APK_UPLOAD_READY
