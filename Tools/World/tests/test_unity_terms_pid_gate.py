"""Regression for Unity Terms dialog belonging to isolated scratch Unity PID."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "ai_codespace_executor.py"
spec = importlib.util.spec_from_file_location("ai_codespace_executor", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TermsWindowPidGateTests(unittest.TestCase):
    def test_exact_scratch_pid_authorized(self):
        self.assertTrue(module._terms_window_belongs_to_scratch(
            "_NET_WM_PID(CARDINAL) = 5645\n", [5645]))

    def test_not_original_workspace_unity_pid(self):
        self.assertFalse(module._terms_window_belongs_to_scratch(
            "_NET_WM_PID(CARDINAL) = 43536\n", [5645]))

    def test_no_running_scratch_editor(self):
        self.assertFalse(module._terms_window_belongs_to_scratch(
            "_NET_WM_PID(CARDINAL) = 5645\n", []))

    def test_multiple_editors_are_unsafe(self):
        self.assertFalse(module._terms_window_belongs_to_scratch(
            "_NET_WM_PID(CARDINAL) = 5645\n", [5645, 9800]))

    def test_spoofed_or_absent_pid(self):
        for raw in ("", "WM_NAME(STRING) = Unity", "_NET_WM_PID = 5645",
                    "_NET_WM_PID(CARDINAL) = 5; rm -rf x"):
            self.assertFalse(module._terms_window_belongs_to_scratch(raw, [5645]))


if __name__ == "__main__":
    unittest.main()
