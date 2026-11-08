#!/usr/bin/env bash
# Codespaces onCreateCommand. GitHub's prebuild service snapshots this phase.
# No secrets, Unity account activation, ULF, OAuth state or Hub login is captured.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
bash .devcontainer/bootstrap.sh

# Pre-hydrate LFS when the prebuild has access; defer failures to postCreate.
# A GitHub prebuild may lack the Codespaces creator's private credentials.
mkdir -p /tmp/aaris-codespaces
if git lfs pull >/tmp/aaris-codespaces/prebuild-lfs.log 2>&1; then
  echo AARIS_PREBUILD_LFS_FETCHED
else
  echo AARIS_PREBUILD_LFS_DEFERRED
fi

# The verified Editor installer is idempotent. It only downloads when missing,
# and does NOT run Unity ID sign-in or request/store a machine license.
bash Tools/Codespaces/install_unity.sh
echo AARIS_PREBUILD_EDITOR_READY
