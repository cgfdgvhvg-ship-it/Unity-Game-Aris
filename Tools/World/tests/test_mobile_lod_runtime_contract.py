"""Source-only regression guards, not a Unity rendering or physics run."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
HOUSES = (
    "a_frame_cabin", "bungalow_house", "detached_two_storey_house",
    "garage_apartment", "pitched_roof_cottage", "row_three_townhouses",
    "two_bedroom_garage_house",
)


class LowRamWorldSourceContracts(unittest.TestCase):
    def test_saved_lods_preserve_distant_level(self):
        paths = [
            ROOT / f"Assets/AarisWorld/Models/{name}/{name}.prefab"
            for name in HOUSES
        ]
        paths.append(ROOT / "Assets/AarisWorld/Props/RockCover/RockCover.prefab")
        for path in paths:
            with self.subTest(prefab=path.name):
                source = path.read_text(encoding="utf-8")
                heights = re.findall(r"^  - screenRelativeHeight: ([0-9.]+)$", source, re.M)
                self.assertEqual(heights, ["0.28", "0.095", "0.0025"])
                self.assertIn("  m_AnimateCrossFading: 1", source)
                self.assertIn("  m_FadeMode: 1", source)

    def test_mobile_detail_caps_are_restorable(self):
        src = (ROOT / "Assets/AarisWorld/Scripts/AarisMobileRuntime.cs").read_text(encoding="utf-8")
        for fragment in (
            "terrainDetailDistanceCap = constrained ? 55f : 80f;",
            "terrainDetailDensityCap = constrained ? 0.58f : 0.78f;",
            "terrain.detailObjectDistance = Mathf.Min(originalDetailDistances[i], terrainDetailDistanceCap);",
            "terrain.detailObjectDensity = Mathf.Min(originalDetailDensities[i], terrainDetailDensityCap);",
            "terrain.detailObjectDistance = originalDetailDistances[i];",
            "terrain.detailObjectDensity = originalDetailDensities[i];",
            "Mathf.Min(currentBudget, Mathf.Max(48f, currentBudget - 32f))",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, src)

    def test_adaptive_grass_uses_sustained_p95_and_preserves_skyline(self):
        src = (ROOT / "Assets/AarisWorld/Scripts/AarisMobileRuntime.cs").read_text(encoding="utf-8")
        for fragment in (
            "adaptDetailsToFrameTime = true;",
            "frameCount < frameTimes.Length || Time.unscaledTime < 15f",
            "p95FrameMs > frameBudgetMs * 1.30f",
            "p95FrameMs < frameBudgetMs * 1.08f",
            "pressureSamples >= 2 && performanceLevel < 2",
            "recoverySamples >= 4 && performanceLevel > 0",
            "nextPerformanceChangeAt = Time.unscaledTime + 12f;",
            "lowMemoryDetailMultiplier = Mathf.Min(lowMemoryDetailMultiplier, 0.75f);",
            "terrainDetailDistanceCap * distanceFactor * lowMemoryDetailMultiplier",
            "terrainDetailDensityCap * densityFactor * lowMemoryDetailMultiplier",
            'if (reason == "sample") TuneForFrameTime(s.p95FrameMs);',
            "effectiveDetailDistanceM, effectiveDetailDensity, lowMemoryDetailMultiplier",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, src)
        # Do not shorten the world horizon to obtain artificially higher FPS.
        self.assertNotIn("farClipPlane =", src)
        self.assertNotIn("treeDistance =", src)

    def test_mobile_distant_tree_lods_keep_visibility_and_restore_every_value(self):
        src = (ROOT / "Assets/AarisWorld/Scripts/AarisMobileRuntime.cs").read_text(encoding="utf-8")
        for fragment in (
            "originalTreeBillboardDistances",
            "originalFullLodTreeCounts",
            "originalHeightmapPixelErrors",
            "originalBasemapDistances",
            "constrained ? 100f : 140f",
            "constrained ? 28 : 44",
            "constrained ? 8f : 6f",
            "constrained ? 400f : 550f",
            "terrain.treeBillboardDistance = originalTreeBillboardDistances[i];",
            "terrain.treeMaximumFullLODCount = originalFullLodTreeCounts[i];",
            "terrain.heightmapPixelError = originalHeightmapPixelErrors[i];",
            "terrain.basemapDistance = originalBasemapDistances[i];",
            "effectiveTreeBillboardDistanceM",
            "effectiveMaxFullLodTrees",
            "effectiveHeightmapPixelError",
            "effectiveBasemapDistanceM",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, src)
        self.assertNotIn("treeDistance =", src)
        self.assertNotIn("farClipPlane =", src)

    def test_fps_switch_resets_samples_and_uses_actual_cap(self):
        src = (ROOT / "Assets/AarisWorld/Scripts/AarisMobileRuntime.cs").read_text(encoding="utf-8")
        player = (ROOT / "Assets/AarisWorld/Scripts/AarisThirdPersonPlayer.cs").read_text(encoding="utf-8")
        self.assertIn("Application.targetFrameRate == 60 ? 30 : 60", player)
        for fragment in (
            "observedTargetFps = Application.targetFrameRate;",
            "int cap = Application.targetFrameRate > 0 ? Application.targetFrameRate : targetFrameRate;",
            "if (cap != observedTargetFps)",
            "Array.Clear(frameTimes, 0, frameTimes.Length);",
            "frameIndex = frameCount = pressureSamples = recoverySamples = 0;",
            "1000f / Mathf.Clamp(observedTargetFps, 30, 120)",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, src)

    def test_explicit_collider_refresh_keeps_physics_queries_current(self):
        src = (ROOT / "Assets/AarisWorld/Scripts/AarisNearbyColliders.cs").read_text(encoding="utf-8")
        self.assertIn("nextCheck) RefreshNow(false);", src)
        self.assertIn("public void RefreshNow() { RefreshNow(true); }", src)
        self.assertIn("if (changedColliders || forceSync) Physics.SyncTransforms();", src)

    def test_collider_manager_recovers_after_reenable(self):
        src = (ROOT / "Assets/AarisWorld/Scripts/AarisNearbyColliders.cs").read_text(encoding="utf-8")
        for fragment in (
            "private void OnEnable()",
            "restoreProximityStateOnEnable = true;",
            "active.Clear();",
            "nextActive.Clear();",
            "if (c is TerrainCollider || c is CharacterController)",
            "if (indexed[i] && obstacles[i] != null) obstacles[i].enabled = false;",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, src)

if __name__ == "__main__":
    unittest.main()
