#!/usr/bin/env bash
# Review only the original user's running Unity Editor in the original Codespace.
# Play Mode is ALWAYS toggled off in an EXIT trap; source, scenes and Git
# working files are never deliberately edited, stashed, reset or cleaned.
set -Eeuo pipefail
umask 077
export DISPLAY=:99
ROOT=/workspaces/Unity-Game-Aris
OUT=/tmp/aaris-codespaces/live-humanoid-review
mkdir -p "$OUT"
test -d "$ROOT/.git" || { echo 'LIVE_REVIEW_WRONG_PROJECT'; exit 11; }
cd "$ROOT"
command -v xdotool >/dev/null || { echo 'LIVE_REVIEW_XDOTOOL_MISSING'; exit 12; }
command -v scrot >/dev/null || { echo 'LIVE_REVIEW_SCROT_MISSING'; exit 13; }
DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || { echo 'LIVE_REVIEW_XDISPLAY_MISSING'; exit 14; }
pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null || { echo 'LIVE_REVIEW_EDITOR_NOT_RUNNING'; exit 15; }

WIN=""
while IFS= read -r candidate; do
  name="$(xdotool getwindowname "$candidate" 2>/dev/null || true)"
  if [[ "$name" == "Unity - Unity-Game-Aris - "* ]]; then
    WIN="$candidate"
    break
  fi
done < <(xdotool search --onlyvisible --name 'Unity - Unity-Game-Aris' 2>/dev/null || true)
test -n "$WIN" || { echo 'LIVE_REVIEW_UNITY_WINDOW_NOT_FOUND'; exit 16; }
GEOM="$(xdotool getwindowgeometry --shell "$WIN")"
WIDTH="$(awk -F= '$1=="WIDTH"{print $2}' <<< "$GEOM")"
HEIGHT="$(awk -F= '$1=="HEIGHT"{print $2}' <<< "$GEOM")"
[[ "$WIDTH" =~ ^[0-9]+$ && "$HEIGHT" =~ ^[0-9]+$ ]] || exit 17
test "$WIDTH" -ge 1000 && test "$HEIGHT" -ge 600 || { echo 'LIVE_REVIEW_UNEXPECTED_WINDOW_SIZE'; exit 18; }
HEAD="$(git rev-parse --short HEAD)"
BEFORE="$(git status --porcelain=v1 --untracked-files=no | sha256sum | cut -d ' ' -f1)"
started=0
mkdir -p "$OUT/screens"
rm -f "$OUT/screens/"*.png
shot() {
  local label="$1"
  xdotool windowactivate --sync "$WIN" >/dev/null
  scrot -o "$OUT/screens/$label.png" >/dev/null 2>&1
  test -s "$OUT/screens/$label.png"
}
cleanup() {
  # Leave the editor in Edit Mode even when Play Mode or motion tests fail.
  DISPLAY=:99 xdotool keyup --clearmodifiers w shift_L ctrl_L b 2>/dev/null || true
  if test "$started" = 1; then
    DISPLAY=:99 xdotool windowactivate "$WIN" >/dev/null 2>&1 || true
    DISPLAY=:99 xdotool key --clearmodifiers ctrl+p >/dev/null 2>&1 || true
    sleep 2
  fi
}
trap cleanup EXIT
xdotool windowactivate --sync "$WIN"
shot '00-before'
# The initial scene screenshot is checked independently before this test.
# Explicit UI condition: do not start if another agent already has Play Mode on.
# The screenshot at this Codespace showed the non-blue toolbar in Edit Mode.
xdotool key --clearmodifiers ctrl+p
started=1
sleep 11
# Select the existing Game tab: coordinates relative to the 1207x740 Unity
# editor window are stable in the inspected, unchanged workspace layout.
xdotool mousemove --window "$WIN" 334 96 click 1
sleep 3
shot '01-play-idle'
xdotool keydown w
sleep 2
shot '02-walk'
xdotool keyup w
xdotool keydown shift_L
xdotool keydown w
sleep 2
shot '03-sprint'
xdotool keyup w shift_L
xdotool key c
sleep 2
xdotool keydown w
sleep 2
shot '04-crouch-walk'
xdotool keyup w
xdotool key z
sleep 2
xdotool keydown w
sleep 2
shot '05-prone-crawl'
xdotool keyup w
xdotool key z
sleep 1
xdotool keydown ctrl_L
sleep 1
shot '06-punch'
xdotool keyup ctrl_L
xdotool keydown b
sleep 1
xdotool keyup b
sleep 2
shot '07-gloo-wall'
# Check nonblank screenshot output and whether actual Game frames changed.
python3 - "$OUT/screens" <<'PY'
from pathlib import Path
import sys,struct
p=Path(sys.argv[1])
expected=[p/f'{i:02d}-{name}.png' for i,name in enumerate(
    ('before','play-idle','walk','sprint','crouch-walk','prone-crawl','punch','gloo-wall'))]
for f in expected:
    if not f.is_file() or f.stat().st_size < 10000: raise SystemExit('LIVE_REVIEW_FRAME_MISSING')
sizes=[]
for f in expected:
    header=f.open('rb').read(24)
    if len(header)!=24 or header[:8]!=bytes((137,80,78,71,13,10,26,10)):
        raise SystemExit('LIVE_REVIEW_NOT_PNG')
    sizes.append(struct.unpack('>II',header[16:24]))
if len(set(sizes))!=1:raise SystemExit('LIVE_REVIEW_SCREEN_SIZE_CHANGED')
if len({f.read_bytes()[:5000] for f in expected})<3:raise SystemExit('LIVE_REVIEW_TOO_FEW_UNIQUE_FRAMES')
print('LIVE_REVIEW_EIGHT_FRAMES_CAPTURED')
print('LIVE_REVIEW_SCREEN_DIMS='+str(sizes[0][0])+'x'+str(sizes[0][1]))
PY
AFTER="$(git status --porcelain=v1 --untracked-files=no | sha256sum | cut -d ' ' -f1)"
if test "$BEFORE" = "$AFTER"; then echo 'LIVE_REVIEW_TRACKED_WORKTREE_UNCHANGED'; else echo 'LIVE_REVIEW_TRACKED_WORKTREE_CHANGED_REVIEW_REQUIRED'; fi
printf 'LIVE_REVIEW_SOURCE_HEAD=%s\n' "$HEAD"
# No full editor logs, auth URLs or Unity credentials are copied into artifacts.
tar -C "$OUT" -czf "$OUT/gameplay-frames.tar.gz" screens
echo 'LIVE_REVIEW_SCREENSHOTS_READY_FOR_MANUAL_POSE_INSPECTION'
