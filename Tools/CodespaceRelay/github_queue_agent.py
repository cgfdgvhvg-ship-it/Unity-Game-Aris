#!/usr/bin/env python3
"""Actions-free GitHub job queue -> bounded native Codespace executor.

Runs INSIDE the Codespace. Uses its existing gh authentication; no Cloudflare
agent secret and no arbitrary shell interpreter. GitHub is the job/result bus.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import quote

import agent as native

REPO = "sundamunda289-art/Unity-Game-Aris"
OWNER = "sundamunda289-art"
BRANCH = "ai/codespace-jobs"
JOBS = ".aaris/relay-jobs"
RESULTS = ".aaris/relay-results"
ROOT = Path("/workspaces/.aaris-world-bridge")
LOCK = ROOT / "github-relay.lock"
WORKDIR = Path("/workspaces/Unity-Game-Aris")


class Missing(Exception):
    pass


def gh(path: str, method="GET", payload=None):
    command = ["gh", "api", "--method", method, path]
    if payload is not None:
        command.extend(["--input", "-"])
    proc = subprocess.run(
        command,
        cwd=WORKDIR,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    if proc.returncode:
        if "HTTP 404" in proc.stderr:
            raise Missing(path)
        raise RuntimeError("GitHub API request failed; check Codespace gh authorization")
    return json.loads(proc.stdout)


def contents_path(path: str):
    return "repos/" + REPO + "/contents/" + quote(path, safe="/")


def read_json(path: str):
    try:
        obj = gh(contents_path(path) + "?ref=" + quote(BRANCH, safe=""))
    except Missing:
        return None
    if not isinstance(obj, dict) or obj.get("type") != "file":
        raise ValueError("Invalid GitHub content object")
    if obj.get("size", 999999) > 18000 or obj.get("encoding") != "base64":
        raise ValueError("Oversized or unsupported job/result encoding")
    return json.loads(base64.b64decode(obj["content"], validate=False).decode("utf-8"))


def jobs():
    try:
        entries = gh(contents_path(JOBS) + "?ref=" + quote(BRANCH, safe=""))
    except Missing:
        return []
    if not isinstance(entries, list) or len(entries) > 900:
        raise ValueError("Invalid or oversized GitHub job directory")
    return sorted(
        item["name"] for item in entries
        if item.get("type") == "file"
        and isinstance(item.get("name"), str)
        and item["name"].endswith(".json")
        and native.ID_RE.fullmatch(item["name"][:-5])
    )


def authorized(job_file: str):
    path = JOBS + "/" + job_file
    response = gh("repos/" + REPO + "/commits?sha=" + quote(BRANCH, safe="")
                  + "&path=" + quote(path, safe="") + "&per_page=1")
    latest = response[0] if isinstance(response, list) and response else {}
    names = [latest.get(x, {}).get("login", "").lower()
             for x in ("author", "committer") if isinstance(latest.get(x), dict)]
    if OWNER not in names:
        raise ValueError("Untrusted job author")
    obj = read_json(path)
    if not isinstance(obj, dict) or job_file != obj.get("id", "") + ".json":
        raise ValueError("Invalid job file identity")
    native.validate_job(obj)
    return obj


def result_payload(job, output):
    fields = {
        "schema": 1,
        "id": job["id"],
        "action": "terminal",
        "command": job["command"],
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "source": "codespace-github-agent",
        "status": output["status"],
        "exit_code": int(output["exit_code"]),
        "stdout": str(output.get("stdout", ""))[-8500:],
        "stderr": str(output.get("stderr", ""))[-2500:],
    }
    raw = json.dumps(fields, ensure_ascii=False)
    if len(raw.encode("utf-8")) > 15000:
        raise ValueError("Result exceeds bounded GitHub write limit")
    return raw


def publish_once(job, output):
    target = RESULTS + "/" + job["id"] + ".json"
    if read_json(target) is not None:
        return False
    raw = result_payload(job, output)
    gh(contents_path(target), "PUT", payload={
        "message": "Codespace terminal result " + job["id"],
        "branch": BRANCH,
        "content": base64.b64encode(raw.encode()).decode("ascii"),
    })
    return True


def poll_once():
    inspected = 0
    completed = 0
    for filename in jobs():
        job_id = filename[:-5]
        if read_json(RESULTS + "/" + filename) is not None:
            continue
        try:
            job = authorized(filename)
        except ValueError:
            continue  # Never execute an unauthorized or malformed job.
        inspected += 1
        path = native.STATE / (job_id + ".json")
        if path.is_file():
            output = native.store_once(job_id, None)
        else:
            try:
                output = native.execute(job)
            except Exception as exc:
                output = {"id": job_id, "status": "error", "exit_code": 1,
                          "stdout": "", "stderr": type(exc).__name__ + ": " + str(exc)[:150]}
            output = native.store_once(job_id, output)
        publish_once(job, output)
        completed += 1
        if inspected >= 3:
            break
    return {"inspected": inspected, "completed": completed}


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--once", action="store_true")
    args = cli.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Aaris GitHub relay already running", flush=True)
            return
        while True:
            try:
                print(json.dumps(poll_once()), flush=True)
            except Exception as exc:
                print("poll_error:" + type(exc).__name__, flush=True)
            if args.once:
                return
            time.sleep(20)


if __name__ == "__main__":
    main()
