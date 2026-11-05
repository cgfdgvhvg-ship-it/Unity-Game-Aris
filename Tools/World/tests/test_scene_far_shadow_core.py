"""Exact static audit for native Unity scene far-LOD shadow core edit.

No performance, rendering, or Android FPS results are inferred from this test.
"""
from pathlib import Path
import json
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"Tools/World"))
from verify_tree_house_upgrade import (
    SCENE_MOBILE_LOD_PATH,restore_reviewed_scene_far_shadow,
    preserved_or_reviewed_lod_only
)


class SceneFarShadowCoreTests(unittest.TestCase):
    def test_full_map_101_groups_far_shadows_only(self):
        source=(ROOT/SCENE_MOBILE_LOD_PATH).read_bytes()
        blocks=re.split(rb'(?=^--- !u!)',source,flags=re.M)
        meshes={}
        groups=[]
        for block in blocks:
            m=re.match(rb'--- !u!23 &(\d+)\nMeshRenderer:\n',block)
            if m:
                self.assertNotIn(m[1],meshes)
                meshes[m[1]]=block
            if re.match(rb'--- !u!205 &',block):
                groups.append(block)
        self.assertEqual(len(groups),101)
        self.assertEqual(len(meshes),522)
        seen=set()
        for group in groups:
            ids=re.findall(rb'- renderer: \{fileID: (\d+)\}',group)
            self.assertEqual(len(ids),3)
            self.assertEqual(len(set(ids)),3)
            shadow_flags=[]
            for i,ident in enumerate(ids):
                self.assertIn(ident,meshes)
                self.assertNotIn(ident,seen)
                seen.add(ident)
                m=re.findall(rb'^  m_CastShadows: (\d+)\n',meshes[ident],flags=re.M)
                self.assertEqual(len(m),1)
                shadow_flags.append(int(m[0]))
            self.assertEqual(shadow_flags,[1,1,0])
        self.assertEqual(len(seen),303)
        self.assertEqual(sum(b'  m_CastShadows: 0\n' in block for block in meshes.values()),101)

    def test_exact_hash_proves_no_other_scene_bytes_changed(self):
        contract=json.loads((ROOT/"Tools/World/tree-house-20261103.postconditions.json").read_text())
        expected=contract["preserved_files"][SCENE_MOBILE_LOD_PATH]
        self.assertTrue(preserved_or_reviewed_lod_only(ROOT,SCENE_MOBILE_LOD_PATH,expected))
        source=(ROOT/SCENE_MOBILE_LOD_PATH).read_bytes()
        restored=restore_reviewed_scene_far_shadow(source)
        self.assertIsNotNone(restored)
        self.assertEqual(len(restored),len(source))
        self.assertEqual(restored.count(b"  m_CastShadows: 0\n"),0)


if __name__=="__main__":unittest.main()
