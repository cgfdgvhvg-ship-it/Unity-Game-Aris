"""Stdlib-only contract tests for the read-only Codespace world sensor."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_world_observe as sensor


class WorldSensorContractTests(unittest.TestCase):
    def parse(self, *argv):
        with patch.object(sys, "argv", ["ai_world_observe.py", *argv]):
            return sensor.parse()

    def test_no_mutating_world_commands_accepted(self):
        for name in ("apply", "preview", "plan", "engine", "watch", "import-model"):
            with self.subTest(name=name):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        self.parse(name)

    def test_validated_site_coordinates_and_pagination(self):
        args, supplied = self.parse(
            "site", "--x", "350", "--z", "167.3", "--radius", "45",
            "--limit", "8", "--scene-offset", "8", "--native-offset", "4")
        self.assertEqual(args.command, "site")
        self.assertEqual(supplied["scene_offset"], 8)
        self.assertEqual(supplied["native_offset"], 4)
        self.assertEqual(supplied["limit"], 8)

    def test_zero_coordinates_remain_explicit(self):
        args, supplied = self.parse("site", "--x", "0", "--z", "0")
        self.assertEqual(supplied["x"], 0.0)
        self.assertEqual(supplied["z"], 0.0)

    def test_rejects_nonfinite_coordinates_and_oversized_pages(self):
        for values in (
            ("site", "--x", "nan", "--z", "0"),
            ("site", "--x", "350", "--z", "0", "--limit", "1000"),
            ("site", "--x", "350", "--z", "0", "--radius", "-10"),
            ("site", "--x", "350"),
            ("describe", "--target", "scene:abc:1", "--x", "0"),
            ("usages", "--path", "../../secrets"),
        ):
            with self.subTest(values=values):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        self.parse(*values)

    def test_bounded_report_remains_valid_json(self):
        report = {"status": "ok", "command": "site",
                  "result": {"objects": [
                      {"name": "Tree_" + str(i), "color": "green" * 500}
                      for i in range(300)]}}
        text = sensor.report(report)
        self.assertLessEqual(len(text), sensor.MAX_JSON)
        parsed = json.loads(text)
        self.assertEqual(parsed["command"], "site")
        self.assertTrue("result" in parsed or "warning" in parsed)

    def test_three_component_coordinates_survive_report_budget(self):
        for cap in (1, 2, 3):
            self.assertEqual(sensor.limited([350.0, -11.9368, 167.3], cap, 10),
                             [350.0, -11.9368, 167.3])
            self.assertEqual(sensor.limited([1.0, 1.0, 1.0, 1.0], cap, 10),
                             [1.0, 1.0, 1.0, 1.0])

    def test_site_summary_keeps_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = {"command": "site", "source_fingerprint": {"sha256": "a" * 64},
                        "result": {
                            "site": {"native": {"counts_by_category_in_full_radius": {"tree": 42}}},
                            "inspection": {"coverage": {"scene_next_offset": 8,
                                                       "native_next_offset": 16},
                                           "terrain_relation": {"point_minus_ground_m": 2}}}}
            mock_run = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(original), stderr="")
            output = io.StringIO()
            with patch.object(sensor, "ROOT", Path(tmp)), \
                 patch.object(sensor, "cmd", return_value=mock_run) as command, \
                 patch.object(sensor, "python_path", return_value=Path(sys.executable)), \
                 patch.object(sys, "argv", [
                     "ai_world_observe.py", "site", "--x", "350", "--z", "167.3",
                     "--limit", "8"]), contextlib.redirect_stdout(output):
                self.assertEqual(sensor.main(), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["result"]["site"]["native"][
                "counts_by_category_in_full_radius"]["tree"], 42)
            self.assertEqual(result["result"]["inspection_coverage"][
                "scene_next_offset"], 8)
            self.assertEqual(command.call_args.args[0][-6:], [
                "--x", "350.0", "--z", "167.3", "--limit", "8"])


if __name__ == "__main__":
    unittest.main()
