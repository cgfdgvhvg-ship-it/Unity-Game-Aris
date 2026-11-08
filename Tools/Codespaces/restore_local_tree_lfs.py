#!/usr/bin/env python3
"""Recover exactly 18 verified new native tree LFS payloads from this Codespace.

The previous successful Unity mesh bake kept its byte-identical files in a
separate immutable worktree. If GitHub's LFS endpoint is unreachable from
this Codespace, store those 18 SHA-verified bytes atomically in git-lfs LocalMediaDir
and checkout this commit's verified pointers without redownloading.

Nothing is copied from any dirty GUI workspace. Neither scene nor source
SpeedTree models, TerrainData, original materials, .meta GUIDs, nor refs are
modified. All payloads must match the SHA256 and byte size recorded in HEAD.
"""
from __future__ import annotations
import hashlib
import os
import tempfile
from pathlib import Path
import re
import subprocess
import sys

SOURCES = Path("/tmp/aaris-tree-mass-worktrees")
PREFIX = "Assets/AarisWorld/Generated/TreeMass/"
SPECIES = ("Conifer", "Cypress", "Pine_A", "Pine_B", "Pine_C", "Pine_D")
PATHS = [PREFIX + f"{species}_LOD{level}.asset"
         for species in SPECIES for level in range(3)]
PTR = re.compile(
    rb"\Aversion https://git-lfs.github.com/spec/v1\n"
    rb"oid sha256:([a-f0-9]{64})\nsize ([0-9]+)\n?\Z"
)

def git(root: Path, *args: str, binary: bytes | None = None,
        timeout: int = 90) -> bytes:
    cmd = ["git", "-C", str(root), *args]
    p = subprocess.run(cmd, input=binary, capture_output=True,
                       timeout=timeout)
    if p.returncode:
        raise RuntimeError("GIT_OPERATION_FAILED")
    return p.stdout

def main(project: Path) -> None:
    project = project.resolve(strict=True)
    revision = git(project, "rev-parse", "HEAD").decode().strip()
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise RuntimeError("INVALID_COMMIT")
    if "aaris-native-photo-worktrees" not in project.parts:
        raise RuntimeError("WRONG_TARGET_WORKTREE")
    all_ptrs = {}
    for rel in PATHS:
        pointer = git(project, "show", "HEAD:" + rel)
        m = PTR.fullmatch(pointer)
        if m is None:
            raise RuntimeError("HEAD_TREE_POINTER_MISSING")
        all_ptrs[rel] = (m.group(1).decode("ascii"), int(m.group(2)))
    if len(all_ptrs) != 18:
        raise RuntimeError("BAD_TREE_MESH_COUNT")
    candidates = sorted(
        p for p in SOURCES.iterdir()
        if p.is_dir() and re.fullmatch(r"[0-9a-f]{40}", p.name)
        and all((p / rel).is_file() for rel in PATHS)
    )
    if len(candidates) != 1:
        raise RuntimeError("BAKED_SOURCE_AMBIGUOUS_OR_MISSING")
    original = candidates[0]
    # Verify all 18 pieces *before* modifying the local LFS cache.
    payloads = {}
    for rel, (oid, size) in all_ptrs.items():
        src = original / rel
        data = src.read_bytes()
        if not 100 <= len(data) <= 60_000_000 or len(data) != size:
            raise RuntimeError("CACHED_MESH_SIZE_MISMATCH")
        if hashlib.sha256(data).hexdigest() != oid:
            raise RuntimeError("CACHED_MESH_OID_MISMATCH")
        if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise RuntimeError("CACHED_MESH_NOT_HYDRATED")
        payloads[rel] = data
    print("TREE_LFS_SOURCE_HASH_VERIFIED=18", flush=True)
    # Resolve the git-lfs configured LocalMediaDir. It may be outside .git:
    # this Codespace deliberately uses a shared LFS cache across worktrees.
    env = git(project, "lfs", "env", timeout=30).decode(
        "utf-8", "replace"
    ).splitlines()
    values = [line.split("=", 1)[1] for line in env
              if line.startswith("LocalMediaDir=")]
    if len(values) != 1:
        raise RuntimeError("LFS_OBJECT_STORE_UNAVAILABLE")
    store = Path(values[0])
    if not store.is_absolute() or not store.name == "objects":
        raise RuntimeError("LFS_OBJECT_STORE_UNEXPECTED_PATH")
    store.mkdir(parents=True, exist_ok=True)
    # LFS v1 content-addressed storage: objects/aa/bb/<sha256>.
    # Write atomically, verify existing objects, never overwrite unrelated
    # original project files, and never depend on another remote LFS pull.
    added = 0
    for rel, raw in payloads.items():
        oid, size = all_ptrs[rel]
        subdir = store / oid[:2] / oid[2:4]
        subdir.mkdir(parents=True, exist_ok=True)
        target = subdir / oid
        if target.is_file():
            existing = target.read_bytes()
            if len(existing) != size or hashlib.sha256(existing).hexdigest() != oid:
                raise RuntimeError("LFS_EXISTING_OBJECT_HASH_MISMATCH")
            continue
        tmpname = None
        try:
            with tempfile.NamedTemporaryFile(
                    dir=subdir, prefix=".aaris-tree-", delete=False
            ) as tmp:
                tmpname = Path(tmp.name)
                tmp.write(raw)
                tmp.flush()
                os.fsync(tmp.fileno())
            if hashlib.sha256(tmpname.read_bytes()).hexdigest() != oid:
                raise RuntimeError("LFS_STAGED_OBJECT_HASH_MISMATCH")
            os.replace(str(tmpname), str(target))
            added += 1
        finally:
            if tmpname is not None and tmpname.exists():
                tmpname.unlink()
    print("TREE_LFS_LOCAL_CACHE_IMPORTED=" + str(added), flush=True)
    # Checkout only the 18 exact native tree assets. Their .meta, original
    # 775 LFS assets, scene, project settings, and all git refs are untouched.
    git(project, "lfs", "checkout", *PATHS, timeout=180)
    for rel, (oid, size) in all_ptrs.items():
        p = project / rel
        if not p.is_file() or p.stat().st_size != size:
            raise RuntimeError("TREE_MESH_CHECKOUT_MISSING")
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != oid:
            raise RuntimeError("TREE_MESH_CHECKOUT_HASH_MISMATCH")
    # Require complete hydration of the *current native main snapshot*.
    listing = git(project, "lfs", "ls-files", "--name-only").decode().splitlines()
    pending = 0
    for rel in listing:
        p = project / rel
        if not p.is_file():
            pending += 1
        else:
            with p.open("rb") as stream:
                if stream.read(110).startswith(
                    b"version https://git-lfs.github.com/spec/v1"
                ):
                    pending += 1
    if len(listing) != 793 or pending:
        raise RuntimeError("FULL_LFS_HYDRATION_NOT_VERIFIED")
    print("AARIS_TREE_LFS_CACHE_RECOVERY_PASSED", flush=True)
    print("tree_meshes=18", flush=True)
    print("lfs_tracked=" + str(len(listing)), flush=True)
    print("lfs_pointer_or_missing=0", flush=True)
    print("worktree_commit=" + revision, flush=True)

if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise RuntimeError("PROJECT_PATH_ARGUMENT_REQUIRED")
        main(Path(sys.argv[1]))
    except Exception as e:
        # No arbitrary stderr, filesystem paths, credential names or hashes.
        reason = str(e)
        if not re.fullmatch(r"[A-Z0-9_]{1,64}", reason):
            reason = "UNCLASSIFIED"
        print("TREE_LFS_CACHE_RECOVERY_FAILED=" + reason, flush=True)
        sys.exit(1)
