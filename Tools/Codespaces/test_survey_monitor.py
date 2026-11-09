#!/usr/bin/env python3
"""Offline tests for the exact Codespace selector embedded in the survey monitor."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/aaris-survey-progress.yml"
PINNED = "aaris-ai-unity-ssh-vp5g97jv4r4gfpjgq"


def selection_expression():
    source = WORKFLOW.read_text(encoding="utf-8")
    # Validate the actual jq filter that Actions executes, not a duplicate.
    start = "jq -er '"
    end = "\n            ')\" || {"
    assert source.count(start) == 1
    return source.split(start, 1)[1].split(end, 1)[0]


def select(machines):
    p = subprocess.run(["jq", "-er", selection_expression()],
                       input=json.dumps(machines), text=True,
                       capture_output=True, timeout=5)
    return (p.returncode, p.stdout.strip())


def machine(name, label):
    return {"name": name, "displayName": label, "state": "Available"}


class SameCodespaceMonitorTests(unittest.TestCase):
    def test_unique_minimal_is_selected_for_new_owner_account(self):
        code, chosen = select([machine("aaris-ai-ubuntu-minimal-jrg7rgvx5rr435wpp",
                                       "aaris-ai-ubuntu-minimal")])
        self.assertEqual((code, chosen),
                         (0, "aaris-ai-ubuntu-minimal-jrg7rgvx5rr435wpp"))

    def test_pinned_host_precedes_minimal(self):
        code, chosen = select([machine("new", "aaris-ai-ubuntu-minimal"),
                               machine(PINNED, "old")])
        self.assertEqual((code, chosen), (0, PINNED))

    def test_single_legacy_host_fallback(self):
        self.assertEqual(select([machine("legacy", "aaris-ai-unity-ssh")]),
                         (0, "legacy"))

    def test_ambiguous_minimal_fails_closed(self):
        code, chosen = select([machine("first", "aaris-ai-ubuntu-minimal"),
                               machine("second", "aaris-ai-ubuntu-minimal"),
                               machine("legacy", "aaris-ai-unity-ssh")])
        self.assertNotEqual(code, 0)
        self.assertFalse(chosen)

    def test_empty_account_fails_closed(self):
        self.assertNotEqual(select([])[0], 0)

    def test_status_and_export_share_one_selected_machine(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(source.count("gh codespace list"), 1)
        self.assertIn('echo "AARIS_MONITOR_CODESPACE=$CODESPACE" >> "$GITHUB_ENV"', source)
        self.assertIn('CS="${AARIS_MONITOR_CODESPACE:?Selected Codespace from inspection required}"', source)
        self.assertIn('timeout 100 gh codespace ssh -c "$CODESPACE"', source)
        self.assertIn('timeout 200 gh codespace ssh -c "$CS"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
