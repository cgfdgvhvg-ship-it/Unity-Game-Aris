#!/usr/bin/env bash
# Read-only installability audit of the ACTUAL 363 MB release APK.
# Never prints private Unity logs, certificate identity, license or tokens.
set -Eeuo pipefail
BASE=/tmp/aaris-codespaces/android-apk
APK="$BASE/Build/AarisGame.apk"
test -s "$APK" || { echo APK_INSTALL_DIAG_FILE_MISSING; exit 11; }
mkdir -p "$BASE"
PRIVATE="$BASE/private-android-install-diagnostic.log"
# Use exactly the Android SDK belonging to the Unity Editor that built
# this APK. A random older SDK from a different editor can give false results.
PLAYER="${AARIS_ANDROID_PLAYER_ROOT:-}"
if test -z "$PLAYER" || ! test -d "$PLAYER/SDK/build-tools"; then
  echo APK_INSTALL_DIAG_EDITOR_SDK_NOT_SPECIFIED
  exit 12
fi
APKSIGNER="$(find "$PLAYER/SDK/build-tools" -maxdepth 2 -type f -name apksigner -print 2>/dev/null | sort -V | tail -n 1)"
printf '%s\n' "$APKSIGNER" > "$BASE/private-apksigner-location.txt"
if ! test -f "$APKSIGNER"; then
  echo APK_INSTALL_DIAG_APKSIGNER_MISSING
  exit 12
fi
SDK_BUILD="$(dirname "$APKSIGNER")"
PLAYER="${SDK_BUILD%/SDK/build-tools/*}"
JDK="$PLAYER/OpenJDK"
if test -x "$JDK/bin/java"; then export JAVA_HOME="$JDK"; export PATH="$JDK/bin:$PATH"; fi
echo APK_INSTALL_DIAG_TOOL_READY
if timeout 180 "$APKSIGNER" verify --verbose --print-certs "$APK" \
    > "$PRIVATE" 2>&1; then
  echo APK_INSTALL_DIAG_APKSIGNER_VERIFY_PASS
else
  echo APK_INSTALL_DIAG_APKSIGNER_VERIFY_FAIL
fi
if test -x "$SDK_BUILD/zipalign"; then
  if timeout 120 "$SDK_BUILD/zipalign" -c -p 4 "$APK" >/dev/null 2>&1; then
    echo APK_INSTALL_DIAG_ZIPALIGN_PASS
    if timeout 120 "$SDK_BUILD/zipalign" -c -P 16 4 "$APK" >/dev/null 2>&1; then
      echo APK_INSTALL_DIAG_ZIPALIGN_16K_PASS
    fi
  else
    echo APK_INSTALL_DIAG_ZIPALIGN_FAIL
  fi
else
  echo APK_INSTALL_DIAG_ZIPALIGN_UNAVAILABLE
fi
AAPT="$SDK_BUILD/aapt"
if test -x "$AAPT"; then
  timeout 120 "$AAPT" dump badging "$APK" > "$BASE/private-aapt-badging.log" \
    2>&1 || true
fi
python3 - "$BASE" <<'PY'
import re, sys, zipfile
from pathlib import Path
root=Path(sys.argv[1])
archive=root/"Build/AarisGame.apk"
log=(root/"private-android-install-diagnostic.log").read_text("utf8","replace")
for version in ("v1","v2","v3","v4"):
    result=re.search(r"Verified using "+version+r" scheme[^\n]*:\s*(true|false)",log,re.I)
    print("apk_signature_"+version+"="+(result.group(1).lower() if result else "unreported"))
result=re.search(r"Number of signers:\s*(\d+)",log)
print("apk_signer_count="+(result.group(1) if result else "unreported"))
with zipfile.ZipFile(archive) as z:
    names=set(z.namelist())
    print("apk_android_manifest="+("yes" if "AndroidManifest.xml" in names else "no"))
    print("apk_classes_dex="+("yes" if any(n.endswith(".dex") for n in names) else "no"))
    for label, abi in (("arm64", "arm64-v8a"), ("armv7", "armeabi-v7a")):
        required={f"lib/{abi}/{lib}" for lib in ("libunity.so", "libmain.so", "libil2cpp.so")}
        print(f"apk_{label}_unity_lib="+("yes" if required <= names else "no"))
    print("apk_v1_certificate_files="+str(sum(n.startswith("META-INF/") and n.upper().endswith((".RSA",".DSA",".EC")) for n in names)))
    print("apk_file_bytes="+str(archive.stat().st_size))
text=(root/"private-aapt-badging.log").read_text("utf8","replace") if (root/"private-aapt-badging.log").is_file() else ""
for key,pattern in (("min_sdk",r"sdkVersion:'(\d+)'"),("target_sdk",r"targetSdkVersion:'(\d+)'")):
    hit=re.search(pattern,text)
    print("apk_"+key+"="+(hit.group(1) if hit else "unreported"))
print("APK_INSTALL_DIAG_COMPLETE")
PY
