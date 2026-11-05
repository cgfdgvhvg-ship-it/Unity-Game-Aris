import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_tree_realism_v2 import (
    MANIFEST,HISTORIC,TreeRealismError,authorized_tree_blobs,verify
)


class NaturalTreeRealismTests(unittest.TestCase):
    ROOT=Path(__file__).resolve().parents[3]

    def test_six_tree_types_match_exact_reviewed_blob_hashes(self):
        result=verify(self.ROOT)
        self.assertEqual(result["approved_files"],12)
        self.assertEqual(len(result["species"]),6)
        self.assertFalse(result["prefab_guids_modified"])
        self.assertFalse(result["speedtree_binary_modified"])

    def test_bases_thicken_but_crowns_change_only_slightly(self):
        report=verify(self.ROOT)
        for row in report["species"]:
            self.assertGreaterEqual(row["base_multiplier"],1.09)
            self.assertLessEqual(row["base_multiplier"],1.13)
            self.assertLessEqual(row["crown_multiplier"],1.04)
            self.assertTrue(row["height_preserved"])
            self.assertTrue(row["collider_active"])
            self.assertEqual(row["lod_count"],4)

    def temp_copy(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        dest=Path(temp.name)
        manifest=json.loads((self.ROOT/MANIFEST).read_text())
        paths=[MANIFEST,HISTORIC,"Assets/AarisWorld/Editor/AarisTreeShapeImporter.cs"]
        for row in manifest["profiles"]:
            paths.extend((row["prefab"],row["source_meta"],row["prefab"]+".meta"))
        for name in paths:
            src=self.ROOT/name
            out=dest/name
            out.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,out)
        return dest,manifest

    def test_unreviewed_tree_prefab_is_rejected(self):
        copy,manifest=self.temp_copy()
        file=copy/manifest["profiles"][0]["prefab"]
        file.write_text(file.read_text().replace("m_Enabled: 1","m_Enabled: 0",1))
        with self.assertRaisesRegex(TreeRealismError,"Unreviewed"):
            authorized_tree_blobs(copy)

    def test_unreviewed_speedtree_import_profile_is_rejected(self):
        copy,manifest=self.temp_copy()
        file=copy/manifest["profiles"][1]["source_meta"]
        file.write_text(file.read_text().replace("aaris-tree-shape-v2","aaris-tree-shape-v1"))
        with self.assertRaisesRegex(TreeRealismError,"Unreviewed"):
            verify(copy)

    def test_prefab_guid_identity_is_unchanged(self):
        copy,manifest=self.temp_copy()
        file=copy/(manifest["profiles"][0]["prefab"]+".meta")
        file.write_text("fileFormatVersion: 2\nguid: 00000000000000000000000000000000\n")
        with self.assertRaisesRegex(TreeRealismError,"GUID changed"):
            verify(copy)


if __name__=="__main__":
    unittest.main()
