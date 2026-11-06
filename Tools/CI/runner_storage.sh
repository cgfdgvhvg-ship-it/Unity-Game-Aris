#!/usr/bin/env bash
# Diagnose and safely reclaim disk on a NEW GitHub-hosted runner, before Unity Docker pulls.
# Usage: bash Tools/CI/runner_storage.sh audit|cleanup|selftest
set -euo pipefail
MODE="${1:-audit}"
case "$MODE" in audit|cleanup|selftest) ;; *) echo "Expected: audit|cleanup|selftest" >&2; exit 2;; esac
allowed() {
  case "$1" in
    /usr/share/dotnet|/usr/local/share/powershell|/opt/ghc|/usr/local/.ghcup) return 0 ;;
    *) return 1 ;;
  esac
}
if [[ "$MODE" == selftest ]]; then
  for p in /usr/share/dotnet /opt/ghc /usr/local/.ghcup; do allowed "$p" || exit 1; done
  for p in / /tmp /home/runner/work /opt/hostedtoolcache /usr/local/lib/android/sdk /project /mnt; do
    if allowed "$p"; then echo "FAIL unsafe path: $p"; exit 1; fi
  done
  echo "Safe Unity storage cleanup allowlist PASS"
  exit 0
fi
WORKSPACE="${GITHUB_WORKSPACE:-$PWD}"
REPORT_DIR="$WORKSPACE/ci-storage-reports"
mkdir -p "$REPORT_DIR"
TARGET_GIB=35
free_bytes() { df -PB1 "$WORKSPACE" | awk 'NR==2{print $4}'; }
BEFORE="$(free_bytes)"
echo "====== Aaris Unity / GitHub runner: $MODE ======"
echo "OS: $(uname -srm) | Runner: ${RUNNER_NAME:-unknown} | CPU threads: $(nproc)"
echo "RAM:"; free -h
echo "Filesystem info:"; df -hT / /tmp "$WORKSPACE"
echo "Block devices:"; lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS || true
echo "Project usage:"; du -sh "$WORKSPACE" 2>/dev/null || true
echo "Docker usage:"; docker system df 2>/dev/null || true
if [[ "$MODE" == cleanup ]]; then
  if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
    echo "Refusing cleanup outside GitHub-hosted Actions." >&2
    exit 3
  fi
  echo "Freeing APT caches and unused Docker layers (before Unity image pull)"
  sudo -n apt-get clean || true
  docker image prune -af 2>/dev/null || true
  docker builder prune -af 2>/dev/null || true
  if (( $(free_bytes) < TARGET_GIB * 1073741824 )); then
    echo "Available space below 35 GiB; cleaning UNUSED runner-only toolchains"
    for d in /opt/ghc /usr/local/.ghcup /usr/local/share/powershell /usr/share/dotnet; do
      allowed "$d" || exit 4
      if [[ -d "$d" && ! -L "$d" ]] && ! mountpoint -q "$d"; then
        echo "Deleting unused system toolchain: $d"
        sudo -n rm -rf -- "$d"
      fi
    done
  fi
  echo "PRESERVED: repository, .git, Git LFS, Unity Library, Android SDK/NDK/JDK, Unity license"
fi
AFTER="$(free_bytes)"
echo "Free bytes before: $BEFORE"
echo "Free bytes after:  $AFTER"
echo "Recovered bytes:   $((AFTER-BEFORE))"
if ((AFTER < 15*1073741824)); then
  echo "::warning::Less than 15 GiB available; Unity Docker/import may run out of space"
fi
export AARIS_BEFORE="$BEFORE" AARIS_AFTER="$AFTER" AARIS_MODE="$MODE"
python3 - "$REPORT_DIR/storage-$MODE.json" <<'PY'
import json, os, pathlib, platform, shutil, sys
def disk(path):
    u=shutil.disk_usage(path)
    return {"path":path,"total_bytes":u.total,"used_bytes":u.used,"free_bytes":u.free}
mem={}
for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
    if line.startswith(("MemTotal:","MemAvailable:")):
        k,v=line.split(":",1);mem[k]=int(v.strip().split()[0])
report={
 "mode":os.environ["AARIS_MODE"],"platform":platform.platform(),
 "cpu_threads":os.cpu_count(),"memory_total_kib":mem.get("MemTotal"),
 "memory_available_kib":mem.get("MemAvailable"),
 "before_free_bytes":int(os.environ["AARIS_BEFORE"]),
 "after_free_bytes":int(os.environ["AARIS_AFTER"]),
 "recovered_bytes":int(os.environ["AARIS_AFTER"])-int(os.environ["AARIS_BEFORE"]),
 "filesystems":[disk("/") ,disk("/tmp"),disk(os.environ.get("GITHUB_WORKSPACE") or os.getcwd())],
 "preserved":["Unity Assets","Unity Library","Git LFS",".git","Android SDK","NDK","JDK","license"]
}
pathlib.Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+"\n")
print("Report: "+sys.argv[1])
PY
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "### Unity Runner Storage ($MODE)"
    echo "| Metric | Value |"
    echo "|---|---:|"
    echo "| CPU logical threads | $(nproc) |"
    echo "| RAM | $(awk '/MemTotal:/{printf "%.1f GiB",$2/1048576}' /proc/meminfo) |"
    echo "| Free disk before | $(awk -v n="$BEFORE" 'BEGIN{printf "%.2f GiB",n/1073741824}') |"
    echo "| Free disk after | $(awk -v n="$AFTER" 'BEGIN{printf "%.2f GiB",n/1073741824}') |"
    echo "| Recovered disk | $(awk -v n="$((AFTER-BEFORE))" 'BEGIN{printf "%.2f GiB",n/1073741824}') |"
    echo
    echo "Unity project, Android toolchain, Library cache, LFS and credentials preserved."
  } >> "$GITHUB_STEP_SUMMARY"
fi
