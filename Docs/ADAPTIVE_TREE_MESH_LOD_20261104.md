# Adaptive low-RAM terrain-tree mesh pressure relief — 2026-11-04

**Scope:** stacked on draft PR #22 (which includes #19's protected house/SpeedTree geometry, #21's emergency render-scale path, and the saved inline scene LOD corrections). This patch changes the existing `Assets/AarisWorld/Scripts/AarisMobileRuntime.cs` source, not any scene, prefab, mesh, texture, TerrainData or `.meta` file.

## Why

The source already caps the expensive *nearby full 3D Terrain trees* at 100 m/28 trees on 2 GB-class Android and 140 m/44 trees on 3 GB-class Android, but those limits stayed constant during sustained frame pressure while grass, shadows and render scale stepped down. Near-tree mesh workload can therefore remain expensive after other fallbacks engage. Terrain distant visibility is independent of `treeBillboardDistance` and `treeMaximumFullLODCount`.

## Added pressure-dependent tree mesh limits

Only on Android devices reporting at most 3584 MB total RAM, after the existing warm-up, 180-frame p95 observation, two pressure samples and 12-second cooldown:

| Quality state | 2 GB class: mesh-to-billboard / max full-LOD trees | 3 GB class: mesh-to-billboard / max full-LOD trees |
| --- | --- | --- |
| Level 0 (baseline) | 100 m / 28 | 140 m / 44 |
| Level 1 | 92 m / 24 | 128.8 m / 37 |
| Level 2 | 82 m / 20 | 114.8 m / 31 |

The table lists **maximum caps**, not guaranteed actual values: runtime always clamps to the original smaller authored `treeBillboardDistance` and `treeMaximumFullLODCount` for each terrain. `Terrain.treeDistance`, the camera far plane, last object LODs, tree instance positions/scales, and SpeedTree geometry are unchanged. Full mesh tree detail may visibly switch to billboards sooner.

The existing four recovery observations and cooldown restore the normal RAM-class tree mesh budget at level 0 **when no low-memory warning has occurred**. After `Application.lowMemory`, a sticky 0.80x cap also applies to nearby mesh-tree distance and count; performance recovery no longer undoes that protective reduction. The runtime retains existing grass and texture-streaming relief too. `OnDestroy` restores the exact authored per-terrain values. The JSONL fields `effectiveTreeBillboardDistanceM`, `effectiveMaxFullLodTrees`, and `lowMemoryTreeMeshMultiplier` expose the runtime budget and warning state.

The saved player script no longer unconditionally resets the startup frame cap to 60 FPS after `AarisMobileRuntime.Awake()`. The runtime's serialized cap is the sole startup authority; players may still deliberately toggle 30/60 FPS through the existing button. This fixes a configuration/quality-feedback inconsistency; it does not imply a measured FPS improvement.

## Verification and limits

- Code scope is two existing gameplay/runtime C# scripts plus source regression tests and this note. No geometry, scene, prefab, .meta or preserved-core hashes changed.
- Test by walking matched routes on physical 2 GB and 3 GB Android phones and record median/p95 frame time, GPU timing, PSS, thermal behavior, tree popping and skyline screenshots; compare to level-0 with identical weather/camera.
- Verify Unity 6000.3.26f1/URP 17.3 compilation, tree billboard material/crossfade and terrain seams with materialized Git LFS assets.
- Static source tests are **not** a Unity compile, Android FPS measurement, or a guarantee of 60 FPS / visual superiority. If transitions are objectionable or no real gain occurs, reject/tune this fallback.
- No external assets were copied or imported, so no new licensing or GUID references were introduced.
