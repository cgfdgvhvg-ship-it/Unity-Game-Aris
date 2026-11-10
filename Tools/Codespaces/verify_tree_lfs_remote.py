#!/usr/bin/env python3
"""Verify all native TreeMass Git LFS objects from the authenticated remote.

Used when the old 2-day GitHub Actions source artifact has expired.
Read-only to source tree: fetches into an isolated temporary LFS object store
and checks each HEAD pointer's exact SHA-256 and byte length.
"""
from __future__ import annotations
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SPECIES=("Conifer","Cypress","Pine_A","Pine_B","Pine_C","Pine_D")
PREFIX="Assets/AarisWorld/Generated/TreeMass/"
PATHS=tuple(f"{PREFIX}{species}_LOD{lod}.asset" for species in SPECIES for lod in range(3))
POINTER=re.compile(rb"\Aversion https://git-lfs\.github\.com/spec/v1\noid sha256:([a-f0-9]{64})\nsize ([0-9]+)\n?\Z")


def main() -> int:
    pointers={}
    try:
        for path in PATHS:
            source=subprocess.run(
                ["git","show","HEAD:"+path],check=True,timeout=30,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout
            match=POINTER.fullmatch(source)
            if match is None:
                print("TREE_REMOTE_HEAD_POINTER_INVALID")
                return 2
            oid=match.group(1).decode("ascii")
            size=int(match.group(2))
            if not 512 <= size <= 60_000_000:
                print("TREE_REMOTE_HEAD_SIZE_INVALID")
                return 2
            pointers[path]=(oid,size)
        if len(pointers)!=18 or len({oid for oid,_ in pointers.values()})!=18:
            print("TREE_REMOTE_EXPECTED_18_DISTINCT_OIDS")
            return 3
        print("TREE_REMOTE_HEAD_18_POINTERS_VALID",flush=True)
        with tempfile.TemporaryDirectory(prefix="aaris-native-lfs-") as temp:
            cmd=["git","-c","lfs.storage="+temp,"lfs","fetch",
                 "--include="+PREFIX+"*","--exclude=","origin","HEAD"]
            result=subprocess.run(cmd,check=False,timeout=900,
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
            if result.returncode:
                print("TREE_REMOTE_LFS_DOWNLOAD_UNAVAILABLE")
                return 4
            for oid,size in pointers.values():
                src=Path(temp)/"objects"/oid[:2]/oid[2:4]/oid
                if not src.is_file() or src.is_symlink() or src.stat().st_size!=size:
                    print("TREE_REMOTE_LFS_OBJECT_MISSING")
                    return 5
                digest=hashlib.sha256()
                with src.open("rb") as f:
                    for part in iter(lambda:f.read(1024*1024),b""):
                        digest.update(part)
                if digest.hexdigest()!=oid:
                    print("TREE_REMOTE_LFS_SHA256_MISMATCH")
                    return 6
        print("TREE_REMOTE_18_NATIVE_MESH_OIDS_SHA256_VERIFIED",flush=True)
        return 0
    except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError):
        print("TREE_REMOTE_VERIFICATION_UNAVAILABLE")
        return 7

if __name__=="__main__":
    sys.exit(main())
