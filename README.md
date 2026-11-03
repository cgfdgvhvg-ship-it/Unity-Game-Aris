# Aaris Island — grounded Android map review

A saved 2 km × 2 km Unity URP island with a visible 1.78 m human reference player.
Open `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity` in **Unity 6000.3.26f1 / URP 17.3**.
Clone with Git LFS and fetch the actual assets before opening or building.

## Walk and inspect

- **Phone:** left joystick moves, drag the right side to look, WALK toggles running, JUMP jumps, HOME returns to the safe spawn.
- **Desktop:** WASD/arrows move, right mouse drag looks, Shift runs, Space jumps, F returns home.
- The saved shoulder view follows the grounded player. The free-flight/overview/altitude controls have been removed.
- CharacterController handles terrain, steps, slopes, trunk and building collisions. Camera obstruction checks avoid passing through walls and trunks.
- The visible human uses shared Unity primitive meshes and saved outfit materials, with walking limb animation. It is a lightweight scale-reference character, not an imported Free Fire character model.
- Water remains visual: review movement stops at the shoreline. Combat, bots, loot, swimming and drivable vehicles are separate work.

## Saved core assets

The daylight sky uses the built-in procedural sky shader with a visible sun disk, a linked directional light and explicit ambient colors. No runtime lighting repair component is used. Asphalt, concrete, sand and marking PNG metadata use TextureImporter, retaining their original GUIDs.

Buildings retain their original close meshes and have saved middle/far meshes, with consistent material slots. Only the high-detail mesh has a static collider. Generated native meshes do not retain unused CPU-readable copies. The Android build selects ETC2 texture compression; global texture mipmap limit and render scale are not reduced.

`Docs/FOREST_PLANTING_PLAN.json` describes 1,100 additional source-tree placements, mostly in the sparse eastern half. Native authoring checks full-resolution slopes and shoreline, reserves district pads and road corridors, and writes accepted instances directly into the four TerrainData files. Shared SpeedTree prefabs, textures and existing LODs are reused. No runtime forest spawner is added. Terrain heights are unchanged.

**The materialized totals, rejected candidates and actual building LOD triangle counts are in `Docs/GROUND_REVIEW_REPORT.json`.** `Docs/TERRAIN_INDEX.json` and per-tile instance exports reflect the saved native terrain bytes.

The island still has 13 districts, 59 placed model objects from 17 sources, connected roads, a 240 m runway and 45 empty vehicle markers. Some source models contain multiple structures or closed doors; every building is not guaranteed enterable.

## Manual APK build

Use **Aaris → Build Android Ground Review APK**, or the existing batch entry point:

`Aaris.MapReview.Editor.AarisExplorerBuild.BuildAndroid`

Output: `Builds/Android/AarisGroundReview.apk`.

Target: ARM64 / IL2CPP / Android 8+ / landscape, package `com.aaris.mapexplorer`. The player targets a stable 30 FPS; actual target-device frame time and memory must be measured. Existing Unity 6.3 URP compatibility defines are preserved. No automatic Unity/APK build is added.

The build preprocessor rejects a missing player/camera, wrong player height, pending native assets, wrong surface importers, missing building LODs, missing terrain data or missing scene scripts.

## Verification and reproduction

`python Tools/Validation/check_explorer.py --native` checks scene references, player and camera bindings, C# syntax, core asset references, LOD levels, terrain checksums and forest road/district clearances.

Native authoring: after fetching the core LFS assets, run `python Tools/MapBuild/ground_native.py`. It saves TerrainData and building LODs, reopens terrain binaries, verifies unchanged heights, regenerates indexes and updates hashes. It is idempotent for the saved planting plan.

`Tools/MapBuild/build_map.py` also invokes ground authoring after the original offline map assembly. Its terrain inputs must be the four original vendor archive tiles, as described in `Tools/MapBuild/README.md`; do not re-sculpt the already edited terrain.

**Offline validation is not a Unity Editor compile, render or Android playtest.** These remain explicitly untested in the reports until performed. The former near-tree termination still requires a device crash log and a repeatable device test before it can be called resolved.

Original vendor terrain assets retain their existing Unity Asset Store licence requirements. Model provenance and licences remain in `Tools/MapBuild/model_sources.json` and `URP-TERRAIN-PROVENANCE.md`. Historical TRANSFER reports describe the initial import; current terrain hashes are in `Docs/MAP_BUILD_REPORT.json`.
