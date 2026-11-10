#!/usr/bin/env bash
# Exact existing Unity Codespace. Capture screenshots only; no Git reset/build/clean.
set -Eeuo pipefail
umask 077
export DISPLAY=:99
cd /workspaces/Unity-Game-Aris
OUT=/tmp/aaris-codespaces/animation-frame-by-frame
mkdir -p "$OUT/frames" "$OUT/sheets"
exec 9>"$OUT/frame-capture.lock"
flock -n 9 || { echo ANIM_FRAMES_OTHER_CAPTURE_RUNNING; exit 21; }
for bin in xdotool scrot convert montage xdpyinfo; do
  command -v "$bin" >/dev/null || { echo "ANIM_FRAMES_DEPENDENCY_MISSING_$bin"; exit 22; }
done
xdpyinfo >/dev/null 2>&1 || { echo ANIM_FRAMES_DISPLAY_MISSING; exit 23; }
pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null || { echo ANIM_FRAMES_UNITY_NOT_RUNNING; exit 24; }
WIN=""
while IFS= read -r id; do
  title="$(xdotool getwindowname "$id" 2>/dev/null || true)"
  if [[ "$title" == 'Unity - Unity-Game-Aris - '* ]]; then WIN="$id"; break; fi
done < <(xdotool search --onlyvisible --name 'Unity - Unity-Game-Aris' 2>/dev/null || true)
test -n "$WIN" || { echo ANIM_FRAMES_WINDOW_NOT_VISIBLE; exit 25; }
GEOM="$(xdotool getwindowgeometry --shell "$WIN")"
readgeom() { printf '%s\n' "$GEOM" | awk -F= -v n="$1" '$1==n{print $2}'; }
WX="$(readgeom X)"; WY="$(readgeom Y)"; WW="$(readgeom WIDTH)"; WH="$(readgeom HEIGHT)"
[[ "$WX" =~ ^[0-9]+$ && "$WY" =~ ^[0-9]+$ && "$WW" =~ ^[0-9]+$ && "$WH" =~ ^[0-9]+$ ]] || exit 26
(( WW >= 1050 && WH >= 630 )) || { echo ANIM_FRAMES_WINDOW_TOO_SMALL; exit 27; }
CROP_W=690; CROP_H=318; CX=$((WX + 230)); CY=$((WY + 125))
rm -f "$OUT/frames/"*.jpg "$OUT/sheets/"*.jpg "$OUT/full-before.png"
started=0
release_inputs() { xdotool keyup w Shift_L Control_L b 2>/dev/null || true; }
cleanup() {
  release_inputs
  if test "$started" = 1; then
    xdotool windowactivate "$WIN" >/dev/null 2>&1 || true
    xdotool key --clearmodifiers ctrl+p >/dev/null 2>&1 || true
    sleep 2
  fi
}
trap cleanup EXIT
xdotool windowactivate --sync "$WIN"
scrot -o "$OUT/full-before.png"
test -s "$OUT/full-before.png"
BEFORE="$(git status --porcelain=v1 --untracked-files=no | sha256sum | cut -d ' ' -f1)"
echo ANIM_FRAMES_SNAPSHOT_BEFORE_CAPTURED
xdotool key --clearmodifiers ctrl+p
started=1
sleep 16
xdotool windowactivate "$WIN"
xdotool mousemove --window "$WIN" 338 96 click 1
sleep 3
capture_frame() {
  local name="$1" i="$2" temp="$OUT/tmp-frame.png" target
  target="$(printf '%s/frames/%s-%02d.jpg' "$OUT" "$name" "$i")"
  sleep 0.18
  scrot -o "$temp"
  convert "$temp" -crop "$CROP_W"x"$CROP_H"+"$CX"+"$CY" +repage -quality 88 "$target"
  test -s "$target" || exit 28
}
capture_six() {
  local name="$1" i
  for i in 1 2 3 4 5 6; do capture_frame "$name" "$i"; done
  montage "$OUT/frames/$name"-*.jpg -tile 3x2 -geometry "$CROP_W"x"$CROP_H"+3+3 -background '#1d1d1d' -quality 91 "$OUT/sheets/$name-six-frames.jpg"
  test -s "$OUT/sheets/$name-six-frames.jpg"
  printf 'ANIM_FRAMES_GROUP_%s_SAVED\n' "$name"
}
capture_six idle
xdotool keydown w
capture_six walk
xdotool keyup w
xdotool keydown Shift_L
xdotool keydown w
capture_six sprint
xdotool keyup w Shift_L
xdotool key c
sleep 0.7
xdotool keydown w
capture_six crouch
xdotool keyup w
xdotool key c
sleep 0.5
xdotool key z
sleep 0.7
xdotool keydown w
capture_six prone
xdotool keyup w
xdotool key z
sleep 0.5
xdotool keydown Control_L
capture_six punch
xdotool keyup Control_L
xdotool keydown b
for i in 1 2 3; do capture_frame gloo "$i"; done
xdotool keyup b
for i in 4 5 6; do capture_frame gloo "$i"; done
montage "$OUT/frames/gloo"-*.jpg -tile 3x2 -geometry "$CROP_W"x"$CROP_H"+3+3 -background '#1d1d1d' -quality 91 "$OUT/sheets/gloo-six-frames.jpg"
python3 - "$OUT/frames" "$OUT/sheets" <<'PY'
import sys,pathlib,hashlib
frames=pathlib.Path(sys.argv[1]); sheets=pathlib.Path(sys.argv[2])
actions=('idle','walk','sprint','crouch','prone','punch','gloo')
for a in actions:
    images=sorted(frames.glob(a+'-*.jpg'))
    if len(images)!=6 or not (sheets/(a+'-six-frames.jpg')).is_file():
        raise SystemExit('ANIM_FRAMES_GROUP_INCOMPLETE_'+a)
    distinct=len({hashlib.sha256(p.read_bytes()).digest() for p in images})
    print('ANIM_FRAMES_'+a.upper()+'_DISTINCT_'+str(distinct))
print('ANIM_FRAMES_42_CAPTURED_IN_7_GROUPS')
PY
AFTER="$(git status --porcelain=v1 --untracked-files=no | sha256sum | cut -d ' ' -f1)"
if test "$BEFORE" = "$AFTER"; then echo ANIM_FRAMES_TRACKED_WORKTREE_UNCHANGED; else echo ANIM_FRAMES_TRACKED_WORKTREE_CHANGED_REVIEW; fi
tar -C "$OUT" -czf "$OUT/motion-capture.tar.gz" frames sheets full-before.png
test -s "$OUT/motion-capture.tar.gz"
echo ANIM_FRAMES_ARCHIVE_READY
