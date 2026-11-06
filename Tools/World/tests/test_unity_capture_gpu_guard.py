"""Guard against a real Unity URP software-render screenshot crash.

Source-level contract; does not claim Android/GPU visual QA.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]
BRIDGE=ROOT/"Assets/AarisWorld/Editor/AarisLiveEditorBridge.cs"


class SoftwareCaptureGuardTests(unittest.TestCase):
    def test_bail_out_before_submit_on_software_renderer(self):
        src=BRIDGE.read_text(encoding="utf-8")
        capture=src.split("private static void Capture(",1)[1].split(
            "private static void DeleteExpiredFrames(",1)[0]
        self.assertIn("SystemInfo.graphicsDeviceName",capture)
        self.assertIn("llvmpipe",capture)
        self.assertIn("lavapipe",capture)
        self.assertIn("softpipe",capture)
        self.assertIn("CPU software renderer cannot safely capture URP",capture)
        self.assertLess(capture.index("rendererName.Contains(\"llvmpipe\")"),
                        capture.index("RenderPipeline.SubmitRenderRequest("))
        self.assertIn("RenderPipeline.SupportsRenderRequest(",capture)


if __name__=="__main__":
    unittest.main()
