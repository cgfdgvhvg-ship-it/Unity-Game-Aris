"""Read-only contract tests for original/scratch Unity Core File reconciliation."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unity_scratch_reconcile as recon


class ScratchCompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.orig = self.base / "original"
        self.scratch = self.base / "scratch"
        self.orig.mkdir()
        self.scratch.mkdir()
        self.name = "Assets/Forest/Tree.prefab"
        for root in (self.orig, self.scratch):
            target = root / self.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"initial prefab")
            (root / (self.name + ".meta")).write_text("guid: preserved\n")

    def report(self, protected=()):
        with patch.object(recon, "owner_protected", return_value=set(protected)):
            return recon.reconcile(self.orig, self.scratch, [self.name])

    def test_identical_prefab_and_meta_read_only(self):
        report = self.report()
        self.assertEqual(report["summary"]["same"], 2)
        self.assertEqual(report["summary"]["different"], 0)
        self.assertFalse(report["promotion_allowed"])
        self.assertEqual(report["writes_performed"], 0)
        self.assertTrue(all(not x["promotion_allowed"] for x in report["assets"]))

    def test_prefab_edit_detected_but_meta_unchanged(self):
        (self.scratch / self.name).write_bytes(b"test prefab position edited")
        report = self.report()
        self.assertEqual(report["summary"]["different"], 1)
        self.assertEqual(report["summary"]["same"], 1)
        self.assertEqual((self.orig / self.name).read_bytes(), b"initial prefab")
        self.assertEqual(
            report["assets"][0]["scratch"]["sha256"],
            hashlib.sha256(b"test prefab position edited").hexdigest(),
        )

    def test_owner_edit_is_flagged_never_overwritten(self):
        (self.scratch / self.name).write_bytes(b"scene change")
        report = self.report(protected=[self.name])
        self.assertTrue(report["assets"][0]["owner_modified_or_untracked"])
        self.assertFalse(report["assets"][0]["promotion_allowed"])

    def test_missing_source_is_not_promotable(self):
        (self.orig / self.name).unlink()
        report = self.report()
        self.assertEqual(report["assets"][0]["comparison"], "missing")
        self.assertFalse(report["assets"][0]["promotion_allowed"])

    def test_symlink_never_read_or_followed(self):
        target = self.scratch / self.name
        target.unlink()
        target.symlink_to(self.orig / self.name)
        report = self.report()
        self.assertEqual(report["assets"][0]["comparison"], "unverified")
        self.assertEqual(report["assets"][0]["scratch"]["state"], "unsafe_symlink")

    def test_traversal_and_unsupported_extension_rejected(self):
        for name in ("../etc/passwd", "/etc/passwd",
                     "Assets/../../home/private.mat",
                     "Assets/TerrainData.zip", "Packages/manifest.json"):
            with self.assertRaises(recon.AuditError, msg=name):
                recon.relative_asset(name)

    def test_limits(self):
        with patch.object(recon, "owner_protected", return_value=set()):
            with self.assertRaises(recon.AuditError):
                recon.reconcile(self.orig, self.scratch, [])
            with self.assertRaises(recon.AuditError):
                recon.reconcile(self.orig, self.scratch, [self.name] * 33)

    def test_untracked_scratch_only_script_requires_review(self):
        name = "Assets/Editor/AarisBatchProbe.cs"
        p = self.scratch / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"scratch-only script")
        with patch.object(recon, "owner_protected", return_value=set()):
            report = recon.reconcile(self.orig, self.scratch, [name])
        self.assertEqual(report["assets"][0]["comparison"], "missing")
        self.assertFalse(report["assets"][0]["promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
