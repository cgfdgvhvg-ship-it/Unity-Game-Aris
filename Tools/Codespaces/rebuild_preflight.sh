#!/usr/bin/env bash
# Read-only preflight before GitHub Codespaces devcontainer rebuild.
# Do NOT modify, clean, reset or commit any project or Git LFS data.
set -euo pipefail
PROJECT="/workspaces/Unity-Game-Aris"
test -d "$PROJECT" || exit 21
test -f "$PROJECT/.devcontainer/devcontainer.json" || exit 22
python3 - "$PROJECT/.devcontainer/devcontainer.json" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as h:
    data=json.load(h)
if data.get('image')!='mcr.microsoft.com/devcontainers/base:ubuntu-22.04':
    raise SystemExit(23)
print('AARIS_REBUILD_TARGET_UBUNTU_22_04')
PY
git -C "$PROJECT" rev-parse --is-inside-work-tree | grep -qx true || exit 24
test -r "$PROJECT/Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity" || exit 25
echo 'AARIS_REBUILD_WORKSPACE_EXISTS'
echo 'AARIS_REBUILD_NATIVE_SCENE_PRESENT'
echo 'AARIS_REBUILD_PREFLIGHT_READY'
