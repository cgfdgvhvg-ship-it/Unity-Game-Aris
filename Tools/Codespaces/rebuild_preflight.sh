#!/usr/bin/env bash
# Read-only preflight before GitHub Codespaces devcontainer rebuild.
# Do NOT modify, clean, reset or commit any project or Git LFS data.
set -euo pipefail
PROJECT="/workspaces/Unity-Game-Aris"
test -d "$PROJECT" || exit 21
test -f "$PROJECT/.devcontainer/devcontainer.json" || exit 22
# Recovery containers may have Bash and grep but no python3. Match the
# actual image property on a standalone JSON line; CI validates JSON syntax.
if ! grep -Eq '^[[:space:]]*"image"[[:space:]]*:[[:space:]]*"mcr.microsoft.com/devcontainers/base:ubuntu-22.04"' "$PROJECT/.devcontainer/devcontainer.json"; then
  exit 23
fi
echo 'AARIS_REBUILD_TARGET_UBUNTU_22_04'
git -C "$PROJECT" rev-parse --is-inside-work-tree | grep -qx true || exit 24
test -r "$PROJECT/Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity" || exit 25
echo 'AARIS_REBUILD_WORKSPACE_EXISTS'
echo 'AARIS_REBUILD_NATIVE_SCENE_PRESENT'
echo 'AARIS_REBUILD_PREFLIGHT_READY'
