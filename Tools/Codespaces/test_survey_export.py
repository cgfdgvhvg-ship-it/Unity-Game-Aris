#!/usr/bin/env python3
"""Unit-only fixture: native PNG export must not require ffmpeg after survey completes.

The synthetic PNG generated here is a parser fixture, NEVER a Unity screenshot.
It is confined to TemporaryDirectory and never published as photo evidence.
"""
import base64
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

SCRIPT = Path(__file__).resolve().with_name("survey_export_first_six.sh")


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(
        ">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def fixture_png():
    # Valid synthetic 1920x720 PNG; oversized tEXt ensures the 8 KiB check.
    ihdr = struct.pack(">IIBBBBB", 1920, 720, 8, 2, 0, 0, 0)
    pixels = (bytes([0]) + bytes(1920 * 3)) * 720
    return (bytes([137,80,78,71,13,10,26,10]) + chunk(b"IHDR", ihdr)
            + chunk(b"tEXt", b"qa_fixture\0" + bytes([70]) * 9000)
            + chunk(b"IDAT", zlib.compress(pixels, 6)) + chunk(b"IEND", b""))


def run_export(root):
    source = SCRIPT.read_text(encoding="utf-8")
    original = "root=pathlib.Path('/tmp/aaris-codespaces/scene-probe')"
    if source.count(original) != 1:
        raise AssertionError("Producer location changed; test must track it")
    source = source.replace(original, "root=pathlib.Path(" + repr(str(root)) + ")")
    return subprocess.run(["bash", "-s"], input=source, text=True,
                          capture_output=True, timeout=12)


class DirectNativeSheetTest(unittest.TestCase):
    def test_completed_unity_sheet_export_needs_no_ffmpeg_or_raw_frames(self):
        with tempfile.TemporaryDirectory(prefix="aaris-survey-export-test-") as temp:
            root = Path(temp)
            real_png_shape_fixture = fixture_png()
            (root / "survey-sheet-1.png").write_bytes(real_png_shape_fixture)
            (root / "survey-report.json").write_text(json.dumps({
                "status": "passed", "mode": "survey", "frameCount": 24,
                "terrainTiles": 4, "locationCount": 12
            }))
            process = run_export(root)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(base64.b64decode(process.stdout.strip()),
                             real_png_shape_fixture)

    def test_incomplete_survey_must_not_publish_old_native_sheet(self):
        with tempfile.TemporaryDirectory(prefix="aaris-survey-export-test-") as temp:
            root = Path(temp)
            (root / "survey-sheet-1.png").write_bytes(fixture_png())
            (root / "survey-report.json").write_text(json.dumps({
                "status": "failed", "frameCount": 5, "terrainTiles": 4,
                "locationCount": 3
            }))
            process = run_export(root)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(process.stdout.strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
