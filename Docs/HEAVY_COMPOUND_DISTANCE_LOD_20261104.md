# Distance-LOD relief for the heaviest authored compounds (2026-11-04)

## Verified inputs / issue

The saved 2 km × 2 km scene has 101 LODGroups. The three high-triangle,
large-footprint complexes below had exactly the same 0.22 / 0.07 / 0.0025
screen-relative transitions as much smaller village assets. This keeps
expensive intermediate meshes visible longer than necessary at small screen
coverage. Triangle counts are from the existing materialized ground-review
report, not GPU counters.

| Source / saved scene | LOD1 triangles | LOD2 triangles | LOD1 to LOD2 triangle reduction |
|---|---:|---:|---:|
| Airfield / SouthernAirfield_Airfield_01 | 224,159 | 143,261 | 36.1% |
| CanalTown / CanalMarket_CanalTown_01 | 257,511 | 125,672 | 51.2% |
| HanokVillage / OldVillage_HanokVillage_01 | 89,423 | 55,215 | 38.3% |

## Exact saved core edit

In the **actual scene** and all three reusable **source .prefab** assets,
LOD1's `screenRelativeHeight` is moved from `0.07` to `0.11`.
LOD0 remains `0.22`; final cutoff remains `0.0025`.
The LOD1-to-LOD2 transition occurs earlier as screen coverage decreases.
Close-range LOD0, all renderers, mesh/material GUIDs, 3 LOD meshes,
MeshColliders, openings, physical proportions, transforms, roots, vegetation,
four native TerrainData files and the .meta identities are unchanged.

Only these six serialized LODGroup records change. The historical protected
source hashes are still checked by **reversing only the new documented scalar**
in memory, plus the earlier reviewed residential/rock transitions. Unexpected
changes to scene geometry, other object properties, prefab fields, LOD culling
cutoff or collider references remain disallowed by the original SHA contracts.
This patch is an additive optimization, not a regeneration of the map.

## Tradeoffs / validation gate

- The geometry reduction percentages apply when a compound's projected screen
  fraction falls between **7% and 11%** and LOD2 is selected instead of LOD1.
  They do **not** predict total frame FPS, memory savings or draw call savings.
  Mesh data remains resident unless an independent streaming change unloads it.
- Alpha-tested crossfade may briefly render both levels. Lower-RAM frame-pressure
  crossfade fallback in AarisMobileRuntime is unchanged, as are the SpeedTree
  screen-height LODs and the far viewing distance.
- Unity Editor 6000.3.26f1 render captures and close/mid/far silhouettes must
  be compared at fixed FOV and resolution. Check ugly LOD popping / fade bands,
  pop-in around district rooftops and the three complexes' materials.
- Profile 2/3/4 GB Android devices with identical paths and camera headings:
  GPU / render-thread p95, FPS, PSS, thermal throttling and artifact screenshots.
  Revert the 0.11 threshold if the visual loss is unacceptable.
- This does **not** solve village clustering, low-memory asset residency,
  mobile crashes, 2 GB/60 FPS capability, SpeedTree source reimport or full
  playable door/window/capsule physics. Those need their own tested passes.

Primary engine references:
- https://docs.unity3d.com/6000.0/Documentation/Manual/class-LODGroup.html
- https://docs.unity3d.com/6000.0/Documentation/Manual/urp/configure-for-better-performance.html
