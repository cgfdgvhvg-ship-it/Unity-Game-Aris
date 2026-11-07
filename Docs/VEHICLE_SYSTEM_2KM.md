# Aaris — 2km×2km mobile vehicle system (2026-11-07)

## Verified native map facts

The game's real source is `Docs/MAP_LAYOUT.json`, not a guessed 17-node
test world. **45 actual empty vehicle spawn markers** are already committed
into the original 2km Unity scene, in 13 areas. These are not vehicles.
The map has **39 authored road polylines**.

`Assets/Resources/AarisVehicles/vehicle_candidates.json` permanently bakes
45 original garage/parking markers and **33 new road-adjacent candidates**,
with original road names, yaw and approximate height. The 78 candidate points
cover 14 of the 16 500m×500m sectors that contain reviewed parking/road data.
The system does **not** invent free-floating cars in the other two sectors.
On each match it chooses **26 possible vehicle slots** across 14 available
sectors with >=100–105m separation and prioritizes original garage
locations. A 300-seed offline spatial audit confirms 26 planned spots and
14 selected sectors in the current map data. A chosen spot produces an
**actual car only if runtime Physics validates it**. Therefore the exact
number of physically spawned cars may be lower than 26; never promise
every candidate works without real Unity Play-mode ground validation.

**Cars are streamed**: plan all matches once; create at most 2 new nearby
cars per 0.3-second tick within 42m and keep at most 10 active local cars.
Static world/road colliders are already activated within 55m by
`AarisNearbyColliders`; check real terrain height, <=12° slope, 4
support samples and a car-sized obstacle box before instantiating any
car. Reject unsafe water, roofs, rocks or solid walls. Parked distant
cars may unload after 160m once both angular and linear velocity are
small; their new world position/heading is persisted, never reset to
the original garage. Occupied/moving cars remain alive.

## Permanent local source assets (no runtime links)

**Kenney Car Kit v3.1**, original artist Kenney, license **CC0 1.0**:
https://kenney.nl/assets/car-kit
Author's CC0 mirror:
https://opengameart.org/content/car-kit

The exact 4,814,237-byte archive was verified against SHA-256
`fac7dacac5c7874348cf19729af3ef205f3d366493edaf0a827d93f4fdf3d0c4`
before extracting:
- six car FBX shapes: sedan, SUV, sedan-sports, hatchback-sports,
  van and truck-flat
- three independent wheel FBXs: wheel-default, wheel-racing, wheel-truck
- one shared `colormap.png` texture atlas and upstream `KENNEY_LICENSE.txt`

These **actual binary files, their fixed GUID meta files and license**
live inside `Assets/Resources/AarisVehicles/` on GitHub. No phone
download or network dependency is required to run the game. The
one-time official/archive-mirror vendor workflow is
`.github/workflows/aaris-vehicle-vendor.yml`; the shipped game
loads only local `Resources` objects. `check_vehicle_system.py`
individually validates nine pinned model SHA256 digests and byte sizes.

**Visual quality boundary:** Kenney's car models are game-ready,
lightweight and stylized, not photorealistic PBR automobiles or
copyrighted cars from PUBG/BGMI/Free Fire. Realistic URP paint, interiors,
lights and full device visual QA remain future art tasks.

## Production-oriented code ownership

| Component | Single responsibility |
|---|---|
| `AarisVehicleWorld.cs` | Source candidate loading, weighted model selection, seeded 500m sectors, world space streaming, floor/slope/obstacle checks, shared URP palette |
| `AarisVehicleMotor.cs` | Rigidbody + four WheelColliders, spring/damper/friction, car type torque/speed, brake/reverse and speed-dependent steering |
| `AarisVehicleSession.cs` | Exclusive foot/drive player state, disable original walking motor while driving, safe verified vehicle exit, chase camera |
| `AarisVehicleHUD.cs` | Four translucent double-chevron arrows, Drive/Exit, multitouch hold/cancel, device safe-area layout |
| `vehicle_catalog.json` | Six car families, relative rarity, weight and maximum speed in metres/second |
| `AarisVehicleImportValidation.cs` | **Real Unity Editor** imported-model/mesh, color atlas, shader, original scene/45 markers and C# compilation gate |

The existing `AarisThirdPersonPlayer` remains the sole walking motor;
driving deactivates that component and its CharacterController.
In-vehicle camera has one owner, and return to foot mode resets
held touch fingers, unarmed/weapon inputs and the player camera.
Fire/Jump/Crouch/Prone/Sprint and ADS/PICK/DROP/RELOAD UI canvases are
hidden only while driving, then restored on a verified exit.

## Four-button control UX

Four hold arrows: **up = forward**, **down = brake then reverse**,
**left/right = steer**. Up/down share the left thumb, left/right the
right thumb. UI is screen-safe, with one cached procedural 128px
double-chevron glyph and translucent ring; no paid icon download,
repeated texture creation or screen-filling pedals.

Desktop test: `F` enter, `X` exit; arrow keys / WASD drive.
`H` resets the on-foot player instead of `F` to avoid key conflict.
If two opposite arrows are held simultaneously, they cancel.
Pointer cancellation/pause/focus loss releases steering/brake safely.

Vehicle physics uses NO `rb.linearVelocity = ...` speed teleport,
NO guaranteed anti-flip cheat and NO snap-rotate steering at high speed.
The torque curve is **speed-dependent**:
strong at first, reducing through 7, 14 and 21 m/s speed thresholds
until the vehicle's type-specific top speed. That is a balance model,
not a claim of an actual automatic transmission/gearbox. The wheels
supply physical acceleration/braking. On releasing Up, the car coasts
and receives a modest engine brake; Down brakes before reversing.
Maximum speeds range from 20m/s (van) to 28m/s (sport).

Separate wheel FBX models are synced every rendered frame to Unity
`WheelCollider.GetWorldPose` for suspension, spinning and turning;
a shared URP Lit material uses Kenney's CC0 color palette. True wheel
axis/scale alignment still requires real Unity visual inspection.

## Security, release QA and limitations

- Never use the user's Unity email/password or runtime website asset
  downloads. No native terrain, scene or prefabs are overwritten.
- All cars are local-only authoritative game objects. Multiplayer
  requires a future server to approve car spawn seeds, seat occupancy,
  inputs, collision and vehicle impacts.
- Real driving physics, collision shapes, side exits, visual wheel
  offsets and Android dual-finger HUD require a licensed Unity Editor
  Play-mode and device test before a verified APK release.
- No roadkill damage by name heuristics; proper hit damage needs
  victim health interface and collision impulse thresholds.
- No fake transparent car meshes or primitive cube fallbacks.
- World plans can be fewer in inaccessible areas; logs distinguish
  planned cars from actually validated placement.

License-free checks:
```
python Tools/Validation/check_vehicle_system.py
python Tools/Validation/check_explorer.py
```
Real Unity import gate:
`Aaris.MapReview.Editor.AarisVehicleImportValidation.Run`
