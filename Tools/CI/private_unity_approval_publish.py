#!/usr/bin/env python3
"""Private short-lived Unity approval URL relay from GitHub Actions to Cloudflare KV.

The *public* GitHub Issue must never receive an OAuth URL. This helper sends a
Unity-owned sign-in URL to a dedicated Cloudflare Worker using GitHub's signed
OIDC identity. The Worker exposes NO public endpoint for reading stored URLs.
ChatGPT's connected Cloudflare account can read the private KV value, then give
the user the genuine Unity link directly in their private chat (no email PIN).
"""
import argparse
import json
import os
from pathlib import Path
import re
import time
from urllib import parse, request
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "ci-live-control"
STATUS = STATE / "approval-bridge-status.json"
SOURCE = STATE / "license-status.json"
WORKER = "https://aaris-unity-approval-relay.aaris-game-control-6f9c.workers.dev/publish"
VALID_RUN = re.compile(r"^[0-9]{6,18}$")

def allowed_url(url):
    from urllib.parse import urlparse
    if not isinstance(url, str) or len(url) > 4000:
        return False
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        return (parsed.scheme == "https" and not parsed.username and
                not parsed.password and bool(hostname) and
                any(hostname == dom or hostname.endswith("." + dom)
                    for dom in ("unity.com", "unity3d.com")))
    except ValueError:
        return False

def oidc_token():
    target = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    secret = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    sep = "&" if "?" in target else "?"
    target += sep + "audience=" + parse.quote(WORKER, safe="")
    req = request.Request(target, headers={
        "Authorization": "Bearer " + secret,
        "Accept": "application/json",
    })
    with request.urlopen(req, timeout=20) as res:
        value = json.loads(res.read(16000).decode("utf-8"))["value"]
    if not isinstance(value, str) or not (100 <= len(value) <= 16000):
        raise ValueError("Invalid GitHub OIDC token")
    return value

def publish(approval, run_id):
    if not VALID_RUN.fullmatch(run_id) or not allowed_url(approval):
        raise ValueError("Invalid Unity authorization")
    jwt = oidc_token()
    body = json.dumps({"run_id": run_id, "auth_url": approval}).encode("utf-8")
    req = request.Request(WORKER, data=body, headers={
        "Authorization": "Bearer " + jwt,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }, method="POST")
    with request.urlopen(req, timeout=25) as res:
        if res.status != 202 or json.loads(res.read(2048)).get("accepted") is not True:
            raise RuntimeError("Private relay rejected request")

def probe():
    """Check real GitHub OIDC -> Worker trust without storing a fake Unity link."""
    token = oidc_token()
    destination = WORKER.rsplit("/", 1)[0] + "/probe"
    req = request.Request(destination, data=b"", method="POST", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    })
    with request.urlopen(req, timeout=25) as res:
        if res.status != 200 or json.loads(res.read(2048)).get("accepted") is not True:
            raise RuntimeError("Private relay OIDC probe rejected")
    print("Signed GitHub Actions -> private Cloudflare worker OIDC probe: PASS")


def state():
    try:
        value = json.loads(SOURCE.read_text("utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}

def record_status(stage, run_id):
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    allowed = {"waiting", "approval_link_stored_privately", "private_relay_unavailable"}
    if stage not in allowed:
        raise ValueError("Invalid status")
    temp = STATUS.with_suffix(".tmp")
    temp.write_text(json.dumps({"state": stage, "run_id": run_id}) + "\n", "utf-8")
    os.replace(temp, STATUS)

def watch(seconds):
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if not VALID_RUN.fullmatch(run_id):
        raise RuntimeError("Missing GitHub Actions run id")
    record_status("waiting", run_id)
    sent = set()
    until = time.monotonic() + max(10, min(seconds, 18000))
    next_retry = 0.0
    while time.monotonic() < until:
        value = state()
        auth_url = value.get("auth_url")
        if allowed_url(auth_url) and auth_url not in sent and time.monotonic() >= next_retry:
            try:
                publish(auth_url, run_id)
                sent.add(auth_url)
                record_status("approval_link_stored_privately", run_id)
                # Never print the URL or OIDC credentials to public Actions logs.
                print("Unity-owned approval URL privately delivered for run", run_id, flush=True)
            except (ValueError, KeyError, RuntimeError, OSError, HTTPError, URLError):
                next_retry = time.monotonic() + 12
                record_status("private_relay_unavailable", run_id)
                print("Private approval delivery needs attention (no secrets logged)", flush=True)
        time.sleep(2)

def selftest():
    assert allowed_url("https://id.unity.com/sso?state=example")
    assert allowed_url("https://accounts.unity3d.com/oauth?a=1")
    for bad in ("http://id.unity.com/login", "https://unity.com.attacker.test/p",
                "https://evil.com", "https://user:password@id.unity.com/",
                "file:///etc/passwd", ""):
        assert not allowed_url(bad)
    assert VALID_RUN.fullmatch("42327066949")
    assert not VALID_RUN.fullmatch("423;rm -rf /")
    print("Unity approval private relay URL validation: PASS")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--probe", action="store_true")
    p.add_argument("--seconds", type=int, default=2700)
    args = p.parse_args()
    if args.selftest:
        selftest()
    elif args.probe:
        probe()
    else:
        watch(args.seconds)
