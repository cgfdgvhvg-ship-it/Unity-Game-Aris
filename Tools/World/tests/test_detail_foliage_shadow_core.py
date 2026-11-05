"""Assert only five original foliage core prefabs changed one shadow flag."""
from pathlib import Path
import hashlib
import re
import unittest

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/"Assets/TerrainDemoScene_URP/Prefabs/Details"
APPROVED={
 "Fern_A":"6403215db0728e979eb737abf4f1d7c84009f4d4",
 "Fern_B":"e84b028b62cc8aff42db8f358051b7a2837876d9",
 "Fern_C":"58f12f29b5b5bd07ad478584f5f2f988b2a38d0e",
 "Heather_A":"cde69a147eacc851b4fec502fd4555546f11ec37",
 "Heather_B":"a6bb9b66408ee5f3ede29d1c7ed502cf301fb8a5"
}
BIG_BUSHES={"Bush_A","Bush_Red"}

def git_hash(data):
 return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

class TestFoliageCore(unittest.TestCase):
 def test_exact_original_source_restored_after_single_flag_reversal(self):
  for name,original_sha in APPROVED.items():
   with self.subTest(name=name):
    data=(BASE/(name+".prefab")).read_bytes()
    self.assertEqual(data.count(b"MeshRenderer:\n"),1)
    self.assertEqual(data.count(b"  m_CastShadows: 0\n"),1)
    self.assertEqual(data.count(b"  m_ReceiveShadows: 1\n"),1)
    before=data.replace(b"  m_CastShadows: 0\n",b"  m_CastShadows: 1\n",1)
    self.assertEqual(git_hash(before),original_sha,
       "Unreviewed geometry/material/transform/metadata or render property changed")

 def test_all_twenty_detail_models_keep_visible_and_receive_shadows(self):
  items=sorted(BASE.glob("*.prefab"))
  self.assertEqual(len(items),20)
  for prefab in items:
   with self.subTest(prefab=prefab.name):
    data=prefab.read_bytes()
    self.assertEqual(data.count(b"MeshRenderer:\n"),1)
    flags=re.findall(rb"(?m)^  m_CastShadows: ([01])$",data)
    self.assertEqual(flags,[b"1" if prefab.stem in BIG_BUSHES else b"0"])
    self.assertIn(b"  m_ReceiveShadows: 1\n",data)

if __name__=="__main__":unittest.main()
