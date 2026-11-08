#!/usr/bin/env bash
# Fixed, reviewable packages for Ubuntu 22.04 Unity Editor GUI startup.
# Only install OS dependencies; never change Unity assets, accounts, licences or secrets.
set -Eeuo pipefail
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "22.04" ]]; then
  echo UNITY_GUI_DEPS_REQUIRES_UBUNTU_2204
  exit 12
fi
mkdir -p /tmp/aaris-codespaces
LOG=/tmp/aaris-codespaces/unity-gui-apt-private.log
# Capture full package output privately on the Codespace, never in a public issue.
if ! sudo apt-get update -qq >"$LOG" 2>&1; then
  echo UNITY_GUI_DEPS_APT_UPDATE_FAILED
  exit 13
fi
if ! sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  libglu1-mesa libgl1 libgl1-mesa-dri libgbm1 libglx-mesa0 \
  libgtk-3-0 libglib2.0-0 libnss3 libnspr4 libasound2 libpulse0 \
  libx11-6 libxext6 libxrender1 libxrandr2 libxcursor1 \
  libxi6 libxinerama1 libxss1 libxtst6 libxkbcommon0 \
  libfontconfig1 libfreetype6 libatk1.0-0 libdbus-1-3 \
  libgdk-pixbuf-2.0-0 libxml2 mesa-utils >>"$LOG" 2>&1; then
  echo UNITY_GUI_DEPS_APT_INSTALL_FAILED
  exit 14
fi
echo UNITY_GUI_DEPS_READY
