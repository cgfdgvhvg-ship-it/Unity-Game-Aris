"""Unity shader log triage must reject normal importer noise."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"ai_codespace_executor.py"
spec=importlib.util.spec_from_file_location("ai_codespace_executor", SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ShaderIssueTests(unittest.TestCase):
    def test_normal_shader_import_does_not_count_as_error(self):
        logs=(
            "Start importing Packages/com.unity.render-pipelines.universal/Shaders/Lit.shader using Guid(x) (ShaderImporter)\n"
            "Start importing Packages/com.unity.shadergraph/Editor/Legacy.hlsl using Guid(y) (DefaultImporter)\n"
            "Launched and connected shader compiler UnityShaderCompiler after 0.07 seconds\n"
        )
        self.assertEqual(module._actual_shader_issues(logs), [])

    def test_interleaved_backend_warnings_are_preserved(self):
        logs=(
            "Start importing Packages/com.unity.render-pipelines.universal/Shaders/Terrain/TerrainLitBase.shader "
            "using Guid(x) (ShaderImporter)WARNING: Shader Unsupported: "
            "'Hidden/Universal Render Pipeline/Terrain/Lit (Base Pass)' - All subshaders removed\n"
            "Shader is not supported on this renderer\n"
            "Error in shader 'BadBuild'\n"
        )
        self.assertEqual(len(module._actual_shader_issues(logs)),3)

    def test_worker_noise_not_counted(self):
        self.assertEqual(module._actual_shader_issues(
            "[Worker0] WARNING: Shader Unsupported: compilation log\n"), [])


if __name__ == "__main__":
    unittest.main()
