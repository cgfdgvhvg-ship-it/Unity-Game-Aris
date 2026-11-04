"""Unit tests for the read-only-by-default Unity/LFS synchronization guard."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unity_lfs_preflight as pre


class UnityLfsPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.editor = self.root / "Editor" / "Unity"
        self.editor.parent.mkdir()
        self.editor.write_bytes(b"unity executable test")
        for f in pre.CORE_FILES:
            target = self.root / f
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "m_EditorVersion: 6000.3.26f1\n" if f.endswith("ProjectVersion.txt")
                else "{}\n"
            )
        self.asset = self.root / "Assets" / "tree.tif"
        self.asset.write_bytes(b"source bytes")
        self.hash = "e" * 64

    def test_clean_checked_out_assets_are_never_refetched(self):
        with patch.object(pre, "protected_paths", return_value=set()), \
             patch.object(pre, "list_lfs", return_value=[("Assets/tree.tif", self.hash)]), \
             patch.object(pre, "git") as invoke, \
             patch.object(pre.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=512*1024**2)):
            result = pre.run_preflight(self.root, self.editor, hydrate=True)
        self.assertEqual(result["status"], "lfs_already_present_no_download")
        self.assertFalse(result["download_attempted"])
        self.assertEqual(result["lfs_present"], 1)
        invoke.assert_not_called()

    def test_missing_asset_dry_run_refuses_low_storage(self):
        self.asset.unlink()
        with patch.object(pre, "protected_paths", return_value=set()), \
             patch.object(pre, "list_lfs", return_value=[("Assets/tree.tif", self.hash)]), \
             patch.object(pre.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=512*1024**2)), \
             patch.object(pre, "git") as invoke:
            result = pre.run_preflight(self.root, self.editor, hydrate=False)
        self.assertEqual(result["status"], "missing_lfs_dry_run_only")
        self.assertFalse(result["hydration"]["allowed"])
        self.assertIn("8 GiB", result["hydration"]["reason"])
        invoke.assert_not_called()

    def test_dirty_lfs_asset_is_protected(self):
        with patch.object(pre, "protected_paths", return_value={"Assets/tree.tif"}), \
             patch.object(pre, "list_lfs", return_value=[("Assets/tree.tif", self.hash)]), \
             patch.object(pre.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=10*1024**3)), \
             patch.object(pre, "git") as invoke:
            result = pre.run_preflight(self.root, self.editor, hydrate=True)
        self.assertEqual(result["lfs_protected"], ["Assets/tree.tif"])
        self.assertFalse(result["download_attempted"])
        invoke.assert_not_called()

    def test_invalid_project_version_cannot_sync(self):
        (self.root/pre.CORE_FILES[0]).write_text("m_EditorVersion: 2022.3.0f1\n")
        with patch.object(pre, "protected_paths", return_value=set()), \
             patch.object(pre, "list_lfs", return_value=[("Assets/tree.tif", self.hash)]), \
             patch.object(pre.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=9*1024**3)):
            result = pre.run_preflight(self.root, self.editor)
        self.assertEqual(result["status"], "blocked_project_core")

    def test_symlinked_asset_refused(self):
        self.asset.unlink()
        self.asset.symlink_to(self.editor)
        with patch.object(pre, "protected_paths", return_value=set()), \
             patch.object(pre, "list_lfs", return_value=[("Assets/tree.tif", self.hash)]), \
             patch.object(pre.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=9*1024**3)):
            result = pre.run_preflight(self.root, self.editor)
        self.assertEqual(result["status"], "blocked_unsafe_symlink")

    def test_lfs_metadata_must_match_oid(self):
        with patch.object(pre, "git", return_value=(
            b"version https://git-lfs.github.com/spec/v1\n"
            b"oid sha256:" + (b"f"*64) + b"\nsize 105\n"
        )):
            with self.assertRaises(pre.SafetyError):
                pre.pointer_metadata(self.root, "Assets/tree.tif", "e"*64)

    def test_hydrate_does_not_omit_disk_guard(self):
        self.asset.unlink()
        entries=[("Assets/tree.tif",self.hash)]
        state={"missing":["Assets/tree.tif"],"pointers":[],"unsafe":[]}
        result=pre.hydration_plan(self.root,entries,state,free=500*1024**2)
        self.assertFalse(result["allowed"])

    def test_optional_image_preserves_exact_full_editor_release(self):
        root=Path(__file__).resolve().parents[3]
        image=root/".devcontainer/aaris-unity-image/Dockerfile"
        cfg=root/".devcontainer/aaris-unity-image/devcontainer.json"
        container=json.loads(cfg.read_text())
        recipe=image.read_text()
        self.assertEqual(container["build"]["dockerfile"],"Dockerfile")
        self.assertEqual(container["remoteUser"],"codespace")
        self.assertIn("ARG UNITY_VERSION=6000.3.26f1",recipe)
        self.assertIn("de8167e7440c/LinuxEditorInstaller",recipe)
        self.assertIn("test -x",recipe)
        self.assertNotIn("COPY Assets",recipe)
        self.assertNotIn("rm -rf /home/codespace/Unity",recipe)

    def test_preflight_contains_required_core_and_editor_version(self):
        self.assertEqual(pre.EXPECTED_EDITOR,"6000.3.26f1")
        self.assertIn("Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity",pre.CORE_FILES)
        self.assertEqual(pre.MIN_FREE,8*1024**3)


if __name__ == "__main__":
    unittest.main()
