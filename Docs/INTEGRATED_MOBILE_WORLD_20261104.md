# Saved world proportions and mobile rendering

This main-based integration brings the compatible #25 -> #27 -> #28 source changes into one review, preserving main's WorldBridge compiler-scope fix. The alternative #17/#20/#24 runtime branches are not combined. Merge the integrated result once, rather than applying overlapping drafts independently.

## Result in the actual core

- Six existing SpeedTree importer profiles lower excessive height, widen the trunk base, and taper that deformation continuously through branches, crowns, morph positions and wind/leaf anchors. Saved prototype colliders match the authored scale. The editor applies mesh deformation during the next Unity import.
- Twenty-one saved residential mesh assets retain vertex buffers, UVs and material slots while removing inspected door/window triangles. All 47 residential scene MeshCollider bindings retain the same non-convex geometry reference. Discrete clear source rays are not a capsule or interior playtest.
- Seven residential source prefabs and 47 inline house + 32 inline rock-cover scene groups use the same 0.28 / 0.095 / 0.0025 LOD profile. Distant geometry remains referenced.
- Android RAM profiles reduce grass/detail distance/density, streaming-mipmap budget, terrain basemap cost and shadow distance. Sustained p95 frame pressure has reversible detail, render-scale and static crossfade fallbacks. The existing collider grid retains initially disabled buildings and can reindex explicitly moved obstacles.

No house/rock positions, native instance records, heightmaps, roads or vehicle pads are relocated by this integration. Village spacing and complete playable interiors remain a separate geometry/terrain/route design pass; this patch does not claim to complete them.

## New correction: use SpeedTree's actual LOD groups

Unity's Terrain billboard-start and maximum-full-LOD-tree controls do not govern SpeedTree LODGroup trees. Those runtime fields remain legacy-tree controls only. The actual six shared prefab transitions now select cheaper middle meshes and billboards earlier, with no per-frame forest traversal and no new per-instance GameObjects.

| Prototype | Original middle thresholds | New middle thresholds | Close-detail threshold | Final cutoff |
|---|---|---|---|---|
| Conifer | 0.28432852 / 0.05470773 | 0.34 / 0.10 | 0.6882781 retained | 0.01 retained |
| Cypress | 0.29313132 / 0.02976629 | 0.32 / 0.06 | 0.58904696 retained | 0.004869537 retained |
| Pine A | 0.25 / 0.07945386 | 0.30 / 0.11 | 0.5 retained | 0.01 retained |
| Pine B | 0.25 / 0.08912427 | 0.30 / 0.12 | 0.5 retained | 0.01 retained |
| Pine C | 0.17395622 / 0.046491824 | 0.24 / 0.08 | 0.43247095 retained | 0.01 retained |
| Pine D | 0.25 / 0.056679536 | 0.30 / 0.095 | 0.5 retained | 0.01 retained |

Thresholds are projected screen fractions, not fixed world-metre distances. Native per-instance size, camera FOV, bounds and engine resolution affect the actual transition distances. The conservative saved LOD bounds remain unchanged. Inspect silhouette/color/wind transitions with the imported assets before final visual approval.

The runtime no longer changes global `QualitySettings.lodBias`. Lowering that value also pulls the final culling distance inward for trees and buildings even if `treeDistance` and the camera far plane stay unchanged. The project keeps its authored global value; the table changes only intermediate transitions. This preserves the authored cutoff policy, not a guarantee that every far object is always visible through occlusion/fog.

The schema-v2 `Tools/World/speedtree-lod-20261104.json` records the original current hashes and exact operation fileIDs. It was planned and previewed before application. Replaying an already-applied transaction fails its stale hashes instead of compounding an edit. The Python operation can be reused for future AI-authored prefab LOD profiles.

## Verification and release evidence

Local checks: 99 unit/regression tests, actual saved-scene four-terrain/45-vehicle-marker contracts, C# syntax parsing, and whitespace checks pass. Transaction tests exercise preview isolation, exact scalar-only writes, original metadata/scene preservation, post-edit state, stale sources, duplicate writes, invalid numbers/order/count and unchanged final cutoff. Historical tree-shape hashes are accepted only after reversing the exact reviewed LOD scalars in memory; geometry, collider, bounds and identity changes still fail. Historical reports are not rewritten.

The connector workspace has a byte-verified partial Git snapshot and LFS pointers, not materialized native terrain or full house meshes. Local native/project checks disclose those missing assets; their failure is not a terrain or geometry defect diagnosis. PR CI fetches the real existing LFS assets and runs source-triangle doorway checks, protected-file/binding verification, terrain decoding/seams and project checks. Consult that exact head's check results.

Still required: Unity 6000.3.26f1 import/compile, URP captures, continuous CharacterController doorway/window/interior routes, billboard/wind/LOD transition inspection, APK build, and sustained 2 GB / 3 GB Android tests with p95 frame time, PSS, texture use, thermal behavior and low-memory events tied to build GUID. No measured FPS gain, RAM saving, universal 2 GB compatibility or comparison victory over other games is asserted.

## Primary references

- [Unity Terrain settings](https://docs.unity3d.com/6000.0/Documentation/Manual/terrain-OtherSettings.html): SpeedTree uses its LODGroup rather than the legacy billboard controls.
- [Unity LOD groups](https://docs.unity3d.com/6000.0/Documentation/Manual/class-LODGroup.html): projected-height transitions and crossfade rendering.
- [Unity QualitySettings.lodBias](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/QualitySettings-lodBias.html): bias changes LOD selection distances globally.
- [Unity URP performance](https://docs.unity3d.com/6000.0/Documentation/Manual/urp/configure-for-better-performance.html): mobile rendering, shadows and crossfade tradeoffs.
