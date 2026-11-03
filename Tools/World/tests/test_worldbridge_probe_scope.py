"""Source-level guard for a C# CS0136 trap in the Unity editor route probe.

Tree-sitter accepts syntactically valid nested variable declarations even if
Unity's C# compiler rejects the name collision. This test is intentionally not
represented as an actual Unity compile or physics traversal.
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BRIDGE = ROOT / "Assets/AarisWorld/Editor/WorldBridge.cs"


class WorldBridgeProbeScopeTests(unittest.TestCase):
    def test_automatic_candidate_flag_cannot_shadow_capsule_hits(self):
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertEqual(source.count("private static void Probe("), 1)
        probe = source.split("private static void Probe(", 1)[1].split(
            "private static bool Finite(", 1
        )[0]
        flag = re.search(
            r"\bbool\s+(\w+)\s*=\s*query\.waypoints\s*==\s*null", probe
        )
        hits = re.search(
            r"\bvar\s+(\w+)\s*=\s*Physics\.CapsuleCastAll\(", probe
        )
        self.assertIsNotNone(flag, "Automatic route-candidate mode flag missing")
        self.assertIsNotNone(hits, "Capsule sweep observation missing")
        self.assertNotEqual(
            flag.group(1), hits.group(1),
            "CS0136: inner capsule hit-buffer declaration hides the enclosing local",
        )
        self.assertRegex(probe, rf"if\s*\(\s*{re.escape(flag.group(1))}\s*\)")
        self.assertRegex(probe, rf"foreach\s*\(\s*var\s+hit\s+in\s+{re.escape(hits.group(1))}\s*\)")
        self.assertIn(f"interpretation = {flag.group(1)} ?", probe)


if __name__ == "__main__":
    unittest.main()
