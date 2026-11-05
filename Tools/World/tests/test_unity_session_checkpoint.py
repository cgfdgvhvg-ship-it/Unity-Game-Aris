"""Tests for honest, idempotent Unity Codespace restart planning."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import unity_session_checkpoint as cp

class RestartTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base=pathlib.Path(t.name)
        self.original=self.base/"orig"
        self.scratch=self.base/"scratch"
        self.editor=self.base/"Unity"
        self.state=self.base/"persistent"/"session.json"
        self.proc=self.base/"proc"
        self.proc.mkdir()
        self.state.parent.mkdir()
        self.original.mkdir()
        self.scratch.mkdir()
        self.editor.write_bytes(b"Unity Editor binary")
        for f in cp.SOURCES:
            for root in (self.original,self.scratch):
                p=root/f
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(f+" content")
        for root in (self.original,self.scratch):
            p=root/cp.TERRAIN
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(b"terrain original")
        (self.scratch.parent/"scene-readback.json").write_text(
            json.dumps({"sceneLoaded":True,"scenePath":cp.SCENE})
        )

    def plan(self):
        with patch.object(cp,"disk_free",side_effect=lambda p: 42*1024**3):
            return cp.plan(self.original,self.scratch,self.editor,self.state,self.proc)

    def test_no_process_reopens_existing_compatible_library(self):
        r=self.plan()
        self.assertEqual(r["step"],"reopen_existing_scratch")
        self.assertTrue(r["scratch_core_matches"])
        self.assertTrue(r["scratch_loaded"])
        self.assertEqual(r["writes_performed"],0)
        self.assertFalse(self.state.exists())

    def test_running_native_editor_is_idempotent(self):
        proc=self.proc/"3211"
        proc.mkdir()
        cmd=[str(self.editor),"-projectPath",str(self.scratch),"-logFile","log"]
        (proc/"cmdline").write_bytes(("\0".join(cmd)+"\0").encode())
        self.assertEqual(self.plan()["step"],"already_running")

    def test_terminated_process_does_not_count_as_running(self):
        proc=self.proc/"3211"
        proc.mkdir()
        (proc/"cmdline").write_bytes(b"/usr/bin/python3\0run.py\0")
        self.assertEqual(self.plan()["step"],"reopen_existing_scratch")

    def test_shutdown_missing_tmp_forces_reimport(self):
        for f in cp.SOURCES:
            (self.scratch/f).unlink()
        self.scratch.rmdir() if not any(self.scratch.iterdir()) else None
        import shutil
        shutil.rmtree(self.scratch)
        self.assertEqual(self.plan()["step"],"recreate_scratch_and_reimport")
        self.assertNotIn("exact_resume",self.plan()["step"])

    def test_source_scene_changes_block_stale_scratch(self):
        (self.original/cp.SCENE).write_bytes(b"Owner scene edit, do not discard")
        self.assertEqual(self.plan()["step"],"blocked_scratch_core_mismatch")

    def test_original_disk_guard(self):
        with patch.object(cp,"disk_free",side_effect=[10*1024**2,35*1024**3]):
            report=cp.plan(self.original,self.scratch,self.editor,self.state,self.proc)
        self.assertEqual(report["step"],"blocked_low_persistent_disk")

    def test_terrain_serialization_drift_is_reported(self):
        (self.scratch/cp.TERRAIN).write_bytes(b"unity reserialized different terrain")
        report=self.plan()
        self.assertEqual(report["step"],"reopen_existing_scratch")
        self.assertTrue(report["scratch_terrain_differs"])
        self.assertTrue(any("never copy back" in w for w in report["warnings"]))

    def test_checkpoint_is_small_and_persistent_but_not_a_library_backup(self):
        report=self.plan()
        data=cp.write_checkpoint(report,self.state)
        self.assertTrue(self.state.is_file())
        self.assertLess(self.state.stat().st_size,8000)
        self.assertIn("NOT a backup",data["recovery_note"])
        self.assertTrue(cp.load_checkpoint(self.state)["scratch_loaded"])
        self.assertEqual((self.original/cp.SCENE).read_text(),cp.SCENE+" content")

    def test_stopped_with_checkpoint_warns_about_lost_tmp(self):
        report=self.plan()
        cp.write_checkpoint(report,self.state)
        import shutil
        shutil.rmtree(self.scratch)
        now=self.plan()
        self.assertEqual(now["step"],"recreate_scratch_and_reimport")
        self.assertTrue(now["previous_checkpoint_present"])
        self.assertTrue(any("may have been lost" in w for w in now["warnings"]))

    def test_last_successful_camera_view_is_retained(self):
        command_dir=self.scratch.parent/"control"/"unity-commands"
        result_dir=self.scratch.parent/"control"/"unity-results"
        command_dir.mkdir(parents=True)
        result_dir.mkdir(parents=True)
        payload={"action":"inspect","cameraTarget":{"x":102.307,"y":-10.85,"z":62.974}}
        (command_dir/"my-view.json").write_text(json.dumps(payload))
        (result_dir/"my-view.json").write_text(json.dumps({"status":"ok"}))
        report=self.plan()
        self.assertAlmostEqual(report["last_camera_target"]["x"],102.307)
        saved=cp.write_checkpoint(report,self.state)
        self.assertAlmostEqual(saved["last_camera_target"]["z"],62.974)

    def test_failed_camera_action_is_not_saved(self):
        command_dir=self.scratch.parent/"control"/"unity-commands"
        result_dir=self.scratch.parent/"control"/"unity-results"
        command_dir.mkdir(parents=True)
        result_dir.mkdir(parents=True)
        (command_dir/"bad.json").write_text(json.dumps(
            {"action":"capture","cameraTarget":{"x":5,"y":6,"z":7}}))
        (result_dir/"bad.json").write_text(json.dumps({"status":"error"}))
        self.assertIsNone(self.plan()["last_camera_target"])

    def test_refuse_checkpoint_on_unsafe_symlink(self):
        report=self.plan()
        self.state.symlink_to(self.original/cp.SCENE)
        with self.assertRaises(ValueError):
            cp.write_checkpoint(report,self.state)

if __name__=="__main__":
    unittest.main()
