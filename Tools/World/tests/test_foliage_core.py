"""Reject asset drift and unrelated scene changes across the foliage migration."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Tools/World'))
from foliage_core import CONTRACT,SCENE,sha,restore_foliage_additions

class FoliageMigrationProof(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.old=b'%YAML 1.1\n--- !u!1 &1\nGameObject:\n  m_Name: Existing\n'
  self.root_before=b'--- !u!1660057539 &2\nSceneRoots:\n  m_Roots: []\n'
  self.root_after=b'--- !u!1660057539 &2\nSceneRoots:\n  m_Roots:\n  - {fileID: 4}\n'
  self.added=b'--- !u!1 &3\nGameObject:\n  m_Name: Bush\n--- !u!4 &4\nTransform:\n  m_LocalPosition: {x: 1, y: 0, z: 2}\n'
  from foliage_core import blocks,identity
  self.source=self.old+self.root_after+self.added
  self.asset='Assets/AarisWorld/Foliage/Test.asset'
  self.contract={'before_scene_sha256':sha(self.old+self.root_before),'after_scene_sha256':sha(self.source),'scene_meta_sha256':sha(b'meta'),'asset_sha256':{self.asset:sha(b'mesh')},'added_blocks':{identity(b):sha(b) for b in blocks(self.added) if b},'replaced_blocks':{'2':{'after_sha256':sha(self.root_after),'before_utf8':self.root_before.decode()}}}
  for p,b in ((self.asset,b'mesh'),(SCENE+'.meta',b'meta')):
   target=self.root/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
  self.save()
 def save(self):
  p=self.root/CONTRACT;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(self.contract))
 def test_exact_legacy_scene_restored(self):
  self.assertEqual(restore_foliage_additions(self.root,self.source),self.old+self.root_before)
 def test_saved_mesh_mutation_rejected(self):
  (self.root/self.asset).write_bytes(b'other geometry')
  self.assertIsNone(restore_foliage_additions(self.root,self.source))
 def test_bush_transform_mutation_rejected(self):
  self.assertIsNone(restore_foliage_additions(self.root,self.source.replace(b'x: 1',b'x: 2')))
 def test_scene_identity_mutation_rejected(self):
  (self.root/(SCENE+'.meta')).write_bytes(b'new guid')
  self.assertIsNone(restore_foliage_additions(self.root,self.source))
 def test_unrelated_scene_change_rejected_even_with_updated_after_hash(self):
  changed=self.source.replace(b'Existing',b'Relocated')
  self.contract['after_scene_sha256']=sha(changed);self.save()
  self.assertIsNone(restore_foliage_additions(self.root,changed))
 def test_root_change_rejected_even_with_updated_after_hash(self):
  changed=self.source.replace(b'fileID: 4',b'fileID: 9')
  self.contract['after_scene_sha256']=sha(changed);self.save()
  self.assertIsNone(restore_foliage_additions(self.root,changed))
 def test_actual_saved_map_and_asset_contract(self):
  if (ROOT/CONTRACT).exists():
   c=json.loads((ROOT/CONTRACT).read_text());self.assertEqual(c['bush_count'],96);self.assertEqual(c['cluster_count'],19)
   self.assertIsNotNone(restore_foliage_additions(ROOT,(ROOT/SCENE).read_bytes()))

if __name__=='__main__':unittest.main()
