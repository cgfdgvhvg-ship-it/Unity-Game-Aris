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