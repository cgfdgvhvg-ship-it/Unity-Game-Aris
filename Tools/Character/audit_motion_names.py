#!/usr/bin/env python3
"""Inspect verified Quaternius glTF animation names without Unity or Blender.

The exact source archive is SHA-256/git-blob pinned by vendor_quaternius.py.
This is an offline build-time/CI audit, never executed by the actual game.
"""
from __future__ import annotations
import json
import struct
from pathlib import Path
from vendor_quaternius import ASSETS, BASE, download, verify

def decode_animation_names(raw: bytes) -> list[str]:
    if raw[:4] != b"glTF" or struct.unpack_from("<I", raw, 4)[0] != 2:
        raise ValueError("Not GLB2")
    if struct.unpack_from("<I", raw, 8)[0] != len(raw):
        raise ValueError("Corrupt length")
    n, kind = struct.unpack_from("<II", raw, 12)
    if kind != 0x4E4F534A or 20 + n > len(raw):
        raise ValueError("Missing JSON chunk")
    doc = json.loads(raw[20:20 + n].decode("utf-8"))
    return sorted(str(a.get("name", "<unnamed>")) for a in doc.get("animations", []))

if __name__ == "__main__":
    source = ASSETS[1]
    raw = download(BASE + source["file"], source["size"])
    verify(source, raw)
    names = decode_animation_names(raw)
    print("Verified GLB animation count:", len(names))
    for name in names:
        print("MOTION_NAME:", name)
    print("JUMP_CANDIDATES:", [x for x in names if "jump" in x.lower()])
    print("CROUCH_CANDIDATES:", [x for x in names if "crouch" in x.lower()])
    print("PRONE_CANDIDATES:", [x for x in names if "prone" in x.lower() or "crawl" in x.lower()])
