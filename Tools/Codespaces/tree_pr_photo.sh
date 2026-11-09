#!/usr/bin/env bash
# Owner-reviewed, isolated PR-head *real Unity* photo comparison.
# NO writes to original GUI project, license material, source refs or main.
set -Eeuo pipefail
REF="${1:-}"
[[ "$REF" =~ ^[0-9a-f]{40}$ ]] || { echo AARIS_PR_INVALID_COMMIT; exit 10; }
SOURCE=/workspaces/Unity-Game-Aris
ROOT=/tmp/aaris-native-tree-pr-review
PROJECT="$ROOT/$REF"
OUT=/tmp/aaris-codespaces/tree-pr-photo
RUN=/tmp/aaris-codespaces/scene-probe
BRANCH=upgrade/selective-pine-core-cover-20261109
EDITOR="$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity"
for option in "$EDITOR" /workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity /tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity; do
  if test -x "$option"; then EDITOR="$option"; break; fi
done
test -x "$EDITOR" || { echo AARIS_PR_EDITOR_MISSING; exit 11; }
test -e "$SOURCE/.git" || { echo AARIS_PR_SOURCE_MISSING; exit 12; }
# Use an exact immutable PR head and require it to still be the branch tip.
git -C "$SOURCE" fetch --quiet origin "refs/heads/$BRANCH" || {
  echo AARIS_PR_FETCH_FAILED; exit 13;
}
test "$(git -C "$SOURCE" rev-parse FETCH_HEAD)" = "$REF" || {
  echo AARIS_PR_HEAD_CHANGED; exit 14;
}
mkdir -p "$ROOT" "$OUT" "$RUN"
if test ! -d "$PROJECT"; then
  GIT_LFS_SKIP_SMUDGE=1 git -C "$SOURCE" -c filter.lfs.process= \
    -c filter.lfs.smudge=cat -c filter.lfs.required=false \
    worktree add --detach "$PROJECT" "$REF" >/dev/null 2>&1 || {
      echo AARIS_PR_ISOLATED_WORKTREE_FAILED; exit 15;
    }
fi
test "$(git -C "$PROJECT" rev-parse HEAD)" = "$REF" || {
  echo AARIS_PR_WORKTREE_SHA_MISMATCH; exit 16;
}
cd "$PROJECT"
if python3 Tools/Codespaces/restore_preserved_source_lfs.py "$PROJECT" >/dev/null 2>&1; then
  echo AARIS_PR_LFS_RESTORED_LOCAL_AND_VERIFIED
elif git lfs pull >/dev/null 2>&1; then
  echo AARIS_PR_LFS_REMOTE_HYDRATED
else
  echo AARIS_PR_LFS_HYDRATION_FAILED; exit 17
fi
test -s Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity || {
  echo AARIS_PR_NATIVE_SCENE_MISSING; exit 18;
}
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo AARIS_PR_EDITOR_BUSY; exit 19
fi
bash .devcontainer/start_screen.sh >/dev/null 2>&1 || {
  echo AARIS_PR_DISPLAY_SETUP_FAILED; exit 20;
}
DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || {
  echo AARIS_PR_DISPLAY_MISSING; exit 21;
}
mkdir -p "$OUT/UnityTemp"
# Remove only this review's previous output, never original Unity source.
rm -f "$OUT"/pr-photo-forest-{1,2}-{detail,context}.png "$OUT"/pr-photo-forest-{1,2}-report.json "$OUT"/pr-report.json
for spec in '1 418 -350 40 18 30' '2 65 870 165 18 30'; do
  read -r label x z yaw pitch distance <<< "$spec"
  rm -f "$RUN/photo-detail.png" "$RUN/photo-context.png" "$RUN/photo-report.json"
  set +e
  timeout --signal=TERM 1500 env DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1 \
    TMPDIR="$OUT/UnityTemp" "$EDITOR" -batchmode -quit -force-glcore \
    -projectPath "$PROJECT" \
    -executeMethod Aaris.MapReview.Editor.AarisCodespaceSceneProbe.CaptureAt \
    "-aarisX=$x" "-aarisZ=$z" "-aarisYaw=$yaw" \
    "-aarisPitch=$pitch" "-aarisDistance=$distance" \
    -logFile "$OUT/private-unity.log" >"$OUT/private-stdout.log" 2>"$OUT/private-stderr.log"
  rc=$?
  set -e
  if test "$rc" -ne 0; then
    echo AARIS_PR_NATIVE_EDITOR_FAILED
    case "$rc" in
      139) echo AARIS_PR_NATIVE_SIGSEGV ;;
      134) echo AARIS_PR_NATIVE_SIGABRT ;;
      124|143) echo AARIS_PR_NATIVE_TIMEOUT ;;
      *) echo AARIS_PR_NATIVE_NONZERO ;;
    esac
    exit 22
  fi
  for kind in detail context; do
    test -s "$RUN/photo-$kind.png" || { echo AARIS_PR_CAMERA_PNG_MISSING; exit 23; }
    cp "$RUN/photo-$kind.png" "$OUT/pr-photo-forest-$label-$kind.png"
  done
  test -s "$RUN/photo-report.json" || { echo AARIS_PR_REPORT_MISSING; exit 24; }
  cp "$RUN/photo-report.json" "$OUT/pr-photo-forest-$label-report.json"
  echo "AARIS_PR_FOREST_$label"_CAMERA_RENDERED
done
python3 - "$OUT" "$REF" <<'PY'
from pathlib import Path
import json,sys
folder=Path(sys.argv[1]); head=sys.argv[2]
reports=[]
for label,x,z in ((1,418,-350),(2,65,870)):
    path=folder/f"pr-photo-forest-{label}-report.json"
    d=json.loads(path.read_text())
    if (d.get("status")!="passed" or d.get("terrainTiles")!=4 or
        abs(d.get("targetX",0)-x)>0.1 or abs(d.get("targetZ",0)-z)>0.1 or
        min(d.get("detailVariation",0),d.get("contextVariation",0))<6):
        raise SystemExit("AARIS_PR_PHOTO_REPORT_INVALID")
    for kind in ("detail","context"):
        photo=folder/f"pr-photo-forest-{label}-{kind}.png"
        if photo.stat().st_size<8192 or photo.read_bytes()[:8]!=b"\\x89PNG\\r\\n\\x1a\\n":
            raise SystemExit("AARIS_PR_PHOTO_BYTES_INVALID")
    reports.append(dict(targetX=x,targetZ=z,detailVariation=d["detailVariation"],
                        contextVariation=d["contextVariation"],tiles=4))
(folder/"pr-report.json").write_text(json.dumps(dict(status="passed",headSha=head,
   mode="PR_HEAD_TWO_FOREST_VIEWS",cameraFrames=4,sites=reports),indent=2)+"\\n")
PY
echo AARIS_PR_HEAD_FOUR_REAL_UNITY_FRAMES_PASSED
