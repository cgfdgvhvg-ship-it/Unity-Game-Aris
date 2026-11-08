#!/usr/bin/env bash
# Codespaces postCreateCommand: verify actual assets on a NEW machine.
# Never reset/clean/revert a Unity scene, Git LFS file, or uncommitted edit.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p /tmp/aaris-codespaces
if bash .devcontainer/start_screen.sh; then
  echo AARIS_POSTCREATE_DISPLAY_READY
else
  echo AARIS_POSTCREATE_DISPLAY_DEFERRED_USE_CS_DEPS
fi
if git lfs install --local; then
  echo AARIS_POSTCREATE_GIT_LFS_READY
else
  echo AARIS_POSTCREATE_GIT_LFS_DEFERRED_USE_CS_LFS
fi

# Avoid downloading 775 LFS assets again if the prebuild already contains them.
if python3 Tools/Codespaces/verify_lfs.py; then
  echo AARIS_CODESPACE_LFS_READY
else
  echo AARIS_CODESPACE_LFS_REHYDRATING
  if git lfs pull > /tmp/aaris-codespaces/postcreate-lfs.log 2>&1 && python3 Tools/Codespaces/verify_lfs.py; then
    echo AARIS_CODESPACE_LFS_READY
  else
    echo AARIS_CODESPACE_LFS_DEFERRED_USE_CS_LFS
  fi
fi
# Unity download/auth errors must not bring down the Ubuntu devcontainer.
if bash Tools/Codespaces/install_unity.sh >/tmp/aaris-codespaces/postcreate-editor-install.log 2>&1; then
  echo AARIS_CODESPACE_EDITOR_READY
else
  echo AARIS_CODESPACE_EDITOR_DEFERRED_USE_CS_INSTALL
fi
echo AARIS_CODESPACE_READY_CHECK_EDITOR_AND_LFS_SEPARATELY
