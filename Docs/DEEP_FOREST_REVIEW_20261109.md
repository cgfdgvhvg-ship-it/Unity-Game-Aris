# 2026-11-09 real Unity tree silhouette fine-tuning

Evidence: the native screenshot run 42562450443 at Clock Tower Town (350,220)
renders four verified TerrainData tiles and shows sparse, long-thin vegetation
on the hills beyond the town. This is a **baseline** screenshot, not a proof
that the new review-branch trees are rendering or installed.

## Saved native assets
Six original SpeedTree prefabs have a moderate additional X/Z root scale
increase (approximately 6–9%; Cypress approximately 6%) without changing Y,
TreeMesh vertex counts, LOD meshes, texture pixels, source SpeedTree importers,
TerrainData, house objects, roads, tree coordinates, or material references.

One new native prefab is `Assets/TerrainDemoScene_URP/Prefabs/Trees/DeepForest/DeepForestPine.prefab`.
It uses the existing four Pine_D LOD meshes and a separate original-texture
URP SpeedTree bark material with slightly dark brown tint; root scale
(1.48,1.00,1.48). It is an **asset**, not yet an additional TerrainData
TreePrototype. Adding it to 2x2 km map requires a **separate Editor-serialized
TerrainData change** with real Unity visual QA; do not pretend the screenshots
already include it.

## Guardrails
- No new poly geometry, wind job, shader, texture, scripts at runtime, or trees.
- Six original 4-LOD groups, BoxColliders and 19 old material GUIDs preserved.
- No main-scene saves from an unverified branch; protects previously dirty GUI workspace.
- CI checks geometries/road clearance and new material/prefab linkage.
- Before any merge, run licensed Unity visual and static tests with the review
  branch in an isolated working copy and inspect low/high view tree silhouette.
- Original LFS TerrainData and 18 baked tree-mass LFS assets are immutable in
  this change. Android 2 GB device FPS testing remains a separate gate.
