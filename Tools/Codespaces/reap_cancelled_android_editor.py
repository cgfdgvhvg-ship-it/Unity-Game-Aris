#!/usr/bin/env python3
"""Stop only the orphaned native Unity batch process from a cancelled APK retry."""
import os
import signal
import subprocess
import time
from pathlib import Path

OLD_SHA = "53a25731850010e9a49b5157c35b85fd8c74ab39"
WORKTREE = "/tmp/aaris-native-android-build-worktrees/" + OLD_SHA
proc = subprocess.run(
    ["git", "-C", WORKTREE, "rev-parse", "HEAD"],
    capture_output=True, text=True, timeout=10
)
if proc.returncode != 0 or proc.stdout.strip() != OLD_SHA:
    print("APK_STALE_EDITOR_WORKTREE_NOT_VERIFIED")
    raise SystemExit(0)

def matches(pid):
    try:
        raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
        args = raw.decode("utf-8", "replace").split("\x00")
    except (OSError, ValueError):
        return False
    if not args or not args[0].endswith("/Editor/Unity"):
        return False
    for i, arg in enumerate(args[:-1]):
        if arg == "-projectPath" and args[i+1].rstrip("/") == WORKTREE:
            return "-buildTarget" in args and "Android" in args
    return False

processes = []
for item in Path("/proc").iterdir():
    if item.name.isdigit():
        pid = int(item.name)
        if pid != os.getpid() and matches(pid):
            processes.append(pid)
print("APK_OLD_CANCELLED_EDITORS_FOUND=" + str(len(processes)))
for pid in processes:
    try:
        if matches(pid):
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
for _ in range(10):
    if not any(matches(pid) for pid in processes):
        break
    time.sleep(1)
for pid in processes:
    try:
        if matches(pid):
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
print("APK_OLD_CANCELLED_EDITOR_CLEANUP_COMPLETE")
