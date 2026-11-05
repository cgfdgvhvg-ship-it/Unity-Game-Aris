"""Tests saved mobile rendering core YAML values and LOD renderer policies."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
QUALITY = ROOT / "ProjectSettings" / "QualitySettings.asset"


def lod_shadow_flags(path):
    s = path.read_text()
    sections = re.split(r"(?=^--- !u!)", s, flags=re.M)
    group = next(x for x in sections if "\nLODGroup:\n" in x)
    ids = re.findall(r"- renderer: \{fileID: (\d+)\}", group)
    assert len(ids) == 3 and len(set(ids)) == 3, path
    flags = []
    for ident in ids:
        mesh = next(x for x in sections if x.startswith(f"--- !u!23 &{ident}\nMeshRenderer:\n"))
        flags.append(int(re.search(r"(?m)^  m_CastShadows: (\d+)$", mesh).group(1)))
    return flags


class TestSavedMobileRenderCore(unittest.TestCase):
    def test_android_shared_quality_budget(self):
        s = QUALITY.read_text()
        for key, value in {
            "streamingMipmapsActive": 1,
            "streamingMipmapsMemoryBudget": 192,
            "streamingMipmapsRenderersPerFrame": 96,
            "streamingMipmapsMaxFileIORequests": 24,
            "shadowDistance": 72,
            "shadowCascades": 2,
            "lodBias": 1,
            "maximumLODLevel": 0,
            "globalTextureMipmapLimit": 0
        }.items():
            self.assertRegex(s, rf"(?m)^    {key}: {value}$")
        self.assertIn("    Android: 0\n", s)

    def test_all_17_structure_prefabs_keep_close_shadows(self):
        files = sorted((ROOT / "Assets" / "AarisWorld" / "Models").glob("*/*.prefab"))
        self.assertEqual(len(files), 17)
        for file in files:
            with self.subTest(file=file.name):
                self.assertEqual(lod_shadow_flags(file), [1, 1, 0])
                self.assertIn("MeshCollider:", file.read_text())

    def test_all_three_prop_prefabs_keep_close_shadows(self):
        files = sorted((ROOT / "Assets" / "AarisWorld" / "Props").glob("*/*.prefab"))
        self.assertEqual(len(files), 3)
        for file in files:
            with self.subTest(file=file.name):
                self.assertEqual(lod_shadow_flags(file), [1, 1, 0])


if __name__ == "__main__":
    unittest.main()
