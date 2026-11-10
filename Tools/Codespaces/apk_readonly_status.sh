#!/usr/bin/env bash
# Read-only, bounded, owner-controlled Android build monitor.
# Never logs raw Unity CLI output, APK contents, account tokens, license state or paths.
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
import re
import subprocess
import time
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
    # Report only failures in the ACTIVE stage. A recovered CLI 403 during
    # module install is not a failed native Unity build hours later.
    if build == "yes":
        relevant = ("editor",)
    elif install == "yes":
        relevant = ("module", "install")
    else:
        relevant = ("editor", "install", "module")
    data="\n".join(tail(private_logs[name]) for name in relevant)
    checks=[
        ("OUT_OF_SPACE",r"no space left|disk full|not enough disk"),
        # Only actual permission/access error contexts; a bare numeric 403
        # can be an innocuous shader variant/asset count in Unity import logs.
        ("ACCESS_DENIED",r"\b(?:error|http|failed)[^\n]{0,90}\b403\b|\b403\b[^\n]{0,90}\b(?:error|forbidden|denied)\b|\bforbidden\b|\baccess\s+denied\b"),
        ("AUTH_REQUIRED",r"login required|authentication required|not authenticated|401 unauthorized"),
        # A bare 429 in a shader/import count is not HTTP 429.
        ("RATE_LIMIT",r"\b(?:http|status(?: code)?|response status)\s*[:=/ -]{0,15}429\b|\b429\s+(?:too many requests|rate[- ]limit(?:ed)?)\b|\b(?:rate[- ]limit(?:ed|ing)?|too many requests)\b"),
        ("NETWORK",r"could not resolve|connection reset|connection timed out|network unreachable|tls handshake"),
        ("MODULE_UNAVAILABLE",r"module.{0,80}not available|no matching module"),
        ("UNITY_COMPILER",r"error CS\d{4}"),
        ("ANDROID_SDK",r"SDK location not found|Android SDK is not installed"),
    ]
    for label,pattern in checks:
        if re.search(pattern,data,re.I):return label
    return "NO_CLASSIFIED_ERROR" if data else "NO_PRIVATE_LOG_YET"

def permission_signal():
    # Public diagnostics never include raw Unity, token or license messages.
    # Count only hits in a bounded editor tail, and emit a fixed subsystem
    # family. Do not conflate a numeric 403 elsewhere with HTTP denial.
    data=tail(private_logs["editor"])
    lines=[line for line in data.splitlines()
           if re.search(r"\b403\b|\bforbidden\b|\baccess\s+denied\b",line,re.I)]
    valid=[line for line in lines if re.search(
        r"\b(?:error|failed|http|forbidden|access|denied)\b",line,re.I)]
    if not valid:return (0,"none")
    joined="\n".join(valid[-6:]).lower()
    if any(t in joined for t in ("package", "registry", "upm", "packages.unity")):
        family="packages"
    elif any(t in joined for t in ("license", "entitlement", "activation")):
        family="license"
    elif any(t in joined for t in ("shader", "variant")):
        family="shader"
    elif any(t in joined for t in ("permission", "filesystem", "file access", "ioexception")):
        family="filesystem"
    elif any(t in joined for t in ("http", "forbidden", "network")):
        family="network"
    else:
        family="unclassified"
    return (min(1000,len(valid)),family)

def log_age_seconds(p):
    try:
        return max(0, int(time.time() - p.stat().st_mtime))
    except OSError:
        return 0

def process_info():
    try:
        p=subprocess.run(["ps","-eo","args="],capture_output=True,text=True,timeout=6,check=True)
        data=p.stdout
    except (OSError,subprocess.SubprocessError):return ("unknown","unknown","unknown")
    # Fixed substring only; do not emit process arguments.
    install = bool(re.search(r"\bunity\s+(?:install|install-modules)\b",data))
    build=bool(re.search(r"/Editor/Unity\b[^\n]*-buildTarget\s+Android",data))
    # Only the immutable 40-hex commit in the existing temp worktree.
    # No paths, arguments or other process data leave the Codespace.
    match=re.search(r"/tmp/aaris-native-android-build-worktrees/([0-9a-f]{40})(?:/|\\s|$)",data)
    source_sha=match.group(1) if match else "unknown"
    return ("yes" if install else "no","yes" if build else "no",source_sha)

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

install,build,source_sha=process_info()
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
print("apk_source_sha="+source_sha)
print("apk_module_log_bytes="+str(size(private_logs["module"])))
print("apk_install_log_bytes="+str(size(private_logs["install"])))
print("apk_editor_log_bytes="+str(size(private_logs["editor"])))
print("apk_editor_log_age_s="+str(log_age_seconds(private_logs["editor"])))
print("apk_build_report="+status)
print("apk_apk_bytes="+str(apk_bytes))
print("apk_apk_zip="+apk_zip)
print("apk_tmp_free_gb="+str(free_gb))
count,family=permission_signal()
print("apk_denied_mentions="+str(count))
print("apk_denied_family="+family)
print("apk_editor_csharp_errors="+str(min(999,len(re.findall(r"error CS\d{4}",tail(private_logs["editor"]),re.I)))))
print("apk_error_class="+classify())
PY
