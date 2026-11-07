#!/usr/bin/env python3
"""Pin and install local CC0 Quaternius male + motion-capture-compatible animations.

One-time vendoring only. Runtime never requests network content. The downloaded
GLB files are verified against SHA-256 and Git blob SHA, converted by Blender
to FBX, then committed through Git LFS into Assets/Resources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Assets" / "Resources" / "AarisCharacters" / "Primary"
BASE = ("https://raw.githubusercontent.com/Seyamalam/blood-league-kickoff/"
        "aa02a4e6d8337a0604d2da131bcbbeb1f01badf0/"
        "public/assets/vendor/quaternius/")
ASSETS = (
    {
        "file": "night-striker.glb",
        "size": 6465208,
        "sha256": "a466828c67a4acc9b2413212ce6d9cde235e3aed9b675680c14fd9673858f118",
        "gitblob": "14697e33502e41ddbc1b7fdbf56bbf0478027700",
    },
    {
        "file": "universal-animation-library.glb",
        "size": 2714756,
        "sha256": "4c748767741a3e495d89667b9a218b690ba9810b9517a12e960780e3ca72c4e9",
        "gitblob": "4fccf561b9b2ef73f611efe21981ef8739080065",
    },
)
LICENSE_FILES = {
    "LICENSE-BASE-CHARACTERS.txt": "CC0-1.0 Quaternius Universal Base Characters",
    "LICENSE-ANIMATIONS.txt": "CC0-1.0 Quaternius Universal Animation Library",
}


def verify(asset: dict, data: bytes) -> None:
    if len(data) != asset["size"]:
        raise ValueError("Unexpected binary size: " + asset["file"])
    if hashlib.sha256(data).hexdigest() != asset["sha256"]:
        raise ValueError("SHA-256 mismatch: " + asset["file"])
    blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    if hashlib.sha1(blob).hexdigest() != asset["gitblob"]:
        raise ValueError("Git blob SHA mismatch: " + asset["file"])
    if data[:4] != b"glTF" or int.from_bytes(data[4:8], "little") != 2:
        raise ValueError("Not a valid GLB 2.0 header: " + asset["file"])
    if int.from_bytes(data[8:12], "little") != len(data):
        raise ValueError("Invalid GLB length: " + asset["file"])


def download(url: str, limit: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Aaris-CC0-Asset-Vendor/1.0"})
    with urllib.request.urlopen(req, timeout=100) as res:
        result = res.read(limit + 1)
    if len(result) > limit:
        raise ValueError("Download exceeded pinned size limit")
    return result


def selftest() -> None:
    for asset in ASSETS:
        assert asset["file"].endswith(".glb")
        assert len(asset["sha256"]) == 64
        assert len(asset["gitblob"]) == 40
    try:
        verify(ASSETS[0], b"not a glb")
    except ValueError:
        pass
    else:
        raise AssertionError("Untrusted data was accepted")
    assert (ROOT / "Tools/Character/export_quaternius_blender.py").is_file()
    print("Pinned sources, tamper rejection and exporter location: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", default="blender", help="Executable Blender binary")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--asset-cache", type=Path, help="Offline directory holding already verified GLB and license files")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    if shutil.which(args.blender) is None and not Path(args.blender).is_file():
        print("Blender is required for one-time GLB to Humanoid FBX conversion.", file=sys.stderr)
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix="aaris-cc0-vendor-") as scratch:
            cache = Path(scratch)
            for asset in ASSETS:
                source = args.asset_cache / asset["file"] if args.asset_cache else None
                data = source.read_bytes() if source else download(BASE + asset["file"], asset["size"])
                verify(asset, data)
                (cache / asset["file"]).write_bytes(data)
            OUT.mkdir(parents=True, exist_ok=True)
            args_blender = [
                args.blender, "--background", "--factory-startup",
                "--python", str(ROOT / "Tools/Character/export_quaternius_blender.py"),
                "--", "--model", str(cache / ASSETS[0]["file"]),
                "--animations", str(cache / ASSETS[1]["file"]),
                "--output", str(OUT)
            ]
            subprocess.run(args_blender, cwd=ROOT, check=True, timeout=1200)
            if not (OUT / "Player.fbx").is_file() or (OUT / "Player.fbx").stat().st_size < 6000:
                raise RuntimeError("Blender did not export a valid male FBX")
            found_clips = [x.stem for x in (OUT / "Animations").glob("*.fbx")]
            required = {"idle", "walk", "run", "jump", "jump_start", "jump_land",
                        "crouch", "crouch_walk", "punch", "shoot"}
            if not required <= set(found_clips):
                raise RuntimeError("Required humanoid motion clips missing: " + repr(found_clips))
            for path, description in LICENSE_FILES.items():
                source = args.asset_cache / path if args.asset_cache else None
                content = source.read_bytes() if source else download(BASE + path, 5000)
                if b"CC0" not in content and b"Creative Commons Zero" not in content:
                    raise ValueError("No CC0 dedication in supplied license: " + path)
                (OUT / path).write_bytes(content)
            manifest = {
                "title": "Aaris male superhero rigged character + locomotion",
                "original_author": "Quaternius",
                "license": "CC0-1.0",
                "model_source": "https://quaternius.com/packs/universalbasecharacters.html",
                "animation_source": "https://quaternius.com/packs/universalanimationlibrary.html",
                "source_redistributor": "Seyamalam/blood-league-kickoff (audited CC0)",
                "files": [{k: a[k] for k in ("file", "sha256", "size", "gitblob")} for a in ASSETS],
                "vendor_output": ["Player.fbx"] + ["Animations/" + name + ".fbx" for name in sorted(found_clips)],
                "runtime_network_required": False
            }
            (OUT / "asset-source.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print("Verified local CC0 male character and animations:", OUT)
            print("Clips:", ", ".join(sorted(found_clips)))
            print("The FBX / texture bytes must be committed to Git LFS, not just their links.")
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print("Quaternius vendoring failed:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
