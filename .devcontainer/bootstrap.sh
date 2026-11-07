#!/usr/bin/env bash
set -euo pipefail
# Installed once at Codespace creation. Unity Editor is a separate on-demand install.
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git-lfs jq python3 python3-pil xvfb fluxbox scrot imagemagick x11-utils curl gnupg ca-certificates procps openssh-server
git lfs install --local
bash .devcontainer/start_screen.sh
echo 'AARIS_BOOTSTRAP_OK'
