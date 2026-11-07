# Deep audit: gun-ready movement and hand handling
Date: 2026-11-07
Repo: sundamunda289-art/Unity-Game-Aris
Review: PR #96

## Scope
This change builds on merged single-gun PR #95. It touches runtime player
movement, visual-only humanoid animation, equipped gun presentation, and
license-free regression checks. **No native Terrain, scene, player prefab,
buildings, vehicles, original FBX or Git LFS map assets are modified.**

## Confirmed source-level bugs fixed

| Impact | Bug | Correction |
| --- | --- | --- |
| High | `KeyCode.E` simultaneously triggered pickup and the player motor's auto-sprint toggle. | E=PICK, G=DROP, T=auto-sprint, V=ADS, R=reload; mouse-right remains camera look. |
| High | Imported humanoid RightHand bone may carry strong 0.01/100x scale. Making gun a child of it changes the gun's actual render size and can cause clipping. | Keep equipped gun root as a player child, normalize its mesh scale once, then update its **world position/rotation** to follow the animated right-hand bone every LateUpdate. |
| High | Rendering the gun's position before character Playables completed in LateUpdate could produce a one-frame hand grip offset. | `AarisCharacterVisual` order +200; `AarisWeaponInventory` order +310. |
| High | Fire and Punch were both full-body mixer channels and could suppress walking/running legs when a shot blend reaches 65%. | Standard `AnimationLayerMixerPlayable` with nine baseline locomotion clips + separate masked upper-body clip layer. |
| Medium | ADS was only a zoom: the user could scope while sprinting and the actor would shoot sideways if camera yaw differed from their travel direction. | ADS cancels auto-sprint, caps standing speed to 2.65m/s, keeps crouch at 2.4m/s/prone 1.1m/s, and rotates armed body to camera yaw during aim/fire for camera-relative strafing. |
| Medium | Mouse-right both toggled ADS and steered the camera simultaneously. | V handles desktop ADS; touchscreen ADS utility button remains, mouse-right remains camera-look. |

## Animation architecture

- **Baseline:** idle/walk/sprint, jump start/loop/land, fall, crouch idle/walk.
  Same single CharacterController controls all movement and collision.
- **Upper body:** aim/ready fallback, pistol firing and unarmed punch
  on a separate Humanoid AvatarMask override. Root, legs, feet and
  foot IK are excluded from the overlay to keep grounded feet animated.
- **Source limitations:** The locally vendored, checksum-verified Quaternius
  pack contains a Pistol_Shoot motion but **no dedicated rifle idle,
  two-handed IK aim, directional strafe, reload or prone crawl clip** in
  the ten exported clips. An early pistol-shoot pose is only a modest
  fallback aiming posture. Real shoulder contact, left-hand grip and a
  convincing rifle run require additional properly licensed motion
  clips and Unity retarget/IK visual verification.
- **Guns:** locally vendored CC0 FBX models remain attached to the player
  renderer hierarchy without their colliders affecting walls or player
  physics; the true camera and muzzle hit-scan authority is unchanged.

## Game feel targets
- Unarmed sprint: 6.5m/s
- Gun sprint: 5.7m/s
- Walk/jog: 4.2m/s
- ADS walk/strafe: 2.65m/s maximum
- Crouch: 2.4m/s
- Prone: 1.1m/s
- Fire-while-moving: 2.0m/s standing baseline
- Smooth camera-yaw facing: exponential 17/s response.
- Mobile five combat buttons and the separate ADS/PICK/DROP/RELOAD
  utility row are retained. No additional controls are added.

## Verification
`Tools/Validation/check_armed_locomotion.py` validates each input intent,
world-space grip, separated animation layering, stance speeds and
10–120 FPS facing maths.
`Tools/Validation/check_battle_hardening.py` checks 12,000 deterministic
animation transitions; `check_battle_hud.py` confirms the five mobile
actions and actual class references. Existing `check_weapon_loot.py` and
`check_single_weapon_transactions.py` still verify real FBX hashes,
reloading and one-gun/drop invariants.

**Still unverified:** Unity 6000.3.26f1 compilation, Playables import and
true avatar retarget, two-handed weapon alignment, hand crossing/animation,
actual muzzle vs visible barrel, Android multitouch and frame times,
collision and gameplay screenshots. Source checks cannot certify these.
Do not market this as an identical proprietary Free Fire/BGMI/PUBG
animation or a tested multiplayer authoritative gun system.
