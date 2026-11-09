#!/usr/bin/env bash
# Read-only, bounded, owner-controlled Android build monitor.
# Never logs raw Unity CLI output, APK contents, account tokens, license state or paths.
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
import re
import subprocess
import zipfile

root=Path("/tmp/aaris-codespaces/android-apk")
editor=Path("/tmp/aaris-codespaces/android-apk/managed-editors")
apk=root/"Build/AarisGame.apk"
private_logs={
    "module":root/"private-module-install.log",
    "install":root/"private-isolated-install.log",
    "editor":root/"private-editor.log"
}
def size(p):
    try:return p.stat().st_size if p.is_file() else 0
    except OSError:return 0
def tail(p):
    try:
        with p.open("rb") as f:
            f.seek(max(0,size(p)-131072))
            return f.read().decode("utf-8","replace")
    except OSError:return ""
def classify():
    data="\n".join(tail(p) for p in private_logs.values())
    checks=[
        ("OUT_OF_SPACE",r"no space left|disk full|not enough disk"),
        ("ACCESS_DENIED",r"403|forbidden|access denied"),
        ("AUTH_REQUIRED",r"login required|authentication required|not authenticated|401 unauthorized"),
        ("RATE_LIMIT",r"429|rate limit"),
        ("NETWORK",r"could not resolve|connection reset|connection timed out|network unreachable|tls handshake"),
        ("MODULE_UNAVAILABLE",r"module.{0,80}not available|no matching module"),
        ("UNITY_COMPILER",r"error CS\d{4}"),
        ("ANDROID_SDK",r"SDK location not found|Android SDK is not installed"),
    ]
    for label,pattern in checks:
        if re.search(pattern,data,re.I):return label
    return "NO_CLASSIFIED_ERROR" if data else "NO_PRIVATE_LOG_YET"

def process_info():
    try:
        p=subprocess.run(["ps","-eo","args="],capture_output=True,text=True,timeout=6,check=True)
        data=p.stdout
    except (OSError,subprocess.SubprocessError):return ("unknown","unknown")
    # Fixed substring only; do not emit process arguments.
    install = bool(re.search(r"\bunity\s+(?:install|install-modules)\b",data))
    build=bool(re.search(r"/Editor/Unity\b[^\n]*-buildTarget\s+Android",data))
    return ("yes" if install else "no","yes" if build else "no")

def module_state():
    candidates=[
       Path("/home/vscode/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Data/PlaybackEngines/AndroidPlayer"),
       Path("/workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Data/PlaybackEngines/AndroidPlayer"),
    ]
    try:
        candidates += list(editor.glob("**/Editor/Data/PlaybackEngines/AndroidPlayer"))
    except OSError: pass
    for d in candidates[:20]:
        if all([(d/"Variations").is_dir(),(d/"SDK/platform-tools").is_dir(),
                (d/"SDK/build-tools").is_dir(),(d/"NDK/toolchains").is_dir(),
                (d/"OpenJDK/bin/java").is_file()]):
            return "ready"
    return "pending"

install,build=process_info()
report=root/"build-report.json"
status="not_created"
if report.is_file():
    try:
        d=json.loads(report.read_text())
        x=d.get("status","invalid")
        status=x if x in ("passed","failed") else "invalid"
    except (ValueError,OSError):status="invalid"
apk_bytes=size(apk)
apk_zip="unavailable"
if 100000<apk_bytes<2_000_000_000:
    try:
        with zipfile.ZipFile(apk) as z:
            names=set(z.namelist())
            if "AndroidManifest.xml" in names and any(n.endswith(".dex") for n in names):
                apk_zip="valid"
    except (OSError,zipfile.BadZipFile): pass
stage=("verified_apk" if status=="passed" and apk_zip=="valid"
       else "unity_build" if build=="yes"
       else "modules_install" if install=="yes"
       else "reported_failure" if status=="failed"
       else "apk_present_unverified" if apk_bytes>0
       else "toolchain_incomplete" if module_state()!="ready"
       else "modules_ready")
free_gb=0
try:
    s=subprocess.run(["df","-BG","/tmp"],capture_output=True,text=True,timeout=5,check=True).stdout.splitlines()[-1].split()
    free_gb=int(s[3].rstrip("G"))
except (OSError,ValueError,IndexError,subprocess.SubprocessError):pass
print("APK_READONLY_PROGRESS")
print("apk_stage="+stage)
print("apk_toolchain="+module_state())
print("apk_cli_installer_running="+install)
print("apk_unity_android_build_running="+build)
print("apk_module_log_bytes="+str(size(private_logs["module"])))
print("apk_install_log_bytes="+str(size(private_logs["install"])))
print("apk_editor_log_bytes="+str(size(private_logs["editor"])))
print("apk_build_report="+status)
print("apk_apk_bytes="+str(apk_bytes))
print("apk_apk_zip="+apk_zip)
print("apk_tmp_free_gb="+str(free_gb))
print("apk_error_class="+classify())
PY
