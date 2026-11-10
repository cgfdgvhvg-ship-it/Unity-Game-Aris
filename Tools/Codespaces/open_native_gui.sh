#!/usr/bin/env bash
# Only operate the existing Unity GUI on the exact approved Codespace.
# No new Unity instance, worktree, git operation, scene write or approval bypass.
set -Eeuo pipefail
MODE="${1:-probe}"
test "$MODE" = probe || test "$MODE" = select || { echo UNITY_NATIVE_OPEN_BAD_MODE; exit 2; }
export DISPLAY=:99
SCENE=/workspaces/Unity-Game-Aris/Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity
test -f "$SCENE" || { echo UNITY_NATIVE_SCENE_MISSING; exit 10; }
if head -c 100 "$SCENE" | grep -q 'git-lfs.github.com/spec'; then
  echo UNITY_NATIVE_SCENE_POINTER_BLOCKED
  exit 11
fi
command -v xdotool >/dev/null || { echo UNITY_NATIVE_GUI_TOOL_MISSING; exit 12; }
DISPLAY=:99 xdpyinfo >/dev/null || { echo UNITY_NATIVE_DISPLAY_MISSING; exit 13; }
mapfile -t win < <(xdotool search --onlyvisible --name 'Unity - Unity-Game-Aris - Untitled' 2>/dev/null || true)
if test "$MODE" = probe; then
  if test "${#win[@]}" != 1; then echo UNITY_NATIVE_UNTITLED_NOT_UNIQUE; exit 14; fi
  xdotool windowactivate --sync "${win[0]}"
  xdotool key --clearmodifiers ctrl+o
  sleep 2
  echo UNITY_NATIVE_OPEN_DIALOG_REQUESTED
  exit 0
fi
# Select only from a real file chooser. Never type a path into an arbitrary GUI.
active="$(xdotool getactivewindow 2>/dev/null || true)"
test -n "$active" || { echo UNITY_NATIVE_NO_ACTIVE_DIALOG; exit 15; }
title="$(xdotool getwindowname "$active" 2>/dev/null || true)"
case "$title" in
  "Open"|"Open File"|"Open Scene"|"Select Scene"|"Select a Scene"|"Choose File") ;;
  *) echo UNITY_NATIVE_FILE_CHOOSER_UNVERIFIED; exit 16 ;;
esac
xdotool key --clearmodifiers ctrl+l
sleep 1
xdotool type --clearmodifiers --delay 1 "$SCENE"
xdotool key --clearmodifiers Return
sleep 3
# A save prompt is private user content: never click Discard/Don't Save.
mapfile -t prompts < <(xdotool search --onlyvisible --name 'Save Scene|Save Changes|Save modified' 2>/dev/null || true)
if (( ${#prompts[@]} > 0 )); then
  echo UNITY_NATIVE_SAVE_PROMPT_PRESERVED
  exit 17
fi
echo UNITY_NATIVE_SCENE_SELECTION_REQUESTED_NEEDS_VISUAL_REVIEW
