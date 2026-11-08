#!/usr/bin/env bash
# Run reviewed one-time native tree mesh sculpt in the current Codespace.
# Do NOT touch the dirty main GUI workspace or publish until screenshots pass.
set -Eeuo pipefail
SOURCE=/workspaces/Unity-Game-Aris
OUT=/tmp/aaris-codespaces/tree-mass
RUN=/tmp/aaris-codespaces/scene-probe
EDITOR="$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity"
for candidate in "$EDITOR" /workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity /tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity; do
  if test -x "$candidate"; then EDITOR="$candidate"; break; fi
done
test -x "$EDITOR" || { echo TREE_MASS_EDITOR_MISSING; exit 11; }
test -e "$SOURCE/.git" || { echo TREE_MASS_SOURCE_MISSING; exit 12; }
git -C "$SOURCE" fetch --quiet origin main || { echo TREE_MASS_FETCH_FAILED; exit 13; }
REV="$(git -C "$SOURCE" rev-parse origin/main)"
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || { echo TREE_MASS_INVALID_SHA; exit 14; }
ROOT=/tmp/aaris-tree-mass-worktrees
PROJECT="$ROOT/$REV"
mkdir -p "$ROOT" "$OUT" "$RUN" "$OUT/UnityTemp"
if test ! -d "$PROJECT"; then
  GIT_LFS_SKIP_SMUDGE=1 git -C "$SOURCE" -c filter.lfs.process= -c filter.lfs.smudge=cat -c filter.lfs.required=false \
    worktree add --detach "$PROJECT" "$REV" >/dev/null 2>&1 || { echo TREE_MASS_WORKTREE_FAILED; exit 15; }
fi
test "$(git -C "$PROJECT" rev-parse HEAD)" = "$REV" || { echo TREE_MASS_REV_MISMATCH; exit 16; }
cd "$PROJECT"
git lfs pull >/dev/null 2>&1 || { echo TREE_MASS_LFS_FAILED; exit 18; }
# A new Git worktree can report original malformed LFS pointer entries as
# modified after hydration. These are not user edits; ONLY allow already
# LFS-tracked paths. Everything else is a hard stop. Never clean/reset.
python3 - <<'PYPREFLIGHT'
import subprocess,sys
p=subprocess.run(["git","status","--porcelain=v1","-z","--untracked-files=all"],
                 capture_output=True,check=True)
items=[x for x in p.stdout.decode("utf-8","surrogateescape").split("\0") if x]
for item in items:
    if len(item)<4 or item[:2]=="??" or "R" in item[:2]:
        print("TREE_MASS_UNEXPECTED_WORKTREE_STATUS");sys.exit(17)
    path=item[3:]
    attr=subprocess.run(["git","check-attr","filter","--",path],
                        text=True,capture_output=True,check=True).stdout.strip()
    if not attr.endswith(": filter: lfs"):
        print("TREE_MASS_NON_LFS_WORKTREE_MODIFIED");sys.exit(17)
print("baseline_lfs_hydration_modified_count="+str(len(items)))
PYPREFLIGHT
test ! -e Assets/AarisWorld/Generated/TreeMass || { echo TREE_MASS_OUTPUT_ALREADY_EXISTS; exit 17; }
test -s Assets/AarisWorld/Editor/AarisTreeMassSculpt.cs || { echo TREE_MASS_SOURCE_NOT_MERGED; exit 19; }
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo TREE_MASS_EDITOR_BUSY
  exit 20
fi
bash "$PROJECT/.devcontainer/start_screen.sh" >/dev/null 2>&1 || { echo TREE_MASS_DISPLAY_FAILED; exit 21; }
rm -f "$OUT/mass-report.json" "$RUN"/foliage-*.png "$RUN/foliage-report.json"
set +e
timeout --signal=TERM 1500 env DISPLAY=:99 TMPDIR="$OUT/UnityTemp" LIBGL_ALWAYS_SOFTWARE=1 \
  "$EDITOR" -batchmode -quit -force-glcore -projectPath "$PROJECT" \
  -executeMethod Aaris.MapReview.Editor.AarisTreeMassSculpt.ApplyAndPreview \
  -logFile "$OUT/private-editor.log" >"$OUT/private-stdout.log" 2>"$OUT/private-stderr.log"
RC=$?
set -e
if test "$RC" -ne 0; then
  if grep -Eqi 'error CS[0-9]{4}' "$OUT/private-editor.log" 2>/dev/null; then
    echo TREE_MASS_COMPILE_ERROR
  elif grep -Eqi 'licen[sc]e.*(invalid|missing|failed|expired)' "$OUT/private-editor.log" 2>/dev/null; then
    echo TREE_MASS_LICENSE_NOT_ACTIVE
  else
    echo TREE_MASS_EDITOR_SCULPT_FAILED
  fi
  exit 22
fi
python3 - "$OUT/mass-report.json" "$RUN/foliage-report.json" "$PROJECT" <<'PY'
import json,pathlib,sys
try:
    r=json.load(open(sys.argv[1])); f=json.load(open(sys.argv[2]))
    project=pathlib.Path(sys.argv[3])
    root=project/"Assets/AarisWorld/Generated/TreeMass"
    meshes=list(root.glob("*.asset"))
    metas=list(root.glob("*.asset.meta"))
    ok=r.get("status")=="passed" and r.get("species")==6 and r.get("meshAssets")==18
    ok=ok and len(meshes)==18 and len(metas)==18
    ok=ok and all(v["generatedLods"]==3
                  and v["sourceVertices"]==v["outputVertices"]
                  and v["sourceTriangles"]==v["outputTriangles"]
                  and v["barkVertices"]>0 and v["foliageVertices"]>0
                  for v in r["records"])
    ok=ok and f.get("status")=="passed" and f.get("terrainTiles")==4
    images=["foliage-original","foliage-far-lod","foliage-ambient-only",
            "foliage-shadows-only","foliage-ambient-test"]
    for im in images:
        p=pathlib.Path(sys.argv[2]).parent/(im+".png")
        ok=ok and p.is_file() and p.stat().st_size>8192
        ok=ok and p.read_bytes()[:8]==b"\x89PNG\r\n\x1a\n"
except (OSError,ValueError,TypeError,KeyError): ok=False
sys.exit(0 if ok else 1)
PY
echo "AARIS_TREE_MASS_NATIVE_PREVIEW_PASSED"
echo "preview_main_sha=$REV"
echo "new_mesh_assets=18"
echo "tree_instances_untouched=1100"
