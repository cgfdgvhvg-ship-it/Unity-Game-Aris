"""No-network regression checks for repo-scoped, secret-free GitHub read auth."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
import ai_master_github_auth as auth

FAKE_TOKEN = "ghs_FAKE_NONSECRET_UNIT_TEST_TOKEN_123456"
MAIN_SHA = "a" * 40


def environment(folder, **updates):
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": auth.REPOSITORY,
        "GITHUB_WORKSPACE": str(folder),
        "GITHUB_TOKEN": FAKE_TOKEN,
    }
    env.update(updates)
    return env


class MasterGitHubAuthTests(unittest.TestCase):
    def test_status_reports_capabilities_only_and_no_secret(self):
        env = environment("/tmp/runner")
        env["AARIS_CODESPACE_TOKEN"] = "codespace-different-secret"
        result = auth.status(env)
        self.assertTrue(result["private_main_read_ready"])
        self.assertTrue(result["codespace_lifecycle_secret_present"])
        self.assertFalse(result["credentials_disclosed"])
        self.assertNotIn(FAKE_TOKEN, repr(result))
        self.assertNotIn("codespace-different-secret", repr(result))

    def test_fetch_exact_main_uses_fixed_url_and_transient_git_askpass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            calls, scripts = [], []
            def fake_run(argv, **kwargs):
                calls.append(tuple(argv))
                self.assertNotIn(FAKE_TOKEN, " ".join(argv))
                self.assertEqual(kwargs["env"]["AARIS_EPHEMERAL_REPO_READ_TOKEN"], FAKE_TOKEN)
                self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
                self.assertEqual(kwargs["env"]["GCM_INTERACTIVE"], "never")
                helper = Path(kwargs["env"]["GIT_ASKPASS"])
                self.assertTrue(helper.is_file())
                self.assertNotIn(FAKE_TOKEN, helper.read_text())
                scripts.append(helper)
                if argv[-2:] == ["rev-parse", "FETCH_HEAD"]:
                    return SimpleNamespace(returncode=0, stdout=MAIN_SHA + "\n", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            self.assertEqual(auth.checked_fetch_main(root, MAIN_SHA,
                environ=environment(root),run=fake_run), MAIN_SHA)
            self.assertEqual(len(calls), 2)
            self.assertIn(auth.READ_URL, calls[0])
            self.assertIn("credential.helper=", calls[0])
            self.assertEqual(calls[1][-2:], ("rev-parse", "FETCH_HEAD"))
            self.assertTrue(all(not file.exists() for file in scripts))

    def test_missing_actions_token_fails_without_codespace_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/".git").mkdir()
            env=environment(root,GITHUB_TOKEN="",AARIS_CODESPACE_TOKEN="c"*40)
            with self.assertRaisesRegex(auth.MasterAuthError,"credential unavailable"):
                auth.checked_fetch_main(root, MAIN_SHA, environ=env)

    def test_rejects_other_repository_and_non_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/".git").mkdir()
            for env in (
                environment(root,GITHUB_REPOSITORY="someone/other"),
                environment(root,GITHUB_ACTIONS="false"),
                environment(root,GITHUB_WORKSPACE="/some/other/checkout"),
            ):
                with self.assertRaises(auth.MasterAuthError):
                    auth.checked_fetch_main(root, MAIN_SHA, environ=env)

    def test_refuses_unreviewed_main_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/".git").mkdir()
            def fake_run(argv,**kwargs):
                return SimpleNamespace(returncode=0,stderr="",stdout="b"*40+"\n")
            with self.assertRaisesRegex(auth.MasterAuthError,"Main changed since review"):
                auth.checked_fetch_main(root, MAIN_SHA,environ=environment(root),run=fake_run)

    def test_failed_git_errors_never_expose_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/".git").mkdir()
            def fail(argv,**kwargs):
                return SimpleNamespace(returncode=128,stdout=FAKE_TOKEN,stderr=FAKE_TOKEN)
            with self.assertRaises(auth.MasterAuthError) as ctx:
                auth.checked_fetch_main(root, MAIN_SHA,environ=environment(root),run=fail)
            self.assertNotIn(FAKE_TOKEN,str(ctx.exception))

    def test_github_app_installation_token_fallback_is_ephemeral(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/".git").mkdir()
            app="ghs_OPTIONAL_NONSECRET_TEST_APP_TOKEN_4567"
            env=environment(root,GITHUB_TOKEN="",AARIS_GITHUB_APP_INSTALLATION_TOKEN=app)
            def success(argv,**kwargs):
                self.assertEqual(kwargs["env"]["AARIS_EPHEMERAL_REPO_READ_TOKEN"],app)
                return SimpleNamespace(returncode=0,stdout=MAIN_SHA+"\n",stderr="")
            self.assertEqual(auth.checked_fetch_main(root,MAIN_SHA,environ=env,run=success),MAIN_SHA)

    def test_rejects_invalid_sha_and_unsafe_token_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/".git").mkdir()
            with self.assertRaises(auth.MasterAuthError):
                auth.checked_fetch_main(root,"main",environ=environment(root))
            with self.assertRaisesRegex(auth.MasterAuthError,"Malformed"):
                auth.checked_fetch_main(root,MAIN_SHA,
                    environ=environment(root,GITHUB_TOKEN=FAKE_TOKEN+"\n"))


if __name__ == "__main__":
    unittest.main()
