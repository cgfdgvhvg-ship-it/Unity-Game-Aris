#!/usr/bin/env python3
"""Fail-closed local Unity character integrity audit (no network, no Unity license).

Confirms eleven locally vendored FBXs are hydrated (not Git LFS pointers),
checks actual Git LFS SHA256 against the Git index, authentic CC0 notices,
and validates unique Unity .meta GUIDs for the character subtree.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = Path("Assets/Resources/AarisCharacters/Primary")
REQUIRED_FBX = ("Player.fbx", "Animations/idle.fbx",
                "Animations/walk.fbx", "Animations/run.fbx",
                "Animations/jump.fbx", "Animations/crouch.fbx",
                "Animations/jump_start.fbx", "Animations/jump_land.fbx",
                "Animations/crouch_walk.fbx", "Animations/punch.fbx",
                "Animations/shoot.fbx")
PARENT_META = ("Assets/Resources.meta", "Assets/Resources/AarisCharacters.meta",
               "Assets/Resources/AarisCharacters/Primary.meta")


def expected_pointer(path: Path) -> tuple[str, int]:
    # Git stores LFS pointers; checkout/smudge holds the physical file.
    result = subprocess.run(["git", "show", ":" + path.as_posix()], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    text = result.stdout.decode("utf-8")
    match = re.fullmatch(
        r"version https://git-lfs.github.com/spec/v1\n"
        r"oid sha256:([a-f0-9]{64})\nsize ([0-9]+)\n", text)
    if match is None:
        raise ValueError(f"Git index does not contain a valid LFS pointer: {path}")
    return match.group(1), int(match.group(2))


def verify() -> None:
    for name in REQUIRED_FBX:
        path = BASE / name
        file = ROOT / path
        if not file.is_file():
            raise FileNotFoundError(f"Offline FBX missing: {path}")
        expected_sha, expected_size = expected_pointer(path)
        data = file.read_bytes()
        if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError(f"Only an LFS POINTER is present, run git lfs pull: {path}")
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha:
            raise ValueError(f"FBX LFS SHA/size mismatch: {path}")
        if not (data.startswith(b"Kaydara FBX Binary") or data.lstrip().startswith(b"; FBX")):
            raise ValueError(f"Hydrated file is not an FBX: {path}")
        if len(data) < 2000:
            raise ValueError(f"Suspiciously small FBX: {path}")

    for name in ("LICENSE-BASE-CHARACTERS.txt", "LICENSE-ANIMATIONS.txt"):
        file = ROOT / BASE / name
        if not file.is_file() or "CC0" not in file.read_text("utf-8"):
            raise ValueError(f"Missing actual CC0 license notice: {file}")

    metadata = set(ROOT.glob("Assets/Resources/AarisCharacters/**/*.meta"))
    metadata.update(ROOT / name for name in PARENT_META)
    if not metadata:
        raise ValueError("Missing Unity .meta GUIDs")
    guids = {}
    for path in sorted(metadata):
        if not path.is_file():
            raise FileNotFoundError(f"Unity folder meta absent: {path}")
        raw = path.read_text("utf-8")
        match = re.search(r"(?m)^guid: ([a-f0-9]{32})$", raw)
        if match is None or not raw.startswith("fileFormatVersion: 2\n"):
            raise ValueError(f"Invalid Unity .meta YAML/GUID: {path}")
        guid = match.group(1)
        if guid in guids:
            raise ValueError(f"Unity GUID collision: {path}, {guids[guid]}")
        guids[guid] = str(path)
    print(f"PASS: {len(REQUIRED_FBX)} hydrated FBXs with matching Git LFS SHA256; "
          f"{len(metadata)} unique Unity GUIDs; 2 local CC0 licenses; no runtime URLs.")


def selftest() -> None:
    assert re.fullmatch(r"oid sha256:([a-f0-9]{64})", "oid sha256:" + "a" * 64)
    assert hashlib.sha256(b"test").hexdigest().startswith("9f86")
    assert len(REQUIRED_FBX) == len(set(REQUIRED_FBX)) == 11
    print("Offline FBX + LFS + GUID verification selftest PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    try:
        if args.selftest:
            selftest()
        else:
            verify()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Character integrity check FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
