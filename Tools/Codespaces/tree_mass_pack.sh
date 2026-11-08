#!/usr/bin/env bash
# Bundle ONLY validated native Unity tree mass output from isolated worktree.
# No credential, license, scene, TerrainData or dirty GUI workspace transfer.
set -Eeuo pipefail
ROOT=/tmp/aaris-tree-mass-worktrees
OUT=/tmp/aaris-codespaces/tree-mass
test -s "$OUT/mass-report.json" || { echo TREE_PUBLISH_PREVIEW_REPORT_MISSING; exit 11; }
test -s /tmp/aaris-codespaces/scene-probe/foliage-report.json || { echo TREE_PUBLISH_PHOTO_MISSING; exit 12; }
mapfile -t PROJECTS < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name '????????????????????????????????????????' -print 2>/dev/null | sort)
FOUND=()
for d in "${PROJECTS[@]}"; do
  if test -f "$d/Assets/AarisWorld/Generated/TreeMass/Pine_A_LOD0.asset"; then
    FOUND+=("$d")
  fi
done
test "${#FOUND[@]}" -eq 1 || { echo TREE_PUBLISH_REVIEW_WORKTREE_AMBIGUOUS; exit 13; }
PROJECT="${FOUND[0]}"
cd "$PROJECT"
SHA="$(git rev-parse HEAD)"
test "$PROJECT" = "$ROOT/$SHA" || { echo TREE_PUBLISH_SOURCE_SHA_MISMATCH; exit 14; }
python3 - "$OUT/mass-report.json" /tmp/aaris-codespaces/scene-probe/foliage-report.json <<'PY'
import json,sys
a=json.load(open(sys.argv[1]));b=json.load(open(sys.argv[2]))
assert a.get("status")=="passed" and a.get("meshAssets")==18 and a.get("species")==6
assert b.get("status")=="passed" and b.get("terrainTiles")==4
PY
PREFABS=(
  Assets/TerrainDemoScene_URP/Prefabs/Trees/Conifer/Conifer.prefab
  Assets/TerrainDemoScene_URP/Prefabs/Trees/Cypress/Cypress_Forest_Desktop.prefab
  Assets/TerrainDemoScene_URP/Prefabs/Trees/Pines/Pine_A/Pine_A.prefab
  Assets/TerrainDemoScene_URP/Prefabs/Trees/Pines/Pine_B/Pine_B.prefab
  Assets/TerrainDemoScene_URP/Prefabs/Trees/Pines/Pine_C/Pine_C.prefab
  Assets/TerrainDemoScene_URP/Prefabs/Trees/Pines/Pine_D/Pine_D.prefab
)
FILES=(Assets/AarisWorld/Generated.meta Assets/AarisWorld/Generated/TreeMass.meta)
SPECIES=(Conifer Cypress Pine_A Pine_B Pine_C Pine_D)
for species in "${SPECIES[@]}"; do
  for lod in 0 1 2; do
    a="Assets/AarisWorld/Generated/TreeMass/${species}_LOD${lod}.asset"
    FILES+=("$a" "$a.meta")
  done
done
FILES+=("${PREFABS[@]}")
test "${#FILES[@]}" -eq 44 || { echo TREE_PUBLISH_FILE_COUNT_INCORRECT; exit 15; }
for item in "${FILES[@]}"; do
  test -f "$item" && test ! -L "$item" || { echo TREE_PUBLISH_EXPECTED_ASSET_MISSING; exit 16; }
done
# Ensure no other tracked Unity YAML file (scene / material) was touched by
# Editor import, apart from the intended six prefabs and known LFS hydration.
python3 - "${PREFABS[@]}" <<'PY'
import subprocess,sys
allowed=set(sys.argv[1:])
s=subprocess.run(["git","diff","--name-only","-z"],capture_output=True,check=True).stdout
for path in s.decode("utf-8","surrogateescape").split("\0"):
    if not path or path in allowed:continue
    a=subprocess.run(["git","check-attr","filter","--",path],capture_output=True,text=True,check=True).stdout
    if not a.strip().endswith(": filter: lfs"):
        print("TREE_PUBLISH_UNEXPECTED_EDITOR_FILE_CHANGED");sys.exit(17)
PY
python3 - "$OUT/mass-manifest.json" "$SHA" "${FILES[@]}" <<'PY'
import hashlib,json,pathlib,sys
dst=pathlib.Path(sys.argv[1]); source=sys.argv[2]; files=sys.argv[3:]
rows=[];total=0
for path in files:
 p=pathlib.Path(path);n=p.stat().st_size;total+=n
 if n>60*1024*1024 or total>240*1024*1024:raise SystemExit(18)
 rows.append({"path":path,"bytes":n,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
dst.write_text(json.dumps({"kind":"aaris_tree_mass_native_editor_bake","sourceSha":source,
                           "files":rows,"count":len(rows)},indent=2))
PY
tar -czf "$OUT/mass-package.tar.gz" -C "$PROJECT" "${FILES[@]}" -C "$OUT" mass-manifest.json
test "$(stat -c '%s' "$OUT/mass-package.tar.gz")" -le 250000000 || {
  echo TREE_PUBLISH_PACKAGE_TOO_LARGE; exit 19;
}
echo "AARIS_TREE_MASS_PACKAGE_VERIFIED"
echo "source_main_sha=$SHA"
echo "mesh_assets=18"
echo "native_prefabs=6"
