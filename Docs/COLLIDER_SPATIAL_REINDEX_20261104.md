# Saved-world collider spatial index correction (2026-11-04)

## Why this is a core fix

The checked-in `Assets/AarisWorld/Scripts/AarisNearbyColliders.cs` manages the authored scene's proximity-gated colliders. The current saved-world registry has 271 indexed entries in its review chain, including 57 authored-disabled MeshColliders that must become active near the player. Its previous spatial hash was built **only in Awake**. Even a caller invoking `RefreshNow()` after moving or scaling a registered building/obstacle would leave that collider assigned to its old XZ grid cells. `Physics.SyncTransforms()` alone cannot update the script-owned grid.

This patch retains the original collider shapes, registered IDs, scene, prefab references, Git LFS bytes, .meta files, terrain, LOD thresholds, visible skyline and proximity activation distance. It adds a **transform-aware explicit refresh**, not a per-frame scene scan.

## Core behavior

- During initial indexing, save each supported Mesh/Box/Sphere/Capsule collider's local bounds and its `localToWorldMatrix`. These bounds work for originally disabled MeshColliders; Unity's `Collider.bounds` is empty while disabled.
- `RefreshNow(false)` keeps the existing 0.25-second / 2 m player-distance polling with **no transform-check loop or spatial rebuild**.
- A caller explicitly invoking public `RefreshNow()` checks registered obstacle matrices. If nothing moved, the spatial hash remains untouched. If any registered obstacle moved, rotated, scaled or inherited a parent transform edit, rebuild the XZ cells and world AABBs once using the original local bounds. The next activation pass uses current positions and can retire old nearby entries.
- Explicit refresh still performs `Physics.SyncTransforms()` before downstream physics queries. Authored-disabled building colliders are still indexed and eligible for activation, while terrain/player colliders remain excluded.
- Geometry changes that alter a collider's **local shape**, or unregistered new obstacles, are **not** handled by this transform-only invalidation; those require an explicit registry rebuild/reinitialization workflow and Unity validation. Do not confuse this fix with a solution for every moving-vehicle physics case.

## Scaling and level-design review (proposal, not applied scene edits)

The saved project's consolidated draft #25 already includes 47 residential LOD scene entries, 32 RockCover entries, seven reviewed house source prefabs and six source-profiled SpeedTree types. Another overlapping draft (#24) changes Cypress proportions differently. Do not combine both approaches or multiply tree-root transforms again.

Review model-relative rendered dimensions against the existing 1.78 m player **before** authoring geometry:

| Gameplay role | Initial physical design review range (metres) | Required validation |
| --- | --- | --- |
| Habitable room | Ceiling clear height roughly 2.4–3.0 | Camera, controller and actual mesh collision |
| Player walk-through door | Clear width roughly 0.9–1.1; height >=2.0 | Source hole, frame collider and controller route |
| Vaultable window | Sill and clear opening matched to an authored vault animation/controller path | Do not infer vaultability solely from visual width |
| Non-vaultable window | Higher sill, narrower usable opening or an intentional blocker | Must not permit unintended clipping |
| Forest trees | Species-dependent trunk/crown ratios and root taper | Source-mesh height, native instance scale and collider-to-trunk alignment |
| Rocks | Orientation follows bedding and slope; collision cover matches readable silhouette | Inspect nine-point terrain footprint and physics contacts |

These are design-check ranges, **not measurements of existing saved buildings**. Without materialized LFS geometry, Unity capture and route probes, do not claim that interiors are already reachable or that any house dimension is now correct.

## Tests and release gate

1. Run `python -m unittest discover -s Tools/World/tests -v`, `python Tools/World/check_contracts.py`, `python Tools/World/world.py verify --native` and `python Tools/World/world.py verify --project-checks`; inspect any GitHub Actions run before merging.
2. In Unity 6000.3.26f1 with complete LFS assets, move a registered collider across a grid boundary (including X/Z negatives) and call `RefreshNow()`. Verify old and new activation cells, far deactivation and collisions.
3. Repeat after parent rotation/nonuniform scale and with an originally disabled building MeshCollider; ensure the authored enabled/disabled restoration and exclude terrain/player.
4. Compare an idle stationary route with the previous commit; verify no additional per-poll `Physics.SyncTransforms` or matrix-wide scans. Validate actual render, physics and 2/3 GB Android memory/p95 frame time; **no FPS improvement is asserted by this source patch**.
5. Do not merge until source CI, Unity import/compile and route/device tests are reviewed. This fix does **not** change house geometry, visual quality, foliage scale or phone FPS directly.

Unity references:
- Physics transform synchronization: https://docs.unity.com/en-us/engine/6000.3/script-reference/unityengine/physics/synctransforms
- Disabled collider bounds: https://docs.unity.com/en-us/engine/6000.0/script-reference/unityengine/collider/bounds
