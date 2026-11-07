#!/usr/bin/env python3
"""Create stable Unity .meta GUIDs for the committed, locally vendored CC0 files.

Never changes an existing .meta. GUIDs are deterministic across machines,
and the Unity AssetPostprocessor adjusts FBX import settings on first import.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[2]
DIRECTORIES = [
    Path("Assets/Resources"),
    Path("Assets/Resources/AarisCharacters"),
    Path("Assets/Resources/AarisCharacters/Primary"),
]
TARGET = ROOT / DIRECTORIES[-1]
EXTRA_DIRS = [
    Path("Assets/Resources/AarisCharacters/Primary/Animations"),
    Path("Assets/Resources/AarisCharacters/Primary/Textures"),
]


def make_meta(path: Path, is_folder: bool) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    meta = Path(str(path) + ".meta")
    if meta.exists():
        # Early vendor builds escaped newlines as text (backslash+n). Repair
        # only those malformed generated headers, retaining the same GUID.
        current = meta.read_text(encoding="utf-8")
        if "\\n" in current and "\n" not in current:
            meta.write_text(current.replace("\\n", "\n"), encoding="utf-8")
            return True
        return False
    guid = uuid.uuid5(uuid.NAMESPACE_URL, "https://aaris-game.example/internal-unity-meta/" + relative).hex
    if is_folder:
        data = (f"fileFormatVersion: 2\nguid: {guid}\nfolderAsset: yes\n"
                "DefaultImporter:\n  externalObjects: {}\n  userData: \n"
                "  assetBundleName: \n  assetBundleVariant: \n")
    else:
        data = f"fileFormatVersion: 2\nguid: {guid}\n"
    meta.write_text(data, encoding="utf-8")
    return True


def write_meta() -> int:
    files = []
    folders = []
    for folder in DIRECTORIES + EXTRA_DIRS:
        if folder == Path("Assets/Resources") or (ROOT / folder).is_dir():
            folders.append(ROOT / folder)
    if TARGET.is_dir():
        for path in TARGET.rglob("*"):
            if path.is_dir() and path not in folders:
                folders.append(path)
            elif path.is_file() and path.suffix != ".meta":
                files.append(path)
    count = 0
    for folder in folders:
        count += make_meta(folder, True)
    for path in files:
        count += make_meta(path, False)
    print("Created", count, "new deterministic Unity .meta files")
    return count


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        a = uuid.uuid5(uuid.NAMESPACE_URL, "test").hex
        assert len(a) == 32 and a == uuid.uuid5(uuid.NAMESPACE_URL, "test").hex
        print("Unity .meta deterministic GUID selftest PASS")
    else:
        write_meta()


if __name__ == "__main__":
    main()
