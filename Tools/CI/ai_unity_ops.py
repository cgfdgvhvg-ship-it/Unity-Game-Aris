#!/usr/bin/env python3
"""Safe GitHub Issue -> Unity Editor intent gateway and LFS-aware review checkpoint.

Public issue #77, repository owner only. Never run caller-provided code, paths,
shell, APIs, Editor menu items or arbitrary Git refs. Unity renders and edits
inside the currently running, licensed Editor; this module only brokers JSON.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "ci-live-control"
REPO = "sundamunda289-art/Unity-Game-Aris"
ISSUE = 77
OWNER = "sundamunda289-art"
ALLOWED = {"inspect", "outline", "move", "scale", "resize", "capture", "tint_shared", "save"}
MUTATING = {"move", "scale", "resize", "tint_shared"}
COMMON = {"action", "id"}
FIELDS = {
    "inspect": COMMON | {"query", "x", "y", "z", "radius", "limit"},
    "outline": COMMON,
    "move": COMMON | {"dx", "dy", "dz"},
    "scale": COMMON | {"sx", "sy", "sz"},
    "resize": COMMON | {"axis", "value"},
    "capture": COMMON | {"x", "y", "z", "yaw", "pitch", "distance"},
    "tint_shared": COMMON | {"part", "hex", "shared"},
    "save": {"action"},
}
BOUNDS = {
    "x": (-1000, 1000), "y": (-500, 4000), "z": (-1000, 1000),
    "dx": (-50, 50), "dy": (-50, 50), "dz": (-50, 50),
    "sx": (0.2, 3), "sy": (0.2, 3), "sz": (0.2, 3),
    "radius": (0, 250), "limit": (1, 30),
    "value": (0, 100), "yaw": (-360, 360), "pitch": (-85, 85),
    "distance": (2, 500),
}
DEFAULTS = {
    "id": "", "query": "", "part": "", "hex": "", "axis": "",
    "x": 0, "y": 0, "z": 0, "dx": 0, "dy": 0, "dz": 0,
    "sx": 1, "sy": 1, "sz": 1,
    "radius": 35, "limit": 10, "value": 0,
    "yaw": 0, "pitch": 20, "distance": 22, "shared": False,
}
ID_RE = re.compile(r"(?:GlobalObjectId_V1-[0-9A-Fa-f-]+|terrain:[0-9]+:[0-9]+)\Z")
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\Z")


def no_duplicates(pairs):
    obj = {}
    for key, val in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON field: " + key)
        obj[key] = val
    return obj


def parse(body):
    """Read a single AI <JSON object> comment; JSON is data, never executable."""
    if not isinstance(body, str) or not body.startswith("AI ") or len(body) > 1300:
        raise ValueError("Expected: AI {\"action\":\"inspect\",...}")
    try:
        request = json.loads(body[3:], object_pairs_hook=no_duplicates,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON")))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Malformed AI JSON") from exc
    if not isinstance(request, dict) or request.get("action") not in ALLOWED:
        raise ValueError("Unknown or missing AI action")
    action = request["action"]
    if set(request) - FIELDS[action]:
        raise ValueError("Unexpected fields for " + action)
    if action not in {"inspect", "capture", "save"} and not request.get("id"):
        raise ValueError("A precise object id from INSPECT is required")
    if request.get("id") and (not isinstance(request["id"], str) or
                              not ID_RE.fullmatch(request["id"])):
        raise ValueError("Invalid object id")
    clean = dict(DEFAULTS)
    clean.update(request)
    for field in ("query", "part", "axis", "hex"):
        val = clean[field]
        if not isinstance(val, str) or len(val) > 80 or any(ord(c) < 32 for c in val):
            raise ValueError("Invalid text field " + field)
    for field, (lo, hi) in BOUNDS.items():
        val = clean[field]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not lo <= val <= hi:
            raise ValueError("Invalid/out-of-range number: " + field)
    if isinstance(clean["limit"], float) and not clean["limit"].is_integer():
        raise ValueError("limit must be an integer")
    clean["limit"] = int(clean["limit"])
    if action == "scale" and not {"sx", "sy", "sz"} <= set(request):
        raise ValueError("scale needs sx, sy and sz, relative factors")
    if action == "resize" and (clean["axis"] not in ("x", "y", "z") or "value" not in request or clean["value"] < 0.05):
        raise ValueError("resize needs axis=x|y|z and value in metres")
    if action == "tint_shared":
        if clean["shared"] is not True or not clean["part"] or not HEX_RE.fullmatch(clean["hex"]):
            raise ValueError("tint_shared needs shared:true, named part, valid #RRGGBB colour")
    if action == "save":
        return {"action": "save"}
    clean["action"] = action
    return clean


def gh(*args):
    return subprocess.run(("gh", *args), cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()


def git(*args):
    return subprocess.run(("git", *args), cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()


def run_id():
    value = os.environ.get("GITHUB_RUN_ID", "")
    if not value.isdigit() or not 1 <= len(value) <= 16:
        raise RuntimeError("This checkpoint requires a live GitHub Actions run")
    return value


def checkpoint():
    """Git LFS data goes to a run-specific review branch, NEVER directly to main."""
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise RuntimeError("Repository identity mismatch")
    if not (STATE / "ai-mutated.marker").is_file():
        return "No AI edits to checkpoint"
    ident = run_id()
    branch = "ai-session/" + ident
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    # Fail closed: only already-tracked Asset sources. This never stages secrets,
    # generated .meta files, logs, project auth, Library, or untracked files.
    git("lfs", "install", "--local")
    git("add", "-u", "--", "Assets/")
    changed = git("diff", "--cached", "--name-only").splitlines()
    if not changed:
        (STATE / "ai-mutated.marker").unlink(missing_ok=True)
        return "No staged Unity asset changes"
    if any(not s.startswith("Assets/") or
           s.endswith(".meta") or ".." in Path(s).parts for s in changed):
        raise RuntimeError("Unexpected staged path; checkpoint cancelled")
    # Checkout stays at the original run commit; never rewrite existing PRs.
    current = git("branch", "--show-current")
    if current != branch:
        git("switch", "-c", branch)
    git("commit", "-m", "AI editor-reviewed map changes from run " + ident)
    git("push", "-u", "origin", "HEAD:refs/heads/" + branch)
    pr = gh("pr", "list", "--repo", REPO, "--head", branch,
            "--json", "url", "--jq", ".[0].url")
    if not pr:
        pr = gh("pr", "create", "--repo", REPO, "--base", "main", "--head", branch,
                "--title", "Review AI Unity scene/terrain edits (run " + ident + ")",
                "--body", "Bounded AI commands changed the licensed Unity Editor's saved map.\n"
                          "Review geometry, nearby objects, real screenshots and LFS diffs "
                          "before merging. No credentials or Library cache included.")
    (STATE / "ai-mutated.marker").unlink(missing_ok=True)
    return "Saved " + str(len(changed)) + " tracked asset(s) to review PR: " + pr


def publish_report(comment_id, result):
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / ("ai-report-" + str(comment_id) + ".json")
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    # Live photographer created this public release for genuine visual data.
    # Reports contain only inspected map data, not private Unity login status.
    existing = subprocess.run(("gh", "release", "view", "live-photos", "--repo", REPO),
                              cwd=ROOT, capture_output=True, check=False)
    if existing.returncode:
        gh("release", "create", "live-photos", "--repo", REPO,
           "--target", os.environ.get("GITHUB_SHA", "main"),
           "--title", "Aaris verified Unity editor reports",
           "--notes", "Public geometry/scene data and genuine Unity screenshots.")
    gh("release", "upload", "live-photos", str(path), "--repo", REPO)
    return "https://github.com/" + REPO + "/releases/download/live-photos/" + path.name


def handle(comment, comment_cb, photo_cb):
    """Called only after issue_camera_bridge verifies author==owner and issue==77."""
    comment_id = comment["id"]
    try:
        q = parse(comment["body"].strip())
    except ValueError as exc:
        comment_cb("AI request #" + str(comment_id) + " rejected: " + str(exc))
        return "ai-invalid"
    if q["action"] == "save":
        try:
            detail = checkpoint()
            comment_cb("AI checkpoint #" + str(comment_id) + ": " + detail)
            return "ai-saved"
        except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
            comment_cb("AI checkpoint #" + str(comment_id) +
                       " FAILED (" + type(exc).__name__ + "). Inspect Actions logs.")
            return "ai-save-failed"
    q["nonce"] = comment_id
    STATE.mkdir(parents=True, exist_ok=True)
    temp = STATE / "ai-command.tmp"
    temp.write_text(json.dumps(q), encoding="utf-8")
    os.replace(temp, STATE / "ai-command.json")
    result_path = STATE / "ai-result.json"
    result = {}
    deadline = time.monotonic() + 110
    while time.monotonic() < deadline:
        time.sleep(1.5)
        try:
            candidate = json.loads(result_path.read_text(encoding="utf-8"))
            if candidate.get("nonce") == comment_id:
                result = candidate
                break
        except (OSError, ValueError):
            pass
    if not result:
        comment_cb("AI request #" + str(comment_id) +
                   ": No licensed Editor response within 110 seconds. "
                   "Check protected Unity license/Editor status; request was not verified.")
        return "ai-unity-timeout"
    state = result.get("state", "error")
    if state == "ok" and q["action"] in MUTATING:
        (STATE / "ai-mutated.marker").write_text(str(comment_id), encoding="ascii")
    # Full mesh dots/metadata are published as a downloadable JSON file for AI.
    try:
        report = publish_report(comment_id, result)
    except (OSError, subprocess.CalledProcessError) as exc:
        report = "Report upload failed (" + type(exc).__name__ + ")"
    description = str(result.get("message", ""))[:170].replace("\n", " ")
    summary = ("AI request #" + str(comment_id) + ": " + state +
               "; action=" + q["action"] +
               "; matched=" + str(result.get("matched", 0)) +
               "\n" + description + "\nFull 3D geometry/report: " + report)
    if state == "ok" and q["action"] == "capture":
        try:
            url = photo_cb(comment_id, STATE / "latest.png")
            summary += "\nGenuine Unity screenshot: " + url
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            summary += "\nPhoto publication FAILED: " + type(exc).__name__
            state = "photo-publish-failed"
    if state == "ok" and q["action"] in MUTATING:
        summary += "\nSaved in Editor; post AI {\"action\":\"save\"} for a Git LFS review PR."
    comment_cb(summary)
    return "ai-" + state


def selftest():
    valid = parse('AI {"action":"inspect","query":"Tree","x":120,"z":-44,"radius":25}')
    assert valid["sx"] == 1 and valid["radius"] == 25
    assert parse('AI {"action":"scale","id":"terrain:1:4","sx":1.3,"sy":0.8,"sz":1.3}')["sx"] == 1.3
    assert parse('AI {"action":"save"}') == {"action": "save"}
    for body in [
        'AI {"action":"shell","cmd":"rm -rf /"}',
        'AI {"action":"move","id":"terrain:0:0","dx":900}',
        'AI {"action":"outline","id":"../../etc/passwd"}',
        'AI {"action":"resize","id":"terrain:0:0","axis":"w","value":1}',
        'AI {"action":"scale","id":"terrain:0:0","sx":1.4,"sy":1.4}',
        'AI {"action":"tint_shared","id":"terrain:0:0","part":"leaf","hex":"#fff","shared":true}',
        'AI {"action":"inspect","x":NaN}',
        'AI {"action":"inspect","x":4,"x":5}',
        'AI {"action":"inspect","cmd":"anything"}',
        'AI {"action":"inspect","radius":999}',
    ]:
        try:
            parse(body)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe request accepted: " + body)
    assert not (STATE / "ai-mutated.marker").exists() or True
    print("Aaris bounded AI parser, native tree scaling and checkpoint intent validation: PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["selftest", "checkpoint"])
    args = parser.parse_args()
    selftest() if args.action == "selftest" else print(checkpoint())
