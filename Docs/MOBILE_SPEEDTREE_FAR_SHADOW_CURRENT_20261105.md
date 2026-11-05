# Mobile SpeedTree distant-shadow core pass (2026-11-05)

## Scope and original-byte protection

Six existing Conifer/Cypress/Pine A–D Unity `.prefab` core files each disable realtime shadow casting on **LOD2 and LOD3 only**. LOD0/LOD1 keep realtime shadow casting and all four LODs receive shadows. The final billboard LOD, transition heights, appearance, existing improved trunk/crown geometry import profiles, exact prefab local bounds, collider and source GUIDs remain as before. No TerrainData tree instances, `.unity` scene, `.meta` or `.st` binary files are changed.

The stale draft PR #36 contains older bounds/collider values relative to newer `main` and must **not** be merged wholesale. This branch is based on current `main` and transplants **only 12 verified far caster flags**, never old bounding values.

`Tools/World/tests/test_speedtree_far_shadow_current_core.py` restores the precise LOD2/LOD3 flags and requires the **original current-main Git blob SHA-1** for each species. The existing exact reviewed source integrity manifest is updated to pin the resulting six new blob SHA-1 values; other source imports and GUID checks remain strict. This is an auditable native serialized prefab edit, not a runtime script or model replacement.

## Visual and mobile QA gate

Distant trees remain visible; *their ground shadows can disappear at LOD2 and LOD3*. This may reduce distant shadow-pass work, but 2–3 GB Android FPS or quality improvement is **not measured**. Verify actual Unity Editor import, tree wind/billboard transition visuals and real hardware FPS, P95 frame time, GPU overdraw, temperature, 2 GB and 3 GB low-memory stability before treating this as a finished release. Do not imply this modifies selective baked tree bark geometry or building scales.

Unity optimization reference: https://docs.unity.com/en-us/engine/6000.0/manual/render-pipelines/universal-render-pipeline/urp-reference/universalrp-asset
