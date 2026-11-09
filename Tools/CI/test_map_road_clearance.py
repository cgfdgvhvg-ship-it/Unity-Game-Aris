#!/usr/bin/env python3
"""Blueprint road/garage clearance boundary tests; no Unity or LFS needed."""
import json
import unittest
from pathlib import Path
from map_static_check import ROOT, check, segment_intersects_aabb_xz


class RoadAndGarageClearance(unittest.TestCase):
    def test_crossing_road_centerline(self):
        self.assertTrue(segment_intersects_aabb_xz(
            [-10, 0, 0], [10, 0, 0], [-2, -2, 2, 2]))

    def test_distant_road_does_not_touch(self):
        self.assertFalse(segment_intersects_aabb_xz(
            [-10, 0, 8], [10, 0, 8], [-2, -2, 2, 2], 3))

    def test_buffer_reaches_road_edge(self):
        a, b, box = [-10, 0, 8], [10, 0, 8], [-2, -2, 2, 2]
        self.assertTrue(segment_intersects_aabb_xz(a, b, box, 6))
        self.assertFalse(segment_intersects_aabb_xz(a, b, box, 5.9))

    def test_zero_length_segment(self):
        self.assertTrue(segment_intersects_aabb_xz(
            [0, 0, 0], [0, 0, 0], [-1, -1, 1, 1]))
        self.assertFalse(segment_intersects_aabb_xz(
            [10, 0, 10], [10, 0, 10], [-1, -1, 1, 1]))

    def test_diagonal_miss_and_hit(self):
        box = [-2, -2, 2, 2]
        self.assertFalse(segment_intersects_aabb_xz(
            [3, 0, 9], [9, 0, 3], box))
        self.assertTrue(segment_intersects_aabb_xz(
            [-8, 0, -8], [8, 0, 8], box))

    def test_synthetic_vehicle_exit_blocked(self):
        house = [-3, -3, 3, 3]
        self.assertTrue(segment_intersects_aabb_xz(
            [0, 0, -9], [0, 0, 9], house, 1))

    def test_saved_59_house_39_road_45_spawn_layout(self):
        layout = json.loads((ROOT / "Docs/MAP_LAYOUT.json").read_text())
        result = check(layout)
        self.assertEqual(result["result"], "passed")
        self.assertTrue(result["checks"]["roads_clear_of_buildings_with_one_metre_edge_guard"]["passed"])
        self.assertTrue(result["checks"]["garage_vehicle_exit_routes_clear_of_buildings"]["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
