# Smart settlement expansion — 2 km × 2 km offline world

## Exact additive plan

A new **15-site** offline expansion is proposed: **12 residential buildings and 3 watchtowers** across **12 of 13 existing districts**. The original native scene already has 59 buildings, 39 roads, 45 vehicle spawn locations, 13 districts and four Git LFS TerrainData tiles.

| Area | Additions |
| --- | --- |
| OldVillage | Two additional local houses |
| ValleySettlement | Two two-storey houses |
| ClockTowerTown | One two-storey house and one bungalow |
| CoastalHamlet | One two-storey house |
| NorthernRidgeTown | One two-storey house |
| LakesideHamlet | One cottage |
| CanalMarket | One cottage |
| EasternPort | One cottage |
| FreightDistrict | One cottage |
| HighlandObservatory | One existing watchtower prefab |
| ForestLookout | One additional existing watchtower prefab |
| SouthernAirfield | One existing watchtower prefab |

Locations, rotations, approximate prefab extents and district ground anchors are in `Assets/Resources/AarisExpansion/WorldExpansionPlan.json`.

At full near-camera LOD, the 15 added instances total approximately **173,242 source triangles** before normal LOD culling; this is a data budget, not an Android FPS measurement. All four reused model families have exactly one `LODGroup`, at least three renderers and one solid `MeshCollider`.

**Only existing, repository-owned local prefab assets are referenced** through the serialized `AarisExpansionCatalog.asset`. This reuses original mesh materials, collider geometry and near/middle/far LODs. No external model/CDN URL is needed at build time or runtime. No new artist model is claimed to have been created.

## Deterministic in-game integration

The `AarisSettlementExpansion` startup component runs only in the native game scene, loads the local plan/catalog, samples the existing TerrainData for level ground and rejects sites with steep slopes, substantial local-ground deviation, tree collisions, or existing obstacle overlap. Each accepted prefab receives a stable, named scene hierarchy child under `__AarisAdditionalSettlements`.

**Important**: The new objects spawn in the running game, not as serialized modifications to the source `.unity` scene. This preserves the owner's existing 210 locally modified project files and all original LFS TerrainData/scene assets. For baked lightmaps, NavMesh integration, or seeing buildings permanently in Unity Edit Mode before pressing Play, a separate reviewed **Editor bake** into a scene/additive scene is still required. Do not report this runtime-only addition as a saved native-scene edit.

## Quality gates

- Static test `python3 Tools/Validation/test_settlement_expansion.py` checks catalog GUIDs, 15 source plan entries, existing footprints, approximate road offsets, vehicle bays, district bounds, and source LOD prefabs. It neither imports nor renders Unity assets.
- Mandatory real Editor verification: re-use the currently licensed Codespace, hydrate original Git LFS and safely overlay current project changes in a temporary test worktree, run Unity Play Mode, inspect `AARIS_EXPANSION_RESULT` site counts, measure collisions/terrain slopes, and capture genuine camera screenshots near different villages and towers.
- Runtime safety may skip proposed placements if terrain or vegetation differs in the owner's current modified worktree; inspect actual placed count and adjust the site plan rather than bypass terrain checks.
- Before merging, inspect Play Mode screenshot evidence, mobile build/frame-time budget, and ensure the expansion works alongside plane/drop, Gloo Wall and existing vehicles. A static PR check is not evidence of visual correctness.

## Scope

The feature is offline single-player only. It contains no multiplayer synchronization, runtime network dependencies, new terrain sculpting, temporary assets in Git LFS or reset/clean/stash commands. It is intentionally a separate feature branch pending Unity validation.
