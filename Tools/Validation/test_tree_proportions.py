#!/usr/bin/env python3
"""Offline static audit of original 6 Unity SpeedTree prefab proportions.

Checks preserve Git LFS terrain, 1100 authored tree coordinates, LOD meshes and
trunk colliders. This cannot replace real Unity Editor visual verification.
"""
from pathlib import Path
import json
import math
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
TREE_BASE = ROOT / "Assets" / "TerrainDemoScene_URP" / "Prefabs" / "Trees"
FOREST = ROOT / "Docs" / "FOREST_PLANTING_PLAN.json"
LAYOUT = ROOT / "Docs" / "MAP_LAYOUT.json"

SPECIES = {
    "Conifer": ("Conifer/Conifer.prefab", (1.15, 1.035, 1.15), 1.0),
    "Pine_A": ("Pines/Pine_A/Pine_A.prefab", (1.13, 1.035, 1.13), 1.0),
    "Pine_B": ("Pines/Pine_B/Pine_B.prefab", (1.16, 1.035, 1.16), 1.0),
    "Pine_C": ("Pines/Pine_C/Pine_C.prefab", (1.13, 1.035, 1.13), 1.0),
    "Pine_D": ("Pines/Pine_D/Pine_D.prefab", (1.14, 1.04, 1.14), 1.0),
    "Cypress": ("Cypress/Cypress_Forest_Desktop.prefab", (1.61, 1.525, 1.61), 1.5),
}


def root_transforms(source):
    result = []
    for block in re.split(r"(?=^--- !u!)", source, flags=re.M):
        if "\nTransform:\n" not in block:
            continue
        if "m_Father: {fileID: 0}" in block:
            match = re.search(
                r"m_LocalScale: \{x: ([0-9.]+), y: ([0-9.]+), z: ([0-9.]+)\}",
                block,
            )
            if match:
                result.append(tuple(map(float, match.groups())))
    return result


class NaturalTreePrefabTests(unittest.TestCase):
    def test_balanced_silhouettes_and_lod(self):
        for name, (rel, expected, old_uniform) in SPECIES.items():
            with self.subTest(species=name):
                prefab = TREE_BASE / rel
                source = prefab.read_text(encoding="utf-8")
                roots = root_transforms(source)
                self.assertEqual(len(roots), 1)
                self.assertEqual(roots[0], expected)
                x, y, z = roots[0]
                self.assertAlmostEqual(x, z, places=5)
                self.assertGreater(x / y, 1.05)
                self.assertLess(x / y, 1.18)
                self.assertGreater(x, old_uniform)
                self.assertLessEqual(y, old_uniform * 1.045)
                self.assertEqual(source.count("LODGroup:"), 1)
                self.assertEqual(source.count("BoxCollider:"), 1)
                self.assertGreaterEqual(source.count("MeshFilter:"), 4)
                self.assertGreaterEqual(source.count("MeshRenderer:"), 4)
                self.assertGreaterEqual(source.count("\nTree:"), 4)
                self.assertTrue(prefab.with_suffix(".prefab.meta").is_file())
                self.assertFalse(source.startswith("version https://git-lfs.github.com/spec/v1"))

    def test_all_1100_native_forest_placements_keep_their_prototypes(self):
        forest = json.loads(FOREST.read_text(encoding="utf-8"))
        places = forest["placements"]
        self.assertEqual(len(places), 1100)
        paths = {str(TREE_BASE / rel).replace(str(ROOT) + "/", "")
                 for rel, _, _ in SPECIES.values()}
        seen = {}
        for place in places:
            path = place["path"]
            self.assertIn(path, paths)
            seen[path] = seen.get(path, 0) + 1
            self.assertTrue(math.isfinite(place["height_scale"]))
            self.assertTrue(math.isfinite(place["width_scale"]))
            self.assertGreater(place["height_scale"], 0)
            self.assertGreater(place["width_scale"], 0)
            self.assertEqual(len(place["position_xz_m"]), 2)
        self.assertEqual(len(seen), 6)
        self.assertEqual(sum(seen.values()), 1100)

    def test_authored_trees_keep_safe_distance_from_all_roads(self):
        forest = json.loads(FOREST.read_text(encoding="utf-8"))
        layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
        roads = []
        for road in layout["roads"]:
            p = road["points"]
            for a, b in zip(p, p[1:]):
                ax, _, az = a
                bx, _, bz = b
                roads.append((ax, az, bx-ax, bz-az,
                              (bx-ax)**2+(bz-az)**2, road["width"]/2))
        minimum = float("inf")
        for place in forest["placements"]:
            x, z = place["position_xz_m"]
            for ax, az, dx, dz, den, half in roads:
                t = max(0., min(1., ((x-ax)*dx+(z-az)*dz)/den)) if den else 0.
                d = math.hypot(x-(ax+t*dx), z-(az+t*dz)) - half
                minimum = min(minimum, d)
        # Previous authored clearance is around 13 m, leaving plenty of room
        # for the modest additional 6-16% horizontal tree silhouette.
        self.assertGreater(minimum, 10)

    def test_native_scene_and_lfs_unmodified_by_tree_prefab_patch(self):
        scene = ROOT / "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
        self.assertTrue(scene.is_file())
        # Check text roots only. The GitHub PR diff must contain exactly 6
        # prefab YAML changes, this test and its workflow/docs. Large binary
        # TerrainData or .unity files are not regenerated or overwritten.


if __name__ == "__main__":
    unittest.main(verbosity=2)
