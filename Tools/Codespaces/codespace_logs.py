#!/usr/bin/env python3
"""Read the owner's GitHub Codespace creation logs, emit ONLY safe fixed diagnostics.

No raw logs are written to GitHub Issues, artifacts, Actions output or other files.
"""
from __future__ import annotations
import re
import subprocess
import sys

PATTERNS = {
    "UBUNTU_IMAGE": r"ubuntu[-:]?22[.]04|ubuntu:22[.]04",
    "ALPINE_IMAGE": r"alpine[: ]?3[.]2|base:alpine",
    "POSTCREATE_STARTED": r"postcreatecommand|post-create|postcreate",
    "POSTCREATE_SUCCESS": r"AARIS_BOOTSTRAP_OK",
    "POSTSTART_SUCCESS": r"DISPLAY_READY",
    "PACKAGE_INSTALL_FAILED": r"apt-get.*(?:fail|error)|dpkg: error|unable to locate package|e: unable to|failed to fetch",
    "DISK_SPACE_ERROR": r"no space left on device|insufficient disk|disk.*full",
    "IMAGE_PULL_ERROR": r"failed to pull|manifest unknown|image pull.*fail|failed to resolve image",
    "DEVCONTAINER_BUILD_FAILED": r"failed to create dev container|failed to build devcontainer|dev container.*failed|container build failed",
    "SSH_SERVER_ERROR": r"ssh.*(?:failed|refused|missing)|sshd.*(?:failed|error)|connection refused",
    "RECOVERY_MODE": r"recovery mode",
    "NETWORK_ERROR": r"network.*(?:timeout|unreachable)|tls.*error|certificate verify failed|connection reset",
}
def scan(text: str) -> list[str]:
    return [name for name, pattern in PATTERNS.items() if re.search(pattern,text,re.I)]
def main(codespace: str) -> int:
    if not re.fullmatch(r"[A-Za-z0-9-]{3,120}",codespace):
        print("CODESPACE_LOGS_INVALID_NAME"); return 2
    print("AARIS_CODESPACE_LOG_REPORT")
    try:
        out=subprocess.run(["gh","codespace","logs","-c",codespace],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=85,
            text=True,errors="replace",check=False)
    except (OSError,subprocess.TimeoutExpired):
        print("CODESPACE_LOGS_COMMAND_FAILED"); return 3
    if out.returncode:
        print("CODESPACE_LOGS_COMMAND_NONZERO"); return 4
    content=out.stdout[-700000:]
    print("CODESPACE_LOGS_ACQUIRED")
    print("CODESPACE_LOGS_EMPTY" if not content.strip() else "CODESPACE_LOGS_NONEMPTY")
    for name in scan(content):
        print("CODESPACE_LOG_"+name)
    # Deliberately do not expose any original log line or runtime exception.
    return 0
def selftest():
    assert "PACKAGE_INSTALL_FAILED" in scan("E: Unable to locate package abc")
    assert "UBUNTU_IMAGE" in scan("mcr.microsoft.com/devcontainers/base:ubuntu-22.04")
    assert "ALPINE_IMAGE" not in scan("ubuntu-22.04")
    assert not scan("Secret token=do-not-print")
    print("CODESPACE_LOG_DIAGNOSTIC_SELFTEST_PASS")
if __name__=="__main__":
    if "--selftest" in sys.argv: selftest()
    elif len(sys.argv)==2: raise SystemExit(main(sys.argv[1]))
    else: raise SystemExit(2)
