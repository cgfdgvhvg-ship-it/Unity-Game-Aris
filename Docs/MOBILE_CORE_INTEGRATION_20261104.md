# Saved-core and low-RAM Android integration — 2026-11-04

Repository: Aaris-khan-don/Unity-Game-Aris. Integration begins at PR #18 head 2088e961a59a29585c03b2aa5dfeb650be86ec14, inheriting its edited *actual* Git LFS residential meshes and SpeedTree source importer. This is source-only work, not a rendered or device-tested game.

## Combined, without double-scaling

PR #18 authored six proportion-corrected SpeedTree source/import profiles, matching core prefabs/colliders, and removed inspected closed residential door/window mesh faces from 21 shared LOD assets across 47 existing residential instances. This branch **does not** copy PR #17's separate six root-tree transform scalings, which would double-apply vegetation adjustments.

From PR #17, this branch adopts:
- Android-only RAM profiles for reported system memory up to 3584 MB. <=2304 MB: mip streaming budget at most 256 MB, LOD bias at most .90, shadow distance at most 90 m, main shadow atlas resolution at most 2048, terrain detail distance at most 55 m and density at most .58. 2305–3584 MB: at most 320 MB, .98, 160 m, 2048, 80 m and .78 respectively.
- The corresponding runtime before/after telemetry, reversibility on destruction, low-memory mip budget trims, and existing camera far visibility.
- Spatial nearby-collider indexing for Mesh, Box, Sphere, Capsule shapes, exclusion of TerrainCollider and CharacterController, reduced idle transform synchronization, and restoration of saved collider enabled states if proximity management stops. Registered obstacles authored disabled can intentionally become enabled when nearby; review registry membership before claiming physics is correct.
- Three-LOD source prefab transition thresholds 0.28 / 0.095 / 0.0025 (formerly 0.22 / 0.07 / 0.0025) for seven existing residential prefabs and RockCover. Original meshes, references, GUIDs, transforms, material slots, cross-fades, and nonconvex collider bindings remain unchanged.
- Source-only unit tests guarding saved LOD thresholds and the runtime/collider contracts. The PR #17 test that assumes independently scaled tree-root transforms is deliberately omitted, since PR #18 uses source-level geometric warping instead.

## Visual/gameplay review gate

1. Import with Unity 6000.3.26f1 and URP 17.3, compile C#, check SpeedTree wind/LOD/billboards, tree trunk/base/crown shapes and correct collider envelope at player scale.
2. Verify the revised doors in actual Unity meshes on all LODs and with a walking CharacterController. Suggested target for a clear human entrance: about 0.9–1.1 m wide, at least 2 m tall; usable room height at least 2.4 m. These are design guidelines, not claims of existing measured dimensions.
3. Only enable window vaulting for openings with measured sill, usable width, controller capsule/jump checks and an authored vault action. Keep other windows blocked intentionally.
4. Reinspect source positions and sampled native TerrainData before choosing house clusters, rock embedding, rotations or street frontage. This patch does not invent rock placements, new models or house re-layout.
5. Confirm real LFS mesh materialization; run Python unittest discovery, check_contracts, verify_tree_house_upgrade and native_smoke. Test actual Android devices with 2 GB, 3 GB and 4 GB+ RAM using identical traversal/camera, p95 frame time, memory/PSS, texture usage, GPU cost and thermal conditions before merge.

Runtime caps do not prove a 60-FPS experience or full 2-GB compatibility. Chunk streaming, actual Android capture, Unity compile/physics tests, and an APK build have not been performed in this source-only integration.
