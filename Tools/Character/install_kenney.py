#!/usr/bin/env python3
"""Install Kenney's CC0 rigged humanoid and FBX clips into Unity Resources.

No Unity license or Editor is needed to download. Binary files are intentionally
not checked in by this installer; review and commit the generated asset changes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "Assets/Resources/AarisCharacters/Kenney"
SOURCE_PAGE = "https://kenney.nl/assets/animated-characters-retro"
SOURCE_ZIP = (
    "https://kenney.nl/media/pages/assets/animated-characters-retro/"
    "93305a3c49-1774772819/kenney_animated-characters-retro.zip"
)
# Reviewed source distribution, see Docs/CHARACTER_UPGRADE.md.
EXPECTED_SHA256 = "1d03f1fb001f3cf629425b69c898df58261a316616220ea25b58bd35298e6882"
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
MAX_EXTRACT_BYTES = 24 * 1024 * 1024
REQUIRED_FBX = ("characterMedium", "idle", "run", "jump")


def verify_zip(data: bytes) -> dict[str, bytes]:
    if not 0 < len(data) <= MAX_DOWNLOAD_BYTES:
        raise ValueError("Character archive has unexpected size")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files: dict[str, bytes] = {}
        total = 0
        for info in archive.infolist():
            if info.is_dir():
                continue
            path = Path(info.filename.replace("\\", "/"))
            if ".." in path.parts or info.filename.startswith("/") or ":" in info.filename:
                raise ValueError("Unsafe path in character archive")
            total += info.file_size
            if total > MAX_EXTRACT_BYTES or info.file_size > MAX_DOWNLOAD_BYTES:
                raise ValueError("Archive exceeds safe extraction size")
            suffix = path.suffix.lower()
            if suffix not in (".fbx", ".png"):
                continue
            stem = path.stem.lower()
            if suffix == ".fbx":
                canonical = next((name for name in REQUIRED_FBX if stem == name.lower()), None)
                if canonical is None:
                    continue
                name = canonical + ".fbx"
            else:
                name = path.name
            if name in files:
                raise ValueError("Duplicated asset name " + name)
            payload = archive.read(info)
            if not payload:
                raise ValueError("Empty asset " + name)
            files[name] = payload
    missing = [name for name in REQUIRED_FBX if name + ".fbx" not in files]
    if missing:
        raise ValueError("Missing model/animation FBX: " + ", ".join(missing))
    if not any(name.endswith(".png") for name in files):
        raise ValueError("No character skin PNG present")
    return files


def install(data: bytes, *, check_hash: bool = True, dry_run: bool = False) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    if check_hash and digest != EXPECTED_SHA256:
        raise ValueError("Source ZIP SHA-256 mismatch; refuse unreviewed asset revision")
    assets = verify_zip(data)
    manifest = {
        "provider": "Kenney",
        "pack": "Animated Characters Retro",
        "license": "CC0-1.0",
        "source": SOURCE_PAGE,
        "sha256": digest,
        "files": sorted(assets),
    }
    if not dry_run:
        DEST.mkdir(parents=True, exist_ok=True)
        for filename, payload in sorted(assets.items()):
            destination = DEST / filename
            if destination.exists() and destination.read_bytes() == payload:
                continue
            destination.write_bytes(payload)
        (DEST / "asset-source.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return manifest


def selftest() -> None:
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as z:
        for name in REQUIRED_FBX:
            z.writestr("Models/" + name + ".fbx", b"example-fbx")
        z.writestr("Skins/humanMale.png", b"example-png")
    manifest = install(memory.getvalue(), check_hash=False, dry_run=True)
    assert "characterMedium.fbx" in manifest["files"]
    assert "run.fbx" in manifest["files"]
    try:
        verify_zip(b"not-a-zip")
    except zipfile.BadZipFile:
        pass
    else:
        raise AssertionError("Invalid ZIP passed")
    print("Character archive validation, deterministic extraction: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, help="Previously downloaded official ZIP")
    parser.add_argument("--allow-updated-source", action="store_true",
                        help="Permit a reviewed updated official archive without the pinned hash")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    try:
        if args.archive:
            data = args.archive.read_bytes()
        else:
            request = urllib.request.Request(
                SOURCE_ZIP, headers={"User-Agent": "AarisCharacterInstaller/1.0"}
            )
            with urllib.request.urlopen(request, timeout=40) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
        manifest = install(data, check_hash=not args.allow_updated_source)
        print("Character installed:", DEST.relative_to(ROOT))
        print("FBX + textures:", len(manifest["files"]), "SHA-256:", manifest["sha256"])
        print("Review and commit imported asset bytes and generated Unity .meta files.")
        return 0
    except (OSError, ValueError, urllib.error.URLError, zipfile.BadZipFile) as error:
        print("Character installation failed:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
