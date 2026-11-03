"""Regression coverage for semantic, appearance, prefab and change evidence."""
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_world import fixture, GUID
from unity_data import BUILTIN_MESH_GUID, SCENE, World, digest
from semantics import describe
from observations import inspect
from patching import apply_yaml
from terrain import color_record


class SemanticContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def add_door(self):
        texture = self.root / "Assets/DoorColor.png"
        Image.new("RGB", (4, 4), (64, 96, 128)).save(texture)
        Path(str(texture)+".meta").write_text("fileFormatVersion: 2\nguid: " + "5"*32 + "\n")
        script = self.root / "Assets/DoorLogic.cs"
        script.write_text("public class DoorLogic { public void OpenDoor() {} private void Update() {} }\n")
        Path(str(script)+".meta").write_text("fileFormatVersion: 2\nguid: " + "6"*32 + "\n")
        material = self.root / "Assets/Test.mat"
        material.write_text(material.read_text() +
            "    m_TexEnvs:\n"
            "    - _BaseMap:\n"
            "        m_Texture: {fileID: 2800000, guid: " + "5"*32 + ", type: 3}\n"
            "        m_Scale: {x: 1, y: 1}\n"
            "        m_Offset: {x: 0, y: 0}\n")
        scene = self.root / SCENE
        scene.write_text(scene.read_text() +
            "--- !u!1 &400\nGameObject:\n  m_Name: FrontDoorRed\n  m_IsActive: 1\n  m_Component:\n"
            "  - component: {fileID: 401}\n  - component: {fileID: 402}\n  - component: {fileID: 403}\n  - component: {fileID: 404}\n"
            "--- !u!4 &401\nTransform:\n  m_GameObject: {fileID: 400}\n  m_Father: {fileID: 201}\n"
            "  m_LocalPosition: {x: 0, y: 1, z: 0}\n  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}\n"
            "  m_LocalScale: {x: 1, y: 2, z: 0.2}\n  m_Children: []\n"
            "--- !u!33 &402\nMeshFilter:\n  m_GameObject: {fileID: 400}\n"
            f"  m_Mesh: {{fileID: 10202, guid: {BUILTIN_MESH_GUID}, type: 0}}\n"
            "--- !u!23 &403\nMeshRenderer:\n  m_GameObject: {fileID: 400}\n  m_Materials:\n"
            "  - {fileID: 2100000, guid: " + "2"*32 + ", type: 2}\n"
            "--- !u!114 &404\nMonoBehaviour:\n  m_GameObject: {fileID: 400}\n  m_Enabled: 1\n"
            "  m_Script: {fileID: 11500000, guid: " + "6"*32 + ", type: 3}\n  opensWhenNear: 1\n  interactionRadius: 2.5\n")

    def test_describe_binds_semantic_part_material_slot_texture_and_dimensions(self):
        self.add_door(); w = World(self.root)
        report = describe(w, {"target": f"scene:{GUID}:200", "texture_analysis": True,
                              "offset": 0, "limit": 20, "dependency_depth": 3})
        door = next(row for row in report["parts"]["items"] if row["name"] == "FrontDoorRed")
        self.assertEqual(door["semantic"]["primary_role"], "door")
        self.assertEqual(door["semantic"]["status"], "labelled")
        self.assertEqual(door["material_slots"][0]["slot_index"], 0)
        stats = door["material_slots"][0]["material"]["textures"][0]["source"]["source_color_statistics"]
        self.assertEqual(stats["mean_srgb8"], [64.0, 96.0, 128.0])
        self.assertGreater(report["target"]["dimensions"]["height_m"], 0)
        self.assertTrue(any(node["path"] == "Assets/DoorColor.png" for node in report["dependencies"]["nodes"]))
        self.assertFalse(report["appearance"]["rendered_pixels"])
        self.assertEqual(report["logic"]["binding_count"], 1)
        self.assertEqual(report["logic"]["bindings"][0]["serialized_fields"]["interactionRadius"], 2.5)
        self.assertIn("OpenDoor", report["logic"]["bindings"][0]["source_summary"]["methods"])

    def test_stripped_imported_transform_is_reported_instead_of_crashing(self):
        model = self.root / "Assets/Rock.fbx"
        model.write_text("version https://git-lfs.github.com/spec/v1\n")
        Path(str(model)+".meta").write_text("fileFormatVersion: 2\nguid: " + "9"*32 + "\n")
        scene = self.root / SCENE
        scene.write_text(scene.read_text() +
            "--- !u!1001 &900\nPrefabInstance:\n  m_Modification:\n    m_TransformParent: {fileID: 0}\n"
            "    m_Modifications:\n"
            "    - target: {fileID: 400000, guid: " + "9"*32 + ", type: 3}\n      propertyPath: m_LocalPosition.x\n      value: 12\n      objectReference: {fileID: 0}\n"
            "    - target: {fileID: 400000, guid: " + "9"*32 + ", type: 3}\n      propertyPath: m_LocalPosition.y\n      value: 3\n      objectReference: {fileID: 0}\n"
            "    - target: {fileID: 400000, guid: " + "9"*32 + ", type: 3}\n      propertyPath: m_LocalPosition.z\n      value: -4\n      objectReference: {fileID: 0}\n"
            "  m_SourcePrefab: {fileID: 100100000, guid: " + "9"*32 + ", type: 3}\n"
            "--- !u!4 &901 stripped\nTransform:\n  m_CorrespondingSourceObject: {fileID: 400000, guid: " + "9"*32 + ", type: 3}\n"
            "  m_PrefabInstance: {fileID: 900}\n  m_PrefabAsset: {fileID: 0}\n")
        world = World(self.root)
        self.assertEqual(world.unbound_transform_documents, [901])
        instance = world.prefab_instances()[0]
        self.assertEqual(instance["source"]["path"], "Assets/Rock.fbx")
        self.assertEqual(instance["source"]["status"], "lfs_pointer")
        self.assertEqual(instance["instance_transform"]["world_position_m"], [12.0, 3.0, -4.0])

    def test_inspect_pages_scene_candidates_without_claiming_page_is_complete(self):
        world = World(self.root)
        first = inspect(world, {"x": 0, "y": 0, "z": 0, "radius": 100, "limit": 1,
                                "scene_offset": 0, "native": False, "geometry": False,
                                "appearance": False, "semantics": False})
        second = inspect(world, {"x": 0, "y": 0, "z": 0, "radius": 100, "limit": 1,
                                 "scene_offset": 1, "native": False, "geometry": False,
                                 "appearance": False, "semantics": False})
        self.assertNotEqual(first["nearby_scene_objects"][0]["id"], second["nearby_scene_objects"][0]["id"])
        self.assertEqual(first["coverage"]["scene_next_offset"], 1)
        self.assertGreater(first["coverage"]["scene_candidates_total"], first["coverage"]["scene_candidates_returned"])

    def test_apply_returns_exact_files_operation_states_and_observation_delta(self):
        patch = {"schema_version": 2, "transaction_id": "semantic-change-0001",
                 "idempotency_key": "semantic-change-0001", "reason": "Measure a selected house move",
                 "expected_files": {p: digest(self.root/p) for p in (SCENE, SCENE+".meta")},
                 "operations": [{"id": "move-house", "op": "set_transform",
                                 "target": f"scene:{GUID}:200", "world_position": [11, 2, 26]}]}
        result = apply_yaml(self.root, patch, True)
        self.assertIn(SCENE, result["written_file_changes"])
        self.assertNotEqual(result["written_file_changes"][SCENE]["before_sha256"],
                            result["written_file_changes"][SCENE]["after_sha256"])
        self.assertTrue(result["operation_deltas"][0]["changed"])
        for actual, expected in zip(result["operation_after"][0]["state"]["world_position_m"], [11.0, 2.0, 26.0]):
            self.assertAlmostEqual(actual, expected)
        self.assertTrue(result["pre_edit_observations"])
        for actual, expected in zip(result["observation_deltas"][0]["target_position_delta_m"], [2.0, 0.0, -2.0]):
            self.assertAlmostEqual(actual, expected)

    def test_native_colors_preserve_serialized_and_normalized_values(self):
        self.assertEqual(color_record({"r": 64, "g": 128, "b": 255, "a": 255})["normalized_rgba"],
                         [64/255, 128/255, 1.0, 1.0])
        self.assertEqual(color_record({"r": .2, "g": .3, "b": .4, "a": 1})["encoding"], "float_0_1")


if __name__ == "__main__":
    unittest.main()
