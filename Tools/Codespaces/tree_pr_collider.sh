#!/usr/bin/env bash
# Validate *actual* Unity BoxCollider/raycasts for PR Pine prefabs in isolated editor.
set -Eeuo pipefail
REV="${1:-}"
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || { echo AARIS_PR_COLLIDER_BAD_SHA; exit 10; }
ROOT=/tmp/aaris-native-tree-pr-review
PROJECT="$ROOT/$REV"
SOURCE=/workspaces/Unity-Game-Aris
OUT=/tmp/aaris-codespaces/tree-pr-photo
BRANCH=upgrade/selective-pine-core-cover-20261109
git -C "$SOURCE" fetch --quiet origin "refs/heads/$BRANCH" || {
  echo AARIS_PR_COLLIDER_FETCH_FAILED; exit 11;
}
test "$(git -C "$SOURCE" rev-parse FETCH_HEAD)" = "$REV" || {
  echo AARIS_PR_COLLIDER_SHA_CHANGED; exit 12;
}
test -d "$PROJECT" && test "$(git -C "$PROJECT" rev-parse HEAD)" = "$REV" || {
  echo AARIS_PR_COLLIDER_ISOLATED_SOURCE_MISSING; exit 13;
}
test -s "$PROJECT/Assets/AarisWorld/Editor/AarisTreeColliderProbe.cs" || {
  echo AARIS_PR_COLLIDER_SCRIPT_MISSING; exit 14;
}
EDITOR="$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity"
for path in "$EDITOR" /workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity /tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity; do
  if test -x "$path"; then EDITOR="$path"; break; fi
done
test -x "$EDITOR" || { echo AARIS_PR_COLLIDER_EDITOR_MISSING; exit 15; }
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo AARIS_PR_COLLIDER_EDITOR_BUSY; exit 16;
fi
cd "$PROJECT"
bash .devcontainer/start_screen.sh >/dev/null 2>&1 || {
  echo AARIS_PR_COLLIDER_SCREEN_FAILED; exit 17;
}
DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || {
  echo AARIS_PR_COLLIDER_DISPLAY_MISSING; exit 18;
}
mkdir -p "$OUT/UnityTemp"
rm -f "$OUT/pr-collider-report.json"
set +e
timeout --signal=TERM 1500 env DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1 \
  TMPDIR="$OUT/UnityTemp" "$EDITOR" -batchmode -quit -force-glcore \
  -projectPath "$PROJECT" \
  -executeMethod Aaris.MapReview.Editor.AarisTreeColliderProbe.Inspect \
  -logFile "$OUT/private-physics-editor.log" \
  >"$OUT/private-physics-stdout.log" 2>"$OUT/private-physics-stderr.log"
RC=$?
set -e
if test "$RC" -ne 0; then
  if grep -Eq 'error CS[0-9]{4}' "$OUT/private-physics-editor.log" 2>/dev/null; then
    echo AARIS_PR_COLLIDER_CSHARP_COMPILE_FAILED
  else
    echo AARIS_PR_COLLIDER_UNITY_EDITOR_FAILED
  fi
  exit 19
fi
python3 - "$OUT/pr-collider-report.json" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1])
try:
    data=json.loads(p.read_text())
    rows=data["trees"]
    ok=data["status"]=="passed" and data["speciesCount"]==3
    ok=ok and {t["species"] for t in rows}=={"Pine_A","Pine_B","Pine_C"}
    ok=ok and all(t["lods"]==4 and t["colliders"]==1
                  and t["standingHeightRaycastHit"] is True
                  and 1.45<=t["trunkCollisionWidth"]<=2.25
                  and 1.45<=t["trunkCollisionDepth"]<=3.0
                  and t["crownWidth"]>t["trunkCollisionWidth"]*1.6
                  for t in rows)
except (OSError,ValueError,KeyError,TypeError): ok=False
if not ok:
    print("AARIS_PR_COLLIDER_NATIVE_REPORT_INVALID")
    sys.exit(20)
print("AARIS_PR_NATIVE_TREE_COLLIDERS_PASSED")
PY
