"""Explicit workflow_dispatch patch -> verify -> new branch/PR; never auto-merge."""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from unity_data import WorldError
from patching import apply_yaml, plan
from world import ROOT, verify
from unity_data import World


def command(*args):
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main():
    raw = os.environ.get("WORLD_PATCH", "")
    if len(raw.encode()) > 32768: raise WorldError("Patch exceeds 32KiB")
    patch = json.loads(raw); report, _ = plan(ROOT, patch)
    backend = os.environ.get("WORLD_BACKEND", "python")
    if backend == "unity":
        import engine
        engine.run(ROOT, {"command": "apply"}, patch, True)
    elif backend == "python":
        apply_yaml(ROOT, patch, True)
    else: raise WorldError("Unknown backend")
    checks = verify(World(ROOT), {"native": backend == "unity", "project_checks": True})
    if not checks["passed"]:
        raise WorldError("Post-edit verification failed; no branch pushed: " + json.dumps(checks))
    changed = command("git", "diff", "--name-only").splitlines()
    if not changed:
        print("Patch produced no source changes"); return
    if set(changed) - set(patch["expected_files"]):
        raise WorldError("Unexpected files changed; no branch pushed")
    branch = "ai/world-edit-" + os.environ["GITHUB_RUN_ID"] + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    command("git", "config", "user.name", "github-actions[bot]")
    command("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    command("git", "switch", "-c", branch)
    command("git", "add", "--", *changed)
    command("git", "commit", "-m", "Apply verified AI world patch")
    command("git", "push", "origin", branch)
    body = ("Apply an explicit map patch to the saved core assets.\n\nReason: "+patch["reason"]+
            "\n\nSaved-file verification passed. Unity import/device playability still require the checks described in Docs/WORLD_AUTOMATION.md.\n\n"+
            "Changed files:\n"+"\n".join("- `"+p+"`" for p in changed))
    # Fixed API route and structured JSON; patch strings are never evaluated by a shell.
    repo = os.environ["GITHUB_REPOSITORY"]
    request = urllib.request.Request("https://api.github.com/repos/"+repo+"/pulls", method="POST",
        data=json.dumps({"title": "Apply verified AI world patch", "head": branch, "base": "main", "body": body}).encode(),
        headers={"Authorization": "Bearer "+os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(json.dumps({"pull_request": json.load(response)["html_url"], "auto_merged": False}))
    except Exception as e:
        raise WorldError(f"Verified branch {branch} was pushed; PR creation failed. Enable Actions PR creation or open a PR from that branch. {type(e).__name__}") from e


if __name__ == "__main__":
    try: main()
    except (WorldError, ValueError, OSError, subprocess.CalledProcessError) as e:
        print(json.dumps({"status": "error", "error": str(e)})); sys.exit(2)
