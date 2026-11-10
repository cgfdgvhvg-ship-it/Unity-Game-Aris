#!/usr/bin/env python3
"""Materialize only SHA-256-verified Git LFS cache into the fresh /tmp clone.

Never touches the source /workspaces project, original Unity installation,
Unity login state or LFS cache content. Does not trust unverified downloads.
"""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import shutil

ROOT = Path("/tmp/aaris-native-photo-worktrees")
SOURCE = Path("/workspaces/Unity-Game-Aris")
EXPECTED_REMOTE = "https://github.com/sundamunda289-art/Unity-Game-Aris.git"


def safe_git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        timeout=95, stderr=subprocess.DEVNULL,
    ).decode("utf-8", "replace").strip()


def run():
    if not SOURCE.is_dir() or not (SOURCE / ".git").is_dir():
        raise RuntimeError("SOURCE_MISSING")
    if not ROOT.is_dir() or ROOT.is_symlink() or ROOT.resolve() != ROOT:
        raise RuntimeError("TMP_ROOT_INVALID")
    # The only acceptable targets are independent fresh clones we created,
    # with a .git DIRECTORY (not a linked worktree marker) and exact SHA name.
    if len(sys.argv) > 2:
        raise RuntimeError("TOO_MANY_PROJECT_ARGUMENTS")
    explicit = Path(sys.argv[1]) if len(sys.argv) == 2 else None
    candidates = []
    for p in ROOT.iterdir():
        if explicit is not None and p != explicit:
            continue
        if not re.fullmatch(r"[a-f0-9]{40}", p.name):
            continue
        if not p.is_dir() or p.is_symlink() or not (p / ".git").is_dir():
            continue
        if safe_git(p, "rev-parse", "HEAD") != p.name:
            continue
        if safe_git(p, "remote", "get-url", "origin") != EXPECTED_REMOTE:
            continue
        candidates.append(p)
    if len(candidates) != 1:
        raise RuntimeError("FRESH_TMP_CLONE_NOT_UNIQUE")
    project = candidates[0]
    # Use checked-in, reviewed LFS functions in this same verified snapshot.
    sys.path.insert(0, str(project / "Tools" / "Codespaces"))
    from restore_preserved_source_lfs import (
        audit_pointers, candidate_matches, object_path, CACHE_ROOT
    )
    expected = audit_pointers(project)
    cache = CACHE_ROOT / project.name / "lfs" / "objects"
    # Fail before any writes unless ALL 793 OIDs are available and verified.
    for oid, size in expected.values():
        if not candidate_matches(object_path(cache, oid), oid, size):
            raise RuntimeError("CACHED_LFS_OID_INVALID_OR_MISSING")
    pending = []
    nonpointer_files = 0
    bytes_required = 0
    for relative, (oid, size) in expected.items():
        target = project / relative
        if not target.parent.resolve().is_relative_to(project):
            raise RuntimeError("TARGET_PATH_ESCAPES_PROJECT")
        if candidate_matches(target, oid, size):
            continue
        if target.is_symlink() or not target.is_file():
            raise RuntimeError("TARGET_NOT_PLAIN_FILE")
        # This is an independently freshly cloned disposable /tmp snapshot,
        # not the owner's dirty source project. Its LFS filter may have left
        # pointer variants or incomplete object bytes in place; the correct
        # output is the SHA-verified HEAD OID from our authenticated cache.
        # Never replace any non-LFS path, links, or paths outside this clone.
        head_pointer = subprocess.check_output(
            ["git", "-C", str(project), "show", "HEAD:" + relative],
            timeout=30, stderr=subprocess.DEVNULL)
        if target.stat().st_size != len(head_pointer):
            nonpointer_files += 1
        else:
            with target.open("rb") as stream:
                if stream.read(len(head_pointer) + 1) != head_pointer:
                    nonpointer_files += 1
        pending.append((relative, oid, size))
        bytes_required += size
    stat = os.statvfs(str(project))
    available = stat.f_bavail * stat.f_frsize
    print("TMP_HYDRATE_LFS_EXPECTED=" + str(len(expected)), flush=True)
    print("TMP_HYDRATE_LFS_PENDING=" + str(len(pending)), flush=True)
    print("TMP_HYDRATE_NONPOINTER_REPLACEMENTS=" + str(nonpointer_files), flush=True)
    print("TMP_HYDRATE_BYTES_REQUIRED=" + str(bytes_required), flush=True)
    if available < bytes_required + 256 * 1024 * 1024:
        raise RuntimeError("TMP_INSUFFICIENT_FREE_DISK")
    for relative, oid, size in pending:
        target = project / relative
        original = object_path(cache, oid)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=".aaris-lfs-",
                delete=False,
            ) as writer:
                temporary = Path(writer.name)
                with original.open("rb") as reader:
                    shutil.copyfileobj(reader, writer, 1024 * 1024)
                writer.flush()
                os.fsync(writer.fileno())
            if not candidate_matches(temporary, oid, size):
                raise RuntimeError("TEMPORARY_LFS_HASH_MISMATCH")
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    for relative, (oid, size) in expected.items():
        if not candidate_matches(project / relative, oid, size):
            raise RuntimeError("MATERIALIZED_LFS_HASH_MISMATCH")
    print("TMP_HYDRATE_LFS_VERIFIED=" + str(len(expected)), flush=True)
    print("AARIS_TMP_CLEAN_GITHUB_LFS_793_READY", flush=True)
    print("AARIS_TMP_ORIGINAL_WORKSPACE_UNCHANGED", flush=True)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch("[A-Z0-9_]{3,72}", reason):
            reason = "UNCLASSIFIED"
        print("AARIS_TMP_HYDRATE_FAILED_" + reason, flush=True)
        sys.exit(1)
