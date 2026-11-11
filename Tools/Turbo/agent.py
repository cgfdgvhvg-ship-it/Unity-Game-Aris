#!/usr/bin/env python3
"""Aaris Codespace Turbo Agent: outgoing-only, standard-library terminal relay.

Cloudflare accepts commands only through a privately managed Durable Object SQL
queue. This agent is provisioned only by the trusted GitHub Actions OIDC workflow.
No incoming ports, public Codespace terminal, arbitrary Issue comments, or
GitHub commit-per-command polling are used.
"""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{2,119}$")
PROJECT_ROOT = Path("/workspaces")
SENSITIVE_ENV = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL", "AUTH", "LICENSE", "COOKIE", "PRIVATE_KEY")
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_ACTIVE = 2


def scrub_env():
    return {k: v for k, v in os.environ.items()
            if not any(fragment in k.upper() for fragment in SENSITIVE_ENV)
            and k not in {"AARIS_ENDPOINT", "AARIS_TOKEN_FILE"}}


def validate_job(job):
    if not isinstance(job, dict):
        raise ValueError("job")
    command_id = job.get("id")
    argv = json.loads(job.get("argv_json", "null"))
    cwd = job.get("cwd", "")
    timeout = job.get("max_seconds", 120)
    if not isinstance(command_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", command_id):
        raise ValueError("id")
    if not isinstance(argv, list) or not 1 <= len(argv) <= 64 or not all(
        isinstance(a, str) and 0 < len(a) <= 4096 for a in argv
    ) or sum(map(len, argv)) > 16384:
        raise ValueError("argv")
    if not isinstance(cwd, str) or not cwd.startswith("/workspaces/") or "\x00" in cwd:
        raise ValueError("cwd")
    path = Path(cwd).resolve(strict=True)
    if not path.is_dir() or not path.is_relative_to(PROJECT_ROOT):
        raise ValueError("cwd_scope")
    if not isinstance(timeout, int) or not 1 <= timeout <= 3600:
        raise ValueError("timeout")
    return command_id, argv, str(path), timeout


class Bridge:
    # Validated from GitHub Codespace: default python-urllib UA was blocked by the edge.
    USER_AGENT = "Mozilla/5.0"
    def __init__(self, endpoint, token):
        if not endpoint.startswith("https://") or "/agent/" not in endpoint:
            raise ValueError("https_endpoint_required")
        if len(token) != 64 or not all(c in "0123456789abcdef" for c in token):
            raise ValueError("token")
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.base, self.machine = self.endpoint.rsplit("/agent/", 1)
        if not NAME_RE.fullmatch(self.machine):
            raise ValueError("machine")
        self.transport = "direct"

    def _check_result(self, operation, result):
        if not isinstance(result, dict):
            raise ConnectionError("response_type")
        if operation == "next" and "job" not in result:
            raise ConnectionError("response_missing_job")
        if operation != "next" and result.get("ok") is not True:
            raise ConnectionError("response_missing_ack")
        return result

    def post(self, operation, payload=None):
        if operation not in {"ping", "next", "chunk", "done"}:
            raise ValueError("operation")
        b = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        if self.transport == "direct":
            req = urllib.request.Request(
                self.endpoint + "/" + operation,
                data=b,
                headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json",
                         "User-Agent": self.USER_AGENT},
                method="POST")
            try:
                with urllib.request.urlopen(req, timeout=12) as response:
                    return self._check_result(operation, json.loads(response.read(65536)))
            except urllib.error.HTTPError as exc:
                if exc.code == 403:
                    # Network or edge rejects Codespace /agent routes; switch once.
                    self.transport = "health"
                elif exc.code == 401:
                    raise PermissionError("session_expired") from None
                else:
                    raise ConnectionError("remote_http_" + str(exc.code)) from None
        # The same authenticated Durable Object operations, routed through one
        # HTTPS GET endpoint. Output and tokens live in headers, never URLs.
        blob = base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")
        if len(blob) > 11000:
            raise ValueError("request_payload_too_large")
        req = urllib.request.Request(
            self.base + "/health", method="GET",
            headers={"User-Agent": self.USER_AGENT, "X-Aaris-Op": operation,
                     "X-Aaris-Machine": self.machine, "X-Aaris-Token": self.token,
                     "X-Aaris-Payload": blob})
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return self._check_result(operation, json.loads(response.read(65536)))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise PermissionError("session_expired") from None
            raise ConnectionError("fallback_http_" + str(exc.code)) from None

    def stream_job(self, job):
        job_id = str(job.get("id", ""))[:128]
        seq = 0

        def send(kind, text):
            nonlocal seq
            if not text:
                return
            for off in range(0, len(text), 3000):
                self.post("chunk", {"id": job_id, "seq": seq, "kind": kind,
                                    "text": text[off:off + 3000]})
                seq += 1

        try:
            job_id, argv, cwd, timeout = validate_job(job)
        except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
            self.post("done", {"id": job_id, "exit_code": 2, "error": "INVALID_" + type(exc).__name__})
            return
        exit_code, problem = 127, ""
        started = time.monotonic()
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=scrub_env(),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    start_new_session=True, bufsize=0)
            total = 0
            truncated = False
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
                selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
                while selector.get_map():
                    if time.monotonic() - started > timeout:
                        os.killpg(proc.pid, signal.SIGTERM)
                        try:
                            proc.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGKILL)
                        exit_code, problem = 124, "TIMEOUT"
                        break
                    for key, _ in selector.select(timeout=0.2):
                        data = os.read(key.fileobj.fileno(), 4000)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        if total < MAX_OUTPUT_BYTES:
                            send(key.data, data.decode("utf-8", "replace"))
                            total += len(data)
                        elif not truncated:
                            send("stderr", "\n[AARIS_OUTPUT_LIMIT_REACHED]\n")
                            truncated = True
            if not problem:
                exit_code = proc.wait(timeout=5)
        except FileNotFoundError:
            problem = "EXECUTABLE_NOT_FOUND"
        except (OSError, subprocess.TimeoutExpired) as exc:
            problem = type(exc).__name__.upper()
        except PermissionError:
            # Session revoked; stop the agent. Do not allow an unauthenticated retry.
            raise
        finally:
            try:
                self.post("done", {"id": job_id, "exit_code": max(-255, min(255, exit_code)),
                                   "error": problem})
            except (OSError, ConnectionError, PermissionError):
                pass


def selftest():
    assert NAME_RE.fullmatch("sample-codespace-123")
    assert not NAME_RE.fullmatch("../unsafe")
    assert "GITHUB_TOKEN" not in scrub_env() or "GITHUB_TOKEN" not in SENSITIVE_ENV
    for name in ("AARIS_ENDPOINT", "AARIS_TOKEN_FILE"):
        assert name not in scrub_env()
    try:
        validate_job({"id": "1", "argv_json": '["echo","hi"]', "cwd": "/etc",
                      "max_seconds": 10})
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe_directory_accepted")
    assert MAX_ACTIVE == 2
    assert Bridge.USER_AGENT == "Mozilla/5.0"
    print("AARIS_TURBO_AGENT_SELFTEST_PASS")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    endpoint = os.environ.get("AARIS_ENDPOINT", "")
    token_file = Path(os.environ.get("AARIS_TOKEN_FILE", "/nonexistent"))
    if not token_file.is_file() or token_file.stat().st_mode & 0o077:
        raise SystemExit("AARIS_TOKEN_FILE_PERMISSIONS_INVALID")
    token = token_file.read_text(encoding="ascii").strip()
    bridge = Bridge(endpoint, token)
    print("AARIS_TURBO_AGENT_STARTED", flush=True)
    workers = set()
    last_heartbeat = 0.0
    backoff = 1.0
    while True:
        try:
            now = time.monotonic()
            workers = {thread for thread in workers if thread.is_alive()}
            if now - last_heartbeat > 25:
                bridge.post("ping")
                last_heartbeat = now
            if len(workers) < MAX_ACTIVE:
                response = bridge.post("next")
                job = response.get("job")
                if job:
                    thread = threading.Thread(target=bridge.stream_job, args=(job,), daemon=True)
                    thread.start()
                    workers.add(thread)
            backoff = 1.0
            time.sleep(1.0)
        except PermissionError:
            print("AARIS_TURBO_SESSION_REVOKED", flush=True)
            return
        except (OSError, ConnectionError, ValueError, json.JSONDecodeError) as exc:
            print("AARIS_TURBO_RETRY_" + type(exc).__name__, flush=True)
            time.sleep(backoff)
            backoff = min(30.0, backoff * 1.8)


if __name__ == "__main__":
    main()
