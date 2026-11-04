import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import ai_codespace_remote as r
import ai_codespace_executor as e


class OnDemandTests(unittest.TestCase):
    def good(self):
        return {"id":"diagnose-20261104-a1", "operation":"diagnose", "args":[]}

    def test_validates_schema(self):
        self.assertEqual(r.validate_job(self.good())["operation"], "diagnose")
        for bad in [dict(self.good(), unexpected=True), dict(self.good(), operation="shell"), dict(self.good(), id="../bad"), dict(self.good(), args=["test"])]:
            with self.assertRaises(r.JobError): r.validate_job(bad)

    def test_rejects_shell_commands(self):
        for argv in [["python3","-c","print(1)"], ["git","reset","--hard"], ["ls","|","cat"], ["du","/etc/passwd"]]:
            with self.assertRaises(r.JobError): r.validate_job({"id":"foo-bar-01","operation":"terminal_readonly","args":argv})

    def test_selects_exact_commit_and_owner(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); path=root/r.QUEUE/(self.good()["id"]+".json")
            path.parent.mkdir(parents=True); path.write_text(json.dumps(self.good()))
            rel=r.QUEUE+path.name
            event={"ref":"refs/heads/"+r.BRANCH,"repository":{"full_name":r.REPOSITORY},
                   "sender":{"login":r.OWNER},"after":"commit-123",
                   "head_commit":{"id":"commit-123"}}
            good_diff=CompletedProcess(args=[],returncode=0,stdout="A\t"+rel+"\n",stderr="")
            # Also verify the fail-closed case if other files were changed.
            changed_diff=CompletedProcess(args=[],returncode=0,stdout="A\t"+rel+"\nM\tAGENTS.md\n",stderr="")
            with patch.object(r.subprocess,"run",return_value=good_diff):
                self.assertEqual(r.select_job(event,root,"commit-123"),self.good())
                with self.assertRaises(r.JobError):
                    r.select_job(dict(event, sender={"login":"stranger"}),root,"commit-123")
                with self.assertRaises(r.JobError): r.select_job(event,root,"other-commit")
            with patch.object(r.subprocess,"run",return_value=changed_diff):
                with self.assertRaises(r.JobError): r.select_job(event,root,"commit-123")

    def test_start_on_stopped_and_poll(self):
        state=["Shutdown","Starting","Available"]
        calls=[]
        def get(method,token,suffix=""):
            calls.append((method,suffix))
            if method=="POST":return {"state":"Starting"}
            return {"name":r.CODESPACE,"repository":{"full_name":r.REPOSITORY},"state":state.pop(0)}
        r.start_and_wait("mock-token",sleep=lambda _:None,get=get,attempts=3)
        self.assertIn(("POST","/start"),calls)

    def test_terminal_states_fail_closed(self):
        for state in ("Deleted", "Deleting", "Failed", "Archived", "Unavailable"):
            calls=[]
            def get(method, token, suffix=""):
                calls.append(method)
                return {"name":r.CODESPACE,"repository":{"full_name":r.REPOSITORY},"state":state}
            with self.assertRaises(r.JobError):
                r.start_and_wait("mock",sleep=lambda _:None,get=get,attempts=2)
            self.assertEqual(calls, ["GET"])

    def test_no_start_when_available(self):
        calls=[]
        def get(method,token,suffix=""):
            calls.append(method)
            return {"name":r.CODESPACE,"repository":{"full_name":r.REPOSITORY},"state":"Available"}
        r.start_and_wait("mock",sleep=lambda _:None,get=get)
        self.assertEqual(calls,["GET","GET"])

    def test_executor_readonly_and_safe(self):
        self.assertIn("free_disk_gib",json.loads(e.execute(self.good())["stdout"])) if e.PROJECT.exists() else None
        with self.assertRaises(ValueError):e.execute({"id":"abc-1234","operation":"shell","args":[]})

    def test_remote_copy_uses_fixed_path_expansion(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            script=root/"Tools/World/ai_codespace_executor.py"
            script.parent.mkdir(parents=True)
            script.write_text("# trusted executor fixture")
            job=self.good()
            path=root/r.QUEUE/(job["id"]+".json")
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(job))
            calls=[]
            def runner(argv, **kwargs):
                calls.append(argv)
                if "python3 /workspaces/.aaris-world-bridge/ondemand/" in " ".join(argv):
                    return SimpleNamespace(stdout=json.dumps({
                        "id":job["id"],"operation":job["operation"],
                        "ok":True,"exit_code":0,"stdout":"{}", "stderr":""
                    })+"\n",returncode=0)
                return SimpleNamespace(stdout="",returncode=0)
            result=root/"result.json"
            r.execute_remote(job,"placeholder-token",root,result,runner=runner)
            self.assertTrue(result.is_file())
            cp=[a for a in calls if a[:3]==["gh","codespace","cp"]]
            self.assertEqual(len(cp),2)
            for argv in cp:
                self.assertIn("-e",argv)
                self.assertTrue(argv[-1].startswith("remote:/workspaces/.aaris-world-bridge/ondemand/"))

    def test_desktop_requires_existing_private_password(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(e, "DESKTOP", Path(d)), patch.object(e.shutil, "which", return_value="/usr/bin/test"):
                reason=e.ensure_desktop()
                self.assertIn("password missing", reason)

    def test_desktop_auto_recovery_triggers_before_xterm(self):
        with patch.object(e, "ensure_desktop", return_value=None) as ensure, \
             patch.object(e, "_process_running", side_effect=[False, True]), \
             patch.object(e, "_spawn_desktop") as spawn, \
             patch.object(e, "_wait_ready", return_value=True), \
             patch.object(e, "_port_ready", return_value=True):
            result=e.execute({"id":"desktop-test-01", "operation":"desktop_xterm","args":[]})
            self.assertEqual(result["exit_code"],0)
            info=json.loads(result["stdout"])
            self.assertTrue(info["novnc_6080"])
            self.assertTrue(info["xterm_running"])
            self.assertTrue(ensure.called)
            self.assertEqual(spawn.call_args.args[0][0],"xterm")

    def test_desktop_slow_start_succeeds_within_bounded_window(self):
        attempts=[]
        def eventually():
            attempts.append(True)
            return len(attempts) >= 25
        with patch.object(e.time, "sleep"):
            self.assertTrue(e._wait_ready(eventually))
        self.assertEqual(len(attempts),25)

    def test_desktop_fails_closed_if_recovery_fails(self):
        with patch.object(e, "ensure_desktop", return_value="Xvfb failed"):
            out=e.execute({"id":"desktop-test-02", "operation":"desktop_xterm","args":[]})
            self.assertEqual(out["exit_code"],3)
            self.assertIn("Xvfb failed",out["stderr"])

    def test_desktop_diagnostics_are_bounded_and_redact_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            (home/"vnc.log").write_text("Port busy. token ghp_123456789012345678901234 more details")
            (home/"vnc.pass").write_text("hidden",encoding="utf-8")
            with patch.object(e, "DESKTOP", home), \
                 patch.object(e, "_process_running", return_value=False), \
                 patch.object(e, "_port_ready", return_value=False):
                report=e.execute({"id":"desktop-diag-test","operation":"desktop_diagnose","args":[]})
            self.assertEqual(report["exit_code"],0)
            data=json.loads(report["stdout"])
            self.assertIn("Port busy",data["logs"]["vnc.log"])
            self.assertIn("[REDACTED]",data["logs"]["vnc.log"])
            self.assertNotIn("ghp_123456",report["stdout"])
            self.assertTrue(data["saved_vnc_password_exists"])

    def test_prune_caches_only_named_paths_and_preserves_assets(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            home=root/"home"
            project=root/"Unity-Game-Aris"
            project.mkdir()
            (project/"Assets").mkdir()
            important=project/"Assets"/"Geometry.asset"
            important.write_bytes(b"saved core geometry must survive")
            a=home/".cache"/"copilot"/"pkg"
            b=home/".npm"/"_cacache"
            for path in (a,b):
                path.mkdir(parents=True)
                (path/"temporary").write_text("cache")
            keep=home/".cache"/"unity3d"/"bee"
            keep.mkdir(parents=True)
            (keep/"keep").write_text("needed")
            with patch.object(e,"PROJECT",project), \
                 patch.object(e,"run",return_value={"exit_code":0,"stdout":" M Assets/Geometry.asset\n","stderr":""}):
                result=e.prune_caches(home)
            self.assertFalse(a.exists())
            self.assertFalse(b.exists())
            self.assertTrue((keep/"keep").exists())
            self.assertEqual(important.read_bytes(),b"saved core geometry must survive")
            self.assertTrue(result["git_worktree_unchanged"])

    def test_lfs_hashing_is_budget_limited_for_large_assets(self):
        import hashlib
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"Assets").mkdir()
            huge=root/"Assets"/"HugeTexture.asset"
            with huge.open("wb") as out:
                out.truncate(129 * 1024 * 1024)
            long_oid=hashlib.sha256(b"dummy").hexdigest()
            def cmd(argv, **kw):
                if argv[:3]==["git","lfs","ls-files"]:
                    return CompletedProcess(argv,0,(long_oid+" * Assets/HugeTexture.asset\n").encode(),b"")
                if argv[:2]==["git","diff"]:
                    return CompletedProcess(argv,0,b"",b"")
                raise AssertionError(argv)
            with patch.object(e,"PROJECT",root), \
                 patch.object(e.subprocess,"run",side_effect=cmd), \
                 patch.object(e,"run",return_value={"exit_code":0,"stdout":"","stderr":""}):
                result=e._lfs_inventory()
            self.assertEqual(result["lfs_status"]["hash_deferred"],1)
            self.assertEqual(result["lfs_status"]["checked_sha256"],0)
            self.assertEqual(result["hash_deferred_bytes"],129*1024*1024)

    def test_chunked_lfs_hash_verification_and_dirty_protection(self):
        import hashlib
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"Assets").mkdir()
            raw=b"material saved by Unity"
            (root/"Assets/good.mat").write_bytes(raw)
            (root/"Assets/protected.asset").write_bytes(b"modified mesh")
            (root/"Assets/missing.prefab").write_text(
                "version https://git-lfs.github.com/spec/v1\n"
                "oid sha256:"+ "4"*64 + "\nsize 40\n")
            rows = (
                hashlib.sha256(raw).hexdigest()+" * Assets/good.mat\n"+
                "1"*64+" * Assets/protected.asset\n"+
                "4"*64+" - Assets/missing.prefab\n"
            )
            def cmd(argv, **kw):
                if argv[:3] == ["git","lfs","ls-files"]:
                    return CompletedProcess(argv,0,rows.encode(),b"")
                if argv[:2] == ["git","diff"]:
                    return CompletedProcess(argv,0,b"Assets/protected.asset\0",b"")
                raise AssertionError(argv)
            with patch.object(e,"PROJECT",root), \
                 patch.object(e.subprocess,"run",side_effect=cmd), \
                 patch.object(e,"run",return_value={"exit_code":0,"stdout":"abc123\n","stderr":""}):
                result=e.lfs_verify_chunk(0)
                last=e.lfs_verify_chunk(3)
            self.assertTrue(result["all_done"])
            self.assertEqual(result["next_cursor"],3)
            self.assertEqual(result["categories"]["hash_matches"],1)
            self.assertEqual(result["categories"]["dirty_protected"],1)
            self.assertEqual(result["categories"]["pointer"],1)
            self.assertEqual(result["categories"]["hash_mismatch"],0)
            self.assertEqual(last["processed"],0)
            self.assertTrue(last["all_done"])

    def test_chunk_cursor_is_guarded(self):
        job={"id":"lfs-chunk-001","operation":"lfs_verify_chunk","args":["120"]}
        self.assertEqual(r.validate_job(job),job)
        for bad in (["-1"],["001"],["0","10"],["foo"],[],["10; rm -rf /"]):
            with self.assertRaises(r.JobError):
                r.validate_job(dict(job,args=bad))

    def test_lfs_hash_matching_preserves_dirty_geometry(self):
        import hashlib
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"Assets").mkdir()
            good=b"the original Unity material bytes"
            (root/"Assets/good.mat").write_bytes(good)
            (root/"Assets/core.asset").write_bytes(b"intentionally baked geometry")
            (root/"Assets/pending.prefab").write_text(
                "version https://git-lfs.github.com/spec/v1\n"
                "oid sha256:"+"1"*64+"\nsize 42\n")
            records=(
                hashlib.sha256(good).hexdigest()+" * Assets/good.mat\n"+
                "0"*64+" * Assets/core.asset\n"+
                "1"*64+" - Assets/pending.prefab\n")
            def cmd(argv, **kwargs):
                if argv[:3]==["git","lfs","ls-files"]:
                    return CompletedProcess(argv,0,records.encode(),b"")
                if argv[:2]==["git","diff"]:
                    return CompletedProcess(argv,0,b"Assets/core.asset\0",b"")
                raise AssertionError("unexpected command "+str(argv))
            with patch.object(e, "PROJECT", root), \
                 patch.object(e.subprocess, "run", side_effect=cmd), \
                 patch.object(e, "run", return_value={"exit_code":0,"stdout":"","stderr":""}):
                data=e._lfs_inventory()
            self.assertEqual(data["lfs_status"]["hash_matches"],1)
            self.assertEqual(data["lfs_status"]["dirty_protected"],1)
            self.assertEqual(data["lfs_status"]["lfs_pointer"],1)
            self.assertEqual(data["lfs_status"]["hash_mismatch"],0)

    def test_unity_live_command_schema_is_restricted(self):
        request={"action":"inspect","cameraTarget":{"x":120,"y":5,"z":88},"radius":30,"limit":12}
        job={"id":"unity-inspect-001","operation":"unity_live","args":[json.dumps(request)]}
        self.assertEqual(r.validate_job(job),job)
        self.assertEqual(e.validate_live_payload(request),request)
        for bad in (
            {"action":"shell","argv":["rm","-rf","/"]},
            {"action":"move","target":"Tree","delta":{"x":float("nan"),"y":0,"z":0}},
            {"action":"move","target":"Tree","delta":{"x":1,"y":2}},
            {"action":"scale","target":"Tree"},
            {"action":"move_tree","target":"terrain-tree:a:1","delta":{"x":1,"y":0,"z":0}},
            {"action":"capture","cameraPosition":{"x":1,"y":2,"z":3},"capturePath":"/etc/passwd"},
        ):
            with self.assertRaises(ValueError): e.validate_live_payload(bad)

    def test_unity_frame_is_temporary_and_validated(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"frames").mkdir()
            frame=root/"frames"/"unity-shot-001.jpg"
            frame.write_bytes(b"\xff\xd8"+b"\x00"*512+b"\xff\xd9")
            with patch.object(e,"DESKTOP",root):
                response=e.execute({"id":"unity-frame-001","operation":"unity_frame",
                                    "args":["unity-shot-001"]})
            self.assertEqual(response["exit_code"],0)
            info=json.loads(response["stdout"])
            self.assertEqual(info["bytes"],frame.stat().st_size)
        with self.assertRaises(r.JobError):
            r.validate_job({"id":"unity-frame-001","operation":"unity_frame","args":["../../etc/passwd"]})

    def test_desktop_screen_job_cannot_contain_commands(self):
        for op in ("desktop_tools","desktop_snapshot"):
            job={"id":"screen-test-001","operation":op,"args":[]}
            self.assertEqual(r.validate_job(job),job)
            with self.assertRaises(r.JobError):
                r.validate_job(dict(job,args=["--delete"]))
        with patch.object(e,"desktop_snapshot",return_value={
            "exit_code":0,"stdout":'{"frame_job":"screen-test-001","bytes":1000}',"stderr":""
        }) as capture:
            result=e.execute({"id":"screen-test-001","operation":"desktop_snapshot","args":[]})
            self.assertEqual(result["exit_code"],0)
            capture.assert_called_once_with("screen-test-001")

    def test_desktop_tool_install_reuses_installed_binaries(self):
        from types import SimpleNamespace
        with patch.object(e.shutil,"which",return_value="/usr/bin/installed"), \
             patch.object(e.shutil,"disk_usage",return_value=SimpleNamespace(free=5*2**30)), \
             patch.object(e.subprocess,"run") as spawn:
            info=e.ensure_desktop_tools()
            self.assertTrue(info["installed"])
            self.assertTrue(info["installed_before"])
            spawn.assert_not_called()

    def test_unity_diagnostics_requires_no_arguments(self):
        job={"id":"unity-diag-test-001","operation":"unity_diagnostics","args":[]}
        self.assertEqual(r.validate_job(job),job)
        with self.assertRaises(r.JobError):
            r.validate_job(dict(job,args=["--delete"]))
        with patch.object(e,"unity_diagnostics",return_value={"gui":{"pid":[123]}}) as probe:
            response=e.execute(job)
        self.assertEqual(response["exit_code"],0)
        self.assertEqual(json.loads(response["stdout"])["gui"]["pid"],[123])
        probe.assert_called_once()

    def test_unity_gui_operation_is_owner_only_and_argument_free(self):
        self.assertEqual(r.validate_job({"id":"unity-gui-01","operation":"unity_gui","args":[]})["operation"],"unity_gui")
        with self.assertRaises(r.JobError):
            r.validate_job({"id":"unity-gui-01","operation":"unity_gui","args":["rm","-rf"]})

    def test_unity_gui_reuses_running_process_without_launch(self):
        with patch.object(e,"_unity_gui_status",return_value={"pid":[4321]}) as state, \
             patch.object(e,"ensure_desktop") as gui, \
             patch.object(e.subprocess,"Popen") as popen:
            result=e.ensure_unity_gui()
        self.assertEqual(result["exit_code"],0)
        gui.assert_not_called()
        popen.assert_not_called()
        state.assert_called_once()

    def test_unity_gui_rejects_low_storage_before_launch(self):
        from types import SimpleNamespace
        status={"pid":[],"editor_present":True,"project_version_present":True,
                "map_scene_present":True}
        with patch.object(e,"_unity_gui_status",return_value=status), \
             patch.object(e.shutil,"disk_usage",return_value=SimpleNamespace(free=2*1024**3)), \
             patch.object(e,"ensure_desktop") as gui, \
             patch.object(e.subprocess,"Popen") as popen:
            result=e.ensure_unity_gui()
        self.assertNotEqual(result["exit_code"],0)
        self.assertIn("8 GiB",result["stderr"])
        gui.assert_not_called()
        popen.assert_not_called()

    def test_unity_gui_rejects_paused_process_without_restarting(self):
        status={"pid":[40121],"paused_pids":[40121],"free_disk_gib":0.585}
        with patch.object(e,"_unity_gui_status",return_value=status), \
             patch.object(e,"ensure_desktop") as desktop, \
             patch.object(e.subprocess,"Popen") as spawn:
            result=e.ensure_unity_gui()
        self.assertEqual(result["exit_code"],3)
        self.assertIn("paused",result["stderr"])
        desktop.assert_not_called()
        spawn.assert_not_called()

    def test_unity_gui_rejects_low_space_with_existing_library(self):
        from types import SimpleNamespace
        status={"pid":[],"editor_present":True,"project_version_present":True,
                "map_scene_present":True,"library_exists":True,
                "library_bytes":2*1024**3}
        with patch.object(e,"_unity_gui_status",return_value=status), \
             patch.object(e.shutil,"disk_usage",return_value=SimpleNamespace(free=3*1024**3)), \
             patch.object(e,"ensure_desktop") as desktop, \
             patch.object(e.subprocess,"Popen") as spawn:
            result=e.ensure_unity_gui()
        self.assertEqual(result["exit_code"],3)
        self.assertIn("4 GiB",result["stderr"])
        desktop.assert_not_called()
        spawn.assert_not_called()

    def test_paused_unity_resume_needs_disk_and_explicit_no_arg_job(self):
        from types import SimpleNamespace
        job={"id":"unity-resume-01","operation":"unity_resume_paused","args":[]}
        self.assertEqual(r.validate_job(job),job)
        with self.assertRaises(r.JobError):
            r.validate_job(dict(job,args=["force"]))
        state={"pid":[40121],"paused_pids":[40121],"library_exists":True}
        with patch.object(e,"_unity_gui_status",return_value=state), \
             patch.object(e.shutil,"disk_usage",return_value=SimpleNamespace(free=512*1024**2)), \
             patch.object(e.os,"killpg") as killer:
            outcome=e.resume_paused_unity()
        self.assertEqual(outcome["exit_code"],3)
        self.assertIn("4 GiB",outcome["stderr"])
        killer.assert_not_called()

    def test_resumed_unity_gets_restarted_watchdog_without_asset_rewrite(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"Library").mkdir()
            state={"pid":[40121],"paused_pids":[40121],"library_exists":True}
            with patch.object(e,"_unity_gui_status",return_value=state), \
                 patch.object(e,"_unity_pids",return_value=[40121]), \
                 patch.object(e,"PROJECT",root), \
                 patch.object(e,"DESKTOP",root/"desktop"), \
                 patch.object(e.shutil,"disk_usage",return_value=SimpleNamespace(free=6*1024**3)), \
                 patch.object(e.os,"getpgid",return_value=40121), \
                 patch.object(e.os,"killpg") as send, \
                 patch.object(e.subprocess,"Popen") as spawned:
                outcome=e.resume_paused_unity()
            self.assertEqual(outcome["exit_code"],0)
            send.assert_called_once_with(40121,e.signal.SIGCONT)
            spawned.assert_called_once()
            self.assertTrue((root/"Library").is_dir())

    def test_storage_audit_remains_read_only(self):
        job={"id":"storage-audit-test","operation":"storage_audit","args":[]}
        self.assertEqual(r.validate_job(job),job)
        expected={"free_disk_gib":3.4,"lfs_inventory":{"pending_count":12}}
        with patch.object(e,"storage_audit",return_value=expected) as inspector:
            response=e.execute(job)
            self.assertEqual(response["exit_code"],0)
            self.assertEqual(json.loads(response["stdout"]),expected)
            inspector.assert_called_once()
        with self.assertRaises(r.JobError):
            r.validate_job(dict(job,args=["--delete"]))

    def test_missing_secret_reports_setup_required(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); f=root/r.QUEUE/(self.good()["id"]+".json");f.parent.mkdir(parents=True);f.write_text(json.dumps(self.good()))
            event={"ref":"refs/heads/"+r.BRANCH,"repository":{"full_name":r.REPOSITORY},"sender":{"login":r.OWNER},"head_commit":{"id":"123"},"after":"123"}
            evt=root/"push.json";evt.write_text(json.dumps(event))
            from subprocess import CompletedProcess
            diff=CompletedProcess(args=[],returncode=0,stdout="A\t"+r.QUEUE+f.name+"\n",stderr="")
            with patch.object(r.subprocess,"run",return_value=diff), patch.dict("os.environ",{"AARIS_CODESPACE_TOKEN":""}):
                self.assertEqual(r.main(["--event",str(evt),"--workspace",str(root),"--sha","123","--result-dir",str(root/"results")]),1)
            self.assertIn("SETUP_REQUIRED",(root/"results"/(self.good()["id"]+".json")).read_text())

if __name__ == "__main__":unittest.main()