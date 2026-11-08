#!/usr/bin/env bash
# Bounded, owner-issued Unity batch probe: no VNC window, arbitrary paths,
# force-kill, credentials, scene saves, Git resets or public raw logs.
set -Eeuo pipefail
MODE="$1"
case "$MODE" in render|play) ;; *) echo AARIS_PROBE_INVALID_MODE; exit 2 ;; esac
PROJECT="/workspaces/Unity-Game-Aris"
RUN="/tmp/aaris-codespaces/scene-probe"
EDITOR="$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity"
if ! test -x "$EDITOR"; then
  for fallback in "/workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity" "/tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity"; do
    if test -x "$fallback"; then EDITOR="$fallback"; break; fi
  done
fi
test -x "$EDITOR" || { echo AARIS_PROBE_EDITOR_MISSING; exit 11; }
cd "$PROJECT"
test "$(git branch --show-current)" = main || { echo AARIS_PROBE_REQUIRES_MAIN; exit 12; }
SCENE="Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
test -s "$SCENE" || { echo AARIS_PROBE_SCENE_MISSING; exit 13; }
if head -c 110 "$SCENE" | grep -q 'version https://git-lfs.github.com/spec/v1'; then
  echo AARIS_PROBE_LFS_POINTER
  exit 14
fi
test -s "Assets/AarisWorld/Editor/AarisCodespaceSceneProbe.cs" || {
  echo AARIS_PROBE_SOURCE_NOT_SYNCED
  exit 15
}
# Do not open the same Unity project twice. Never kill an existing GUI editor.
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo AARIS_PROBE_EDITOR_ALREADY_OPEN_USE_CS_CLOSE_EDITOR
  exit 16
fi
mkdir -p "$RUN/UnityTemp"
# Delete only the prior probe's own transient output; no native source assets.
rm -f "$RUN/map-overview.png" "$RUN/render-report.json" "$RUN/play-frame.png" "$RUN/play-report.json"
bash "$PROJECT/.devcontainer/start_screen.sh" >/dev/null 2>&1 || {
  echo AARIS_PROBE_XVFB_FAILED
  exit 17
}
DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || {
  echo AARIS_PROBE_DISPLAY_NOT_READY
  exit 18
}
if test "$MODE" = render; then
  METHOD="Aaris.MapReview.Editor.AarisCodespaceSceneProbe.Capture"
  REPORT="$RUN/render-report.json"
  IMAGE="$RUN/map-overview.png"
else
  METHOD="Aaris.MapReview.Editor.AarisCodespaceSceneProbe.Play"
  REPORT="$RUN/play-report.json"
  IMAGE="$RUN/play-frame.png"
fi
# A separate batch Editor avoids stale GUI/Safe Mode state and screenshots of
# Ubuntu's splash. Unity executes the method AFTER its C# import/compilation.
# No -nographics: Mesa/Xvfb must expose a real graphics device to URP.
set +e
if test "$MODE" = render; then
  timeout --signal=TERM 1500 env DISPLAY=:99 TMPDIR="$RUN/UnityTemp" \
    LIBGL_ALWAYS_SOFTWARE=1 "$EDITOR" -batchmode -quit -force-glcore \
    -projectPath "$PROJECT" -executeMethod "$METHOD" \
    -logFile "$RUN/unity-probe-editor.log" >"$RUN/private-stdout.log" 2>"$RUN/private-stderr.log"
  RC=$?
else
  # The Play probe itself exits after real Play Mode frame observations.
  timeout --signal=TERM 1500 env DISPLAY=:99 TMPDIR="$RUN/UnityTemp" \
    LIBGL_ALWAYS_SOFTWARE=1 "$EDITOR" -batchmode -force-glcore \
    -projectPath "$PROJECT" -executeMethod "$METHOD" \
    -logFile "$RUN/unity-probe-editor.log" >"$RUN/private-stdout.log" 2>"$RUN/private-stderr.log"
  RC=$?
fi
set -e
if test "$RC" -ne 0; then
  echo AARIS_PROBE_EDITOR_EXIT_NONZERO
  # No raw Unity log in public issues/artifacts. Report a diagnostic class.
  if grep -Eqi 'licen[sc]e.*(invalid|missing|failed|expired)|no valid.*licen[sc]e' "$RUN/unity-probe-editor.log" 2>/dev/null; then
    echo AARIS_PROBE_LICENSE_NOT_ACTIVE
  elif grep -Eqi 'error CS[0-9]{4}' "$RUN/unity-probe-editor.log" 2>/dev/null; then
    echo AARIS_PROBE_COMPILE_ERROR
  elif test "$RC" -eq 124 || test "$RC" -eq 143; then
    echo AARIS_PROBE_TIMED_OUT
  else
    echo AARIS_PROBE_EXECUTION_FAILED
  fi
  exit 20
fi
python3 - "$REPORT" "$IMAGE" "$MODE" <<'PY'
import json, pathlib, sys
report, image, mode = (pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3])
if not report.is_file():
    print("AARIS_PROBE_REPORT_MISSING")
    sys.exit(21)
try:
    data=json.loads(report.read_text())
except (ValueError,OSError):
    print("AARIS_PROBE_REPORT_INVALID")
    sys.exit(22)
if data.get("mode")!=mode or data.get("status")!="passed" or data.get("terrainTiles")!=4:
    print("AARIS_PROBE_SCENE_OR_PLAY_ASSERTIONS_FAILED")
    sys.exit(23)
if not image.is_file() or image.stat().st_size < 8192 or image.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
    print("AARIS_PROBE_REAL_PNG_MISSING")
    sys.exit(24)
if mode=="play":
    if data.get("frames",0)<60 or not all(data.get(k) for k in ("playerPresent","cameraPresent","vehicleManagerPresent")):
        print("AARIS_PROBE_PLAY_ASSERTIONS_MISSING")
        sys.exit(25)
    if data.get("runtimeErrors")!=0:
        print("AARIS_PROBE_RUNTIME_ERRORS")
        sys.exit(26)
if data.get("pixelStandardDeviation",0)<6:
    print("AARIS_PROBE_FLAT_FRAME_REJECTED")
    sys.exit(27)
print("AARIS_NATIVE_"+mode.upper()+"_PASSED")
print("terrain_tiles=4")
print("pixel_deviation="+format(data["pixelStandardDeviation"],".1f"))
print("image_bytes="+str(image.stat().st_size))
if mode=="play":
    print("play_frames="+str(data["frames"]))
    print("runtime_errors=0")
PY
