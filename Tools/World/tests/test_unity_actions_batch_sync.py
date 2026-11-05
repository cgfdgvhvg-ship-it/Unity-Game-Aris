"""Contracts for owner-only GitHub Actions Unity batch transport and review."""
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unity_actions_batch_sync as runner


class ActionsSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/".aaris/jobs").mkdir(parents=True)
        self.name="unity-save-session-20261105-999"
        self.path=".aaris/jobs/"+self.name+".json"
        (self.root/self.path).write_text(json.dumps({
            "id":self.name,"operation":"unity_sync_save_session","args":[]
        }))
        self.event={"ref":"refs/heads/ai/codespace-jobs",
                    "repository":{"full_name":runner.REPO},
                    "sender":{"login":runner.OWNER},
                    "head_commit":{"added":[self.path],"modified":[],"removed":[]}}

    def test_owner_save_action_is_selected(self):
        self.assertEqual(runner.choose_mode(self.event,"push",self.root),"manual")

    def test_other_user_cannot_upload(self):
        self.event["sender"]["login"]="unknown-actor"
        with self.assertRaises(runner.RunnerError):
            runner.choose_mode(self.event,"push",self.root)

    def test_wrong_operation_ignores_job(self):
        (self.root/self.path).write_text(json.dumps({
            "id":self.name,"operation":"unity_virtual_live","args":[]
        }))
        self.assertEqual(runner.choose_mode(self.event,"push",self.root),"skip")

    def test_arbitrary_commit_cannot_trigger_privileged_uploader(self):
        self.event["head_commit"]["added"].append("README.md")
        self.assertEqual(runner.choose_mode(self.event,"push",self.root),"skip")

    def test_schedule_needs_no_owner_queue_job(self):
        self.assertEqual(runner.choose_mode({},"schedule",self.root),"scheduled")

    def valid_export(self):
        name="Assets/TerrainDemoScene_URP/Terrain/Data/Sample.asset"
        content=b"Unity saved native TerrainData"
        folder=self.root/"transfer"
        folder.mkdir()
        manifest=folder/"batch-0123456789abcd.json"
        bundle=folder/"batch-0123456789abcd.tar"
        import hashlib
        hashval=hashlib.sha256(content).hexdigest()
        data={"schema":1,"repo":runner.REPO,
              "scratch_identity":"123:999","branch":None,
              "files":[{"path":name,"sha256":hashval,
                        "original_sha256":hashval,
                        "meta_sha256":"a"*64,
                        "bytes":len(content),
                        "previously_pushed_sha256":None}]}
        manifest.write_text(json.dumps(data))
        with tarfile.open(bundle,"w") as stream:
            i=tarfile.TarInfo(name=name)
            i.size=len(content)
            stream.addfile(i,io.BytesIO(content))
        return folder,{"manifest":str(manifest),"tar":str(bundle)},data

    def test_manifest_and_archive_are_bounded(self):
        folder,export,data=self.valid_export()
        report,tar=runner.verified_manifest(export,folder)
        self.assertEqual(report["files"],data["files"])
        self.assertTrue(tar.is_file())

    def test_manifest_rejects_path_traversal(self):
        folder,export,data=self.valid_export()
        data["files"][0]["path"]="Assets/../../private.asset"
        Path(export["manifest"]).write_text(json.dumps(data))
        with self.assertRaises(runner.sync.SyncError):
            runner.verified_manifest(export,folder)

    def test_manifest_rejects_meta_mismatch_or_invalid_hash(self):
        folder,export,data=self.valid_export()
        data["files"][0]["meta_sha256"]="NOTSHA"
        Path(export["manifest"]).write_text(json.dumps(data))
        with self.assertRaises(runner.RunnerError):
            runner.verified_manifest(export,folder)

    def test_manifest_rejects_unexpected_archive_size(self):
        folder,export,data=self.valid_export()
        data["files"][0]["bytes"]=runner.sync.MAX_BYTES+1
        Path(export["manifest"]).write_text(json.dumps(data))
        with self.assertRaises(runner.RunnerError):
            runner.verified_manifest(export,folder)

    def test_no_credentials_in_app_status(self):
        self.assertNotIn("GH_TOKEN",json.dumps({
            "status":"codespace_stopped_no_tmp_to_sync"}))


if __name__=="__main__":
    unittest.main()
