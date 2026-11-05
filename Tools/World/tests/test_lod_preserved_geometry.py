"""Strict regression for PR #19: only 2 LOD lines differ from PR #18 protected prefabs.

No Unity/physics/Android rendering is represented by these source tests.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Tools/World'))
from verify_tree_house_upgrade import RESIDENTIAL_MOBILE_LOD_PREFABS,preserved_or_reviewed_lod_only,restore_reviewed_far_shadow


class ReviewedMobileLodIntegrity(unittest.TestCase):
    def test_all_and_only_seven_protected_house_prefabs_have_reviewed_lod_edits(self):
        contract=json.loads((ROOT/'Tools/World/tree-house-20261103.postconditions.json').read_text())
        self.assertEqual(len(RESIDENTIAL_MOBILE_LOD_PREFABS),7)
        for path in sorted(RESIDENTIAL_MOBILE_LOD_PREFABS):
            with self.subTest(prefab=path):
                content=(ROOT/path).read_bytes()
                self.assertEqual(content.count(b'  - screenRelativeHeight: 0.28\n'),1)
                self.assertEqual(content.count(b'  - screenRelativeHeight: 0.095\n'),1)
                self.assertTrue(preserved_or_reviewed_lod_only(ROOT,path,contract['preserved_files'][path]))
                historical=restore_reviewed_far_shadow(content,path)
                self.assertIsNotNone(historical)
                original=(historical.replace(b'  - screenRelativeHeight: 0.28\n',b'  - screenRelativeHeight: 0.22\n')
                    .replace(b'  - screenRelativeHeight: 0.095\n',b'  - screenRelativeHeight: 0.07\n'))
                self.assertEqual(hashlib.sha256(original).hexdigest(),contract['preserved_files'][path])

    def test_unrelated_protected_assets_cannot_be_exempted(self):
        contract=json.loads((ROOT/'Tools/World/tree-house-20261103.postconditions.json').read_text())
        path='Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity.meta'
        self.assertTrue(preserved_or_reviewed_lod_only(ROOT,path,contract['preserved_files'][path]))
        self.assertFalse(preserved_or_reviewed_lod_only(ROOT,path,'0'*64))


if __name__=='__main__':unittest.main()
