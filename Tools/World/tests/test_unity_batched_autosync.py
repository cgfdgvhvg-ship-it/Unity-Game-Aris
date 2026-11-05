"""Safety/transaction tests for debounced Unity native asset LFS uploads."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unity_batched_autosync as sync


def git(*args,cwd=None):
    p=subprocess.run(["git",*args],cwd=cwd,check=True,stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE)
    return p.stdout


class UnityAutosyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.original=self.root/"original"
        self.scratch=self.root/"scratch"
        self.control=self.root/"control"
        self.statefile=self.root/"persistent"/"state.json"
        self.asset="Assets/TerrainDemoScene_URP/Terrain/Data/Sample.asset"
        self.original.mkdir()
        self.scratch.mkdir()
        self.statefile.parent.mkdir()
        (self.control/"unity-results").mkdir(parents=True)
        (self.control/"unity-commands").mkdir(parents=True)
        for root in (self.original,self.scratch):
            target=root/self.asset
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(b"initial NativeTerrainData")
            (root/(self.asset+".meta")).write_text("fileFormatVersion: 2\nguid: abc123\n")
            scene=root/"Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
            scene.parent.mkdir(parents=True,exist_ok=True)
            scene.write_text("test scene")
        git("init","-b","main",cwd=self.original)
        git("config","user.email","test@example.com",cwd=self.original)
        git("config","user.name","Test",cwd=self.original)
        (self.original/".gitattributes").write_text(
            self.asset+" filter=lfs diff=lfs merge=lfs -text\n"
        )
        if shutil.which("git-lfs") or subprocess.run(
            ["git","lfs","version"],capture_output=True).returncode==0:
            git("lfs","install","--local",cwd=self.original)
        git("add",".gitattributes",self.asset,self.asset+".meta",
            "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity",
            cwd=self.original)
        git("commit","-m","initial",cwd=self.original)
        self.remote=self.root/"bare.git"
        git("init","--bare",str(self.remote))
        git("remote","add","origin",str(self.remote),cwd=self.original)
        git("push","origin","main",cwd=self.original)
        self.st=sync.arm(self.original,self.scratch,self.statefile)

    def reply(self,ident,action="move_tree",changed=None,offset=3):
        file=self.control/"unity-results"/(ident+".json")
        file.write_text(json.dumps({"id":ident,"action":action,
                                    "status":"ok",
                                    "changedAsset":changed or self.asset}))
        at=self.st["armed_at"]+offset
        os.utime(file,(at,at))
        return file

    def report(self,now=None):
        return sync.status(self.original,self.scratch,self.control,self.statefile,
                           now=self.st["armed_at"]+200 if now is None else now)

    def test_no_old_mutations_before_arm(self):
        self.reply("old-tree-001",offset=-5)
        self.assertEqual(self.report()["pending"],0)

    def test_non_mutating_actions_are_not_uploaded(self):
        self.reply("camera-inspect-01",action="inspect")
        self.reply("camera-capture-01",action="capture")
        self.assertEqual(self.report()["pending"],0)

    def test_same_asset_many_changes_become_one_batch(self):
        for i in range(5):
            self.reply(f"tree-shift-{i:03d}",offset=5+i)
        (self.scratch/self.asset).write_bytes(b"changed once at end")
        report=self.report(now=self.st["armed_at"]+400)
        self.assertEqual(report["pending"],1)
        self.assertEqual(report["changed_assets"],[self.asset])
        self.assertTrue(report["safe_to_push"])

    def test_no_push_while_user_still_editing(self):
        self.reply("tree-shift-new",offset=25)
        (self.scratch/self.asset).write_bytes(b"new")
        r=self.report(now=self.st["armed_at"]+50)
        self.assertFalse(r["safe_to_push"])
        result=sync.flush(original=self.original,scratch=self.scratch,
                          control=self.control,statefile=self.statefile,
                          now=self.st["armed_at"]+50)
        self.assertEqual(result["status"],"debouncing")

    def test_pending_unity_command_blocks_snapshot(self):
        self.reply("tree-shift-002")
        (self.scratch/self.asset).write_bytes(b"new")
        (self.control/"unity-commands"/"next-tree.json").write_text("{}")
        with self.assertRaises(sync.SyncError):
            sync.flush(force=True,original=self.original,scratch=self.scratch,
                       control=self.control,statefile=self.statefile)

    def test_broken_meta_fails_safely(self):
        self.reply("tree-shift-003")
        (self.scratch/self.asset).write_bytes(b"new")
        (self.scratch/(self.asset+".meta")).write_text("guid: hijacked")
        with self.assertRaises(sync.SyncError):
            sync.flush(force=True,dry_run=True,original=self.original,
                       scratch=self.scratch,control=self.control,
                       statefile=self.statefile)

    def test_uncommitted_original_asset_is_never_overwritten_or_promoted(self):
        self.reply("tree-shift-004")
        (self.scratch/self.asset).write_bytes(b"new")
        (self.original/self.asset).write_bytes(b"owner has other edits")
        with self.assertRaises(sync.SyncError):
            sync.flush(force=True,dry_run=True,original=self.original,
                       scratch=self.scratch,control=self.control,
                       statefile=self.statefile)
        self.assertEqual((self.original/self.asset).read_bytes(),b"owner has other edits")

    def test_only_allow_native_content_types(self):
        for bad in ("Assets/../../.git/config","/etc/passwd",
                    "Assets/Editor/Evil.cs","Assets/rocks.unknown",
                    "Assets\\evil.asset"):
            with self.assertRaises(sync.SyncError,msg=bad):
                sync.relative_asset(bad)

    def test_scratch_identity_changes_refuse_future_upload(self):
        self.reply("tree-shift-005")
        import unittest.mock
        with patch.object(sync,"scratch_identity",return_value="different-session"):
            with self.assertRaises(sync.SyncError):
                sync.scan(self.st,self.scratch,self.control)

    def test_dry_run_never_creates_branch_or_writes_source(self):
        self.reply("tree-shift-006")
        (self.scratch/self.asset).write_bytes(b"new")
        original=sync.sha(self.original/self.asset)
        with patch.object(sync,"URL",str(self.remote)):
            result=sync.flush(force=True,dry_run=True,original=self.original,
                              scratch=self.scratch,control=self.control,
                              statefile=self.statefile)
        self.assertEqual(result["status"],"dry_run_validated")
        self.assertEqual(sync.sha(self.original/self.asset),original)
        self.assertFalse(sync.load_state(self.statefile)["branch"])

    def test_lfs_remote_pointer_match(self):
        digest="a"*64
        raw=(b"version https://git-lfs.github.com/spec/v1\n"
             +b"oid sha256:"+digest.encode()+b"\nsize 300\n")
        self.assertTrue(sync.match_remote_blob(raw,digest))
        self.assertFalse(sync.match_remote_blob(raw,"b"*64))

    def test_export_after_idle_contains_only_verified_latest_core_asset(self):
        self.reply("tree-update-101",offset=1)
        self.reply("tree-update-102",offset=3)
        (self.scratch/self.asset).write_bytes(b"twice-edited latest terrain")
        result=sync.export_for_actions(force=False,original=self.original,
                                       scratch=self.scratch,control=self.control,
                                       statefile=self.statefile,
                                       now=self.st["armed_at"]+200)
        self.assertEqual(result["status"],"ready_for_actions_upload")
        manifest=json.loads(Path(result["manifest"]).read_text())
        self.assertEqual(len(manifest["files"]),1)
        self.assertEqual(manifest["files"][0]["path"],self.asset)
        import tarfile
        with tarfile.open(result["tar"],"r") as archive:
            self.assertEqual(archive.getnames(),[self.asset])
            self.assertEqual(archive.extractfile(self.asset).read(),
                             b"twice-edited latest terrain")

    def test_acknowledged_push_keeps_later_edits_pending(self):
        self.reply("tree-save-201",offset=2)
        (self.scratch/self.asset).write_bytes(b"first saved version")
        old=sync.sha(self.scratch/self.asset)
        receipt=self.root/"receipt.json"
        receipt.write_text(json.dumps({
            "schema":1,"repo":sync.REPO,
            "scratch_identity":sync.scratch_identity(self.scratch),
            "branch":"ai/unity-batched-test1",
            "commit":"a"*40,"pushed":{self.asset:old}
        }))
        result=sync.acknowledge_actions_receipt(receipt,statefile=self.statefile,
                                                 scratch=self.scratch)
        self.assertEqual(result["status"],"actions_remote_verified_and_acknowledged")
        (self.scratch/self.asset).write_bytes(b"later unsaved version")
        self.reply("tree-save-202",offset=8)
        self.assertEqual(self.report()["pending"],1)
        self.assertEqual(sync.load_state(self.statefile)["pushed"][self.asset],old)

    def test_real_local_git_and_lfs_branch_upload_then_single_branch_update(self):
        if subprocess.run(["git","lfs","version"],capture_output=True).returncode:
            self.skipTest("git lfs unavailable")
        self.reply("tree-edit-first",offset=4)
        (self.scratch/self.asset).write_bytes(b"tree moved 1 metre")
        with patch.object(sync,"URL",str(self.remote)):
            first=sync.flush(force=True,original=self.original,
                             scratch=self.scratch,control=self.control,
                             statefile=self.statefile)
        self.assertTrue(first["pushed"])
        branch=first["branch"]
        self.assertTrue(branch.startswith("ai/unity-batched-"))
        self.assertEqual((self.original/self.asset).read_bytes(),
                         b"initial NativeTerrainData")
        remote_ptr=git("--git-dir",str(self.remote),"show",branch+":"+self.asset)
        self.assertTrue(sync.match_remote_blob(remote_ptr,
                                               sync.sha(self.scratch/self.asset)))
        self.reply("tree-edit-second",offset=9)
        (self.scratch/self.asset).write_bytes(b"tree moved twice and a rock added")
        with patch.object(sync,"URL",str(self.remote)):
            second=sync.flush(force=True,original=self.original,
                              scratch=self.scratch,control=self.control,
                              statefile=self.statefile)
        self.assertEqual(second["branch"],branch)
        self.assertNotEqual(second["commit"],first["commit"])
        self.assertEqual((self.original/self.asset).read_bytes(),
                         b"initial NativeTerrainData")


if __name__=="__main__":
    unittest.main()
