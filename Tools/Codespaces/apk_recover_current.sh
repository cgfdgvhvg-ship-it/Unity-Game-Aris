#!/usr/bin/env bash
# Read-only handoff of an ALREADY successful Unity Android build in the exact owner's Codespace.
# Never launches Unity, touches the GUI project, or copies keys or private logs.
set -Eeuo pipefail
BASE=/tmp/aaris-codespaces/android-apk
APK="$BASE/Build/AarisGame.apk"
REPORT="$BASE/build-report.json"
test -f "$REPORT" && test -s "$APK" || { echo APK_RECOVERY_BUILD_OR_APK_MISSING; exit 11; }
python3 - "$REPORT" "$APK" <<'PY'
import json,sys,zipfile
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text())
p=Path(sys.argv[2])
required={"status":"passed","reason":"NATIVE_ANDROID_APK_BUILD_SUCCEEDED",
          "unityVersion":"6000.3.26f1","buildTarget":"Android",
          "applicationId":"com.aaris.game","scriptingBackend":"IL2CPP"}
for k,v in required.items():
    assert d.get(k)==v, "APK_RECOVERY_REPORT_"+k.upper()+"_INVALID"
for k,v in {"sceneCount":1,"terrainTiles":4,"applicationVersionCode":7}.items():
    assert d.get(k)==v, "APK_RECOVERY_REPORT_"+k.upper()+"_INVALID"
actual=p.stat().st_size
assert 100000<actual<2_000_000_000 and d.get("apkBytes")==actual, "APK_RECOVERY_SIZE_REPORT_MISMATCH"
with zipfile.ZipFile(p) as z:
    names=set(z.namelist())
    assert "AndroidManifest.xml" in names, "APK_RECOVERY_MANIFEST_MISSING"
    assert any(n.endswith(".dex") for n in names), "APK_RECOVERY_DEX_MISSING"
    assert any(n.startswith("lib/arm64-v8a/") and n.endswith(".so") for n in names), "APK_RECOVERY_ARM64_MISSING"
print("APK_RECOVERY_NATIVE_REPORT_AND_ARCHIVE_PASSED")
PY
# Validate actual Android signing and alignment, not merely ZIP validity.
APKSIGNER="$(find "$BASE/managed-editors" \
    /home/vscode/.local/share/aaris-unity-editors \
    /workspaces/.aaris-unity-editors -type f -name apksigner -print -quit 2>/dev/null || true)"
test -f "$APKSIGNER" || { echo APK_RECOVERY_SIGNER_TOOL_MISSING; exit 12; }
BUILD_TOOLS="$(dirname "$APKSIGNER")"
AAPT="$BUILD_TOOLS/aapt"
ZIPALIGN="$BUILD_TOOLS/zipalign"
test -x "$AAPT" && test -x "$ZIPALIGN" || { echo APK_RECOVERY_ANDROID_TOOLS_MISSING; exit 13; }
ANDROID_PLAYER="$(printf '%s' "$BUILD_TOOLS" | sed -E 's#/SDK/build-tools/[^/]+$##')"
if test -x "$ANDROID_PLAYER/OpenJDK/bin/java"; then
    export JAVA_HOME="$ANDROID_PLAYER/OpenJDK"
    export PATH="$JAVA_HOME/bin:$PATH"
fi
# Temporary verification logs stay on the Codespace. Never export certificates or secrets.
timeout 180 "$APKSIGNER" verify --verbose --print-certs "$APK" >"$BASE/private-recovered-apksigner.log" 2>&1 ||
    { echo APK_RECOVERY_SIGNATURE_FAILED; exit 14; }
grep -Eqi 'Verified using v2 scheme.*: true' "$BASE/private-recovered-apksigner.log" ||
    { echo APK_RECOVERY_V2_SIGNATURE_MISSING; exit 15; }
grep -qxF 'Number of signers: 1' "$BASE/private-recovered-apksigner.log" ||
    { echo APK_RECOVERY_SIGNER_COUNT_WRONG; exit 16; }
timeout 120 "$ZIPALIGN" -c -p 4 "$APK" >/dev/null 2>&1 ||
    { echo APK_RECOVERY_ZIPALIGN_FAILED; exit 17; }
timeout 120 "$AAPT" dump badging "$APK" >"$BASE/private-recovered-aapt.log" 2>&1 ||
    { echo APK_RECOVERY_PACKAGE_UNREADABLE; exit 18; }
python3 - "$BASE/private-recovered-aapt.log" <<'PY'
import re,sys
from pathlib import Path
data=Path(sys.argv[1]).read_text("utf-8","replace")
package=re.search(r"^package: name='([^']+)' versionCode='(\d+)'",data,re.M)
min_sdk=re.search(r"^sdkVersion:'(\d+)'$",data,re.M)
target=re.search(r"^targetSdkVersion:'(\d+)'$",data,re.M)
assert package and package.groups()==("com.aaris.game","7"), "APK_RECOVERY_WRONG_GAME_ID"
assert min_sdk and int(min_sdk.group(1))==26, "APK_RECOVERY_WRONG_MIN_SDK"
assert target and 26<=int(target.group(1))<=40, "APK_RECOVERY_TARGET_SDK_UNEXPECTED"
print("apk_actual_target_sdk="+target.group(1))
PY
# Reject a build currently overwriting the same APK.
if ps -eo args= | grep -E '[/]Editor/Unity.*-buildTarget Android' >/dev/null; then
    echo APK_RECOVERY_BUILD_IN_PROGRESS
    exit 19
fi
# Hash from present APK bytes; ignore stale older-build SHA files.
BYTES="$(stat -c %s "$APK")"
DIGEST="$(sha256sum "$APK" | awk '{print $1}')"
[[ "$DIGEST" =~ ^[0-9a-f]{64}$ && "$BYTES" =~ ^[0-9]{6,10}$ ]] || exit 20
echo "apk_bytes=$BYTES"
echo "apk_sha256=$DIGEST"
echo APK_RECOVERY_CURRENT_SIGNED_INSTALLABLE_VERIFIED
