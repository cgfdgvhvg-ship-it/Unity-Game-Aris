# Natural SpeedTree Trunks v2 — Reviewed six-species upgrade

**Goal:** Improve visibly thin tree trunks without cartoonishly fat crowns, losing branches, changing the 2×2-km terrain, or increasing source mesh topology.

### Approved geometry and collision adjustments

| SpeedTree | Base width before → after | Crown width before → after | Height |
| --- | --- | --- | --- |
| Conifer | 1.55 → **1.74** (+12.3%) | 1.12 → 1.16 (+3.6%) | Unchanged |
| Cypress | 1.40 → **1.55** (+10.7%) | 1.10 → 1.13 (+2.7%) | Unchanged |
| Pine A | 1.55 → **1.74** (+12.3%) | 1.12 → 1.16 (+3.6%) | Unchanged |
| Pine B | 1.55 → **1.71** (+10.3%) | 1.12 → 1.15 (+2.7%) | Unchanged |
| Pine C | 1.50 → **1.68** (+12.0%) | 1.12 → 1.16 (+3.6%) | Unchanged |
| Pine D | 1.50 → **1.66** (+10.7%) | 1.12 → 1.15 (+2.7%) | Unchanged |

**The values are source mesh radial authoring factors, not absolute trunk diameters in metres.** They apply proportionally across all native Terrain TreeInstances using the respective SpeedTree prototypes. The previously authored height reduction remains unchanged; this pass tackles thin bases, silhouette and collision consistency.

The existing import-time `AarisTreeShapeImporter.cs` already deforms bark, branches, leaves, and LOD meshes continuously using a smooth lower-to-upper taper. It recalculates deformed vertex normals/tangents and SpeedTree 8 wind/LOD UV anchor channels so close and distant meshes retain the same shape. This upgrade bumps the importer version to **2**, accepts v1 and v2 metadata, and changes only six explicit source `.st.meta` importer profiles plus six matching `.prefab` source colliders/LOD bounds. Importing the assets in the normal Unity Editor makes the physical mesh shape.

**Physics and performance considerations:** BoxCollider horizontal X/Z sizes and centers are updated by the base-width ratio for each prefab, keeping the trunk envelope consistent. The prefab LOD sphere size is padded by 2.5% for potential horizontal expansion without changing the four LOD screen-height transitions. No new geometry vertices, foliage shader materials, textures, SpeedTree source `.st` binaries, native TerrainData `.asset` tree placements, scene objects, or prefab `.meta` GUIDs are edited by this PR.

### Validation and limits

Source validity is checked by `Tools/World/verify_tree_realism_v2.py` against **exact reviewed Git blob hashes** for all 12 modified assets, the historical profile, unchanged prefab GUID, four LOD tiers, collider enabled status, and proportional bounds. New unit tests reject unauthorized prefab edits, metadata changes or GUID collisions. The historical tree/house contract remains enforced for all other saved source files.

**Actual Unity Editor reimport and visual comparison still must be verified separately** before claiming the trees look natural in the real rendered world; the source contract does not prove camera quality, terrain collision in gameplay, mobile FPS, occlusion or wind animation. After import the AI should take matching before/after camera screenshots from several forest/roadside angles and check close-up trunks, crown distribution, wind/LOD transitions and collisions. If any issue appears, revise only the reviewed source profiles in a new PR.

We deliberately avoid multiplying the entire Terrain TreeInstance `widthScale` indiscriminately. That would widen every canopy along with the trunk, while this source-level taper is strongest at the lower trunk.

The initial production review should be on an isolated Unity `/tmp/aaris-unity-batch/project` copy; keep the original `/workspaces/Unity-Game-Aris` checkout untouched and do not replace its 764 Git LFS files. For normal AI edits, continue to use the verified debounced `Tools/World/unity_batched_autosync.py` session workflow; for source upgrades, use this separately reviewed PR.
