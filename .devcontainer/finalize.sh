#!/usr/bin/env bash
# Codespaces postCreateCommand: verify actual assets on a NEW machine.
# Never reset/clean/revert a Unity scene, Git LFS file, or uncommitted edit.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p /tmp/aaris-codespaces
bash .devcontainer/start_screen.sh
git lfs install --local

# Avoid downloading 775 LFS assets again if the prebuild already contains them.
if ! python3 Tools/Codespaces/verify_lfs.py; then
  echo AARIS_CODESPACE_LFS_REHYDRATING
  if ! git lfs pull > /tmp/aaris-codespaces/postcreate-lfs.log 2>&1; then
    echo AARIS_CODESPACE_LFS_FETCH_FAILED
    exit 21
  fi
  python3 Tools/Codespaces/verify_lfs.py
fi
# If the snapshot already has Editor bits, this returns immediately.
bash Tools/Codespaces/install_unity.sh
echo AARIS_CODESPACE_FAST_START_READY
