#!/usr/bin/env bash
# Only predetermined terminal tasks; no shell commands from public issue comments.
set -euo pipefail
TASK="$1"
PROJECT="/workspaces/Unity-Game-Aris"
RUN="/tmp/aaris-codespaces"
EDITOR="/workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity"
mkdir -p "$RUN"
cd "$PROJECT"
case "$TASK" in
  status)
    echo 'AARIS_CODESPACE_STATUS'
    printf 'commit=%s\n' "$(git rev-parse --short HEAD)"
    printf 'arch=%s\n' "$(uname -m)"
    printf 'cpus=%s\n' "$(nproc)"
    printf 'memory_mb=%s\n' "$(awk '/MemTotal:/ {printf "%.0f", $2/1024}' /proc/meminfo)"
    printf 'workspace_free_kb=%s\n' "$(df -Pk /workspaces | awk 'NR==2{print $4}')"
    printf 'tmp_free_kb=%s\n' "$(df -Pk /tmp | awk 'NR==2{print $4}')"
    if test -x "$EDITOR"; then echo 'editor_installed=yes'; else echo 'editor_installed=no'; fi
    if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then echo 'editor_running=yes'; else echo 'editor_running=no'; fi
    if DISPLAY=:99 xdpyinfo >/dev/null 2>&1; then echo 'display=ready'; else echo 'display=stopped'; fi
    if head -c 100 Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity 2>/dev/null | grep -q 'git-lfs.github.com/spec'; then
      echo 'scene=lfs_pointer'
    else echo 'scene=hydrated_or_missing'; fi
    ;;
  sync)
    # Never discard unsaved world edits or reset source files.
    if test -n "$(git status --porcelain --untracked-files=no)"; then echo 'SYNC_BLOCKED_DIRTY'; exit 8; fi
    git fetch --quiet origin main
    git merge --ff-only --quiet origin/main || { echo 'SYNC_NON_FAST_FORWARD'; exit 9; }
    git lfs pull >/dev/null 2>&1 || { echo 'SYNC_LFS_FAILED'; exit 10; }
    echo 'SYNC_LFS_READY'
    ;;
  install)
    bash "$PROJECT/Tools/Codespaces/install_unity.sh"
    ;;
  editor)
    test -x "$EDITOR" || { echo 'EDITOR_NOT_INSTALLED'; exit 11; }
    bash "$PROJECT/.devcontainer/start_screen.sh" >/dev/null
    if ! pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
      mkdir -p "$RUN/UnityTemp"
      nohup setsid env DISPLAY=:99 TMPDIR="$RUN/UnityTemp" LIBGL_ALWAYS_SOFTWARE=1 "$EDITOR" -projectPath "$PROJECT" -logFile "$RUN/Editor.log" </dev/null >/dev/null 2>&1 &
      sleep 8
    fi
    if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
      echo 'EDITOR_PROCESS_STARTED_LICENSE_NOT_VERIFIED'
    else echo 'EDITOR_LAUNCH_FAILED'; exit 12; fi
    ;;
  license)
    if test -x "$EDITOR"; then
      echo 'UNITY_EDITOR_BINARY_PRESENT_CHECK_HUB_LICENSE_MANUALLY'
    else echo 'UNITY_EDITOR_NOT_INSTALLED'; fi
    ;;
  shot)
    pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null || { echo 'SHOT_BLOCKED_EDITOR_NOT_RUNNING'; exit 14; }
    DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || { echo 'SHOT_BLOCKED_NO_DISPLAY'; exit 15; }
    scrot -o "$RUN/screen.png" || { echo 'SHOT_FAILED'; exit 16; }
    test -s "$RUN/screen.png" || exit 16
    VARIANCE="$(convert "$RUN/screen.png" -colorspace Gray -format '%[fx:standard_deviation]' info: 2>/dev/null || echo 0)"
    python3 - "$VARIANCE" <<'PY'
import sys
try: ok=float(sys.argv[1])>=0.015
except ValueError: ok=False
if not ok: raise SystemExit("SHOT_BLANK_REJECTED")
PY
    echo 'SHOT_CREATED_NEEDS_VISUAL_REVIEW'
    ;;
  test)
    python3 Tools/CI/ai_world_commands.py
    python3 Tools/CI/session_store.py selftest
    echo 'SELFTEST_OK'
    ;;
  *)
    echo 'INVALID_TASK'; exit 2 ;;
esac
