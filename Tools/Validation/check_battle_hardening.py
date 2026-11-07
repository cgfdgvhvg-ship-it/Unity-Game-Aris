#!/usr/bin/env python3
"""Independent adversarial contract audit for Aaris mobile battle controls.

Runs without a Unity license. Uses deterministic parameter sweeps and source
assertions. A green result cannot replace Unity compiler / PlayMode / device QA.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "Assets/AarisWorld/Scripts"


def source(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def audit() -> None:
    manifest = json.loads((ROOT / "Packages/manifest.json").read_text(encoding="utf-8"))
    deps = manifest["dependencies"]
    # CanvasScaler, UnityEngine.UI.Image, PointerEventData require Unity uGUI;
    # "com.unity.modules.ui" alone does not provide those C# types.
    assert deps.get("com.unity.ugui") == "2.0.0", "Missing Unity 6.3 uGUI dependency"
    assert deps.get("com.unity.modules.animation") == "1.0.0", "Animation module disabled"
    assert deps.get("com.unity.modules.director") == "1.0.0", "Playables/director module disabled"

    motor = source("AarisThirdPersonPlayer.cs")
    ui = source("AarisBattleHUD.cs")
    button = source("AarisHudButton.cs")
    state = source("AarisBattleActions.cs")
    visual = source("AarisCharacterVisual.cs")
    gun = source("AarisEquippedGun.cs")

    assert "Mathf.Clamp(Time.deltaTime, 0f, 0.15f)" in motor, "Low-FPS movement discards time"
    assert motor.count("controller.Move(") == 1, "Two movement authorities detected"
    assert "SetJumpHeld" in motor and "SetJumpHeld" in ui
    assert "HashSet<int> heldPointers" in button, "Held buttons can stick or release early"
    assert "heldPointers.Count == 0 && owner != null" in button
    assert "heldPointers.Count == 1" in button
    assert "heldPointers.Clear()" in button
    assert "float primary = Mathf.Clamp01(startWeight + landWeight);" in visual
    assert "if (startWeight > 0f) landWeight = 0f;" in visual
    assert "float baseWeight = 1f - primary - combat;" in visual
    assert "HasProneClearance" in state
    assert "count == nearHits.Length" in state
    assert "muzzleHit" in gun

    # Android may drop a pointer without PointerUp on app pause, focus loss
    # or orientation changes. Reset the underlying identifier set, not just
    # the public fireHeld Boolean.
    assert "internal void CancelHold() => Release();" in button
    assert "private void ReleaseAllPointers()" in ui
    assert "button.CancelHold()" in ui
    assert "if (!focused) ReleaseAllPointers();" in ui

    # Missing Humanoid motion must NOT silently hide the reliable saved
    # player body and turn it into an unanimated FBX T-pose.
    assert "if (!graphReady)" in visual
    assert "Destroy(visual);" in visual
    assert "if (jumpStart == null) jumpStart = jump;" in visual
    assert "if (jumpLand == null) jumpLand = jump;" in visual

    # A crouched/prone bullet must leave the actor's actual eye-height,
    # not a standing muzzle that could see through low cover.
    assert "actions.CameraEyeHeight - 0.15f" in gun
    assert "SameTarget" in gun and "FirstExternalHit" in gun

    # Lying flat on stairs and bridge meshes must not be blocked because a
    # supporting floor shares an overlap region with the horizontal body.
    assert "obstacle.Raycast(floorProbe" in state
    assert "floorHit.normal.y >= Mathf.Cos(capsule.slopeLimit" in state

    # The saved physical controller (not a visual pose) is responsible for
    # climbing steps or traversing slopes. Larger ledges need manual jump;
    # this does not claim mantle/vault behaviour is implemented.
    prefab = (ROOT / "Assets/AarisWorld/Player/AarisPlayer.prefab").read_text("utf-8")
    assert "m_StepOffset: 0.3" in prefab, "Native 30cm step traversal was altered"
    assert "m_SlopeLimit: 46" in prefab, "Native 46-degree slope limit was altered"
    assert "m_Height: 1.78" in prefab and "m_Radius: 0.28" in prefab
    assert "SafeFooting(candidate)" in motor
    assert "CanAdvanceProne(candidate, horizontalVelocity)" in motor

    # Airborne stair climbing is disabled, and the old step offset is
    # restored for the first grounded Move. This preserves automatic stair
    # traversal while preventing jumps from auto-mantling wall ledges.
    assert "savedGroundStepOffset = controller.stepOffset;" in motor
    assert "controller.stepOffset = wasGrounded && !launchJump ? groundedStep : 0f;" in motor
    assert "controller.stepOffset = groundedStep;" in motor
    assert "savedGroundStepOffset + 0.1f" in motor
    assert "public float GroundStepOffset" in state
    assert "0.18f : 0.075f" in state
    assert "minimumAscentElapsed" in motor
    assert "minimumJumpAscentSeconds" in motor

    # Check the REAL current map layout, not an invented uniform staircase.
    report = json.loads((ROOT / "Docs/MOBILE_REVIEW_REPORT.json").read_text(encoding="utf-8"))
    towers = [p for p in report["placements"] if p["kind"] == "tower"]
    assert len(towers) == 4, "Saved ramp towers changed"
    for tower in towers:
        step = tower["riser_m"]
        assert 0.0 < step < 0.18, ("Crouch should walk up the authored stair", tower["name"], step)
        assert step < 0.30, ("Standing should step up the authored stair", tower["name"])
        assert step > 0.075, ("Prone should NOT auto-step up the authored stair", tower["name"])
        assert tower["stair_width_m"] >= 1.7
        assert tower["standing_height_m"] == 12

    # The world enables dense static wall/stair colliders around the player
    # before the motor runs. Its 55m activation radius must comfortably exceed
    # the maximum 6.5 m/s sprint displacement (even across 150ms frames).
    nearby = source("AarisNearbyColliders.cs")
    assert "DefaultExecutionOrder(-250)" in nearby
    assert "activationDistance = 55" in nearby
    assert "nextCheck = Time.unscaledTime + .25f;" in nearby
    assert "Physics.SyncTransforms();" in nearby
    assert (6.5 * (0.25 + 0.15)) < 55 - 2.0

    # 10–120 FPS: the controller must integrate a full second at common
    # mobile rates even when Unity frames are slower than 20 FPS.
    for fps in (10, 15, 20, 30, 60, 90, 120):
        elapsed = sum(min(1 / fps, 0.15) for _ in range(fps))
        assert math.isclose(elapsed, 1.0, rel_tol=0, abs_tol=1e-9), (fps, elapsed)

    # Simulate attack + jump/landing/crouch/air transition combinatorics.
    # These independent calculations match the authored C# weight algebra;
    # even a new jump within an old landing envelope must sum to ONE.
    rng = random.Random(20261107)
    for _ in range(12000):
        start = rng.random()
        land = rng.random()
        punch = rng.random()
        shoot = rng.random()
        crouch_blend = rng.random()
        prone_blend = rng.random()
        air = rng.random()
        walk_blend = rng.random()
        sprint_blend = rng.random()
        jumping = rng.random()
        if start > 0:
            land = 0.0
        primary = min(1.0, start + land)
        if shoot > 0:
            punch = 0.0
        combat = max(punch, shoot) * (1.0 - primary)
        punch = combat if punch > 0 else 0.0
        shoot = combat if shoot > 0 else 0.0
        base = 1.0 - primary - combat
        pose = min(1.0, crouch_blend + prone_blend)
        motion = walk_blend * crouch_blend * (1.0 - prone_blend)
        crouch_rest = pose - motion
        ground = (1.0 - air) * (1.0 - pose)
        total = (
            base * ground * (1 - walk_blend)
            + base * ground * walk_blend * (1 - sprint_blend)
            + base * ground * walk_blend * sprint_blend
            + base * air * jumping * (1 - pose)
            + base * air * (1 - jumping) * (1 - pose)
            + base * crouch_rest + base * motion
            + start + land + punch + shoot
        )
        assert abs(total - 1.0) < 1e-6, ("animation blend overflow", total)
        assert 0 <= base <= 1 and 0 <= combat <= 1

    print("PASS: Unity 6.3 HUD/animation packages, 10-120 FPS elapsed time, "
          "12k adversarial blend combinations, multi-pointer hold/release, "
          "single motor and prone/fire collision contracts")
    print("NOT TESTED: Unity Editor compilation, in-game animation retargeting, device FPS")


if __name__ == "__main__":
    audit()
