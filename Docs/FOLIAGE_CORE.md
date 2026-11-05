# Authored forest undergrowth

The map uses two native saved bush meshes, materials, texture assets and prefabs in Assets/AarisWorld/Foliage. The scene contains 96 explicit placements across 19 irregular clusters. There is no runtime bush generator or custom foliage import callback.

- LeafyAiry: 1,830 triangles, two material slots, 1.28 m source height; 64 placements.
- LeafyDense: 7,876 triangles, two material slots, 0.95 m source height; 32 placements.
- Instances have varied saved yaw and modest width/height variation. Their roots sit 8.5 cm below sampled terrain height.
- Leaves use double-sided alpha clipping, mipmaps with preserved alpha coverage, a 1024-pixel maximum texture size and instanced materials.
- Each bush has one native LODGroup with a 0.012 screen-height cull threshold. Bushes have no colliders. Houses, roads, vehicle aprons and existing terrain instances are preserved.

The authored locations were selected after measuring terrain elevation and local footprint variation, road triangles, house envelopes, vehicle aprons and existing tree/rock positions. Road-adjacent, trunk-overlapping and steep discontinuous candidates were omitted. These source measurements are not Unity capsule sweeps or device performance evidence.

## Source and license

Both source models are CC0 downloads from TerrainTale. Credits: TerrainTale, ambientCG textures, ez-tree by Daniel Greenheck. These are independently licensed foliage assets; no PUBG or Free Fire game assets were extracted.

- https://terraintale.com/library/realistic-surfaces/bush-leafy-b
- https://terraintale.com/library/realistic-surfaces/bush-leafy-c

Each Source.json records the source URL, download SHA256, license, native mesh bounds, triangle count and authored prefab. The original web model is not needed at runtime or during a build.

## Integrity

Tools/World/foliage-core-20261104.json binds the authored scene, every new asset and metadata file, added YAML documents, and the one existing SceneRoots document. The read-only foliage_core.py verifier reconstructs the exact previous scene in memory and checks its historical SHA256. Existing house/rock LOD and doorway checks still validate that reconstructed scene; their historical contracts were not rewritten.

This proof covers saved data. Android FPS, complete house navigation and full-map visual quality require separate engine/device checks.
