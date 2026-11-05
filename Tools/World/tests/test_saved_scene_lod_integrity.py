"""Exact scene-integrity proof for 47 residential and 32 rock-cover LOD groups.

These checks validate serialized YAML only, not rendered image quality or Android FPS.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'Tools/World'))
from verify_tree_house_upgrade import SCENE_MOBILE_LOD_PATH, restore_scene_mobile_lod


class SavedSceneMobileLodIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from foliage_core import restore_foliage_additions
        cls.scene = restore_foliage_additions(ROOT, (ROOT / SCENE_MOBILE_LOD_PATH).read_bytes())
        assert cls.scene is not None, "Unreviewed foliage/scene change"
        cls.contract = json.loads(
            (ROOT / 'Tools/World/tree-house-20261103.postconditions.json').read_text()
        )

    def test_exact_original_scene_restored_by_only_reviewed_lod_changes(self):
        original = restore_scene_mobile_lod(self.scene)
        self.assertIsNotNone(original, 'Unexpected scene LOD counts, identities or thresholds')
        expected = self.contract['preserved_files'][SCENE_MOBILE_LOD_PATH]
        self.assertEqual(hashlib.sha256(original).hexdigest(), expected)
        self.assertEqual(self.scene.count(b'  - screenRelativeHeight: 0.28\n'), 79)
        self.assertEqual(self.scene.count(b'  - screenRelativeHeight: 0.095\n'), 79)
        self.assertEqual(self.scene.count(b'  - screenRelativeHeight: 0.22\n'), 22)
        self.assertEqual(self.scene.count(b'  - screenRelativeHeight: 0.07\n'), 22)
        self.assertEqual(self.scene.count(b'  - screenRelativeHeight: 0.0025\n'), 101)

    def test_modified_scene_geometry_or_metadata_cannot_pass(self):
        modified = self.scene.replace(b'  m_Fog: 1\n', b'  m_Fog: 0\n', 1)
        self.assertNotEqual(modified, self.scene)
        restored = restore_scene_mobile_lod(modified)
        self.assertIsNotNone(restored)
        expected = self.contract['preserved_files'][SCENE_MOBILE_LOD_PATH]
        self.assertNotEqual(hashlib.sha256(restored).hexdigest(), expected)

    def test_unexpected_threshold_fails_closed(self):
        changed = self.scene.replace(
            b'  - screenRelativeHeight: 0.28\n',
            b'  - screenRelativeHeight: 0.29\n', 1
        )
        self.assertNotEqual(changed, self.scene)
        self.assertIsNone(restore_scene_mobile_lod(changed))


if __name__ == '__main__':
    unittest.main()
