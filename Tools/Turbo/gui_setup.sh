#!/usr/bin/env bash
# Optional one-time GUI dependencies for the chosen, owner-approved Codespace.
# Never modifies Unity project files, global shell profile or public services.
set -euo pipefail
umask 077
DIR="$HOME/.cache/aaris-turbo"
mkdir -p "$DIR"
chmod 700 "$DIR"
need=0
for tool in Xvfb fluxbox scrot xdotool xterm xclip; do
  if ! command -v "$tool" >/dev/null 2>&1; then need=1; fi
done
if ! python3 -c 'import PIL.Image' >/dev/null 2>&1; then need=1; fi
if test "$need" -eq 0; then
  echo "AARIS_GUI_DEPENDENCIES_READY"
  exit 0
fi
command -v sudo >/dev/null || { echo "AARIS_GUI_SUDO_MISSING"; exit 2; }
command -v apt-get >/dev/null || { echo "AARIS_GUI_APT_MISSING"; exit 3; }
if ! sudo -n true 2>/dev/null; then
  echo "AARIS_GUI_SUDO_NOT_NONINTERACTIVE"
  exit 4
fi
# Do not echo raw package logs: they stay private in this Codespace's home.
export DEBIAN_FRONTEND=noninteractive
if ! sudo -n apt-get update -qq > "$DIR/apt-update.log" 2>&1; then
  echo "AARIS_GUI_APT_UPDATE_FAILED"; exit 5
fi
if ! sudo -n apt-get install -y -qq --no-install-recommends \
    xvfb fluxbox scrot xdotool xterm xclip python3-pil \
    > "$DIR/apt-install.log" 2>&1; then
  echo "AARIS_GUI_APT_INSTALL_FAILED"; exit 6
fi
if ! python3 -c 'from PIL import Image, ImageDraw' >/dev/null 2>&1; then
  echo "AARIS_GUI_PIL_IMPORT_FAILED"; exit 7
fi
echo "AARIS_GUI_DEPENDENCIES_READY"
