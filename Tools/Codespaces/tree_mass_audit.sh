#!/usr/bin/env bash
# Read-only bounded native mesh audit in the owner's existing Codespace.
# Creates a clean detached LFS-hydrated worktree; does not touch dirty GUI
# workspace, unity imports, source mesh bytes, scenes or other Git refs.
set -Eeuo pipefail
SOURCE=/workspaces/Unity-Game-Aris
OUT=/tmp/aaris-codespaces/tree-mass
EDITOR="$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity"
for candidate in "$EDITOR" /workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity /tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity; do
  if test -x "$candidate"; then EDITOR="$candidate"; break; fi
done
test -x "$EDITOR" || { echo TREE_AUDIT_EDITOR_MISSING; exit 11; }
test -e "$SOURCE/.git" || { echo TREE_AUDIT_SOURCE_MISSING; exit 12; }
git -C "$SOURCE" fetch --quiet origin main || { echo TREE_AUDIT_FETCH_FAILED; exit 13; }
SHA="$(git -C "$SOURCE" rev-parse origin/main)"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo TREE_AUDIT_REV_INVALID; exit 14; }
ROOT=/tmp/aaris-native-photo-worktrees
PROJECT="$ROOT/$SHA"
mkdir -p "$ROOT" "$OUT"
if test ! -d "$PROJECT"; then
  GIT_LFS_SKIP_SMUDGE=1 git -C "$SOURCE" -c filter.lfs.process= -c filter.lfs.smudge=cat -c filter.lfs.required=false \
    worktree add --detach "$PROJECT" "$SHA" >/dev/null 2>&1 || { echo TREE_AUDIT_WORKTREE_FAILED; exit 15; }
fi
test "$(git -C "$PROJECT" rev-parse HEAD)" = "$SHA" || { echo TREE_AUDIT_REV_MISMATCH; exit 16; }
cd "$PROJECT"
git lfs pull >/dev/null 2>&1 || { echo TREE_AUDIT_LFS_FAILED; exit 17; }
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo TREE_AUDIT_EDITOR_ALREADY_OPEN
  exit 18
fi
bash "$PROJECT/.devcontainer/start_screen.sh" >/dev/null 2>&1 || { echo TREE_AUDIT_XVFB_FAILED; exit 19; }
test -s Assets/AarisWorld/Editor/AarisTreeMassAudit.cs || { echo TREE_AUDIT_SCRIPT_MISSING; exit 20; }
rm -f "$OUT/audit.json"
mkdir -p "$OUT/UnityTemp"
set +e
timeout --signal=TERM 1500 env DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1 TMPDIR="$OUT/UnityTemp" \
  "$EDITOR" -batchmode -quit -force-glcore -projectPath "$PROJECT" \
  -executeMethod Aaris.MapReview.Editor.AarisTreeMassAudit.Inspect \
  -logFile "$OUT/private-unity.log" >"$OUT/private-stdout.log" 2>"$OUT/private-stderr.log"
RC=$?
set -e
if test "$RC" -ne 0; then
  if grep -Eqi 'error CS[0-9]{4}' "$OUT/private-unity.log" 2>/dev/null; then
    echo TREE_AUDIT_COMPILE_ERROR
  else
    echo TREE_AUDIT_EDITOR_FAILED
  fi
  exit 21
fi
python3 - "$OUT/audit.json" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    ok=(d.get("status")=="passed" and d.get("speciesCount")==6
        and len(d.get("species",[]))==6)
    ok=ok and all(v["lodCount"]==4 and v["colliders"]>=1
                  and len(v["lods"])==4
                  and all(l["vertices"]>0 and l["triangles"]>0
                          and l["subMeshes"]==len(l["sections"]) for l in v["lods"])
                  for v in d["species"])
except (OSError,ValueError,TypeError,KeyError):
    ok=False
sys.exit(0 if ok else 1)
PY
echo "AARIS_TREE_MASS_AUDIT_PASSED"
echo "audit_commit=$SHA"
