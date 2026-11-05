#!/usr/bin/env python3
"""Read-only reconciliation of original Unity project vs isolated Unity scratch import.

Reports selected source asset and .meta hashes without changing either project.
This tool deliberately CANNOT promote a scratch file to the original project.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

DEFAULT_PATHS = (
    "Assets/TerrainDemoScene_URP/Terrain/Data/"
    "Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset",
    "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity",
    "Assets/AarisWorld/Editor/AarisLiveEditorBridge.cs",
    "Assets/Editor/AarisBatchProbe.cs",
)
ALLOWED = {".asset", ".unity", ".prefab", ".mat", ".meta", ".cs"}
MAX_ASSETS = 32
MAX_HASH_BYTES = 1024 ** 3


class AuditError(Exception):
    pass


def relative_asset(value: str) -> str:
    if not isinstance(value, str) or "\0" in value or "\\" in value:
        raise AuditError("Unsupported asset path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not value.startswith("Assets/"):
        raise AuditError("Only repository-relative Assets/... paths are permitted")
    if path.suffix not in ALLOWED or value.endswith("/"):
        raise AuditError("Asset type not approved for reconciliation")
    return path.as_posix()


def hash_asset(root: Path, relative: str) -> dict:
    path = root.joinpath(*PurePosixPath(relative).parts)
    if any(p.is_symlink() for p in (root, *list(path.parents)[:-1], path)):
        return {"state": "unsafe_symlink"}
    try:
        st = path.stat()
    except FileNotFoundError:
        return {"state": "missing"}
    except OSError:
        return {"state": "unreadable"}
    if not path.is_file():
        return {"state": "not_regular_file"}
    if st.st_size > MAX_HASH_BYTES:
        return {"state": "oversized", "bytes": st.st_size}
    h = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return {"state": "unreadable"}
    return {"state": "ok", "bytes": st.st_size, "sha256": h.hexdigest()}


def owner_protected(project: Path) -> set[str]:
    commands = [
        ["git", "-C", str(project), "diff", "--name-only", "-z", "HEAD", "--"],
        ["git", "-C", str(project), "ls-files", "--others", "--exclude-standard", "-z"],
    ]
    names: set[str] = set()
    for args in commands:
        proc = subprocess.run(args, check=False, capture_output=True, timeout=25)
        if proc.returncode:
            raise AuditError("Cannot verify owner-modified/untracked source files")
        names.update(
            value.decode("utf-8", "surrogateescape")
            for value in proc.stdout.split(b"\0") if value
        )
    return names


def reconcile(project: Path, scratch: Path, assets: list[str]) -> dict:
    if not project.is_dir() or project.is_symlink():
        raise AuditError("Original project missing or symlinked")
    if not scratch.is_dir() or scratch.is_symlink():
        raise AuditError("Scratch project missing or symlinked")
    if not assets or len(assets) > MAX_ASSETS:
        raise AuditError("Require 1..32 explicitly selected assets")
    protected = owner_protected(project)
    paths: list[str] = []
    for name in assets:
        safe = relative_asset(name)
        if safe not in paths:
            paths.append(safe)
        if not safe.endswith(".meta"):
            mate = safe + ".meta"
            if mate not in paths:
                paths.append(mate)
    items = []
    summary = {"same": 0, "different": 0, "missing": 0, "unverified": 0}
    for name in paths:
        original = hash_asset(project, name)
        experimental = hash_asset(scratch, name)
        status = "unverified"
        if original["state"] == "ok" and experimental["state"] == "ok":
            status = "same" if original["sha256"] == experimental["sha256"] else "different"
        elif original["state"] == "missing" or experimental["state"] == "missing":
            status = "missing"
        summary[status] += 1
        items.append({
            "file": name, "comparison": status,
            "owner_modified_or_untracked": name in protected,
            "original": original, "scratch": experimental,
            "promotion_allowed": False,
        })
    return {
        "mode": "read_only", "original_project": str(project),
        "scratch_project": str(scratch), "summary": summary,
        "original_dirty_or_untracked_count": len(protected),
        "assets": items, "writes_performed": 0,
        "promotion_allowed": False,
        "note": ("This is NOT a three-way merge: the scratch copy may contain "
                 "changes by Unity import or testing; never overwrite original "
                 "dirty files without a base snapshot, owner's approval, "
                 "conflict check and a verified Git LFS workflow."),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path,
                        default=Path("/workspaces/Unity-Game-Aris"))
    parser.add_argument("--scratch", type=Path,
                        default=Path("/tmp/aaris-unity-batch/project"))
    parser.add_argument("--asset", action="append",
                        help="Approved Assets-relative path, repeatable")
    args = parser.parse_args(argv)
    try:
        result = reconcile(args.original, args.scratch,
                           args.asset if args.asset else list(DEFAULT_PATHS))
    except (AuditError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"state": "error", "message": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
