import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from tree_shapes import apply
from unity_data import digest,documents,WorldError


class TreeShapeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
        self.prefab='Assets/TerrainDemoScene_URP/Prefabs/Trees/Test/Test.prefab';self.meta=self.prefab.replace('.prefab','.st.meta')
        p=self.root/self.prefab;p.parent.mkdir(parents=True)
        p.write_text('%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!1 &1\nGameObject:\n  m_Name: Test\n--- !u!65 &2\nBoxCollider:\n  m_Size: {x: 1, y: 6, z: 1}\n  m_Center: {x: 0, y: 3, z: 0}\n')
        (self.root/(self.prefab+'.meta')).write_text('guid: '+'a'*32+'\n')
        (self.root/self.meta).write_text('guid: '+'b'*32+'\nSpeedTreeImporter:\n  scaleFactor: 0.3048\n  userData: \n')
    def tearDown(self):self.temp.cleanup()
    def patch(self):return {'schema_version':1,'transaction_id':'test-tree-shape-0001',
        'expected_files':{p:digest(self.root/p)for p in (self.prefab,self.prefab+'.meta',self.meta)},
        'profiles':[{'prefab':self.prefab,'source_meta':self.meta,'height_factor':.62,'base_width_factor':1.55,'crown_width_factor':1.12}]}
    def test_source_preview_then_write_keep_guid_and_coordinate_frame(self):
        patch=self.patch();old=(self.root/self.meta).read_bytes();meta=(self.root/(self.prefab+'.meta')).read_bytes()
        self.assertTrue(apply(self.root,patch)['dry_run']);self.assertEqual((self.root/self.meta).read_bytes(),old)
        result=apply(self.root,patch,True);self.assertFalse(result['dry_run'])
        d=documents(self.root/self.prefab)[1][1]['data'];self.assertAlmostEqual(d['m_Size']['y'],3.72)
        self.assertAlmostEqual(d['m_Size']['x'],1.55)
        self.assertIn('aaris-tree-shape-v1|2.5|',(self.root/self.meta).read_text())
        self.assertEqual((self.root/(self.prefab+'.meta')).read_bytes(),meta)
    def test_stale_or_already_authored_profile_is_rejected(self):
        patch=self.patch();apply(self.root,patch,True)
        with self.assertRaises(WorldError):apply(self.root,patch,True)
        patch['expected_files']={p:digest(self.root/p)for p in patch['expected_files']}
        with self.assertRaisesRegex(WorldError,'already authored'):apply(self.root,patch,True)
    def test_invalid_factors_do_not_write(self):
        patch=self.patch();patch['profiles'][0]['height_factor']=0
        with self.assertRaises(WorldError):apply(self.root,patch,True)


if __name__=='__main__':unittest.main()
