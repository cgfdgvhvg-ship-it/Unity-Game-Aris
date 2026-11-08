#!/usr/bin/env bash
# One-shot owner-only selection of Enter Safe Mode in the current Unity session.
# Unlike accepting legal terms, this is a safe diagnostic startup choice.
set -Eeuo pipefail
export DISPLAY=:99
if ! xdpyinfo >/dev/null 2>&1 || ! command -v xdotool >/dev/null; then
  echo SAFE_MODE_DISPLAY_OR_INPUT_MISSING
  exit 21
fi
mapfile -t windows < <(xdotool search --onlyvisible --name '^Enter Safe Mode\?$' 2>/dev/null || true)
if (( ${#windows[@]} != 1 )); then
  echo SAFE_MODE_WINDOW_NOT_UNIQUE
  exit 22
fi
wid="${windows[0]}"
if [[ "$(xdotool getwindowname "$wid" 2>/dev/null || true)" != 'Enter Safe Mode?' ]]; then
  echo SAFE_MODE_WRONG_DIALOG
  exit 23
fi
geometry="$(xdotool getwindowgeometry --shell "$wid")"
width="$(sed -n 's/^WIDTH=\([0-9]*\)$/\1/p' <<<"$geometry")"
height="$(sed -n 's/^HEIGHT=\([0-9]*\)$/\1/p' <<<"$geometry")"
if [[ ! "$width" =~ ^[0-9]{3,4}$ || ! "$height" =~ ^[0-9]{3,4}$ ]] ||
   ((width < 550 || width > 710 || height < 185 || height > 285)); then
  echo SAFE_MODE_UNEXPECTED_DIALOG_SIZE
  exit 24
fi
# Verified on the 1600x900 Unity 6000.3.26f1 screenshot:
# Button 1 is Enter Safe Mode; never click the adjacent Ignore / Quit buttons.
xdotool windowactivate --sync "$wid"
xdotool mousemove --window "$wid" "$((width * 38 / 100))" "$((height - 38))" click 1
sleep 5
if xdotool search --onlyvisible --name '^Enter Safe Mode\?$' >/dev/null 2>&1; then
  echo SAFE_MODE_DIALOG_STILL_VISIBLE
  exit 25
fi
echo SAFE_MODE_ENTER_CLICKED_DIALOG_CLOSED
