#!/usr/bin/env python3
"""One-time, SHA-verified recovery of 18 original native SpeedTree Git LFS objects.

Source: immutable Actions run 42472771253, not a reconstructed or placeholder mesh.
Never changes Git refs, original scene, TerrainData, prefabs, .meta or a Codespace.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SPECIES = ("Conifer", "Cypress", "Pine_A", "Pine_B", "Pine_C", "Pine_D")
PREFIX = "Assets/AarisWorld/Generated/TreeMass/"
PATHS = tuple(f"{PREFIX}{species}_LOD{lod}.asset"
              for species in SPECIES for lod in range(3))
SOURCE_SHA = "fb17b1c0fcf91900d15eb10666b2e279eb322f60"
POINTER = re.compile(
    rb"version https://git-lfs\.github\.com/spec/v1\n"
    rb"oid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?"
)


class RecoveryError(Exception):
    pass


def checked(*args, timeout=300):
    try:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=True, timeout=timeout).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise RecoveryError("GIT_OR_LFS_COMMAND_FAILED") from None


def load_verified_meshes(package: Path):
    if not package.is_file() or package.stat().st_size > 20_000_000:
        raise RecoveryError("ORIGINAL_PACKAGE_MISSING_OR_OVERSIZED")
    verified = {}
    try:
        with tarfile.open(package, mode="r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != 45 or len(set(names)) != len(names) or not all(
                member.isfile() and member.size <= 5_000_000 for member in members
            ):
                raise RecoveryError("PACKAGE_MEMBER_SET_INVALID")
            header = archive.getmember("mass-manifest.json")
            if header.size > 65_536:
                raise RecoveryError("PACKAGE_MANIFEST_OVERSIZED")
            manifest = json.load(archive.extractfile(header))
            if (manifest.get("kind") != "aaris_tree_mass_native_editor_bake"
                    or manifest.get("sourceSha") != SOURCE_SHA):
                raise RecoveryError("PACKAGE_PROVENANCE_MISMATCH")
            entries = manifest.get("files", [])
            records = {item["path"]: item for item in entries}
            if len(entries) != 44 or len(records) != 44:
                raise RecoveryError("PACKAGE_MANIFEST_DUPLICATE_OR_MISSING")
            for relative in PATHS:
                pointer = POINTER.fullmatch(checked("git", "show", f"HEAD:{relative}"))
                if pointer is None:
                    raise RecoveryError("MAIN_LFS_POINTER_INVALID")
                oid, expected_size = pointer.group(1).decode(), int(pointer.group(2))
                member = archive.getmember(relative)
                if member.size != expected_size or expected_size < 512:
                    raise RecoveryError("MESH_SIZE_DIFFERENT_FROM_MAIN")
                raw = archive.extractfile(member).read()
                if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != oid:
                    raise RecoveryError("MESH_SHA256_DIFFERENT_FROM_MAIN")
                entry = records.get(relative)
                if (entry is None or entry.get("sha256") != oid
                        or entry.get("bytes") != expected_size):
                    raise RecoveryError("MESH_MANIFEST_DIFFERENT_FROM_MAIN")
                if oid in verified:
                    raise RecoveryError("MESH_DUPLICATE_HASH")
                verified[oid] = raw
    except (tarfile.TarError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise RecoveryError("ARCHIVE_INVALID") from None
    if len(verified) != 18:
        raise RecoveryError("MESH_COUNT_INVALID")
    return verified


def lfs_media_dir():
    env = checked("git", "lfs", "env", timeout=30).decode("utf-8", "replace")
    line = next((s for s in env.splitlines() if s.startswith("LocalMediaDir=")), "")
    if not line:
        raise RecoveryError("LFS_LOCAL_MEDIA_UNAVAILABLE")
    media = Path(line.partition("=")[2]).resolve()
    git_dir = Path(checked("git", "rev-parse", "--absolute-git-dir")
                   .decode().strip()).resolve()
    # This workflow uses a clean hosted checkout; never write to an unknown cache.
    if media != (git_dir / "lfs" / "objects").resolve():
        raise RecoveryError("LFS_LOCAL_MEDIA_OUTSIDE_CHECKOUT")
    return media


def store_verified_objects(meshes):
    media = lfs_media_dir()
    for oid, raw in meshes.items():
        target = media / oid[:2] / oid[2:4] / oid
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != oid:
                raise RecoveryError("EXISTING_LOCAL_OBJECT_CORRUPT")
            continue
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as writer:
            temp = Path(writer.name)
            try:
                writer.write(raw)
                writer.flush()
                os.fsync(writer.fileno())
            except OSError:
                temp.unlink(missing_ok=True)
                raise
        try:
            if hashlib.sha256(temp.read_bytes()).hexdigest() != oid:
                raise RecoveryError("STAGED_OBJECT_HASH_MISMATCH")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)


def publish_and_remote_verify(meshes):
    if (os.getenv("GITHUB_REPOSITORY") != "sundamunda289-art/Unity-Game-Aris"
            or os.getenv("GITHUB_REF") != "refs/heads/main"
            or os.getenv("GITHUB_EVENT_NAME") not in ("push", "workflow_dispatch")):
        raise RecoveryError("UNAUTHORIZED_LFS_PUBLISH_CONTEXT")
    store_verified_objects(meshes)
    # --object-id sends ONLY the 18 original OIDs, not 775 unrelated LFS files.
    checked("git", "lfs", "push", "--object-id", "origin", *sorted(meshes),
            timeout=900)
    # Prove actual remote download with a NEW empty LFS cache, not our import.
    with tempfile.TemporaryDirectory(prefix="aaris-lfs-server-check-") as directory:
        checked("git", "-c", f"lfs.storage={directory}", "lfs", "fetch",
                f"--include={PREFIX}*", "--exclude=", "origin",
                checked("git", "rev-parse", "HEAD").decode().strip(), timeout=900)
        for oid, raw in meshes.items():
            downloaded = Path(directory) / "objects" / oid[:2] / oid[2:4] / oid
            if (not downloaded.is_file() or downloaded.stat().st_size != len(raw)
                    or hashlib.sha256(downloaded.read_bytes()).hexdigest() != oid):
                raise RecoveryError("REMOTE_LFS_REFETCH_UNVERIFIED")
    print("AARIS_TREE_LFS_REMOTE_REFETCH_VERIFIED=18", flush=True)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("--verify", "--push"):
        print("Usage: recover_verified_tree_lfs.py --verify|--push ORIGINAL.tar.gz")
        return 2
    try:
        meshes = load_verified_meshes(Path(sys.argv[2]))
        print("AARIS_ORIGINAL_TREE_MESH_POINTER_SHA256_VERIFIED=18", flush=True)
        if sys.argv[1] == "--push":
            publish_and_remote_verify(meshes)
        return 0
    except RecoveryError as exc:
        print("AARIS_TREE_LFS_RECOVERY_FAILED=" + str(exc), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
