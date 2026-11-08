#!/usr/bin/env bash
# Owner-authorized real Unity map review in EXISTING Codespace.
# It never checks out over the user's working tree, nor discards LFS assets.
set -Eeuo pipefail
umask 077
SOURCE=/workspaces/Unity-Game-Aris
FEATURE=feature/smart-settlement-expansion-20261108
TEMP_ROOT=/tmp/aaris-map-expansion-worktrees
RUN=/tmp/aaris-codespaces/map-expansion-probe
EDITOR="$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity"
for candidate in "/workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity" "/tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity"; do
  if ! test -x "$EDITOR" && test -x "$candidate"; then EDITOR="$candidate"; fi
done
test -x "$EDITOR" || { echo AARIS_MAP_EDITOR_NOT_INSTALLED; exit 11; }
test -d "$SOURCE/.git" || { echo AARIS_MAP_ORIGINAL_REPO_NOT_FOUND; exit 12; }

# Never take the GUI Editor away from the user or open the same Unity project twice.
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo AARIS_MAP_EDITOR_ALREADY_RUNNING; exit 13
fi
mkdir -p "$TEMP_ROOT" "$RUN" "$RUN/UnityTemp"
echo AARIS_MAP_SAME_CODESPACE_ORIGINAL_SOURCE_PRESERVED

if ! git -C "$SOURCE" fetch --quiet origin "+refs/heads/$FEATURE:refs/remotes/origin/$FEATURE"; then
  echo AARIS_MAP_FEATURE_BRANCH_FETCH_FAILED; exit 14
fi
REV="$(git -C "$SOURCE" rev-parse --verify "refs/remotes/origin/$FEATURE^{commit}")"
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || { echo AARIS_MAP_REF_INVALID; exit 14; }
PROJECT="$TEMP_ROOT/$REV"
if ! test -d "$PROJECT"; then
  GIT_LFS_SKIP_SMUDGE=1 git -C "$SOURCE" -c filter.lfs.process= \
    -c filter.lfs.smudge=cat -c filter.lfs.required=false \
    worktree add --detach "$PROJECT" "$REV" >/dev/null 2>&1 || {
      echo AARIS_MAP_WORKTREE_ADD_FAILED; exit 15;
    }
fi
test "$(git -C "$PROJECT" rev-parse HEAD)" = "$REV" || {
  echo AARIS_MAP_WORKTREE_SHA_INVALID; exit 16;
}
git -C "$PROJECT" lfs pull >/dev/null 2>&1 || {
  echo AARIS_MAP_LFS_PULL_FAILED; exit 17;
}

# Preserve all actual player-made edits by COPYING only bounded, known asset
# file types to a disposable /tmp test worktree. Never alter the original repo.
python3 - "$SOURCE" "$PROJECT" <<'PYOVERLAY'
import shutil,subprocess,sys
from pathlib import Path
source,target=map(Path,sys.argv[1:3])
args=[["git","-C",str(source),"diff","--name-only","-z","HEAD","--","Assets","Packages","ProjectSettings"],
      ["git","-C",str(source),"diff","--cached","--name-only","-z","--","Assets","Packages","ProjectSettings"]]
paths=set()
for cmd in args:
    paths.update(filter(None,subprocess.check_output(cmd).decode("utf-8","replace").split("\0")))
protected={
"Assets/AarisWorld/Scripts/AarisSettlementExpansion.cs",
"Assets/AarisWorld/Editor/AarisSettlementExpansionProbe.cs",
"Assets/Resources/AarisExpansion/WorldExpansionPlan.json",
"Assets/Resources/AarisExpansion/AarisExpansionCatalog.asset",
}
allowed={".mat",".meta",".unity",".asset",".prefab",".shader",".png",".jpg",".jpeg",
         ".obj",".fbx",".controller",".anim",".json",".cs",".tga",".terrainlayer",
         ".asmdef",".uxml",".uss",".overridecontroller"}
copied,total=0,0
for name in sorted(paths):
    path=Path(name)
    if name in protected:
        print("AARIS_MAP_PROTECTED_SOURCE_LOCALLY_MODIFIED")
        raise SystemExit(18)
    if (len(path.parts)<2 or path.parts[0] not in {"Assets","Packages","ProjectSettings"}
        or any(part.startswith(".") for part in path.parts) or path.suffix.lower() not in allowed):
        continue
    source_file=source/path
    target_file=target/path
    if not source_file.is_file() or source_file.is_symlink() or target_file.is_symlink():continue
    size=source_file.stat().st_size
    total+=size
    if copied>=700 or total>24*1024**3:
        print("AARIS_MAP_LOCAL_OVERLAY_LIMIT")
        raise SystemExit(19)
    target_file.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source_file,target_file)
    copied+=1
print("AARIS_MAP_LOCAL_CHANGES_COPIED")
print("overlay_files="+str(copied))
PYOVERLAY

SCENE="$PROJECT/Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
test -s "$SCENE" || { echo AARIS_MAP_SCENE_MISSING; exit 20; }
if head -c 120 "$SCENE" | grep -q 'version https://git-lfs.github.com/spec/v1'; then
  echo AARIS_MAP_SCENE_IS_ONLY_LFS_POINTER; exit 21
fi
test -s "$PROJECT/Assets/AarisWorld/Editor/AarisSettlementExpansionProbe.cs" ||
  { echo AARIS_MAP_EDITOR_PROBE_MISSING; exit 22; }
test -s "$PROJECT/Assets/Resources/AarisExpansion/AarisExpansionCatalog.asset" ||
  { echo AARIS_MAP_LOCAL_CATALOG_MISSING; exit 23; }

bash "$PROJECT/.devcontainer/start_screen.sh" >/dev/null 2>&1 ||
  { echo AARIS_MAP_DISPLAY_INIT_FAILED; exit 24; }
DISPLAY=:99 xdpyinfo >/dev/null 2>&1 ||
  { echo AARIS_MAP_DISPLAY_NOT_READY; exit 25; }
rm -f "$RUN/report.json" "$RUN"/ARX_*.png
echo AARIS_MAP_REAL_UNITY_PLAY_STARTED
set +e
timeout --signal=TERM 1500 env DISPLAY=:99 TMPDIR="$RUN/UnityTemp" LIBGL_ALWAYS_SOFTWARE=1 \
 "$EDITOR" -batchmode -force-glcore -projectPath "$PROJECT" \
 -executeMethod Aaris.MapReview.Editor.AarisSettlementExpansionProbe.Verify \
 -logFile "$RUN/private-editor.log" \
 > "$RUN/private-stdout.log" 2>"$RUN/private-stderr.log"
RC=$?
set -e
if ! test -s "$RUN/report.json"; then
  if grep -qE 'error CS[0-9]{4}' "$RUN/private-editor.log" 2>/dev/null; then
    echo AARIS_MAP_UNITY_COMPILE_ERROR
  elif test "$RC" -eq 124; then
    echo AARIS_MAP_UNITY_BATCH_TIMEOUT
  else
    echo AARIS_MAP_NATIVE_REPORT_MISSING
  fi
  exit 26
fi
python3 - "$RUN/report.json" <<'PYREPORT'
import json,sys
try: d=json.load(open(sys.argv[1]))
except (OSError,ValueError):print("AARIS_MAP_NATIVE_REPORT_INVALID");raise SystemExit(27)
for key,label in [("placed","placed"),("skippedTerrain","skipped_terrain"),
                  ("skippedTrees","skipped_trees"),("skippedObstacle","skipped_obstacles"),
                  ("skippedResources","skipped_assets"),("imageCount","image_count"),
                  ("runtimeErrors","runtime_errors")]:
    value=d.get(key)
    if isinstance(value,int) and 0<=value<500:
        print(label+"="+str(value))
if d.get("status")=="passed":print("AARIS_MAP_REAL_UNITY_VERIFIED")
else:print("AARIS_MAP_REAL_UNITY_NEEDS_FIXES")
PYREPORT
# Return 0 when a genuine structured report was produced, even if the game
# failed assertions; the controller still marks the review FAILED, but the
# report and any real Unity screenshots remain available for diagnosis.
echo AARIS_MAP_REPORT_READY_FOR_REVIEW
