#!/usr/bin/env bash
# Read-only verification of the real APK already built in the owner Codespace.
# Fail closed: do not rebuild or alter the owner GUI workspace, assets or license.
set -Eeuo pipefail
SHA="$1"
EXPECTED_BYTES="$2"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo APK_RECOVERY_BAD_COMMIT; exit 11; }
[[ "$EXPECTED_BYTES" =~ ^[0-9]{6,10}$ ]] || { echo APK_RECOVERY_BAD_SIZE; exit 12; }
BASE=/tmp/aaris-codespaces/android-apk
PROJECT="/tmp/aaris-native-android-build-worktrees/$SHA"
test -d "$PROJECT" || { echo APK_RECOVERY_WORKTREE_MISSING; exit 13; }
test "$(git -C "$PROJECT" rev-parse HEAD)" = "$SHA" || {
  echo APK_RECOVERY_SOURCE_COMMIT_MISMATCH; exit 14;
}
test -s "$BASE/build-report.json" || { echo APK_RECOVERY_REPORT_MISSING; exit 15; }
test -s "$BASE/Build/AarisGame.apk" || { echo APK_RECOVERY_APK_MISSING; exit 16; }
test -s "$BASE/apk-sha256.txt" || { echo APK_RECOVERY_DIGEST_MISSING; exit 17; }
(
  cd "$BASE/Build"
  sha256sum -c "$BASE/apk-sha256.txt" >/dev/null
) || { echo APK_RECOVERY_DIGEST_MISMATCH; exit 18; }
python3 - "$BASE" "$EXPECTED_BYTES" <<'PY'
import json
from pathlib import Path
import sys
import zipfile
root=Path(sys.argv[1])
expected=int(sys.argv[2])
p=root/"Build/AarisGame.apk"
data=json.loads((root/"build-report.json").read_text())
assert data["status"]=="passed", "NATIVE_REPORT_NOT_PASSED"
assert data["reason"]=="NATIVE_ANDROID_APK_BUILD_SUCCEEDED", "WRONG_BUILD_REASON"
assert data["buildTarget"]=="Android" and data["sceneCount"]==1, "WRONG_TARGET_OR_SCENE"
assert data["terrainTiles"]==4 and data["scriptingBackend"]=="IL2CPP", "WRONG_NATIVE_MAP_OR_BACKEND"
assert data["unityVersion"]=="6000.3.26f1", "EDITOR_VERSION_MISMATCH"
assert p.stat().st_size==expected==data["apkBytes"], "APK_SIZE_MISMATCH"
with zipfile.ZipFile(p) as z:
    names=set(z.namelist())
    assert "AndroidManifest.xml" in names, "ANDROID_MANIFEST_MISSING"
    assert any(n.endswith(".dex") for n in names), "ANDROID_DEX_MISSING"
print("APK_EXISTING_NATIVE_ARCHIVE_VERIFIED")
PY
