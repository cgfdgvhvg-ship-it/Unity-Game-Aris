#!/usr/bin/env python3
"""Externally hosted GitHub Actions -> user Codespace, no issue-comment inbox.

The GITHUB_TOKEN cannot start a user's personal Codespace. Keep a separate
Codespaces-scoped credential in repository Actions secret AARIS_CODESPACE_TOKEN.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY = "Aaris-khan-don/Unity-Game-Aris"
OWNER = "Aaris-khan-don"
BRANCH = "ai/codespace-jobs"
CODESPACE = "musical-carnival-jjxp9r6vw45wfjgvg"
QUEUE = ".aaris/jobs/"
ID_RE = re.compile(r"[a-z][a-z0-9-]{3,55}\Z")
API = f"https://api.github.com/user/codespaces/{CODESPACE}"
MAX_OUTPUT = 18000


class JobError(Exception):
    pass


def validate_job(data: dict, *, expected_file: str | None = None) -> dict:
    if not isinstance(data, dict) or set(data) != {"id", "operation", "args"}:
        raise JobError("job requires exactly id, operation and args")
    ident = data["id"]
    op = data["operation"]
    if not isinstance(ident, str) or not ID_RE.fullmatch(ident):
        raise JobError("invalid job id")
    if op not in {"diagnose", "desktop_xterm", "desktop_diagnose", "unity_gui", "unity_resume_paused", "unity_diagnostics", "desktop_tools", "desktop_snapshot", "unity_live", "unity_result", "unity_frame", "world_site", "storage_audit", "lfs_verify_chunk", "prune_caches", "unity_version", "world_doctor", "terminal_readonly"}:
        raise JobError("unsupported operation")
    args = data["args"]
    if not isinstance(args, list) or len(args) > 16 or any(
        not isinstance(a, str) or not (0 < len(a) < 500) for a in args
    ):
        raise JobError("args must be short strings")
    if op == "unity_live":
        if len(args) != 1:
            raise JobError("unity_live requires one short JSON request")
        try:
            from Tools.World.ai_codespace_executor import validate_live_payload
            validate_live_payload(json.loads(args[0]))
        except ImportError:
            # Queue source layout doesn't have Tools as a Python package in
            # every legacy checkout; remote executor validates independently.
            if not args[0].startswith("{") or len(args[0]) > 500:
                raise JobError("invalid Unity live request")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise JobError("invalid live Unity request: " + str(exc)[:160])
    elif op in {"unity_result", "unity_frame"}:
        if len(args) != 1 or not ID_RE.fullmatch(args[0]):
            raise JobError("expected one previously issued Unity job ID")
    elif op == "world_site":
        import math
        if len(args)!=3:
            raise JobError("world_site requires x z radius")
        try:
            x,z,radius=map(float,args)
        except ValueError:
            raise JobError("invalid world_site coordinates")
        if not all(math.isfinite(v) for v in (x,z,radius)) or max(abs(x),abs(z))>10000 or not 1<=radius<=150:
            raise JobError("world_site coordinates outside inspected bounds")
    elif op == "lfs_verify_chunk":
        if len(args) != 1 or not re.fullmatch(r"(?:0|[1-9][0-9]{0,4})", args[0]):
            raise JobError("lfs_verify_chunk requires one numeric cursor")
    elif op != "terminal_readonly" and args:
        raise JobError("this operation takes no arguments")
    if op == "terminal_readonly":
        validate_readonly_argv(args)
    if expected_file is not None and expected_file != f"{QUEUE}{ident}.json":
        raise JobError("filename/job id mismatch")
    return data


def validate_readonly_argv(args: list[str]):
    if not args:
        raise JobError("missing terminal command")
    command = args[0]
    allowed = {"pwd", "df", "free", "ps", "stat", "ls", "du", "glxinfo", "pgrep"}
    if command not in allowed:
        raise JobError("terminal_readonly supports only fixed diagnostic commands")
    if any(a.startswith("-") and ("exec" in a or "delete" in a) for a in args[1:]):
        raise JobError("option not supported")
    if any(a.startswith("/") and not (a.startswith("/workspaces/") or a.startswith("/home/codespace/")) for a in args[1:]):
        raise JobError("only workspace and Codespace home file paths are allowed")
    if any(a in {";", "&&", "|", ">", "<", "`", "$("} for a in args[1:]):
        raise JobError("shell syntax not supported")


def select_job(event: dict, workspace: Path, sha: str):
    if event.get("ref") != f"refs/heads/{BRANCH}":
        raise JobError("job must come from the dedicated queue branch")
    if event.get("repository", {}).get("full_name") != REPOSITORY:
        raise JobError("wrong repository")
    if event.get("sender", {}).get("login", "").casefold() != OWNER.casefold():
        raise JobError("job must be submitted by Codespace owner")
    head = event.get("head_commit") or {}
    if event.get("after") != sha or (head.get("id") not in (None, sha)):
        raise JobError("push commit and checked-out HEAD do not match")
    # GitHub Actions push payloads omit added/modified/removed arrays.
    # Inspect the actual checked-out Git commit rather than trusting webhook metadata.
    diff = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", sha],
        cwd=workspace, text=True, capture_output=True, timeout=20, check=False,
    )
    if diff.returncode != 0:
        raise JobError("cannot inspect job commit diff: " + diff.stderr[-300:])
    changes = [line.split("\t", 1) for line in diff.stdout.splitlines()]
    if len(changes) != 1 or len(changes[0]) != 2 or changes[0][0] != "A":
        raise JobError("submit exactly one newly added job file, no other changes")
    path = changes[0][1]
    if not isinstance(path, str) or not re.fullmatch(r"\.aaris/jobs/[a-z][a-z0-9-]{3,55}\.json", path):
        raise JobError("new file must be a queue JSON job")
    file = workspace / path
    if not file.is_file() or file.is_symlink() or file.stat().st_size > 4096:
        raise JobError("job is missing, too large or symlinked")
    return validate_job(json.loads(file.read_text(encoding="utf-8")), expected_file=path)


def github_api(method, token, suffix="", *, payload=None, timeout=30):
    req = Request(API + suffix, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Aaris-Codespace-OnDemand/1.0",
    }, data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except HTTPError as exc:
        err = exc.read(500).decode("utf-8", "replace")
        raise JobError(f"Codespaces API {method} status={exc.code}: {err}") from None
    except URLError as exc:
        raise JobError(f"Codespaces API unreachable: {exc.reason}") from None


def start_and_wait(token: str, *, sleep=time.sleep, get=github_api, attempts=30):
    info = get("GET", token)
    if info.get("name") != CODESPACE or info.get("repository", {}).get("full_name") != REPOSITORY:
        raise JobError("Codespace identity/repository mismatch: refusing to start another")
    state = info.get("state", "Unknown")
    if state in {"Unavailable", "Deleted", "Deleting", "Archived", "Failed"}:
        raise JobError(f"Codespace lifecycle state is {state}")
    # Shutdown means normally stopped, not deleted; request a start.
    if state not in {"Available", "Running"}:
        print("AARIS: requesting Codespace start; prior state", state, flush=True)
        try:
            get("POST", token, "/start")
        except JobError as exc:
            # A concurrent request can transition state: confirm with GET.
            after = get("GET", token)
            if after.get("state") not in {"Available", "Running", "Starting"}:
                raise exc
    for i in range(attempts):
        info = get("GET", token)
        state = info.get("state")
        print(f"AARIS: Codespace state {state} (poll {i + 1}/{attempts})", flush=True)
        if state in {"Available", "Running"}:
            return
        if state in {"Unavailable", "Deleted", "Deleting", "Archived", "Failed"}:
            raise JobError("Codespace became unavailable")
        sleep(5)
    raise JobError("Codespace did not become ready; check billing or quota")


def invoke(args, *, env, timeout=90, attempts=3):
    last = None
    for i in range(attempts):
        try:
            r = subprocess.run(args, capture_output=True, text=True, env=env,
                               timeout=timeout, check=False, stdin=subprocess.DEVNULL)
            if r.returncode == 0:
                return r
            last = f"exit {r.returncode}: {(r.stderr or r.stdout)[-1100:]}"
        except subprocess.TimeoutExpired:
            last = f"command timed out ({timeout} s)"
        if i + 1 < attempts:
            print(f"AARIS: remote connection retry {i + 2}/{attempts}", flush=True)
            time.sleep(4)
    raise JobError(f"Remote transfer/SSH failed: {last}")


def execute_remote(job: dict, token: str, workspace: Path, result_file: Path, *, runner=invoke):
    result_file.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    cs = CODESPACE
    remote = "/workspaces/.aaris-world-bridge/ondemand"
    local_script = workspace / "Tools/World/ai_codespace_executor.py"
    if not local_script.is_file():
        raise JobError("remote executor source missing")
    local_job = workspace / QUEUE / (job["id"] + ".json")
    runner(["gh", "codespace", "ssh", "-c", cs, "--", f"mkdir -p {remote}"], env=env, timeout=70)
    runner(["gh", "codespace", "cp", "-e", "-c", cs, str(local_script), f"remote:{remote}/ai_codespace_executor.py"], env=env, timeout=90)
    runner(["gh", "codespace", "cp", "-e", "-c", cs, str(local_job), f"remote:{remote}/{job['id']}.json"], env=env, timeout=90)
    if job["operation"] in {"unity_gui", "unity_live", "unity_result"}:
        # Trusted reviewed bridge sources are transferred to a staging folder,
        # never to the owner's dirty Unity project by GitHub CLI directly.
        for leaf in ("AarisLiveEditorBridge.cs", "AarisLiveEditorBridge.cs.meta"):
            source = workspace / "Assets/AarisWorld/Editor" / leaf
            if not source.is_file():
                raise JobError("Native Unity editor bridge missing from checked-out job source")
            runner(["gh","codespace","cp","-e","-c",cs,str(source),f"remote:{remote}/{leaf}"],
                   env=env, timeout=90)
    proc = runner(["gh", "codespace", "ssh", "-c", cs, "--",
                   f"python3 {remote}/ai_codespace_executor.py {remote}/{job['id']}.json"],
                  env=env, timeout=125, attempts=1)
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, TypeError):
        raise JobError("remote executor returned invalid JSON")
    if not isinstance(result, dict) or result.get("id") != job["id"] or result.get("operation") != job["operation"]:
        raise JobError("remote result identity mismatch")
    if result.get("ok") and job["operation"] in {"unity_frame", "desktop_snapshot"}:
        # Screenshot stays out of Git history. Copy to short-lived Actions artifact;
        # remove original only after secure remote copy and size check.
        frame_id=job["id"] if job["operation"]=="desktop_snapshot" else job["args"][0]
        remote_frame=f"/home/codespace/.aaris-desktop/frames/{frame_id}.jpg"
        local_frame=result_file.parent/(frame_id+".jpg")
        runner(["gh","codespace","cp","-e","-c",cs,f"remote:{remote_frame}",str(local_frame)],
               env=env,timeout=90)
        info=json.loads(result.get("stdout","{}"))
        if not local_frame.is_file() or local_frame.stat().st_size!=info.get("bytes"):
            raise JobError("Unity screenshot transfer size check failed; retaining source")
        runner(["gh","codespace","ssh","-c",cs,"--",f"rm -f -- {remote_frame}"],env=env,timeout=65)
        print("AARIS_FRAME_STAGED=",frame_id,local_frame.stat().st_size,flush=True)
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("AARIS_RESULT_JSON=" + json.dumps(result, ensure_ascii=False)[:MAX_OUTPUT], flush=True)
    if not result.get("ok"):
        raise JobError("remote operation reported failure (see result artifact)")


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--event", type=Path, required=True)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--result-dir", type=Path, required=True)
    args = p.parse_args(argv)
    job = None
    result = args.result_dir / "failure.json"
    try:
        event = json.loads(args.event.read_text())
        job = select_job(event, args.workspace, args.sha)
        result = args.result_dir / (job["id"] + ".json")
        token = os.getenv("AARIS_CODESPACE_TOKEN", "")
        if not token:
            raise JobError("SETUP_REQUIRED: add repository Actions secret AARIS_CODESPACE_TOKEN; it requires Codespaces lifecycle admin write, Codespaces read and permission for gh codespace ssh")
        start_and_wait(token)
        execute_remote(job, token, args.workspace, result)
        print("AARIS_JOB_COMPLETE", job["id"], flush=True)
        return 0
    except (JobError, ValueError, OSError, json.JSONDecodeError) as exc:
        args.result_dir.mkdir(parents=True, exist_ok=True)
        safe = str(exc)
        # No exceptions should echo tokens, but never store accidental contents.
        token = os.getenv("AARIS_CODESPACE_TOKEN", "")
        if token:
            safe = safe.replace(token, "[REDACTED]")
        failure = {"id": job["id"] if job else None, "ok": False, "error": safe}
        result.write_text(json.dumps(failure, ensure_ascii=False, indent=2))
        print("AARIS_JOB_ERROR=" + safe, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())