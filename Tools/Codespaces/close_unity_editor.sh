#!/usr/bin/env bash
# Explicit owner-requested graceful Unity Editor shutdown. No force-kill or reset.
set -Eeuo pipefail
export DISPLAY=:99
if ! pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo UNITY_EDITOR_ALREADY_CLOSED
  exit 0
fi
if ! xdpyinfo >/dev/null 2>&1 || ! command -v xdotool >/dev/null 2>&1; then
  echo UNITY_EDITOR_CLOSE_DISPLAY_MISSING
  exit 21
fi
mapfile -t windows < <(xdotool search --onlyvisible --name 'Unity - Unity-Game-Aris' 2>/dev/null || true)
if (( ${#windows[@]} != 1 )); then
  echo UNITY_EDITOR_CLOSE_WINDOW_NOT_UNIQUE
  exit 22
fi
wid="${windows[0]}"
if [[ "$(xdotool getwindowname "$wid" 2>/dev/null || true)" != *'Unity-Game-Aris'* ]]; then
  echo UNITY_EDITOR_CLOSE_WRONG_WINDOW
  exit 23
fi
# WM_DELETE_WINDOW offers Unity a chance to save/decline and shut down cleanly;
# deliberately do not send SIGKILL or discard unsaved changes.
xdotool windowclose "$wid"
for _ in $(seq 1 20); do
  if ! pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
    echo UNITY_EDITOR_GRACEFUL_EXIT_CONFIRMED
    exit 0
  fi
  sleep 1
done
echo UNITY_EDITOR_GRACEFUL_EXIT_PENDING_USER_DIALOG
exit 24
