#!/usr/bin/env python3
"""Repo-scoped GitHub authentication bridge for Aaris Unity AI automation.

Use the GitHub connector for interactive AI. For unattended GitHub Actions
source reads, obtain the job-scoped GITHUB_TOKEN (or optional short-lived
GitHub App installation token) from the environment and pass it through
an ephemeral Git askpass program, never a URL, argv, repository file, or log.

This module deliberately does not grant Codespace lifecycle access, arbitrary
shell execution, Git writes, PR merges, or LFS upload permission. Those use
separate reviewed, least-privilege workflows.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Iterator, Mapping

REPOSITORY = "sundamunda289-art/Unity-Game-Aris"
READ_URL = "https://github.com/" + REPOSITORY + ".git"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class MasterAuthError(RuntimeError):
    """Safe public error; must never contain credential value."""


def status(environ: Mapping[str, str] | None = None) -> dict:
    """Only boolean readiness. Do not inspect or print secret values."""
    env = os.environ if environ is None else environ
    action = env.get("GITHUB_ACTIONS", "").lower() == "true"
    matched = env.get("GITHUB_REPOSITORY") == REPOSITORY
    github = bool(env.get("GITHUB_TOKEN"))
    app = bool(env.get("AARIS_GITHUB_APP_INSTALLATION_TOKEN"))
    codespace = bool(env.get("AARIS_CODESPACE_TOKEN"))
    return {
        "repository": REPOSITORY,
        "actions_runtime": action,
        "repo_context_matches": matched,
        "actions_repository_token_present": github,
        "short_lived_app_token_present": app,
        "codespace_lifecycle_secret_present": codespace,
        "private_main_read_ready": bool(action and matched and (github or app)),
        "native_unity_lfs_upload": "separate verified Actions writer; token presence is not proof of upload",
        "credentials_disclosed": False,
    }


def _read_token(environ: Mapping[str, str]) -> str:
    """Never use account-level Codespace credential for repository cloning."""
    if environ.get("GITHUB_ACTIONS", "").lower() != "true":
        raise MasterAuthError("Run the verified repository read in GitHub Actions, not the owner Codespace")
    if environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise MasterAuthError("Unexpected repository context; refusing credential use")
    token = environ.get("GITHUB_TOKEN") or environ.get("AARIS_GITHUB_APP_INSTALLATION_TOKEN")
    if not token:
        raise MasterAuthError("Repository read credential unavailable: configure job-scoped GITHUB_TOKEN")
    if len(token) < 20 or len(token) > 4096 or any(ord(char) < 33 or ord(char) == 127 for char in token):
        raise MasterAuthError("Malformed repository credential; no token was used")
    return token


@contextmanager
def _git_read_environment(environ: Mapping[str, str]) -> Iterator[dict[str, str]]:
    """Only a temporary executable helper is written; secret stays in process env."""
    token = _read_token(environ)
    with tempfile.TemporaryDirectory(prefix="aaris-github-read-") as folder:
        askpass = Path(folder) / "askpass.py"
        askpass.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "if len(sys.argv) != 2:\n"
            "    raise SystemExit(2)\n"
            "if 'Username' in sys.argv[1]:\n"
            "    print('x-access-token')\n"
            "elif 'Password' in sys.argv[1]:\n"
            "    print(os.environ['AARIS_EPHEMERAL_REPO_READ_TOKEN'])\n"
            "else:\n"
            "    raise SystemExit(2)\n",
            encoding="utf-8",
        )
        askpass.chmod(0o700)
        scoped = dict(environ)
        scoped.update({
            "GIT_ASKPASS": str(askpass),
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            "AARIS_EPHEMERAL_REPO_READ_TOKEN": token,
        })
        # Explicit git -c credential.helper= also overrides inherited helpers.
        yield scoped


def checked_fetch_main(
    workspace: Path,
    expected_sha: str,
    *,
    environ: Mapping[str, str] | None = None,
    run=subprocess.run,
) -> str:
    """Fetch ONLY this repo/main into the ephemeral Actions checkout.

    Fail closed when main differs from an already reviewed 40-hex commit.
    Never clone/reset/checkout the dirty user's existing Codespace worktree.
    No token appears in a command line, Git remote or persistent credential store.
    """
    env = os.environ if environ is None else environ
    token = _read_token(env)
    del token
    if not isinstance(expected_sha, str) or not SHA40.fullmatch(expected_sha):
        raise MasterAuthError("Expected reviewed main SHA must be 40 lowercase hex characters")
    root = Path(workspace).resolve()
    target = str(root)
    if target == "/workspaces/Unity-Game-Aris" or target.startswith("/workspaces/Unity-Game-Aris/"):
        raise MasterAuthError("Original Codespace worktree is protected from source fetch")
    if not env.get("GITHUB_WORKSPACE") or Path(env["GITHUB_WORKSPACE"]).resolve() != root:
        raise MasterAuthError("Only the active ephemeral Actions checkout can fetch GitHub source")
    if not (root / ".git").exists() or (root / ".git").is_symlink():
        raise MasterAuthError("Expected Actions checkout is missing")
    try:
        with _git_read_environment(env) as safeenv:
            command = [
                "git", "-c", "credential.helper=", "fetch",
                "--no-tags", "--depth=1", READ_URL, "main",
            ]
            fetched = run(
                command, cwd=root, env=safeenv, text=True,
                capture_output=True, timeout=85, check=False,
                stdin=subprocess.DEVNULL,
            )
            # Never include stdout or stderr: they can contain credential errors.
            if fetched.returncode:
                raise MasterAuthError("Authenticated main fetch failed; check GitHub Actions repository permissions")
            head = run(
                ["git", "rev-parse", "FETCH_HEAD"], cwd=root,
                env=safeenv, text=True, capture_output=True,
                timeout=10, check=False, stdin=subprocess.DEVNULL,
            )
            if head.returncode:
                raise MasterAuthError("GitHub main ref verification failed")
            actual = head.stdout.strip()
    except MasterAuthError:
        raise
    except (OSError, subprocess.TimeoutExpired):
        raise MasterAuthError("Private GitHub source read failed or timed out") from None
    if actual != expected_sha:
        raise MasterAuthError("Main changed since review; refusing unreviewed source snapshot")
    return actual


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "status":
        print("Usage: ai_master_github_auth.py status", file=sys.stderr)
        return 2
    print(json.dumps(status(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
