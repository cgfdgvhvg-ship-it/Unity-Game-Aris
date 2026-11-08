#!/usr/bin/env python3
"""Read-only LFS hydration check. Print counts only, no filenames/secrets."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
try:
    p = subprocess.run(["git", "lfs", "ls-files", "--name-only"],
                       cwd=ROOT, text=True, capture_output=True, timeout=35,
                       check=False)
except (OSError, subprocess.TimeoutExpired):
    print("AARIS_LFS_LIST_UNAVAILABLE")
    raise SystemExit(3)
if p.returncode:
    print("AARIS_LFS_LIST_UNAVAILABLE")
    raise SystemExit(3)
paths = [n for n in p.stdout.splitlines() if n]
if not paths:
    print("AARIS_LFS_TRACKED_ZERO")
    raise SystemExit(4)
missing = pointers = 0
for rel in paths:
    path = ROOT / rel
    try:
        with path.open("rb") as f:
            head = f.read(110)
        if head.startswith(b"version https://git-lfs.github.com/spec/v1"):
            pointers += 1
    except OSError:
        missing += 1
print(f"AARIS_LFS_TRACKED_{len(paths)}")
print(f"AARIS_LFS_POINTERS_{pointers}")
print(f"AARIS_LFS_MISSING_{missing}")
if pointers or missing:
    raise SystemExit(2)
print("AARIS_LFS_HYDRATED")
