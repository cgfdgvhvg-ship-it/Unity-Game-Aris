# Offline BR Combat and Aerial Drop

This feature is designed for offline single-player vs AI bots. It does not add networking, cloud game servers, multiplayer synchronization, or runtime downloads.

## Fully local source art

All four original OBJ and MTL source models are committed to this GitHub repository:

- Assets/Resources/AarisDrop/CargoPlane.obj: original cargo aircraft; local propeller pivots and animation.
- Assets/Resources/AarisDrop/ElongatedParachute.obj: long, tapered, elliptical curved canopy with local suspension ropes; not square-shaped.
- Assets/Resources/AarisCombat/GlooWall.obj: original curved cover mesh.
- Assets/Resources/AarisCombat/FragGrenade.obj: original thrown grenade mesh.

The scripts also contain local visual fallbacks. Unity Resources.Load reads these included files from the built game, not from the internet. Stable Unity .meta GUIDs accompany the assets. Existing TerrainData, SpeedTree and map LFS source files are left unchanged. Original art in this PR is preview-quality, not a verified replacement for polished studio assets.

## Real project integration

- AarisOfflineDrop attaches to the existing AarisThirdPersonPlayer. It temporarily disables that on-foot motor while it is the only CharacterController/camera authority during plane flight, freefall and parachute gliding. After CollisionFlags.Below or roof/ground landing it calls ResumeFromAerialDrop and restores walking, the previous HUD and combat.
- AarisOfflineDropVisuals uses only local OBJ geometry or its local generated fallback and URP materials.
- AarisOfflineGlooWall provides ray/ground placement, OverlapBox clearance, an always-full collider and bottom-pivot visual deployment. Existing guns already use IAarisDamageable and can stop on this wall.
- AarisOfflineFragGrenade performs local Rigidbody flight, fuse, OverlapSphere damage and wall-occluded line-of-sight.
- AarisOfflineHealth is a lightweight IAarisDamageable receiver (default 200 HP). Bot prefabs can use the same class later; the existing source tree does not yet provide a complete AI combat/match state system.
- AarisOfflineTacticalHUD supplies on-foot mobile WALL and FRAG actions.

## Controls

Mobile: EJECT, OPEN, flight joystick + right drag, then WALL hold/release and FRAG tap after landing.
PC: Space/F eject, Space open canopy, WASD + right mouse steer/look, V hold/release wall, G throw frag.

Initial values: 5 walls at 600 HP/50 seconds each, 3 grenades, approximately 85m ground-relative automatic canopy deployment. These are project tuning defaults, not authenticated Garena values.

## QA gate

License-free static tests: python3 Tools/Validation/test_offline_drop_assets.py.
Before merge: real Unity 6000.3.26f1 scene import and script compilation, real camera render, Play Mode smoke test, rooftop/terrain landing, obstruction placement and grenade damage, mobile touch handling, and Android GPU/CPU profiling.

Static tests do not prove Unity compilation or gameplay. GitHub Actions/Codespace Editor success should not be claimed without actual reports and validated PNGs. No unrelated scene, material, LFS asset or existing dirty Codespace file should be overwritten. Advanced AI bot tactics, looting consumables, sound, improved animation and more finished textures require later work.
