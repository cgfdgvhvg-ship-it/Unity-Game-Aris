"""Built-in shapes must remain visible to source neighbourhood inspection."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from observations import inspect
from unity_data import BUILTIN_MESH_GUID, SCENE, World, digest
from test_world import fixture


class BuiltinBoundsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        fixture(self.root)
        self.scene_text = (self.root/SCENE).read_text()

    def tearDown(self):
        self.tmp.cleanup()

    def shape(self, file_id, kind="MeshFilter", guid=BUILTIN_MESH_GUID):
        scene = self.root / SCENE
        text = self.scene_text.replace(
            "  - component: {fileID: 201}\n",
            "  - component: {fileID: 201}\n  - component: {fileID: 202}\n",
        )
        class_id = 33 if kind == "MeshFilter" else 64
        text += (f"--- !u!{class_id} &202\n{kind}:\n"
                 "  m_GameObject: {fileID: 200}\n"
                 f"  m_Mesh: {{fileID: {file_id}, guid: {guid}, type: 0}}\n")
        scene.write_text(text)

    def test_primitives_use_world_scale_rotation_and_preserve_source(self):
        # Parent rotates 90 degrees around Y and scales X/Y/Z by 2/1/3.
        for file_id, expected_size in (
            (10202, [3, 1, 2]), (10206, [3, 2, 2]),
            (10207, [3, 1, 2]), (10208, [3, 2, 2]),
            (10209, [30, 0, 20]), (10210, [0, 1, 2]),
        ):
            with self.subTest(file_id=file_id):
                self.shape(file_id)
                before = {p: digest(self.root/p) for p in (SCENE, SCENE+".meta")}
                record = World(self.root).object(200, True)
                self.assertEqual(record["bounds_incomplete"], [])
                np.testing.assert_allclose(record["renderer_bounds"]["size_m"], expected_size, atol=1e-10)
                np.testing.assert_allclose(
                    np.mean([record["renderer_bounds"]["min_m"], record["renderer_bounds"]["max_m"]], axis=0),
                    [9, 2, 28], atol=1e-10,
                )
                self.assertEqual(before, {p: digest(self.root/p) for p in before})

    def test_far_pivot_sphere_and_capsule_are_neighbours_without_colliders(self):
        for file_id in (10207, 10208):
            with self.subTest(file_id=file_id):
                self.shape(file_id)
                report = inspect(World(self.root), {
                    "x": 10.4, "y": 2, "z": 28, "radius": .1, "native": False,
                })
                row = next(r for r in report["nearby_scene_objects"] if r["id"].endswith(":200"))
                self.assertGreater(row["distance_m"], report["radius_m"])
                self.assertEqual(row["distance_to_bounds_m"], 0)
                self.assertEqual(row["bounds_source"], "renderer_mesh_aabb")
                self.assertEqual(report["coverage"]["scene_shape_bounds_unavailable_count"], 0)
                self.assertFalse(report["coverage"]["physics_tested"])

    def test_builtin_mesh_colliders_resolve_the_same_envelopes(self):
        self.shape(10208, "MeshCollider")
        record = World(self.root).object(200, True)
        self.assertEqual(record["collider_bounds_incomplete"], [])
        np.testing.assert_allclose(record["saved_collider_bounds"]["size_m"], [3, 2, 2], atol=1e-10)
        self.assertIsNone(record["renderer_bounds"])

    def test_unknown_builtin_and_missing_lfs_remain_explicitly_unavailable(self):
        for file_id, guid, reason in ((99999, BUILTIN_MESH_GUID, "unity_builtin"),
                                      (4300000, "4"*32, "lfs_pointer")):
            with self.subTest(reason=reason):
                self.shape(file_id, guid=guid)
                if reason == "lfs_pointer":
                    (self.root/"Assets/Missing.asset").write_text("version https://git-lfs.github.com/spec/v1\n")
                    (self.root/"Assets/Missing.asset.meta").write_text("guid: "+guid+"\n")
                report = inspect(World(self.root), {"x": 9, "y": 2, "z": 28, "native": False})
                self.assertEqual(report["coverage"]["scene_shape_bounds_unavailable_count"], 1)
                unknown = report["coverage"]["scene_shape_bounds_unavailable_sample"][0]
                self.assertIn(reason, " ".join(unknown["reasons"]))
                row = next(r for r in report["nearby_scene_objects"] if r["id"].endswith(":200"))
                self.assertIsNone(row["bounds"])


if __name__ == "__main__":
    unittest.main()
