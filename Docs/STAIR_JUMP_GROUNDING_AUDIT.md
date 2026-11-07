# Stair jumping and collision hardening

This change follows merged PR #92 without modifying the saved 2 × 2 km Terrain scene, native terrain LFS blobs, props, or AarisPlayer prefab.

## Findings

- **Airborne stair climbing:** The physics controller kept its standing/crouched `stepOffset` while airborne, allowing unwanted automatic vertical stepping at the edge of walls and stair blocks. The player motor now uses `stepOffset=0` during jumps/fall and restores the correct stance-specific offset after ground contact. This preserves the intended single `CharacterController.Move` authority.
- **Crouch/prone step behaviour:** While crouching, automatic 30cm climbing would be too aggressive under low ceilings; while prone, the original code still allowed roughly 18.6cm auto-climbing. The character now uses up to **30cm standing**, **18cm crouched**, and **7.5cm prone**; default saved prefab remains 30cm.
- **Underwater bridge/ramp support:** The shoreline `SafeFooting` probe previously used the mutable `CharacterController.stepOffset`. Because that offset is deliberately zero in the air, the bridge ray would become too short during a jump. Support checks now use the saved original 30cm ground step dimension instead.
- **Fast taps on low FPS phones:** Releasing Jump before the next frame could cause very weak takeoff. A small minimum normal-gravity ascent period (75ms) is enforced before early-release gravity is applied. A held jump retains its intended 1m relative height.

## Limits

Unity uses the native CharacterController, so its Step Offset allows auto-stepping over small stairs; a **0.5m or 1m ledge is not automatically climbed**. Jumping can raise the feet by approximately 1m above the launch tread, subject to headroom, slope, active collisions and the player's control. No unverified mantling / vaulting / ladder animations have been added.

The source-level Python regression compares 10/15/20/30/60/120 FPS short and full jump trajectories and asserts the step-offset state transitions. It is not an actual Unity physics run. True step geometry, ledge clipping, camera, and Android touchscreen interactions require a licensed Unity Editor/PlayMode session and a mobile build.

## QA commands

```
python Tools/Validation/check_explorer.py
python Tools/Validation/check_battle_hud.py
python Tools/Validation/simulate_battle_feel.py
python Tools/Validation/check_battle_hardening.py
```

The complete Map Explorer GitHub Actions workflow also validates original scene and render assets. Do not mistake C# parsing and analytical physics simulations for Unity compilation or real-world device performance.
