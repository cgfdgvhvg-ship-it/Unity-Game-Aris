# Unity 6 Android core-asset render budget — 2026-11-05

## Second pass — actual placed-scene native shadows

The **first prefab-only pass was not sufficient for the placed map**. A direct read of `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity` showed that the map's **101 LODGroups are serialized as expanded scene GameObjects** with individual MeshRenderers, rather than linked PrefabInstances: all **303 LOD renderers** still had `m_CastShadows: 1` despite the 20 prefab edits.

This second pass edits the **actual native 1,793,876-byte `.unity` scene**: for each of its 101 LODGroups, exact third/farthest LOD MeshRenderer `m_CastShadows` is now **0**, while the two nearer LOD renderers remain **1**. The other 219 MeshRenderers, all transform/scales, original LOD thresholds, geometry references, 63 MeshColliders, doors, windows, lighting, terrain, 45 spawn points, source/meta GUIDs and all four Git LFS TerrainData blobs are unchanged. The scene has the same bytes count and object IDs. No runtime script changes.

Fail-closed verification uses `restore_reviewed_scene_far_shadow()` in `Tools/World/verify_tree_house_upgrade.py` to reverse **exactly 101** recognized shadow bits, then applies the already-approved historical LOD threshold reversal and compares the historical scene SHA-256. `Tools/World/tests/test_scene_far_shadow_core.py` checks 101 groups, 303 LOD refs, 522 MeshRenderers, `[1,1,0]` shadow flags and the exact historical hash.

This disables **distant** shadows, not distant visible meshes. It does not demonstrate any real Android frame-rate gain until profiling.

---

## Files and deliberate tradeoffs

This pass edits **21 existing serialized Unity core files**, not runtime scripts: `ProjectSettings/QualitySettings.asset`, 17 structure/house prefabs under `Assets/AarisWorld/Models/`, and 3 prop prefabs under `Assets/AarisWorld/Props/`. It also adds a static regression test and this record.

| Core property | Previous | Now |
|---|---:|---:|
| Streaming mipmaps memory budget | 384 MB | **192 MB** |
| Streaming renderer updates / frame | 128 | **96** |
| Concurrent mipmap file I/O requests | 64 | **24** |
| Realtime shadow distance | 100 m | **72 m** |
| LOD bias | 1 | **1, unchanged** |
| Quality shadow cascades | 2 | **2, unchanged** |

Across each of **20 existing house/landmark/prop prefabs**, exact LOD2 MeshRenderer `m_CastShadows` changes from 1 to 0. LOD0 and LOD1 shadow casting stay enabled. All third-LOD mesh geometry, far visibility, source materials, source GUIDs, mesh colliders, door/window openings, root scales, LOD thresholds and fade modes remain identical. Houses remain visible at distance, just without far-LOD realtime shadow casting.

**Important quality/engineering limits:** 192 MB is Unity's streaming texture budget, *not total app RAM or hard GPU allocation cap*. Nonstreamed textures and terrain textures consume additional memory. The quality profile is shared with Standalone, so the budget and distance affect Standalone until a future per-platform split is measured. Performance, temperature, actual FPS, stream pop-in and render quality on 2/3 GB Android still require device testing. This does not resize buildings, redesign doors, selectively thicken trunks or solve house interior gameplay. Six SpeedTree prefabs are unchanged because their separate source-integrity manifest and tests require another reviewed operation. The failed Xvfb software OpenGL/Vulkan Unity screenshot workflow is not evidence of game runtime quality.

**Verification:** `python -m unittest Tools.World.tests.test_mobile_render_core -v`, `python -m unittest discover -s Tools/World/tests -v`, GitHub compare; then Unity GPU-backed Editor import and hardware profiling. Preserve original `.meta` GUIDs and untouched terrain `.asset` LFS pointers.

Official Unity references: https://docs.unity.com/en-us/engine/6000.5/manual/render-pipelines/universal-render-pipeline/introduction/configure-for-better-performance and https://docs.unity.com/en-us/engine/6000.0/manual/materials-and-shaders/textures/texture-loading/texture-streaming/configure.
