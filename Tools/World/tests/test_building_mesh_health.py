"""Regressions for native LFS geometry triage. No Unity instance required."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

SOURCE = Path(__file__).resolve().parents[2] / "Validation/check_building_mesh_health.py"
spec = importlib.util.spec_from_file_location("mesh_health", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BOUNDS = {"m_Center": {"x": .5, "y": 0, "z": .5},
          "m_Extent": {"x": .5, "y": 0, "z": .5}}


def sample_mesh():
    vertices = np.zeros((3, 12), dtype="<f4")
    vertices[:, :3] = [[0, 0, 0], [1, 0, 0], [0, 0, 1]]
    vertices[:, 3:6] = [0, 1, 0]
    vertices[:, 6:10] = [1, 0, 0, 1]
    vertices[:, 10:12] = [[0, 0], [1, 0], [0, 1]]
    indices = np.array([0, 1, 2], dtype="<u4")
    return """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!43 &4300000
Mesh:
  m_Name: test
  m_IndexFormat: 1
  m_IndexBuffer: "__IX__"
  m_SubMeshes:
  - firstByte: 0
    indexCount: 3
    topology: 0
    baseVertex: 0
    localAABB: &bound
      m_Center: {x: 0.5, y: 0, z: 0.5}
      m_Extent: {x: 0.5, y: 0, z: 0.5}
  m_LocalAABB: *bound
  m_VertexData:
    m_VertexCount: 3
    m_DataSize: 144
    m_Channels:
    - {stream: 0, offset: 0, format: 0, dimension: 3}
    - {stream: 0, offset: 12, format: 0, dimension: 3}
    - {stream: 0, offset: 24, format: 0, dimension: 4}
    - {stream: 0, offset: 0, format: 0, dimension: 0}
    - {stream: 0, offset: 40, format: 0, dimension: 2}
    _typelessdata: "__VX__"
""".replace("__IX__", indices.tobytes().hex()).replace("__VX__", vertices.tobytes().hex())


class MeshTests(unittest.TestCase):
    def test_normal_native_mesh(self):
        r = mod.inspect_mesh(sample_mesh(), BOUNDS, 1, 1)
        self.assertEqual((r["triangles"], r["submeshes"]), (1, 1))

    def test_lfs_pointer_not_geometry(self):
        with self.assertRaisesRegex(mod.MeshHealthError, "LFS pointer"):
            mod.inspect_mesh("version https://git-lfs.github.com/spec/v1\n", BOUNDS)

    def test_broken_triangle_index(self):
        bad = sample_mesh().replace("000000000100000002000000",
                                    "000000000100000006000000")
        with self.assertRaisesRegex(mod.MeshHealthError, "out of vertex range"):
            mod.inspect_mesh(bad, BOUNDS)

    def test_empty_reserved_material_slot_is_valid(self):
        original = sample_mesh()
        empty = """  - firstByte: 12
    indexCount: 0
    topology: 0
    baseVertex: 0
    localAABB: *bound
"""
        expanded = original.replace("  m_LocalAABB: *bound", empty + "  m_LocalAABB: *bound")
        report = mod.inspect_mesh(expanded, BOUNDS, 1, 2)
        self.assertEqual(report["empty_submeshes"], [1])
        self.assertEqual(report["triangles"], 1)

    def test_triangle_count_may_decrease_when_door_is_cut(self):
        r = mod.inspect_mesh(sample_mesh(), BOUNDS, 2)
        self.assertEqual(r["triangles_removed_since_layout"], 1)

    def test_triangle_count_must_not_increase_over_original(self):
        with self.assertRaisesRegex(mod.MeshHealthError, "triangle count"):
            mod.inspect_mesh(sample_mesh(), BOUNDS, 0)

    def test_material_slot_drift(self):
        with self.assertRaisesRegex(mod.MeshHealthError, "material/submesh"):
            mod.inspect_mesh(sample_mesh(), BOUNDS, 1, 2)

    def test_mesh_bounds_outside_layout(self):
        too_small = {"m_Center": {"x": 0, "y": 0, "z": 0},
                     "m_Extent": {"x": .1, "y": 0, "z": .1}}
        with self.assertRaisesRegex(mod.MeshHealthError, "original model bounds"):
            mod.inspect_mesh(sample_mesh(), too_small, 1, 1)


if __name__ == "__main__":
    unittest.main()
