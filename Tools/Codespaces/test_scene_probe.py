#!/usr/bin/env python3
"""License-free security/contract regressions for native Codespace scene probing."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[2]
editor = (ROOT / "Assets/AarisWorld/Editor/AarisCodespaceSceneProbe.cs").read_text()
shell = (ROOT / "Tools/Codespaces/scene_probe.sh").read_text()
controller = (ROOT / "Tools/Codespaces/controller.sh").read_text()
workflow = (ROOT / ".github/workflows/aaris-codespaces-control.yml").read_text()
issue = (ROOT / "Tools/Codespaces/issue_response.py").read_text()
agent = (ROOT / "AGENTS.md").read_text()
assert 'AarisExplorerBuild.ScenePath' in editor
assert 'EditorSceneManager.OpenScene(Scene, OpenSceneMode.Single)' in editor
assert 'terrains.Length != 4' in editor
assert 'SCENE_IS_LFS_POINTER' in editor
assert 'cam.transform.position = new Vector3(0f, 1600f, 0f)' in editor
assert 'cam.orthographic = true' in editor
assert 'cam.Render()' in editor and 'ReadPixels' in editor
assert 'FRAME_NEARLY_UNIFORM' in editor and 'FRAME_MAGENTA_SHADER_FAILURE' in editor
assert 'EditorApplication.isPlaying = true' in editor
assert 'EditorApplication.isPlaying = false' in editor
assert 'Time.frameCount < PlayFrames' in editor
assert 'AarisVehicleWorld' in editor and 'AarisThirdPersonPlayer' in editor
assert 'runtimeErrors == 0' in editor
assert 'EditorApplication.Exit(exit)' in editor
assert 'EditorSceneManager.SaveScene' not in editor and 'AssetDatabase.SaveAssets' not in editor
assert shell.startswith('#!/usr/bin/env bash')
assert 'MODE="$1"' in shell
assert 'render|play' in shell
assert 'SCENE="Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"' in shell
assert 'scene-probe' in shell and 'map-overview.png' in shell and 'play-frame.png' in shell
assert 'pgrep -f' in shell and 'AARIS_PROBE_EDITOR_ALREADY_OPEN' in shell
assert '-batchmode' in shell and '-executeMethod' in shell and 'timeout --signal=TERM' in shell
assert '-nographics' not in shell and 'scrot' not in shell and 'xdotool' not in shell
assert 'git reset' not in shell and 'git clean' not in shell
assert 'pkill' not in shell and 'kill -9' not in shell and 'eval ' not in shell
assert 'git branch --show-current' in shell and 'main' in shell
assert 'data.get("status")!="passed"' in shell
assert 'data.get("frames",0)<60' in shell
assert 'image.read_bytes()[:8]' in shell
for op in ('scene_render', 'scene_play'):
    assert "'CS SCENE " + op.split('_')[1].upper() + "') OP=" + op in controller
    assert op in workflow and op in issue
assert 'Tools/Codespaces/test_scene_probe.py' in workflow
assert 'Only verified Unity camera PNGs' in issue
assert 'CS SCENE RENDER' in agent and 'CS SCENE PLAY' in agent
assert 'noVNC' in agent
print('AARIS_NATIVE_SCENE_PROBE_STATIC_PASS')
