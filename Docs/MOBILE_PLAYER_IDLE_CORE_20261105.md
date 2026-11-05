# Saved player idle-frame CPU pass — 2026-11-05

The real existing `Assets/AarisWorld/Scripts/AarisThirdPersonPlayer.cs` now evaluates candidate terrain/bridge/shoreline support only when horizontal input is nonzero. This removes up to one `SafeFooting()` attempt per idle frame, including potential `Terrain.SampleHeight` and physics raycasts, without changing the authored map or draw distance.

Every nonzero movement still runs the exact 975 m boundary and shoreline/bridge footing checks. Jump coyote-time, gravity, CharacterController.Move, camera, collider-window refresh and animation continue updating while idle. The patch is C# source only: no scene, native TerrainData, meshes, materials, prefabs or `.meta` GUIDs changed.

Regression tests cover the exact movement gate and retained player/physics mechanics. `Tools/World/check_contracts.py` now syntax-checks this player source in addition to the runtime code.

**Limits:** This is CPU-query reduction, not a measured reduction in total CPU, GPU, RAM, or Android frame time. Test on real device in a fixed camera position, then with walking/jumping on shorelines, near bridges and buildings, and inspect the frame-time P95. Native Unity reimport and 2 GB Android release QA are separate evidence gates. The older draft PR #35 is not merged wholesale.