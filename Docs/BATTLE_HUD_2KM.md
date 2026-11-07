# Five-control mobile battle HUD — 2 km Aaris map

## Goal
A minimalist, battle-royale-style third-person touch layout, without
copying proprietary Free Fire or BGMI button art or adding another motor.
Exactly **five action controls** are generated at scene start using
Unity UI and locally rasterized, original white silhouette icons:

| Action | Placement | Behavior |
| --- | --- | --- |
| Sprint | Left upper-middle, above movement joystick | Tap toggles forward auto-sprint; pulling backward cancels; camera look steers |
| Fire/Punch | Right-middle, large transparent circle | Pointer down/up holds attack; no equipped weapon = repeat punch |
| Jump | Right upper-middle | Short tap for low jump; hold for full height; buffers before landing; stands only when headroom is clear |
| Crouch | Right low corner | Toggle crouch / stand, resize the existing collision capsule |
| Prone | Right-bottom beside crouch | Toggle crawl / stand; low capsule plus a forward/back body-footprint clearance check |

Legacy movement joystick and right-thumb camera look remain unchanged.
The saved HOME / REPORT / FPS diagnostics are available only in Unity Editor
or development builds; a release APK keeps just the five action buttons
and the movement joystick. New action icons are **not** URL-loaded:
`AarisHudGlyphs.cs` draws textures once inside the app.
`AarisBattleHUD.cs` handles safe-area constraints, responsive canvas scaling
and multi-finger pointer capture. `AarisHudButton.cs` releases hold-fire on
pointer-up/cancel/disable. No extra HUD prefabs, EventSystem duplicates
or manual editor drag/drop are required for normal scene boot.

## Movement contract (Unity world units: 1 unit is 1 m)

| State | Target horizontal speed |
| --- | ---: |
| Sprint, hands empty | 6.5 m/s |
| Sprint with gun equipped | 5.7 m/s |
| Jog/walk | 4.2 m/s |
| Crouch move | 2.4 m/s |
| Prone crawl | 1.1 m/s |
| Combat move while firing | 2.0 m/s |

These are **Aaris design defaults**, not verified proprietary Free Fire/BGMI
speed constants. The native scene still has its 2 km bounds and four 1 km
Terrain tiles. A 13 m/s² acceleration target and 19 m/s² deceleration
smooth speed changes. The player's original gravity/grounding and
`SafeFooting` checks remain authoritative; there is exactly **one**
`CharacterController.Move` call per player frame.

Auto-sprint retains forward intent after releasing the joystick, allows
the right thumb to rotate the view, cancels on backwards input or fire,
and eases the original camera FOV up by 6 degrees while running. Jump uses
0.17 s input buffering, about 0.11 s coyote time, early-release gravity,
short downhill support probes and a 0.15 s smooth camera stance spring.
These are design-tunable starting settings, not a claim of tested Android feel.

## Separation of responsibilities
- `AarisThirdPersonPlayer`: only movement authority, collision/terrain,
  joystick/look, buffered jump, camera, speed and auto-sprint.
- `AarisBattleActions`: three mutually exclusive stances, **head-only**
  stand-up clearance, predictive horizontal prone body-footprint checks,
  equipment slot, held attack/cooldown, melee range and line-of-sight checks.
  No second movement controller.
- `AarisEquippedGun`: optional local hit-scan equipment and
  `IAarisDamageable` interface; optional muzzle clearance check prevents
  camera-angle shots through walls. Empty slot uses punches.
- `AarisCharacterVisual`: independent eleven-input Humanoid Playables
  mixer: idle/walk/sprint, airborne loop, falling, crouch idle/walk,
  jump start/land, punch and shoot. Smooth crossfades, sprint lean and
  brief landing compression are visual-only; root motion is disabled.
- `AarisBattleHUD`, `AarisHudButton`, `AarisHudGlyphs`: only responsive
  view and pointer intent; no per-icon physics or gun logic.

Prone currently has a rotated/ground-aligned **visual fallback** because
the verified library provides idle/crouch-walk/punch/shoot/jump phases,
but **does not contain** a true prone crawl cycle. A high-fidelity prone animation, proper animation-specific
root offset/IK, weapon reload/ammo and network-authoritative combat are
future production work. Current melee/gun damage is **local gameplay**,
not secure online multiplayer damage adjudication.

## Verification
The GitHub Actions `Map explorer checks` pipeline runs:
```sh
python Tools/Validation/check_explorer.py
python Tools/Validation/check_battle_hud.py
python Tools/Validation/simulate_battle_feel.py
```
These checks parse every C# script, ensure five and only five action
controls, preserve saved scene/player GUIDs, and reject duplicate movement
motors. They are static tests, **not proof of Unity compilation or
touch interaction on a physical phone**.

Once Unity 6000.3.26f1 and its Personal license work normally, run:
```sh
unity-editor -batchmode -quit -projectPath . \
  -executeMethod Aaris.MapReview.Editor.AarisBattleHudValidation.Run \
  -logFile -
```
The menu equivalent is **Aaris > Validate Battle HUD And Player**.
This adds Unity's actual importer/rig/binding checks. Follow with a real
portrait/landscape phone Play-mode test, screenshot and FPS profile.

The branch deliberately does **not** modify the native terrain scene,
big LFS map assets, house positions, vehicle spawns or the saved player prefab.
It extends the existing source code and stores stable script .meta files.

## Final audit checkpoints (not yet executed on Unity Editor)
- Hold Jump and tap Jump at 30/60/120 Hz; confirm short/full arc separation.
- Jog, sprint and brake over flat terrain; check the real third-person camera.
- Crouch/prone beneath a roof, then attempt standing; never push the head through a ceiling.
- Prone beside house walls/rocks; head and legs must not cross colliders.
- Fire empty handed (Punch_Jab), equip a compatible gun (Pistol_Shoot), and check cover occlusion.
- Inspect retargeted FBX materials and animated feet on ramps, roofs, rocks and slopes.
- The original Quaternius library provides **10 separate imported animation clips**;
  `Player.fbx` is an additional, locally vendored male model. All 11 FBX
  assets must pass Git LFS hydration and SHA-256 integrity checks.
- Capture true Unity screenshots and compare Android frame-time percentiles
  before upgrading this Draft PR to merge-ready.
