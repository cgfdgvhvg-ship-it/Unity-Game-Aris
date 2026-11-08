#!/usr/bin/env bash
set -euo pipefail
# Installed once at Codespace creation. Unity Editor is a separate on-demand install.
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git-lfs jq python3 python3-pil xvfb fluxbox scrot imagemagick x11-utils curl gnupg ca-certificates procps openssh-server
git lfs install --local
# The Unity Linux Editor links to desktop/OpenGL libraries absent in minimal images.
bash Tools/Codespaces/unity_gui_deps.sh
bash .devcontainer/start_screen.sh
echo 'AARIS_BOOTSTRAP_OK'
