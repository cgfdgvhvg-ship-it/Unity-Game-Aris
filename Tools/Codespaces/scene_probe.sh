#!/usr/bin/env bash
# Bounded, owner-issued Unity batch probe: no VNC window, arbitrary paths,
# force-kill, credentials, scene saves, Git resets or public raw logs.
set -Eeuo pipefail
MODE="$1"
case "$MODE" in render|play|photo|foliage|survey) ;; *) echo AARIS_PROBE_INVALID_MODE; exit 2 ;; esac
SOURCE="/workspaces/Unity-Game-Aris"
RUN="/tmp/aaris-codespaces/scene-probe"
ISOLATED_ROOT="/tmp/aaris-native-photo-worktrees"
EDITOR="$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity"
if ! test -x "$EDITOR"; then
  for fallback in "/workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity" "/tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity"; do
    if test -x "$fallback"; then EDITOR="$fallback"; break; fi
  done
fi
test -x "$EDITOR" || { echo AARIS_PROBE_EDITOR_MISSING; exit 11; }
# The long-running GUI Codespace can have hundreds of genuine Unity-generated
# local material / project changes. Never discard or stash those edits just to
# take a photograph. Fetch the immutable main snapshot into its own worktree.
test -d "$SOURCE/.git" || test -f "$SOURCE/.git" || {
  echo AARIS_PROBE_SOURCE_REPOSITORY_MISSING
  exit 12
}
if ! git -C "$SOURCE" fetch --quiet origin main; then
  echo AARIS_PROBE_FETCH_MAIN_FAILED
  exit 12
fi
REV="$(git -C "$SOURCE" rev-parse --verify 'origin/main^{commit}')" || {
  echo AARIS_PROBE_MAIN_COMMIT_MISSING
  exit 12
}
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || { echo AARIS_PROBE_MAIN_SHA_INVALID; exit 12; }
mkdir -p "$ISOLATED_ROOT"
PROJECT="$ISOLATED_ROOT/$REV"
if test ! -d "$PROJECT"; then
  umask 077
  if ! GIT_LFS_SKIP_SMUDGE=1 git -C "$SOURCE" \
      -c filter.lfs.process= -c filter.lfs.smudge=cat \
      -c filter.lfs.required=false worktree add --detach "$PROJECT" "$REV" >/dev/null 2>&1; then
    echo AARIS_PROBE_ISOLATED_WORKTREE_CREATE_FAILED
    exit 13
  fi
fi
if test "$(git -C "$PROJECT" rev-parse HEAD)" != "$REV"; then
  echo AARIS_PROBE_ISOLATED_WORKTREE_SHA_MISMATCH
  exit 14
fi
cd "$PROJECT"
if ! git lfs pull >/dev/null 2>&1; then
  echo AARIS_PROBE_ISOLATED_LFS_PULL_FAILED
  exit 15
fi
SCENE="Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
test -s "$SCENE" || { echo AARIS_PROBE_SCENE_MISSING; exit 16; }
if head -c 110 "$SCENE" | grep -q 'version https://git-lfs.github.com/spec/v1'; then
  echo AARIS_PROBE_LFS_POINTER
  exit 17
fi
test -s "Assets/AarisWorld/Editor/AarisCodespaceSceneProbe.cs" || {
  echo AARIS_PROBE_SOURCE_NOT_SYNCED
  exit 18
}
echo AARIS_PROBE_ISOLATED_GIT_WORKTREE_READY
echo "probe_commit=$REV"
# Do not open the same Unity project twice. Never kill an existing GUI editor.
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo AARIS_PROBE_EDITOR_ALREADY_OPEN_USE_CS_CLOSE_EDITOR
  exit 16
fi
mkdir -p "$RUN/UnityTemp"
# Delete only the prior probe's own transient output; no native source assets.
case "$MODE" in
  render) rm -f "$RUN/map-overview.png" "$RUN/render-report.json" ;;
  play) rm -f "$RUN/play-frame.png" "$RUN/play-report.json" ;;
  photo) rm -f "$RUN/photo-detail.png" "$RUN/photo-context.png" "$RUN/photo-report.json" ;;
  survey) rm -f "$RUN"/survey-*.png "$RUN/survey-report.json" ;;
  foliage) rm -f "$RUN/foliage-original.png" "$RUN/foliage-far-lod.png" \
    "$RUN/foliage-ambient-test.png" "$RUN/foliage-ambient-only.png" \
    "$RUN/foliage-shadows-only.png" "$RUN/foliage-report.json" ;;
esac
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
elif test "$MODE" = foliage; then
  METHOD="Aaris.MapReview.Editor.AarisCodespaceSceneProbe.DiagnoseFoliage"
  REPORT="$RUN/foliage-report.json"
  IMAGE="$RUN/foliage-original.png"
elif test "$MODE" = survey; then
  METHOD="Aaris.MapReview.Editor.AarisCodespaceSceneProbe.CaptureSurvey"
  REPORT="$RUN/survey-report.json"
  IMAGE="$RUN/survey-sheet-1.png"
elif test "$MODE" = photo; then
  METHOD="Aaris.MapReview.Editor.AarisCodespaceSceneProbe.CaptureAt"
  REPORT="$RUN/photo-report.json"
  IMAGE="$RUN/photo-detail.png"
else
  METHOD="Aaris.MapReview.Editor.AarisCodespaceSceneProbe.Play"
  REPORT="$RUN/play-report.json"
  IMAGE="$RUN/play-frame.png"
fi
# A separate batch Editor avoids stale GUI/Safe Mode state and screenshots of
# Ubuntu's splash. Unity executes the method AFTER its C# import/compilation.
# No -nographics: Mesa/Xvfb must expose a real graphics device to URP.
set +e
if test "$MODE" = photo; then
  # The controller already validated and normalized these five finite
  # decimal values; no user-controlled string can become a shell command.
  test "$#" -eq 6 || { echo AARIS_PROBE_INVALID_COORDINATE_COUNT; exit 28; }
  for coordinate in "$2" "$3" "$4" "$5" "$6"; do
    [[ "$coordinate" =~ ^-?[0-9]{1,4}([.][0-9]{1,3})?$ ]] || {
      echo AARIS_PROBE_INVALID_COORDINATES
      exit 29
    }
  done
  timeout --signal=TERM 1500 env DISPLAY=:99 TMPDIR="$RUN/UnityTemp" \
    LIBGL_ALWAYS_SOFTWARE=1 "$EDITOR" -batchmode -quit -force-glcore \
    -projectPath "$PROJECT" -executeMethod "$METHOD" \
    "-aarisX=$2" "-aarisZ=$3" "-aarisYaw=$4" \
    "-aarisPitch=$5" "-aarisDistance=$6" \
    -logFile "$RUN/unity-probe-editor.log" >"$RUN/private-stdout.log" 2>"$RUN/private-stderr.log"
  RC=$?
elif test "$MODE" = render || test "$MODE" = foliage || test "$MODE" = survey; then
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
  if test "$MODE" = play && test -f "$RUN/play-report.json"; then
    python3 - "$RUN/play-report.json" <<'PYREPORT'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    allowed={"VEHICLE_SOURCE_MISSING","VEHICLE_CATALOG_INVALID","VEHICLE_CATALOG_MAP_MISMATCH",
       "VEHICLE_MODEL_MISSING","VEHICLE_SHADER_MISSING","LOOT_SOURCE_MISSING",
       "LOOT_DATA_INVALID","LOOT_DATA_MAP_MISMATCH","PLAYER_CAMERA_MISSING",
       "PLAYER_ANIMATION_CLIPS_INVALID","WEAPON_STATE_INVALID","NULL_REFERENCE",
       "MISSING_REFERENCE","UNASSIGNED_REFERENCE","ARRAY_INDEX","MISSING_COMPONENT",
       "VEHICLE_RUNTIME_EXCEPTION","LOOT_RUNTIME_EXCEPTION","PLAYER_RUNTIME_EXCEPTION",
       "VEHICLE_MOTOR_EXCEPTION","GAME_ASSERTION","UNCLASSIFIED_EXCEPTION","UNCLASSIFIED_ERROR",
       "UNITY_EXCEPTION","INVALID_OPERATION","NOT_SUPPORTED","INVALID_ARGUMENT",
       "IO_EXCEPTION","FILE_NOT_FOUND","TYPE_LOAD","INVALID_FORMAT",
       "MISSING_METHOD","OTHER_EXCEPTION"}
    k=d.get("runtimeErrorKind","")
    if k in allowed: print("runtime_error_kind="+k)
    source=d.get("runtimeErrorSource","")
    sources={"UNITY_ENGINE","UNITY_EDITOR","UNIDENTIFIED"}
    sources.update({"AARISWEAPONLOOTWORLD","AARISVEHICLEWORLD","AARISWEAPONCATALOG",
      "AARISVEHICLESESSION","AARISVEHICLEMOTOR","AARISTHIRDPERSONPLAYER",
      "AARISCHARACTERVISUAL","AARISMOBILERUNTIME","AARISBATTLEACTIONS",
      "AARISNEARBYCOLLIDERS","AARISEQUIPPEDGUN","AARISWEAPONINVENTORY",
      "AARISHUDBUTTON","AARISCICAPTURE","AARISCODESPACESCENEPROBE",
      "AARISWEAPONPICKUP","AARISWEAPONHUD","AARISVEHICLEHUD"})
    if source in sources: print("runtime_error_source="+source)
    n=d.get("runtimeErrors",-1)
    if type(n)==int and 0<=n<=10000:print("runtime_errors="+str(n))
    reason=d.get("reason","")
    if reason in {"PLAY_PREFLIGHT_FAILED","PLAY_MODE_TIMED_OUT","PLAY_RUNTIME_ASSERTIONS_FAILED"}:
        print("play_reason="+reason)
except (OSError,ValueError,TypeError):pass
PYREPORT
  fi
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
images = [image]
if mode=="photo":
    images.append(image.parent/"photo-context.png")
elif mode=="survey":
    images.extend([image.parent/("survey-sheet-%s.png"%n) for n in (2,3,4)])
elif mode=="foliage":
    images.extend([image.parent/"foliage-far-lod.png",
                   image.parent/"foliage-ambient-only.png",
                   image.parent/"foliage-shadows-only.png",
                   image.parent/"foliage-ambient-test.png"])
for candidate in images:
    if not candidate.is_file() or candidate.stat().st_size < 8192 or candidate.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        print("AARIS_PROBE_REAL_PNG_MISSING")
        sys.exit(24)
if mode=="play":
    if data.get("frames",0)<60 or not all(data.get(k) for k in ("playerPresent","cameraPresent","vehicleManagerPresent")):
        print("AARIS_PROBE_PLAY_ASSERTIONS_MISSING")
        sys.exit(25)
    if data.get("runtimeErrors")!=0:
        print("AARIS_PROBE_RUNTIME_ERRORS")
        sys.exit(26)
if mode=="foliage":
    if min(data.get("originalVariation",0),data.get("distantLodVariation",0),
           data.get("ambientOnlyVariation",0),data.get("shadowsOnlyVariation",0),
           data.get("ambientVariation",0)) < 6:
        print("AARIS_PROBE_FLAT_FOLIAGE_FRAME_REJECTED")
        sys.exit(27)
    print("tree_prototypes="+str(data.get("treePrototypes",0)))
    print("foliage_materials="+str(data.get("customFoliageMaterials",0)))
    print("image_bytes="+str(sum(p.stat().st_size for p in images)))
elif mode=="survey":
    places=data.get("locations",[])
    if data.get("locationCount")!=12 or data.get("frameCount")!=24 or len(places)!=12:
        print("AARIS_SURVEY_INCOMPLETE"); sys.exit(27)
    if any(min(site.get("detailVariation",0),site.get("contextVariation",0))<6 for site in places):
        print("AARIS_SURVEY_FLAT_SOURCE_FRAME_REJECTED"); sys.exit(27)
    print("native_survey_locations=12")
    print("native_survey_frames=24")
    print("contact_sheets=4")
    print("image_bytes="+str(sum(p.stat().st_size for p in images)))
elif mode=="photo":
    if min(data.get("detailVariation",0),data.get("contextVariation",0)) < 6:
        print("AARIS_PROBE_FLAT_FRAME_REJECTED")
        sys.exit(27)
    print("photo_target_x="+format(data.get("targetX",0),".1f"))
    print("photo_target_z="+format(data.get("targetZ",0),".1f"))
    print("photo_camera_y="+format(data.get("cameraY",0),".1f"))
    print("image_bytes="+str(sum(p.stat().st_size for p in images)))
else:
    if data.get("pixelStandardDeviation",0)<6:
        print("AARIS_PROBE_FLAT_FRAME_REJECTED")
        sys.exit(27)
    print("pixel_deviation="+format(data["pixelStandardDeviation"],".1f"))
    print("image_bytes="+str(image.stat().st_size))
print("AARIS_NATIVE_"+mode.upper()+"_PASSED")
print("terrain_tiles=4")
if mode=="play":
    print("play_frames="+str(data["frames"]))
    print("runtime_errors=0")
PY
