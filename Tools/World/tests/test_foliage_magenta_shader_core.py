"""Guard native foliage shader fix against any texture, tint, wind or GUID regressions.

The original saved Unity material bytes are reconstructed exactly by reverting
ONE shader GUID field. No fabricated replacements, geometry, .st or .meta edits.
A matched real Unity Editor A/B render demonstrated magenta foliage removal.
"""
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]
TREE="Assets/TerrainDemoScene_URP/Prefabs/Trees/"
OLD_GUID=b"d4fdc026464a42041be7fe785babd90e"
NEW_GUID=b"9920c1f1781549a46ba081a2a15a16ec"
OLD={
    "Conifer/Materials/Conifer_Branches.mat": "a39112199b493ea8323255125164c50460ecf5cb",
    "Conifer/Materials/Conifer_Billboard.mat": "749ce78bf11164f56a3fe8ef9b6b7e647578d915",
    "Cypress/Materials/Cypress_Forest_Desktop.mat": "1ac91e762ce742b29a0b7616291a81fd5144a4c5",
    "Cypress/Materials/Cypress_Forest_Desktop_Billboard.mat": "2ae13c3c97710ba35c59454e195d0cc9702948f2",
    "Pines/Pine_A/Materials/Pine_A.mat": "0caadbd5e266d488081e0eff1c46b254f6ee835f",
    "Pines/Pine_A/Materials/Pine_A_Billboard.mat": "de5583c80d6ecc4551a2e5a1126a0358c8d902ee",
    "Pines/Pine_B/Materials/Pine_B.mat": "b2e5efd35ac4f5a35b0e65b342c3f45e66cebeea",
    "Pines/Pine_B/Materials/Pine_B_Billboard.mat": "91f0374ba996f8fbdf7ff538b68430608ad052b4",
    "Pines/Pine_C/Materials/Pine_C.mat": "0a1074fce260aaa59c5ecb5710e42bcc100e0033",
    "Pines/Pine_C/Materials/Pine_C_Billboard.mat": "e0fa9f40869883c627c740d9bb2338fa5b1c2d1e",
    "Pines/Pine_D/Materials/Pine_D.mat": "abaecea3abe7df7351e09c0da6fce1a3929fcfd4",
    "Pines/Pine_D/Materials/Pine_D_Billboard.mat": "1b3cfc53d29b1339ca2cdde713760dfffdb98882",
}
SHADER_LINE=b"m_Shader: {fileID: -6465566751694194690, guid: "+NEW_GUID+b", type: 3}"


def blob_sha1(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class FoliageMagentaCoreTests(unittest.TestCase):
    def test_only_twelve_reviewed_material_shader_guids_change(self):
        self.assertEqual(len(OLD), 12)
        for rel, git_blob in OLD.items():
            with self.subTest(material=rel):
                path=ROOT/TREE/rel
                data=path.read_bytes()
                self.assertEqual(data.count(SHADER_LINE),1)
                self.assertEqual(data.count(NEW_GUID),1)
                self.assertEqual(data.count(OLD_GUID),0)
                old=data.replace(NEW_GUID,OLD_GUID)
                self.assertEqual(blob_sha1(old),git_blob,
                                 "Material property, texture, alpha, color, wind or pass changed")
                self.assertTrue((ROOT/(str(path.relative_to(ROOT))+".meta")).is_file())
                # The actual material text remains intact, including original texture IDs.
                self.assertIn(b"    - _MainTex:",data)
                self.assertIn(b"    - _Color:",data)

    def test_active_unity_pipeline_and_speedtree_packages(self):
        packages=json.loads((ROOT/"Packages/manifest.json").read_text())
        self.assertEqual(packages["dependencies"]["com.unity.render-pipelines.universal"],"17.3.0")
        graphics=(ROOT/"ProjectSettings/GraphicsSettings.asset").read_text()
        quality=(ROOT/"ProjectSettings/QualitySettings.asset").read_text()
        self.assertIn("m_CustomRenderPipeline: {fileID: 11400000, guid: 4f455263fdaa19b4894b6dbdb822f8d6, type: 2}",graphics)
        self.assertIn("customRenderPipeline: {fileID: 11400000, guid: 4f455263fdaa19b4894b6dbdb822f8d6, type: 2}",quality)

    def test_fixed_materials_are_only_reviewed_foliage_variants(self):
        actual=set()
        for name in ("Conifer","Cypress","Pines/Pine_A","Pines/Pine_B","Pines/Pine_C","Pines/Pine_D"):
            for path in (ROOT/TREE/name/"Materials").glob("*.mat"):
                rel=path.relative_to(ROOT/TREE).as_posix()
                if NEW_GUID in path.read_bytes():
                    actual.add(rel)
        self.assertEqual(actual,set(OLD),"Unreviewed bark/cap or other material shader was modified")


if __name__=="__main__":
    unittest.main()
