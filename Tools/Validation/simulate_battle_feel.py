#!/usr/bin/env python3
"""Deterministic 30/60/120 FPS tuning contract for Aaris battle movement.

Independent mathematical regression checks. This does NOT execute Unity or
certify PlayerController behavior; Unity playmode and Android device profiling
remain mandatory before merge.
"""
from __future__ import annotations
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOTOR = (ROOT / "Assets/AarisWorld/Scripts/AarisThirdPersonPlayer.cs").read_text("utf-8")
ACTION = (ROOT / "Assets/AarisWorld/Scripts/AarisBattleActions.cs").read_text("utf-8")
VISUAL = (ROOT / "Assets/AarisWorld/Scripts/AarisCharacterVisual.cs").read_text("utf-8")
HUD = (ROOT / "Assets/AarisWorld/Scripts/AarisBattleHUD.cs").read_text("utf-8")
GUN = (ROOT / "Assets/AarisWorld/Scripts/AarisEquippedGun.cs").read_text("utf-8")


def setting(name: str) -> float:
    match = re.search(r"\b" + re.escape(name) + r"\s*=\s*([0-9.]+)f\b", MOTOR)
    if match is None:
        raise AssertionError("Missing numeric tuning constant: " + name)
    return float(match.group(1))


def approach(current: float, target: float, rate: float, dt: float) -> float:
    return min(target, current + rate * dt) if current <= target else max(target, current - rate * dt)


def jump(fps: int, release_after_seconds: float | None) -> tuple[float, float]:
    gravity = setting("gravity")
    jump_height = setting("jumpHeight")
    extra = setting("earlyJumpReleaseGravity")
    v = math.sqrt(2 * gravity * jump_height)
    y = apex = 0.0
    dt = 1.0 / fps
    for i in range(fps * 3):
        t = i * dt
        airborne_gravity = gravity * (extra if v > 0 and release_after_seconds is not None
                                     and t >= release_after_seconds else 1.0)
        v = max(v - airborne_gravity * dt, -40.0)
        y += v * dt
        apex = max(apex, y)
        if y <= 0 and t > 0.08:
            return apex, t + dt
    raise AssertionError("Jump never landed")


def assert_regression() -> None:
    assert setting("unarmedSprintSpeed") == 6.5
    assert setting("armedSprintSpeed") == 5.7
    assert setting("walkSpeed") == 4.2
    assert setting("crouchMoveSpeed") == 2.4
    assert setting("proneMoveSpeed") == 1.1
    assert setting("combatMoveSpeed") == 2.0
    acc = setting("horizontalAcceleration")
    brake = setting("horizontalBraking")

    # Simulated target approach is consistent across mobile refresh rates,
    # including frame-rate-independent velocity convergence.
    for fps in (30, 60, 120):
        dt = 1.0 / fps
        s = 0.0
        for _ in range(math.ceil(0.55 * fps)):
            s = approach(s, 6.5, acc, dt)
        assert 6.49 <= s <= 6.51, (fps, "sprint acceleration", s)
        for _ in range(math.ceil(0.4 * fps)):
            s = approach(s, 0.0, brake, dt)
        assert 0.0 <= s <= 0.01, (fps, "braking", s)

        full_apex, full_time = jump(fps, None)
        short_apex, short_time = jump(fps, 0.10)
        assert 0.79 <= full_apex <= 1.05, (fps, "full jump height", full_apex)
        assert 0.25 <= short_apex < full_apex - 0.13, (fps, "short jump", short_apex)
        assert 0.36 <= short_time < full_time <= 0.75, (fps, "jump timings", short_time, full_time)

    assert MOTOR.count("controller.Move(") == 1, "Duplicate motor/controller update"
    assert "jumpUntil = Time.unscaledTime + 0.17f" in MOTOR
    assert "now - lastGrounded <= 0.11f" in MOTOR
    assert "jumpButtonHeld || Input.GetKey(KeyCode.Space)" in MOTOR
    assert "earlyJumpReleaseGravity" in MOTOR
    assert "Time.deltaTime" in MOTOR and "airborneSteering" in MOTOR
    assert "Physics.SphereCast(" in MOTOR
    assert "CollisionFlags.Below" in MOTOR
    assert "Mathf.SmoothDamp(smoothedEyeHeight" in MOTOR
    assert "player.SetJumpHeld(true)" in HUD and "player.SetJumpHeld(false)" in HUD

    # The headroom query must begin above the old capsule, excluding the
    # TerrainCollider at foot level. No inflation to larger radius on prone.
    assert "currentTop - radius * 0.35f" in ACTION
    assert "floor + radius" in ACTION
    assert "capsule.radius - capsule.skinWidth" in ACTION
    assert "count == nearHits.Length" in ACTION
    assert "HasProneClearance" in ACTION
    assert "Physics.OverlapCapsuleNonAlloc(head, legs" in ACTION
    assert "CanAdvanceProne(candidate, horizontalVelocity)" in MOTOR

    # No melee through cover; no hitscan overflow or behind-cover damage.
    assert "Physics.Raycast(origin, delta.normalized" in ACTION
    assert "if (count >= hits.Length) return false;" in GUN
    assert "Vector3 muzzle" in GUN and "muzzleHit" in GUN

    # Pure visuals must never move gameplay capsule.
    assert "landingCompressionMetres" in VISUAL
    assert "sprintForwardLeanDegrees" in VISUAL
    assert "controller.Move(" not in VISUAL
    assert "animator.applyRootMotion = false" in VISUAL
    print("PASS: 30/60/120 FPS sprint, braking, tap/hold jump arc, coyote/buffer, " +
          "downhill probe, stance clearance, combat occlusion and in-place animation contracts")


if __name__ == "__main__":
    assert_regression()
