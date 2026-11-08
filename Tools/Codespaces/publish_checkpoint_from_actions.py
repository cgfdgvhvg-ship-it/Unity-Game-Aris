#!/usr/bin/env python3
"""Publish only the 210 edited Unity files using authenticated Actions runner.

The existing Codespace is READ-ONLY: its immutable snapshot gets transferred
from /tmp, then one LFS object and the review Git ref are pushed from the
GitHub Actions runner using GitHub's proper authenticated LFS endpoint.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO = Path(os.environ["GITHUB_WORKSPACE"])
REMOTE_ARCHIVE = "/tmp/aaris-codespaces/working-changes-checkpoint/validated-unity-edits.tar.gz"
BRANCH = "backup/codespace-local-changes-20261108"


def shell(args, *, stdin=None, stdout=None, timeout=240):
    return subprocess.run(
        args,
        stdin=stdin,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        cwd=REPO,
        check=False,
    )


def abort(message):
    print(message, flush=True)
    raise SystemExit(1)


def git(*args, timeout=300):
    result = shell(["git", *args], timeout=timeout)
    if result.returncode:
        abort("AARIS_RUNNER_GIT_OPERATION_FAILED")
    return result.stdout


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-zA-Z0-9-]{3,100}", sys.argv[1]):
        abort("AARIS_RUNNER_INVALID_CODESPACE")
    cs = sys.argv[1]
    exporter = REPO / "Tools/Codespaces/export_checkpoint_for_actions.sh"
    if not exporter.is_file() or not (REPO / ".git").exists():
        abort("AARIS_RUNNER_SOURCE_MISSING")

    with tempfile.TemporaryDirectory(prefix="aaris-lfs-publish-") as dirname:
        work = Path(dirname)
        with exporter.open("rb") as script:
            result = shell(["gh", "codespace", "ssh", "-c", cs, "--", "bash -s"],
                           stdin=script, timeout=340)
        safe = result.stdout.decode(errors="replace")
        for line in safe.splitlines():
            if re.fullmatch(r"AARIS_EXPORT_[A-Z0-9_]{3,80}", line):
                print(line, flush=True)
            elif re.fullmatch(r"(tracked_changed_count|lfs_changed_count|lfs_object_bytes|package_bytes)=[0-9]{1,14}", line):
                print(line, flush=True)
        if result.returncode:
            abort("AARIS_RUNNER_CODESPACE_EXPORT_FAILED")

        raw_b64 = work / "snapshot.b64"
        with raw_b64.open("wb") as dest:
            result = shell(["gh", "codespace", "ssh", "-c", cs, "--",
                            "base64 " + REMOTE_ARCHIVE],
                           stdout=dest, timeout=900)
        if result.returncode:
            abort("AARIS_RUNNER_CODESPACE_ARCHIVE_TRANSFER_FAILED")
        with (work / "snapshot.tar.gz").open("wb") as dest, raw_b64.open("rb") as source:
            result = shell(["base64", "--decode"], stdin=source, stdout=dest, timeout=180)
        raw_b64.unlink()
        if result.returncode:
            abort("AARIS_RUNNER_ARCHIVE_DECODE_FAILED")

        archive = work / "snapshot.tar.gz"
        if archive.stat().st_size > 660 * 1024**2:
            abort("AARIS_RUNNER_ARCHIVE_TOO_LARGE")
        try:
            with tarfile.open(archive, "r:gz") as tf:
                members = tf.getmembers()
                if {m.name for m in members} != {"manifest.json", "checkpoint.patch", "one-lfs-object.bin"}:
                    abort("AARIS_RUNNER_UNEXPECTED_ARCHIVE_FILES")
                if len(members) != 3 or any(not m.isfile() or m.size > 512 * 1024**2 for m in members):
                    abort("AARIS_RUNNER_UNSAFE_ARCHIVE")
                for member in members:
                    with tf.extractfile(member) as origin, (work / member.name).open("wb") as dest:
                        shutil.copyfileobj(origin, dest)
        except (OSError, tarfile.TarError):
            abort("AARIS_RUNNER_INVALID_ARCHIVE")

        data = json.loads((work / "manifest.json").read_text())
        files = data.get("files", [])
        if (data.get("kind") != "aaris_codespace_working_assets_checkpoint" or
            data.get("branch") != BRANCH or not isinstance(files, list) or
            len(files) != 210 or data.get("changedCount") != 210 or
            data.get("lfsChangedCount") != 1):
            abort("AARIS_RUNNER_MANIFEST_INVALID")
        paths = [r["path"] for r in files]
        if len(set(paths)) != 210 or any(
            not re.fullmatch(r"(Assets|Packages|ProjectSettings|Tools|Docs)/[A-Za-z0-9_.() /-]{1,350}", p)
            or "/.." in p for p in paths
        ):
            abort("AARIS_RUNNER_PATH_SCOPE_INVALID")

        lfs = [r for r in files if r.get("lfs")]
        if len(lfs) != 1:
            abort("AARIS_RUNNER_LFS_SCOPE_INVALID")
        oid = lfs[0]["sha256"]
        raw = work / "one-lfs-object.bin"
        if (not re.fullmatch(r"[0-9a-f]{64}", oid) or
            raw.stat().st_size != lfs[0]["bytes"] or
            hashlib.sha256(raw.read_bytes()).hexdigest() != oid):
            abort("AARIS_RUNNER_LFS_DATA_MISMATCH")
        print("AARIS_RUNNER_EXACT_210_EDITED_FILES_VERIFIED", flush=True)
        print("lfs_changed_count=1", flush=True)
        print("lfs_object_bytes=" + str(raw.stat().st_size), flush=True)

        git("config", "user.name", "Aaris Codespace Changes")
        git("config", "user.email", "codespace-recovery@users.noreply.github.com")
        git("lfs", "install", "--local")
        result = shell(["git", "am", "--3way", str(work / "checkpoint.patch")])
        if result.returncode:
            shell(["git", "am", "--abort"])
            abort("AARIS_RUNNER_PATCH_CONFLICT_REVIEW_REQUIRED")
        actual = sorted(p for p in git("diff-tree", "--no-commit-id",
                                       "--name-only", "-r", "-z", "HEAD").decode().split("\0") if p)
        if actual != sorted(paths):
            abort("AARIS_RUNNER_COMMIT_PATHS_DIFFER_FROM_210_EDITS")
        print("AARIS_RUNNER_ONLY_210_TRACKED_CHANGES_APPLIED", flush=True)

        gitdir = Path(git("rev-parse", "--git-dir").decode().strip())
        target = gitdir / "lfs" / "objects" / oid[:2] / oid[2:4] / oid
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(raw, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != oid:
            abort("AARIS_RUNNER_LOCAL_LFS_CACHE_INVALID")

        result = shell(["git", "lfs", "push", "--object-id", "origin", oid], timeout=460)
        if result.returncode:
            msg = result.stderr.decode(errors="replace")[-30000:]
            if re.search(r"403|401|authorization|authentication|permission denied", msg, re.I):
                abort("AARIS_RUNNER_LFS_AUTH_DENIED")
            if re.search(r"quota|billing|storage limit", msg, re.I):
                abort("AARIS_RUNNER_LFS_QUOTA_REACHED")
            if re.search(r"batch response|invalid character|html", msg, re.I):
                abort("AARIS_RUNNER_LFS_BATCH_RESPONSE_INVALID")
            abort("AARIS_RUNNER_LFS_UPLOAD_FAILED")
        print("AARIS_RUNNER_ONE_NEW_LFS_OBJECT_UPLOADED", flush=True)

        exists = shell(["git", "ls-remote", "--exit-code", "--heads", "origin", BRANCH])
        if exists.returncode == 0:
            abort("AARIS_RUNNER_REVIEW_BRANCH_ALREADY_EXISTS")
        result = shell(["git", "push", "origin", "HEAD:refs/heads/" + BRANCH], timeout=320)
        if result.returncode:
            msg = result.stderr.decode(errors="replace")[-30000:]
            if re.search(r"403|permission denied|write access|authentication", msg, re.I):
                abort("AARIS_RUNNER_BRANCH_PUSH_AUTH_DENIED")
            abort("AARIS_RUNNER_BRANCH_PUSH_FAILED")
        dest = REPO / "codespace-results"
        dest.mkdir(exist_ok=True)
        shutil.copyfile(work / "manifest.json", dest / "changes-manifest.json")
        print("AARIS_RUNNER_EXACT_210_FILES_UPLOADED_TO_GITHUB", flush=True)
        print("checkpoint_branch=" + BRANCH, flush=True)
        print("checkpoint_sha=" + git("rev-parse", "HEAD").decode().strip(), flush=True)
        print("tracked_changed_count=210", flush=True)
        print("AARIS_RUNNER_ORIGINAL_CODESPACE_UNTOUCHED", flush=True)


if __name__ == "__main__":
    main()
