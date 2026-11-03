# Saved scene LOD alignment — 2026-11-04

Scope: `Aaris-khan-don/Unity-Game-Aris`, based on the existing draft low-RAM branch `ai/adaptive-lowram-resolution-20261104`. This is a **saved core scene** modification, not a claim of finished high-end visuals or measured device performance.

## Identified mismatch

The 7 residential model prefabs and RockCover source prefab already use screen-height LOD thresholds `0.28 / 0.095 / 0.0025` in the reviewed PR #19 chain. But the 2 km × 2 km authored scene consists of **inline** building/rock YAML objects, not linked source prefab instances. Its 101 LODGroups still used `0.22 / 0.07 / 0.0025`, so changing source prefabs alone did not update the current world.

## Exact changed core fields

In `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity`, update only the first two `screenRelativeHeight` values to match the existing source prefabs for:

- **47 residential** LODGroups whose names end with one of the seven reviewed home model names and an instance index.
- **32 RockCover** LODGroups named `RockCover_<index>`.
- **22 other** LODGroups (towers, industrial and civic models, wrecks, etc.) stay unchanged at their authored thresholds.

The last LOD remains `0.0025` in all 101 groups so the existing far-distance silhouettes are retained. Existing animated cross-fades, renderers, mesh GUIDs, colliders, transforms, terrain, vehicle pads, materials, metadata and runtime scripts are not altered in this diff. This adjustment switches to cheaper intermediate LOD meshes at a *larger* on-screen size; actual FPS and visible transition quality require profiling.

## Fail-closed integrity

`restore_scene_mobile_lod` in `Tools/World/verify_tree_house_upgrade.py` accepts only exactly 47/32 matching scene object identities, all with the reviewed ordered thresholds, plus 22 untouched LODGroups. It reverses just the 158 changed scalar lines in memory, then checks the SHA256 of the **entire reconstructed scene** against the original protected `tree-house-20261103.postconditions.json` scene SHA256. Any other byte change fails. The original `.unity.meta` and all existing GUID/fileID connections remain untouched.

`Tools/World/tests/test_saved_scene_lod_integrity.py` verifies this proof and rejects unauthorized scene mutations and thresholds. Existing native TerrainData/LFS mesh checks remain mandatory.

## Before merging

1. Run the full Python World unit tests, contract checks, original core integrity verifier and project native verification with actual Git LFS assets.
2. Import into Unity 6000.3.26f1 (URP 17.3); verify editor compilation and near/mid/far LOD silhouettes, especially house door/window openings and rock-cover shape at transitions.
3. Compare matched scene routes on physical 2-GB and 3-GB Android devices: median and p95 frame time, GPU stalls, FPS, PSS, texture residency, thermals and screenshot quality. The render-scale fallback inherited from PR #21 is separately opt-out.
4. Test player capsule entry/vault interactions against real cooked colliders, not source-only doorway rays. Do not interpret a passed SHA or unit test as an interior playtest.

No new third-party models, artificial object scaling, root transform changes or automatic house clustering is introduced without materialized geometry, terrain neighbourhood evidence, source/license review and a Unity device check. No 60-FPS guarantee is made.
