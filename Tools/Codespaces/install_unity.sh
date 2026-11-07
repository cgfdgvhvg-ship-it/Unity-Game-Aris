#!/usr/bin/env bash
set -euo pipefail
VERSION="6000.3.26f1"
INSTALL_ROOT="/workspaces/.aaris-unity-editors"
mkdir -p "$INSTALL_ROOT" /tmp/aaris-codespaces
if test -x "$INSTALL_ROOT/$VERSION/Editor/Unity"; then echo 'UNITY_ALREADY_INSTALLED'; exit 0; fi
# Official Unity Hub Linux apt repository + documented headless Editor installer.
if ! command -v unityhub >/dev/null 2>&1; then
  sudo install -d /etc/apt/keyrings
  curl -fsSL https://hub.unity3d.com/linux/keys/public | sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/unityhub.gpg
  printf '%s\n' 'Types: deb' 'URIs: https://hub.unity3d.com/linux/repos/deb' 'Suites: stable' 'Components: main' 'Signed-By: /etc/apt/keyrings/unityhub.gpg' | sudo tee /etc/apt/sources.list.d/unityhub.sources >/dev/null
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unityhub
fi
echo 'UNITY_HUB_INSTALLED'
unityhub --headless install-path -s "$INSTALL_ROOT" >/tmp/aaris-codespaces/hub-path.log 2>&1 || { echo 'UNITY_INSTALL_PATH_FAILED'; exit 4; }
unityhub --headless install --version "$VERSION" >/tmp/aaris-codespaces/hub-install.log 2>&1 || { echo 'UNITY_INSTALL_FAILED'; exit 5; }
test -x "$INSTALL_ROOT/$VERSION/Editor/Unity" || { echo 'UNITY_BINARY_MISSING'; exit 6; }
echo 'UNITY_EDITOR_INSTALLED'
