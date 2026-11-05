# Second Android mobile optimization — actual fern/heather prefab shadows (2026-11-05)

Existing 20 Unity Terrain foliage-detail prefabs were audited. **13** already had realtime shadow casting disabled; **Fern_A/B/C, Heather_A/B, Bush_A and Bush_Red** still cast realtime shadows. This pass changes **only the first five** smaller foliage source `.prefab` files: exact `MeshRenderer.m_CastShadows: 1 → 0`.

All **20** detail-prefab sources keep the identical renderer, mesh, material, transforms, scale, texture, alpha, receive-shadows state, and GUIDs; **Bush_A and Bush_Red retain realtime shadows** for prominent nearby plants. No SpeedTrees, terrain positions, GameObjects, house geometry, LFS TerrainData `.asset`, or `.meta` assets were modified. Afterward **18** types cast no shadows and the two larger bushes do. Since these are prefab sources, every relevant instance referencing the sources can benefit; the exact runtime impact depends on Unity terrain detail draw mode and must be verified.

## Strong regression
Run `python -m unittest Tools.World.tests.test_detail_foliage_shadow_core -v`. The test reconstructs the **exact original Git blob SHA1** for each modified prefab by reversing just the one shadow property; it rejects all other edits (including geometry or material changes). It also validates all 20 detail sources, and that the two large bushes still cast shadows.

This is a source-core authoring change, not a runtime or compile-time wrapper. There has been **no real Android FPS measurement, Unity GPU rendering screenshot, or device profiling**, and any FPS benefit is not guaranteed. Scene may contain expanded renderers rather than prefab-linked instances; an independent scene audit must validate where source edits affect runtime. Never assume a 2 GB device performs like a premium one.

Guidance: [Unity 6 URP shadow optimization](https://docs.unity.com/en-us/engine/6000.7/manual/lighting-overview/lighting/shadows-in-urp/shadows-optimization) and [Terrain instanced detail mode](https://docs.unity.com/en-us/engine/6000.3/manual/creating-environments/script-terrain/terrain-grass).
