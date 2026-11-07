# Aaris battle controller — independent deep audit, 2026-11-07

## Scope and non-destructive rule

Audit of PR #92 on `feat/rigged-character-locomotion-20261107`. The native
2 × 2 km Terrain scene, real TerrainData tiles, house prefabs, roads, vehicles,
materials and legacy Git LFS map assets were not intentionally modified.
`main` remains unchanged. Character body, HUD, gameplay motor and source
integrity are investigated separately.

Unity Editor 6000.3.26f1 license activation, true Play-mode execution and
Android APK playback are **not** verified by these license-free CI tests.

## Findings addressed in PR #92

| Priority | Finding | Code-level mitigation |
| --- | --- | --- |
| High | Manifest lacks uGUI: `Image`, `CanvasScaler` and `EventSystem` may be unresolved at compile time. It also lacked the animation/director modules. | `Packages/manifest.json` now declares `com.unity.ugui` 2.0.0 plus Animation and Director modules. |
| High | A 50 ms `deltaTime` cap made a character run at half speed during 10 FPS frames. | Motor integrates real time up to a 150 ms extraordinary-hitch safety limit, with real-time integration checks for 10–120 FPS. |
| High | End-velocity Euler jump displacement lost roughly 33% of 1 m jump apex at 10 FPS. | Trapezoidal vertical displacement integration, without a duplicate CharacterController.Move. |
| Medium | Overlapping jump-start / jump-land / combat Playables could produce mixer weights summing to more than 1 and snap the pose. | Priorities are mutually exclusive and weights normalized; deterministic 12,000-case sweep. |
| Medium | Attack one-shots abruptly replaced entire-body locomotion, and manually phase-driven gait clips also advanced with the normal graph clock. | Time-controlled gait clips use speed 0; attack crossfades are limited to a 0.65 full-body share with short fade-in/out. This reduces stutter but is not a replacement for real upper-body masked animation. |
| Medium | Holding Fire/Jump with multiple fingers could stop when the first finger lifted, leaving the other finger held. | Each hold button keeps a HashSet of pointer IDs; releases the action only after its final pointer is released. |
| Medium | Blanket filtering of the player's entire layer meant opponents on the same layer could not be punched or shot. | Collision/raycast checks exclude only the attacking player's hierarchy, not all players on that layer. |
| Medium | Camera-aimed shots could bypass nearby cover, particularly with a shoulder camera. | Raycasts choose the closest external collider, then validate the muzzle-to-target line; saturated hit buffers fail closed. |
| Medium | Previous stand-up headroom tests could mistakenly detect the ground. Prone could clip into nearby building walls. | Stand-up tests only newly occupied headroom. Prone adds predictive horizontal body clearance and maintains the authoritative short collision capsule. |

## CI verification and separate boundaries

- C# syntax, GUIDs, source-contract and existing native-scene pointer tests run in
  `.github/workflows/explorer-checks.yml`.
- `Tools/Validation/check_battle_hardening.py` independently checks Unity
  package dependencies, correct mobile hold/release structures, safe physics
  invariants and **12,000 randomized animation-mixer weight cases**.
- `Tools/Validation/simulate_battle_feel.py` checks predictable acceleration,
  braking and tap/hold jump trajectories at **10, 15, 20, 30, 60 and 120 FPS**.
  It is a Python model of motion equations, not actual Unity Play-mode frames.
- Source-pinned Quaternius animation library was audited: 43 GLB source actions.
  Eleven verified FBX files (the male model + ten clips) are versioned through
  Git LFS. GitHub Actions LFS integrity verifier confirmed hydration, SHA-256,
  20 Unity GUIDs and 2 CC0 licenses.
- Real Unity importer or runtime cannot be considered verified merely because
  these source tests succeed. Unity itself must compile/import the UI and FBX
  assets and render them before merging this Draft PR.

## Remaining risks / release gates

1. **Unity Editor compilation and importer:** UPM must resolve core uGUI; verify
   Human avatar validity, animation retargeting and material import in
   Unity 6000.3.26f1 under an authorized license.
2. **Physical phone UX:** verify landscape notch/safe-area placement, rapid
   two-finger Fire + Jump + joystick + camera-look concurrency, pointer
   cancellation, orientation changes, tap/hold jump and FPS percentiles.
3. **Actual physical surfaces:** test standing under low ceilings, 46° slopes,
   stream bridges, indoor MeshCollider floors and prone movement around walls.
   No static physics test proves those scene-specific collisions behave well.
4. **Animation quality:** original CC0 motion pack lacks a dedicated prone crawl
   clip. Rotated-body pose is only a visual fallback. Full production polish
   should include a dedicated prone crawl, IK contact and upper-body-only
   weapon overlay, plus frame-by-frame screenshot/video evidence.
5. **Battle networking:** the current optional gun and punch damage hooks are
   local prototypes. Authoritative multiplayer damage, anti-cheat, ammo,
   reload, hit reconciliation and lag compensation are not implemented.
6. **Build quality:** Android IL2CPP compile, shaders, memory usage, LFS cache
   correctness and real frame times remain dependent on an Editor-equipped
   runner/device test.

## References

Unity 6000.3 core uGUI:
https://docs.unity.com/en-us/engine/6000.3/manual/packages-list/packages-all/pack-core

Unity modules:
https://docs.unity.com/en-us/engine/6000.3/manual/packages-list/packages-all/pack-build

All changes and evidence are retained in:
https://github.com/sundamunda289-art/Unity-Game-Aris/pull/92
