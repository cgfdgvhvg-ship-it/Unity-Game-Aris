#!/usr/bin/env bash
# Execute ONLY inside the old owner's Codespace, with original source read-only.
set -Eeuo pipefail
umask 077
EXPECTED="$1"
[[ "$EXPECTED" =~ ^[a-f0-9]{40}$ ]] || { echo AARIS_DOOR_EXPECTED_SHA_INVALID; exit 10; }
SOURCE=/workspaces/Unity-Game-Aris
BRANCH=fix/map-6-district-expansion-20261108
SNAPSHOTS=/tmp/aaris-native-photo-worktrees
RUN=/tmp/aaris-codespaces/interactive-house-probe
test -d "$SOURCE/.git" || { echo AARIS_DOOR_ORIGINAL_REPO_NOT_FOUND; exit 11; }
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo AARIS_DOOR_ANOTHER_EDITOR_RUNNING; exit 12
fi
git -C "$SOURCE" fetch --quiet origin \
  "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" || {
  echo AARIS_DOOR_FETCH_PR_FAILED; exit 13;
}
REV="$(git -C "$SOURCE" rev-parse --verify "refs/remotes/origin/$BRANCH^{commit}")"
[[ "$REV" =~ ^[a-f0-9]{40}$ ]] && test "$REV" = "$EXPECTED" || {
  echo AARIS_DOOR_PR_SHA_CHANGED; exit 14;
}
mkdir -p "$SNAPSHOTS" "$RUN" "$RUN/UnityTemp"
# Never upload stale previous-attempt photos or reports.
rm -f "$RUN/report.json" "$RUN"/door-*.png "$RUN/window-broken.png"
PROJECT="$SNAPSHOTS/$REV"
if ! test -d "$PROJECT"; then
  GIT_LFS_SKIP_SMUDGE=1 git -C "$SOURCE" \
    -c filter.lfs.process= -c filter.lfs.smudge=cat \
    -c filter.lfs.required=false \
    worktree add --detach "$PROJECT" "$REV" >/dev/null 2>&1 || {
      echo AARIS_DOOR_WORKTREE_FAILED; exit 15;
    }
fi
test "$(git -C "$PROJECT" rev-parse HEAD)" = "$EXPECTED" || {
  echo AARIS_DOOR_WORKTREE_SHA_MISMATCH; exit 16;
}
# The immutable tree-mesh verifier runs 'git show HEAD:...' in its
# process working directory; it MUST be the isolated PR checkout.
cd "$PROJECT"
# Verify all 793 LFS payloads against HEAD, never trust pointers alone.
if python3 "$PROJECT/Tools/Codespaces/restore_preserved_source_lfs.py" "$PROJECT" \
  > "$RUN/private-lfs.log" 2>&1; then
  echo AARIS_DOOR_ALL_793_LFS_VERIFIED
elif git -C "$PROJECT" lfs pull >> "$RUN/private-lfs.log" 2>&1 &&
     python3 "$PROJECT/Tools/Codespaces/restore_preserved_source_lfs.py" "$PROJECT" \
       >> "$RUN/private-lfs.log" 2>&1; then
  echo AARIS_DOOR_ALL_793_LFS_VERIFIED
else
  echo AARIS_DOOR_LFS_VERIFICATION_FAILED
  # Emit only the helper's closed-vocabulary diagnostic classification.
  # Never print git-lfs HTTP error, raw logs, tokens, account paths or secrets.
  grep -E '^AARIS_PRESERVED_LFS_RECOVERY_FAILED=[A-Z_]{3,65}$' "$RUN/private-lfs.log" | head -n 2 || true
  grep -E '^AARIS_PRESERVED_OR_CACHED_LFS_HASH_VERIFIED=[0-9]{1,4}$' "$RUN/private-lfs.log" | head -n 1 || true
  exit 17
fi
test -s "$PROJECT/Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity" &&
test -s "$PROJECT/Assets/AarisWorld/Editor/AarisInteractiveHouseProbe.cs" || {
  echo AARIS_DOOR_REAL_UNITY_FILES_MISSING; exit 18;
}
EDITOR="$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity"
for candidate in "/workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity" \
  "/tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity"; do
  if ! test -x "$EDITOR" && test -x "$candidate"; then EDITOR="$candidate"; fi
done
test -x "$EDITOR" || { echo AARIS_DOOR_EDITOR_NOT_INSTALLED; exit 19; }
bash "$PROJECT/.devcontainer/start_screen.sh" > "$RUN/private-display.log" 2>&1 || {
  echo AARIS_DOOR_DISPLAY_START_FAILED; exit 20;
}
DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || {
  echo AARIS_DOOR_NO_DISPLAY; exit 21;
}
rm -f "$RUN/report.json" "$RUN"/door-*.png "$RUN/window-broken.png"
echo AARIS_DOOR_NATIVE_PLAY_STARTED
set +e
timeout --signal=TERM 1700 env DISPLAY=:99 TMPDIR="$RUN/UnityTemp" \
  LIBGL_ALWAYS_SOFTWARE=1 "$EDITOR" -batchmode -force-glcore \
  -projectPath "$PROJECT" \
  -executeMethod Aaris.MapReview.Editor.AarisInteractiveHouseProbe.Verify \
  -logFile "$RUN/private-editor.log" \
  > "$RUN/private-stdout.log" 2> "$RUN/private-stderr.log"
RC=$?
set -e
if ! test -s "$RUN/report.json"; then
  if grep -qE 'error CS[0-9]{4}' "$RUN/private-editor.log" 2>/dev/null; then
    echo AARIS_DOOR_COMPILER_ERROR
  elif test "$RC" -eq 124; then
    echo AARIS_DOOR_EDITOR_TIMEOUT
  else
    echo AARIS_DOOR_EDITOR_REPORT_MISSING
  fi
  exit 22
fi
python3 - "$RUN/report.json" <<'PYREPORT'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);d=json.loads(p.read_text())
for name in ("terrainTiles","sites","modularHomes","panels","doors","windows",
             "screenshotCount","runtimeErrors"):
    v=d.get(name)
    if isinstance(v,int) and 0<=v<=100:
        print("native_"+name+"="+str(v))
for name in ("startsClosed","openedNearPlayer","clearDoorGap",
             "closesWhenUnoccupied","windowHitAndBroken","doorHitAndBroken"):
    if isinstance(d.get(name),bool):
        print("native_"+name+"="+("yes" if d[name] else "no"))
required={"door-closed.png","door-open.png","window-broken.png","door-broken.png"}
valid=(d.get("status")=="passed" and d.get("sites")==21
  and d.get("modularHomes")==4 and d.get("panels")==16
  and d.get("runtimeErrors")==0 and d.get("screenshotCount")==4
  and all((p.parent/f).is_file() and (p.parent/f).stat().st_size>=16000
          and (p.parent/f).read_bytes()[:8]==b"\x89PNG\r\n\x1a\n" for f in required))
print("AARIS_DOOR_NATIVE_VERIFIED" if valid else "AARIS_DOOR_NATIVE_NEEDS_FIXES")
sys.exit(0 if valid else 23)
PYREPORT
