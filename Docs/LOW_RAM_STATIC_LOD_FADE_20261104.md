# Guarded low-RAM static LOD crossfade fallback (2026-11-04)

This is a **follow-up stacked on consolidated draft PR #25**. It changes the checked-in runtime C# and regression tests, **not** the saved scene, building/rock/tree source prefabs, GUIDs, meshes, material links, terrain height/instances, or any Git LFS bytes. It is an A/B-testable GPU optimization hypothesis; not a measured FPS result.

## Technical reason

Unity URP recommends disabling LOD crossfades for lower-end mobile GPUs to avoid the alpha-tested overlap of incoming/outgoing meshes. Our actual saved three-LOD house and RockCover renderers use CrossFade/animated transitions. With a two-stage sustained-frame-pressure controller already in PR #25, we can retain the authored visual quality until the frame-time evidence supports testing the cheaper mode.

On Android with reported RAM <=3584 MB only, the runtime captures each active **three-LOD** scene LODGroup whose original mode is CrossFade and its original animateCrossFading value **once**. At performanceLevel 2 and only while the serialized opt-out remains enabled, it temporarily switches those groups to LODFadeMode.None, and disables animation. On performance recovery or runtime teardown it restores exactly those recorded properties. The 2 GB/3 GB RAM class is a device-budget gate, not a substitute for GPU measurements. There are no per-frame scene scans and no prefab writes.

This trades smooth transition appearance for lower alpha-test cost **only under severe sustained pressure**. Do not label it a visual upgrade until a scene walkthrough verifies that visible LOD popping is acceptable. Disable via the runtime field suppressStaticLodCrossFadeUnderPressure if popping is objectionable or GPU timings fail to improve. This preserves LOD level count, thresholds, renderers, scene objects and camera far plane, so it does not intentionally shorten the world horizon.

## Important SpeedTree correction

The project's six SpeedTree prefabs carry their own four-level LODGroups. Unity Terrain Settings documentation explicitly states that `Terrain.treeBillboardDistance` and `Terrain.treeMaximumFullLODCount` are **not** authoritative for SpeedTree trees: use each source tree's LODGroup. The preexisting runtime Terrain caps in PR #25 are retained for any legacy Tree Editor tree prototypes, but **must not be claimed as a proven SpeedTree mesh-work reduction**. This patch deliberately does not guess new SpeedTree LOD thresholds or alter 3D tree scale/billboards without rendered import and physical device screenshots.

Sources:
- Unity 6 URP performance: https://docs.unity.com/en-us/engine/6000.5/manual/render-pipelines/universal-render-pipeline/introduction/configure-for-better-performance
- Unity 6 Terrain settings: https://docs.unity.com/en-us/engine/6000.0/manual/creating-environments/script-terrain/terrain-other-settings
- Unity 6 LODGroup runtime properties: https://docs.unity.com/en-us/engine/6000.0/script-reference/unityengine/lodgroup

## Verification before merge

1. Import the complete project/Git LFS content with pinned Unity 6000.3.26f1. Check C# compile and confirm mobile runtime sees the intended number of active three-LOD groups; 79 scene LOD groups were revised in PR #25 but the runtime capture count is environment-dependent.
2. Run `python -m unittest discover -s Tools/World/tests -v` and existing world checks, inspect actual CI status; the new test is source-contract only.
3. Walk matched 2 GB, 3 GB and higher-RAM Android routes; check the in-game REPORT JSON for `staticLodCrossFadeSuppressed`, `staticLodCrossFadeGroupCount`, `performanceLevel`, `p95FrameMs`, RAM/PSS and `renderScale`.
4. Capture close/far houses, rock cover and tree silhouettes at performance levels 0/1/2; compare render thread/GPU timings, draw calls, overdraw and visible popping. Ensure restoration on recovery. Native SpeedTree LOD remains untouched.
5. If the severe-pressure no-fade mode produces ugly transitions or no measurable improvement, turn the new serialized field off and keep the authored fades. Do not merge based on a synthetic FPS estimate.

No Android profile or Unity Editor test has been performed in this GitHub source-only patch.

## Foreground-resume frame-pacing safeguard

The same Android runtime now resets only its 180-sample frame-time observation window, downgrade/recovery counters and six-second change cooldown when the application resumes or regains focus. It also uses that helper for an in-game 60/30 FPS switch. The chosen quality tier is retained until new measurements support a change. This prevents stale pre-background p95 frame times from incorrectly triggering additional near-grass/shadow reductions on return; it does not alter meshes, native terrain, far clip, device memory budget or source Prefabs. The resumed app still requires Unity/physical-device validation because OS callbacks and GPU recovery timings vary.
