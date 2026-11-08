#!/usr/bin/env bash
# Owner-requested Unity Assets > Refresh (Ctrl+R). No source/scene reset.
set -Eeuo pipefail
export DISPLAY=:99
if ! DISPLAY=:99 xdpyinfo >/dev/null 2>&1 ||
   ! command -v xdotool >/dev/null 2>&1; then
  echo 'UNITY_REFRESH_NO_DISPLAY_OR_INPUT'
  exit 21
fi
if ! pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo 'UNITY_REFRESH_EDITOR_NOT_RUNNING'
  exit 22
fi
mapfile -t ids < <(xdotool search --onlyvisible --name 'Unity - Unity-Game-Aris' 2>/dev/null || true)
if (( ${#ids[@]} != 1 )); then
  echo 'UNITY_REFRESH_EDITOR_WINDOW_NOT_UNIQUE'
  exit 23
fi
wid="${ids[0]}"
title="$(xdotool getwindowname "$wid" 2>/dev/null || true)"
if [[ "$title" != *'Unity-Game-Aris'* ]]; then
  echo 'UNITY_REFRESH_WRONG_WINDOW'
  exit 24
fi
# Do not redirect clicks to the Safe Mode error dialogs or other processes.
if xdotool search --onlyvisible --name '^Enter Safe Mode\?$' >/dev/null 2>&1; then
  echo 'UNITY_REFRESH_BLOCKED_BY_SAFE_MODE_DIALOG'
  exit 25
fi
mkdir -p /tmp/aaris-codespaces
# The Unity Safe Mode Console retains stale errors from earlier sessions.
# Force a genuine C# reimport of the specific source affected by the
# reviewed VehiclesModule package fix; touch only changes the mtime.
PROJECT=/workspaces/Unity-Game-Aris
MOTOR="$PROJECT/Assets/AarisWorld/Scripts/AarisVehicleMotor.cs"
MANIFEST="$PROJECT/Packages/manifest.json"
if ! test -f "$MOTOR" || ! test -f "$MANIFEST"; then
  echo 'UNITY_REFRESH_VEHICLE_SOURCE_OR_MANIFEST_MISSING'
  exit 26
fi
python3 - "$MANIFEST" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f:
    d=json.load(f).get('dependencies',{})
if d.get('com.unity.modules.vehicles')!='1.0.0':
    print('UNITY_REFRESH_VEHICLES_MODULE_NOT_CONFIGURED')
    raise SystemExit(27)
PY
touch -c "$MOTOR" "$MANIFEST"
echo 'UNITY_VEHICLE_RECOMPILE_MTIME_REQUESTED'
date +%s >/tmp/aaris-codespaces/last-assets-refresh-epoch
xdotool windowactivate --sync "$wid"
xdotool key --clearmodifiers --window "$wid" ctrl+r
echo 'UNITY_ASSETS_REFRESH_REQUESTED'
