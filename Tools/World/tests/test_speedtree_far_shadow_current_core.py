"""Guard six native SpeedTree prefab LOD shadow-only edits against exact main blobs.

Tests use serialized GameObject/LOD/MeshRenderer identity, not line offsets.
Restoring ONLY LOD2/LOD3 shadow flags must reconstruct each approved original
Git blob byte-for-byte, including trunk/collider/LOD/visible mesh data.
"""
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PREFIX = "Assets/TerrainDemoScene_URP/Prefabs/Trees/"
OLD = {
    "Conifer/Conifer": "fa9d9cc07822b938ef5ba29bfa20eab7ce25de10",
    "Cypress/Cypress_Forest_Desktop": "65c18f7e3449f24240f6a52a33182991eda3d80e",
    "Pines/Pine_A/Pine_A": "f91d80bab50c2ef0cdc816fc0a5f0f30036b6f5f",
    "Pines/Pine_B/Pine_B": "526af9d0f166ca774cfe61b0d6906c11483929fc",
    "Pines/Pine_C/Pine_C": "959a20643bb07c39f9553623133eca7affa81ffb",
    "Pines/Pine_D/Pine_D": "344363e72f13f909c3cca8ad036491484c2a7373",
}
RECORD = re.compile(r"(?ms)^--- !u!(\d+) &(\d+)\n(.*?)(?=^--- !u!|\Z)")
RENDERER = re.compile(r"(?ms)^--- !u!23 &\d+\nMeshRenderer:\n.*?(?=^--- !u!|\Z)")


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def restore_far_shadows(text):
    go_names = {}
    for kind, ident, body in RECORD.findall(text):
        if kind != "1":
            continue
        name = re.search(r"(?m)^  m_Name: ([^\n]+)$", body)
        if name:
            go_names[ident] = name.group(1)
    states = {}
    restored = [0]

    def rewrite(match):
        block = match.group(0)
        owner = re.search(r"(?m)^  m_GameObject: \{fileID: (\d+)\}", block)
        name = go_names.get(owner.group(1), "") if owner else ""
        lod = re.search(r"_LOD([0-3])$", name)
        if not lod:
            return block
        level = int(lod.group(1))
        assert level not in states, "Duplicate LOD renderer: " + name
        cast = re.search(r"(?m)^  m_CastShadows: ([01])$", block)
        receive = re.search(r"(?m)^  m_ReceiveShadows: ([01])$", block)
        assert cast and receive, "Missing renderer shadow fields"
        states[level] = (int(cast.group(1)), int(receive.group(1)))
        if level >= 2:
            assert cast.group(1) == "0", "Far LOD unexpectedly casts shadows"
            block, count = re.subn(r"(?m)^  m_CastShadows: 0$", "  m_CastShadows: 1", block)
            assert count == 1, "Expected one precisely identified caster flag"
            restored[0] += 1
        return block

    before = RENDERER.sub(rewrite, text)
    assert restored[0] == 2, "Expected exactly two far-LOD changes"
    assert states == {0:(1,1), 1:(1,1), 2:(0,1), 3:(0,1)}, states
    groups = [body for kind, _, body in RECORD.findall(text) if kind == "205"]
    assert len(groups) == 1, "Expected one SpeedTree LODGroup"
    heights = [float(h) for h in re.findall(r"(?m)^  - screenRelativeHeight: ([0-9.]+)$", groups[0])]
    assert len(heights) == 4 and all(a > b > 0 for a, b in zip(heights, heights[1:]))
    assert "m_LastLODIsBillboard: 1" in groups[0], "Far billboard removed"
    return before


class SavedSpeedTreeFarShadowCoreTests(unittest.TestCase):
    def test_only_two_far_shadow_fields_changed_in_original_core(self):
        manifest = json.loads((ROOT / "Tools/World/tree-realism-v2-reviewed.json").read_text())
        reviewed = {row["key"]:row["reviewed_prefab_git_blob_sha1"] for row in manifest["profiles"]}
        self.assertEqual(set(reviewed), set(OLD))
        for name, original in OLD.items():
            with self.subTest(tree=name):
                file = ROOT / (PREFIX + name + ".prefab")
                raw = file.read_bytes()
                self.assertEqual(git_blob(raw), reviewed[name], "Unreviewed prefab change")
                restored = restore_far_shadows(raw.decode("utf-8"))
                self.assertEqual(git_blob(restored.encode("utf-8")), original,
                                 "More than two shadow fields changed from approved original")


if __name__ == "__main__":
    unittest.main()
