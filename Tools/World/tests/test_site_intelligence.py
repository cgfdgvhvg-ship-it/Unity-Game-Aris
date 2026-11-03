"""Synthetic contracts for site intelligence and foreground core watching.

No licensed Unity Editor is needed for these deterministic unit tests.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from site_intelligence import site_summary, _direction
from site_watcher import SiteWatcher, file_inventory, changed_paths
from patching import observation_requests
from unity_data import WorldError


def observation(x=0.0):
    return {
        "center_world_m": [0, 2, 0], "radius_m": 40,
        "target": {"id": None, "kind": "coordinate", "world_position_m": [0, 2, 0]},
        "terrain_relation": {"samples": [{"height_m": 1.5}], "point_minus_ground_m": .5},
        "grass_detail_context": {"status": "available"},
        "terrain_under_footprint": {"status": "not_requested"},
        "nearby_scene_objects": [{
            "id": "scene:abc:1", "name": "FrontDoor", "components": ["MeshRenderer"],
            "semantic": {"primary_role": "door", "confidence": .99, "status": "labelled"},
            "world_position_m": [x + 3, 2, 1], "relative_m": [x + 3, 0, 1],
            "distance_m": 3.2 + x, "distance_to_bounds_m": 2.8 + x,
            "world_axis_scale": [1, 1, 1],
            "bounds": {"size_m": [1, 2, .2]}, "bounds_source": "renderer_mesh_aabb",
            "appearance": {"material_slots": [{
                "node_id": "scene:abc:1", "node_name": "FrontDoor", "slot_index": 0,
                "material": {"name": "painted_door", "path": "Assets/Wall.mat",
                             "color_properties": [{"property": "_BaseColor", "rgba": [.2, .3, .4, 1]}],
                             "textures": [{"property": "_BaseMap",
                                           "reference": {"path": "Assets/Wall.png"},
                                           "source": {"status": "read"}}]}
            }]},
        }],
        "nearby_native_instances": [{
            "id": "terrain:a:4", "category": "tree", "path": "Assets/Pine.prefab",
            "position_m": [6, 1, -2], "relative_m": [6, -1, -2],
            "width_scale": 1.2, "height_scale": 1.8, "distance_m": 6.4,
            "color": {"rgba8": [255, 255, 255, 255]},
            "prototype_geometry": {"status": "unavailable"},
        }],
        "native_radius_summary": {
            "counts_by_category": {"tree": 42, "rock": 3},
            "scale_ranges": {"tree": {"width_scale_min_max": [1, 2]}},
            "evidence_scope": "all candidates inside radius before pagination",
        },
        "unresolved_serialized_prefab_instances": {"total": 0},
        "coverage": {
            "scene_candidates_total": 1, "native_candidates_total": 45,
            "scene_next_offset": None, "native_next_offset": None,
            "scene_candidates_truncated": False, "native_candidates_truncated": False,
            "scene_shape_bounds_unavailable_count": 0, "skipped_scene_objects": [],
            "inline_scene_objects_indexed": 100, "native_errors": [],
        },
        "source_fingerprint": {"sha256": "abc", "files": []},
    }


class SiteSummaryTests(unittest.TestCase):
    def test_site_reports_semantics_color_direction_and_native_counts(self):
        data = site_summary(observation())
        self.assertEqual(data["scene"]["nearest_by_role_on_page"]["door"]["distance_m"], 2.8)
        self.assertEqual(data["scene"]["objects_on_page"][0]["direction_world_xz"], "+X")
        surfaces = data["scene"]["objects_on_page"][0]["material_surfaces"]
        self.assertEqual(surfaces[0]["serialized_rgba"][0]["rgba"], [.2, .3, .4, 1])
        self.assertEqual(data["native"]["counts_by_category_in_full_radius"]["tree"], 42)
        self.assertEqual(data["native"]["instances_on_page"][0]["direction_world_xz"], "+X")
        self.assertFalse(data["coverage"]["can_assert_no_other_serialized_obstacles"])
        self.assertTrue(data["coverage"]["serialized_candidate_coverage_complete"])
        self.assertIn("not UV/shader/lighted surface colors", data["interpretation"]["colors"])

    def test_truncated_scene_or_missing_geometry_never_means_empty(self):
        item = observation()
        item["coverage"]["scene_next_offset"] = 100
        item["coverage"]["scene_shape_bounds_unavailable_count"] = 2
        item["unresolved_serialized_prefab_instances"]["total"] = 1
        data = site_summary(item)
        self.assertFalse(data["coverage"]["can_assert_no_other_serialized_obstacles"])
        self.assertEqual(data["coverage"]["scene_next_offset"], 100)
        self.assertTrue(data["coverage"]["nearest_roles_are_page_scoped"])

    def test_global_direction_coordinate_basis(self):
        self.assertEqual(_direction([0, 0, 7]), "+Z")
        self.assertEqual(_direction([-9, 1, 0]), "-X")
        self.assertEqual(_direction([0, 0, 0]), "overlapping_xz")


class ObservationContractTests(unittest.TestCase):
    def test_explicit_queries_augment_automatic_queries(self):
        q = {"operations": [{"op": "set_transform", "target": "scene:abc:10",
                              "world_position": [1, 2, 3]}],
             "observe_after": [{"x": 90, "z": 50, "radius": 10}]}
        rows = observation_requests(q)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["x"], 90)
        self.assertTrue(any(item.get("target") == "scene:abc:10" for item in rows))
        self.assertTrue(any(item.get("x") == 1 for item in rows))

    def test_shared_material_users_generate_bounded_observations(self):
        class FakeWorld:
            guid_paths = {"f" * 32: "Assets/Wall.mat"}
            docs = {1: {"kind": "MeshRenderer", "data": {
                "m_GameObject": {"fileID": 101},
                "m_Materials": [{"fileID": 2100000, "guid": "f" * 32, "type": 2}]}}}
            gos = {101: {"m_Name": "Wall"}}
            go_transform = {101: 102}
            def stable_id(self, go):
                return "scene:abc:" + str(go)
        q = {"operations": [{"op": "set_material_color", "path": "Assets/Wall.mat",
                              "file_id": 2100000, "property": "_BaseColor",
                              "rgba": [1, 0, 0, 1]}]}
        self.assertEqual(observation_requests(q, FakeWorld())[0]["target"], "scene:abc:101")

    def test_shared_material_large_usage_is_sampled_not_rejected(self):
        class ManyUsers:
            guid_paths = {"f" * 32: "Assets/Wall.mat"}
            docs = {
                i: {"kind": "MeshRenderer", "data": {
                    "m_GameObject": {"fileID": i},
                    "m_Materials": [{"fileID": 2100000, "guid": "f" * 32, "type": 2}]}}
                for i in range(101, 181)
            }
            gos = {i: {"m_Name": "Wall"} for i in range(101, 181)}
            go_transform = {i: i + 1000 for i in range(101, 181)}
            def stable_id(self, go):
                return "scene:abc:" + str(go)
        q = {"operations": [{"op": "set_material_color", "path": "Assets/Wall.mat"}]}
        rows = observation_requests(q, ManyUsers())
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["target"], "scene:abc:101")
        self.assertGreater(int(rows[-1]["target"].split(":")[-1]), 170)

    def test_over_budget_observations_fail_without_dropping_user_requests(self):
        q = {"operations": [], "observe_after": [
            {"x": i, "z": 0, "radius": 1} for i in range(33)]}
        with self.assertRaises(WorldError):
            observation_requests(q)


class WatcherTests(unittest.TestCase):
    def test_watch_reload_after_local_file_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            mat = root / "Assets" / "Test.mat"
            mat.write_text("old")
            old = observation()
            newer = observation(2)
            with patch("site_watcher.World", return_value=object()), patch(
                "site_watcher.inspect", side_effect=[old, newer]
            ):
                watch = SiteWatcher(root, {"x": 0, "z": 0, "radius": 40})
                self.assertIsNone(watch.check())
                mat.write_text("new material contents")
                event = watch.check()
            self.assertEqual(event["event"], "core_files_changed")
            self.assertEqual(event["files"][0]["path"], "Assets/Test.mat")
            self.assertEqual(event["files"][0]["event"], "modified")
            self.assertEqual(event["current_site"]["scene"]["objects_on_page"][0]["position_m"], [5, 2, 1])
            self.assertIn("scene:abc:1", event["observation_deltas"][0]["scene_neighbour_distance_changes_m"])
    
    def test_inventory_detects_created_and_deleted_meta(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            a = file_inventory(root)
            (root / "Assets" / "Test.prefab.meta").write_text("guid: test")
            b = file_inventory(root)
            self.assertEqual(changed_paths(a, b), ["Assets/Test.prefab.meta"])
            (root / "Assets" / "Test.prefab.meta").unlink()
            self.assertEqual(changed_paths(b, file_inventory(root)), ["Assets/Test.prefab.meta"])


if __name__ == "__main__":
    unittest.main()
