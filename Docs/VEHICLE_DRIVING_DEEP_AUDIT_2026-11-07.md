# Vehicle driving: post-merge deep audit (2026-11-07)

Repo: sundamunda289-art/Unity-Game-Aris, follow-up to merged PR #97.

## Grounded code issues found and corrected

| Severity | Original failure | Correction |
| --- | --- | --- |
| High | Vehicle exit checked only forward-projected velocity, so a car sliding *sideways* at high speed could allow an unsafe player exit. | `AarisVehicleMotor.IsSafeToExit` checks full 3D speed under 1.1m/s, angular velocity under .5 rad/s, upright tilt (up dot >.72), and at least two wheels grounded. |
| High | Single-hit chase-camera sphere cast could hit the car's own collider first; filtering that hit dropped the search and missed a building behind it. | Bounded `SphereCastNonAlloc`, own vehicle/player collider filtering, choose nearest external wall. If buffer overflows, fail closed to a close-up camera position rather than clipping through geometry. |
| Medium | Chase camera followed the interpolated Rigidbody inside `Update`, potentially producing physics/render stepping jitter. | Camera follows in `LateUpdate`, with exponential field-of-view and damped position. |
| Medium | Driverless parking brake applied only 600Nm per wheel, so an unoccupied vehicle could slowly roll away on slopes and never qualify for distant streaming. | 3600Nm per-wheel parking brake, zero torque on deactivation, tighter standstill thresholds for stream-out. |
| Medium | Forward/reverse sign switching permitted opposite motor torque at +/-0.8m/s before coming to a stop. | A 0.55m/s brake-before-reversing transition prevents sudden torque inversion. |
| Medium | Sharp bends on uneven ground can roll the car; low COM alone does not solve axle load transfer. | Bounded 4800N axle anti-roll applied only to grounded wheels using standard `WheelCollider.GetGroundHit` suspension travel. This reduces roll tendency, not a guarantee against flips. |
| Diagnostics | No regularly sampled actual vehicle speed, steering, contact or brake values in logs. | A `Debug.isDebugBuild`-only, 3-second `AARIS_DRIVE_TELEMETRY` line logs signed speed, full speed, grounded wheels, steering, throttle, brake torque and roll angle. |

## Not changed
- Original four Terrain tiles, scene, 45 existing parking points and 39 road polylines.
- 33 baked extra roadside candidates and 26 target parked-vehicle plans.
- 6 locally committed, SHA256-verified CC0 Kenney car models, 3 local CC0 wheel meshes, textures/license and model GUIDs.
- Four mobile arrow controls (forward, reverse, left, right), one DRIVE/EXIT button.
- Rigidbody + actual WheelColliders, real 3D wheel visuals, guarded player enter/exit and exclusive on-foot versus vehicle controls.
- No cheat `Rigidbody.linearVelocity = targetSpeed` assignment, no fake permanently-upright physics and no external runtime model URL.

## Automated verification

`python Tools/Validation/check_vehicle_system.py`: 45 + 33 candidate provenance, 300 seeded 500m-sector plans, nine actual FBX hashes, 4 wheel mesh integration, HUD and base movement contracts.

`python Tools/Validation/check_vehicle_drive_hardening.py`: source invariants for safe full-speed exits, wheel contact, brakes and anti-roll; numeric reference cases covering forward-to-reverse braking, self-hit camera ray ordering, sideways sliding exits and 15–120 FPS damping. These are **not** an actual Unity WheelCollider solver test.

GitHub Actions' `Map explorer checks` combines these with C# syntax parsing and all preexisting world/weapon/HUD tests. Any failure prevents merging.

## Still required for a verified vehicle release

Run Unity **6000.3.26f1** with valid Editor license and invoke `Aaris.MapReview.Editor.AarisVehicleImportValidation.Run`; then visually test the car meshes/materials, wheel axis/offset, tire rotation, suspension and collisions, a steep downhill, collision with a house, reversing into a wall, 0–100km/h acceleration, 20–100km/h turn stability, sideways-slide exit protection, camera obstruction and simultaneous two-finger input on Android. The live game has not been driven here; no timing, screenshot, build or measured FPS is claimed.

Unity's official WheelCollider docs confirm `motorTorque`, `brakeTorque`, `steerAngle` and `GetGroundHit` contact functionality, but tire friction does not automatically respond to standard PhysicMaterials; wet/soil/road handling must later be validated/tuned for the actual terrain data.
