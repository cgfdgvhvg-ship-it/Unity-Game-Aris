#!/usr/bin/env bash
# Explicit one-shot acceptance of the visible Unity Editor Software Terms window.
# This script NEVER runs during Codespaces bootstrap, prebuild or background startup.
# It is available only through the owner-gated "CS ACCEPT TERMS" control.
set -Eeuo pipefail
export DISPLAY=:99
RUN=/tmp/aaris-codespaces
mkdir -p "$RUN"
if ! DISPLAY=:99 xdpyinfo >/dev/null 2>&1; then
  echo 'UNITY_TERMS_NO_DISPLAY'
  exit 21
fi
# The lightweight mouse utility is part of the reviewed, fixed Ubuntu GUI deps.
if ! command -v xdotool >/dev/null 2>&1; then
  echo 'UNITY_TERMS_INPUT_TOOL_MISSING_RUN_CS_DEPS'
  exit 22
fi
mapfile -t windows < <(xdotool search --onlyvisible --name '^Unity Editor Software Terms$' 2>/dev/null || true)
if (( ${#windows[@]} != 1 )); then
  echo 'UNITY_TERMS_WINDOW_NOT_UNIQUELY_VISIBLE'
  exit 23
fi
wid="${windows[0]}"
title="$(xdotool getwindowname "$wid" 2>/dev/null || true)"
if [[ "$title" != 'Unity Editor Software Terms' ]]; then
  echo 'UNITY_TERMS_WRONG_WINDOW'
  exit 24
fi
geometry="$(xdotool getwindowgeometry --shell "$wid")"
width="$(printf '%s\n' "$geometry" | sed -n 's/^WIDTH=\([0-9]*\)$/\1/p')"
height="$(printf '%s\n' "$geometry" | sed -n 's/^HEIGHT=\([0-9]*\)$/\1/p')"
if [[ ! "$width" =~ ^[0-9]{3,4}$ || ! "$height" =~ ^[0-9]{3,4}$ ]] ||
   (( width < 580 || width > 760 || height < 420 || height > 580 )); then
  echo 'UNITY_TERMS_UNEXPECTED_DIALOG_GEOMETRY'
  exit 25
fi
# Unity Editor 6000.3.26f1 Software Terms dialog (verified screenshot):
# the agreement checkbox is 5% from left, 85px from content bottom;
# Accept and Continue is 55% from left, 36px from bottom.
# Both clicks are relative to the EXACT identified window (not the whole screen).
xdotool windowactivate --sync "$wid"
xdotool mousemove --window "$wid" "$(( width * 5 / 100 ))" "$(( height - 85 ))" click 1
sleep 1
# Recheck that the very same dialog remains in front after selecting the checkbox.
if [[ "$(xdotool getwindowname "$wid" 2>/dev/null || true)" != 'Unity Editor Software Terms' ]]; then
  echo 'UNITY_TERMS_DIALOG_CHANGED_BEFORE_ACCEPT'
  exit 26
fi
xdotool mousemove --window "$wid" "$(( width * 55 / 100 ))" "$(( height - 36 ))" click 1
sleep 6
mapfile -t remaining < <(xdotool search --onlyvisible --name '^Unity Editor Software Terms$' 2>/dev/null || true)
if (( ${#remaining[@]} > 0 )); then
  echo 'UNITY_TERMS_DIALOG_STILL_VISIBLE'
  exit 27
fi
echo 'UNITY_TERMS_ACCEPT_AND_CONTINUE_CLICKED_DIALOG_CLOSED'
