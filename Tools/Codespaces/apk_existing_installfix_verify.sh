#!/usr/bin/env bash
# Release gate for the already compiled, source-tracked Aaris Game v7 APK.
# READ ONLY. Never runs Unity, changes its license, or touches original source.
set -Eeuo pipefail
BASE=/tmp/aaris-codespaces/android-apk
SHA=93ee9c452785741aff302d425ef315f664b13f5f
EXPECTED_SIZE=362307306
PROJECT="/tmp/aaris-native-android-build-worktrees/$SHA"
APK="$BASE/Build/AarisGame.apk"
[[ "$SHA" =~ ^[a-f0-9]{40}$ ]] || exit 11
test -d "$PROJECT" || { echo APK_INSTALLFIX_SOURCE_WORKTREE_MISSING; exit 12; }
test "$(git -C "$PROJECT" rev-parse HEAD)" = "$SHA" || {
  echo APK_INSTALLFIX_SOURCE_REVISION_MISMATCH; exit 13;
}
test -s "$BASE/build-report.json" && test -s "$BASE/apk-sha256.txt" && test -s "$APK" || {
  echo APK_INSTALLFIX_BUILD_EVIDENCE_MISSING; exit 14;
}
python3 - "$BASE" "$EXPECTED_SIZE" <<'PY'
import json, sys, zipfile
from pathlib import Path
root=Path(sys.argv[1])
p=root/"Build/AarisGame.apk"
d=json.loads((root/"build-report.json").read_text())
assert d["status"]=="passed" and d["reason"]=="NATIVE_ANDROID_APK_BUILD_SUCCEEDED"
assert d["unityVersion"]=="6000.3.26f1"
assert d["buildTarget"]=="Android" and d["sceneCount"]==1 and d["terrainTiles"]==4
assert d["scriptingBackend"]=="IL2CPP" and d["applicationId"]=="com.aaris.game"
assert p.stat().st_size==int(sys.argv[2])==d["apkBytes"]
with zipfile.ZipFile(p) as z:
    entries=set(z.namelist())
    assert "AndroidManifest.xml" in entries
    assert any(n.endswith(".dex") for n in entries)
    assert any(n.startswith("lib/arm64-v8a/") and n.endswith(".so") for n in entries)
print("APK_INSTALLFIX_NATIVE_BUILD_VERIFIED")
PY
(cd "$BASE/Build" && sha256sum -c "$BASE/apk-sha256.txt" >/dev/null) || {
  echo APK_INSTALLFIX_DIGEST_BAD; exit 15;
}
# Official Android SDK tools from the already-installed isolated Unity Editor.
APKSIGNER="$(find "$BASE/managed-editors" /home/vscode/.local/share/aaris-unity-editors /workspaces/.aaris-unity-editors -type f -name apksigner -print -quit 2>/dev/null || true)"
test -f "$APKSIGNER" || { echo APK_INSTALLFIX_APKSIGNER_UNAVAILABLE; exit 16; }
BUILD_TOOLS="$(dirname "$APKSIGNER")"
AAPT="$BUILD_TOOLS/aapt"
ZIPALIGN="$BUILD_TOOLS/zipalign"
test -x "$AAPT" && test -x "$ZIPALIGN" || {
  echo APK_INSTALLFIX_ANDROID_TOOLS_UNAVAILABLE; exit 17;
}
ANDROID_PLAYER="${BUILD_TOOLS%/SDK/build-tools/*}"
if test -x "$ANDROID_PLAYER/OpenJDK/bin/java"; then
  export JAVA_HOME="$ANDROID_PLAYER/OpenJDK"
  export PATH="$JAVA_HOME/bin:$PATH"
fi
timeout 180 "$APKSIGNER" verify --verbose --print-certs "$APK" \
  > "$BASE/private-installfix-signature.log" 2>&1 || {
  echo APK_INSTALLFIX_APK_SIGNATURE_INVALID; exit 18;
}
grep -qiE 'Verified using v2 scheme.*: true' "$BASE/private-installfix-signature.log" || {
  echo APK_INSTALLFIX_V2_SIGNATURE_MISSING; exit 19;
}
grep -qE '^Number of signers: 1$' "$BASE/private-installfix-signature.log" || {
  echo APK_INSTALLFIX_SIGNER_COUNT_WRONG; exit 20;
}
timeout 120 "$ZIPALIGN" -c -p 4 "$APK" > /dev/null 2>&1 || {
  echo APK_INSTALLFIX_ZIPALIGN_INVALID; exit 21;
}
timeout 120 "$AAPT" dump badging "$APK" \
  > "$BASE/private-installfix-aapt.log" 2>&1 || {
  echo APK_INSTALLFIX_MANIFEST_UNREADABLE; exit 22;
}
grep -Eq "^package: name='com[.]aaris[.]game' versionCode='7'" "$BASE/private-installfix-aapt.log" || {
  echo APK_INSTALLFIX_APP_PACKAGE_OR_VERSION_WRONG; exit 23;
}
grep -qx "sdkVersion:'26'" "$BASE/private-installfix-aapt.log" || {
  echo APK_INSTALLFIX_MIN_SDK_WRONG; exit 24;
}
# Unity 6000.3 targeted API 36 despite the stored target API 33.
# Target 36 is backward-compatible with the owner's Android 13 device.
grep -qx "targetSdkVersion:'36'" "$BASE/private-installfix-aapt.log" || {
  echo APK_INSTALLFIX_ACTUAL_TARGET_UNEXPECTED; exit 25;
}
echo APK_INSTALLFIX_NEW_GAME_V7_SIGNED_API36_VERIFIED
echo "apk_bytes=$EXPECTED_SIZE"
echo "apk_commit=$SHA"
echo APK_INSTALLFIX_READY_FOR_RELEASE
