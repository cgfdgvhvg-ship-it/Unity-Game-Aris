#!/usr/bin/env bash
# Scoped recovery-only fast-forward for a Codespace with no Python/Unity.
# Never reset, clean, force-merge, or overwrite unsaved source assets.
set -euo pipefail
PROJECT="/workspaces/Unity-Game-Aris"
test -d "$PROJECT" || { echo 'AARIS_RECOVERY_PROJECT_MISSING'; exit 21; }
cd "$PROJECT"
test "$(git rev-parse --is-inside-work-tree)" = true || exit 22
test "$(git branch --show-current)" = main || { echo 'AARIS_RECOVERY_NOT_MAIN'; exit 23; }
ORIGIN="$(git remote get-url origin)"
case "$ORIGIN" in
  *github.com/sundamunda289-art/Unity-Game-Aris|*github.com/sundamunda289-art/Unity-Game-Aris.git|*github.com:sundamunda289-art/Unity-Game-Aris|*github.com:sundamunda289-art/Unity-Game-Aris.git) ;;
  *) echo 'AARIS_RECOVERY_UNEXPECTED_ORIGIN'; exit 24 ;;
esac
# Preserve ONLY devcontainer-local changes in a named, recoverable Git stash.
# Never discard anything under Assets, scenes, prefabs, Git LFS or ProjectSettings.
if ! git diff --quiet -- .devcontainer || ! git diff --cached --quiet -- .devcontainer; then
  BEFORE="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
  if ! git stash push -u -m 'Aaris new Codespace devcontainer recovery 20261109' -- .devcontainer >/dev/null 2>/dev/null; then
    echo 'AARIS_RECOVERY_CONFIG_BACKUP_FAILED'
    exit 25
  fi
  AFTER="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
  if test -z "$AFTER" || test "$AFTER" = "$BEFORE"; then
    echo 'AARIS_RECOVERY_CONFIG_STASH_NOT_VERIFIED'
    exit 26
  fi
  echo 'AARIS_RECOVERY_CONFIG_STASH_SAVED'
fi
# No LFS hydration or project reset during recovery. Git refuses fast-forward
# if the updated branch would overwrite a local tracked modification.
if ! GIT_TERMINAL_PROMPT=0 git fetch --no-tags origin main >/dev/null 2>/dev/null; then
  echo 'AARIS_RECOVERY_FETCH_FAILED'
  exit 27
fi
if ! GIT_TERMINAL_PROMPT=0 GIT_LFS_SKIP_SMUDGE=1 git merge --ff-only FETCH_HEAD >/dev/null 2>/dev/null; then
  echo 'AARIS_RECOVERY_SAFE_FAST_FORWARD_BLOCKED'
  exit 28
fi
if ! grep -Eq '^[[:space:]]*"image"[[:space:]]*:[[:space:]]*"mcr.microsoft.com/devcontainers/base:ubuntu-22.04"' .devcontainer/devcontainer.json; then
  echo 'AARIS_RECOVERY_UBUNTU_CONFIG_MISSING'
  exit 29
fi
echo 'AARIS_RECOVERY_FAST_FORWARD_SUCCESS'
echo 'AARIS_RECOVERY_UBUNTU_CONFIG_READY'
