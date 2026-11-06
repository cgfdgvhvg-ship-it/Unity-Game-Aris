#!/usr/bin/env python3
"""GitHub issue jobs -> Codespace process -> GitHub issue results.

ONLY comments authored by sundamunda289-art on the configured private issue
with exact AARIS_JOB prefix are accepted. This is a remote command channel.
The owner must keep the repo, issue and credentials private.
"""
import base64
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO = "sundamunda289-art/Unity-Game-Aris"
OWNER = "sundamunda289-art"
ROOT = Path("/workspaces/Unity-Game-Aris")
DATA = Path("/workspaces/.aaris-world-bridge")
ISSUE = int((DATA / "issue.txt").read_text().strip())
JOB_ID = re.compile(r"[a-z][a-z0-9-]{2,55}\Z")
PREFIX = "AARIS_JOB\n"
ALLOWED = {"pwd", "ls", "git", "python3", "pytest", "find", "rg", "du", "df", "free", "cat", "head", "tail", "stat", "ps"}
DENIED_GIT = {"reset", "clean", "checkout", "switch", "stash", "pull", "rebase", "merge", "push"}
MAX_OUTPUT = 12000


def gh(path, method="GET", *, body=None):
    command = ["gh", "api", "--method", method, path]
    if body is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(command, input=json.dumps(body) if body is not None else None,
                            cwd=ROOT, text=True, capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-500:])
    return json.loads(result.stdout)


def publish(text):
    # GitHub issue comments have a bounded size; only the last output fragment is posted.
    return gh(f"repos/{REPO}/issues/{ISSUE}/comments", "POST", body={"body": text[-16000:]})


def redact(output):
    return re.sub(r"(?i)\b(?:ghp_|ghu_|gho_|ghs_|ghr_|github_pat_|sk-)[A-Za-z0-9_-]{8,}",
                  "[REDACTED_TOKEN]", output)[-MAX_OUTPUT:]


def execute(payload):
    if not isinstance(payload, dict) or set(payload) != {"id", "argv"}:
        raise ValueError("job JSON must contain only 'id' and 'argv'")
    name = payload["id"]
    argv = payload["argv"]
    if not isinstance(name, str) or not JOB_ID.fullmatch(name):
        raise ValueError("invalid job ID")
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 30
        or not all(isinstance(v, str) and 0 < len(v) <= 4000 for v in argv)
        or argv[0] not in ALLOWED):
        raise ValueError("command not on approved program list")
    if argv[0] == "git" and any(x in DENIED_GIT for x in argv[1:]):
        raise ValueError("destructive or branch-changing git subcommand is disabled")
    # This runner intentionally supports python3 -c, so trusted owner jobs can
    # edit project files. Treat it as powerful as a local terminal command.
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                            errors="replace", timeout=150, stdin=subprocess.DEVNULL)
    return {"status": "completed", "exit_code": result.returncode,
            "output": redact(result.stdout + result.stderr)}


def all_comments():
    page = 1
    while True:
        comments = gh(f"repos/{REPO}/issues/{ISSUE}/comments?per_page=100&page={page}")
        if not isinstance(comments, list):
            raise RuntimeError("invalid GitHub comments response")
        yield from comments
        if len(comments) < 100:
            break
        page += 1


def once():
    receipts = DATA / "receipts"
    for comment in all_comments():
        if comment.get("user", {}).get("login", "").lower() != OWNER.lower():
            continue
        body = comment.get("body") or ""
        if not body.startswith(PREFIX) or len(body) > 16000:
            continue
        comment_id = str(comment["id"])
        local = receipts / (comment_id + ".json")
        if local.exists():
            state = json.loads(local.read_text())
        else:
            try:
                payload = json.loads(body[len(PREFIX):])
                outcome = execute(payload)
                name = payload["id"]
            except Exception as exc:
                outcome = {"status": "failed", "exit_code": -1, "output": redact(str(exc))}
                name = comment_id
            state = {"id": name, "comment_id": comment_id, **outcome}
            # Persist results BEFORE posting, preventing execution twice on retries.
            temp = local.with_suffix(".tmp")
            temp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
            temp.replace(local)
        if not state.get("published"):
            msg = "AARIS_RESULT\n" + json.dumps({k: v for k, v in state.items() if k != "published"}, ensure_ascii=False)
            try:
                publish(msg)
                state["published"] = True
                local.write_text(json.dumps(state, ensure_ascii=False, indent=2))
                print("result published for", comment_id, flush=True)
            except Exception as exc:
                print("publish pending:", str(exc)[-300:], flush=True)


def main():
    DATA.mkdir(exist_ok=True)
    with (DATA / "worker.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("Aaris bridge online, issue", ISSUE, flush=True)
        while True:
            try:
                once()
            except Exception as exc:
                print("poll error:", str(exc)[-300:], flush=True)
            time.sleep(20)


if __name__ == "__main__":
    main()
