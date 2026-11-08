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
  if git -c user.name='Aaris Codespace Recovery' -c user.email='codespace-recovery@users.noreply.github.com' stash push -u -m 'Aaris new Codespace devcontainer recovery 20261109' -- .devcontainer >/dev/null 2>/dev/null; then
    AFTER="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
    if test -z "$AFTER" || test "$AFTER" = "$BEFORE"; then
      echo 'AARIS_RECOVERY_CONFIG_STASH_NOT_VERIFIED'
      exit 26
    fi
    echo 'AARIS_RECOVERY_CONFIG_STASH_SAVED'
  else
    # Git stash can fail in Alpine recovery (identity, index, hook or filter).
    # Archive only config files to a private persistent path OUTSIDE the repo,
    # verify its checksum, then restore only those tracked config paths to HEAD.
    umask 077
    mkdir -p /workspaces/.aaris-recovery
    chmod 700 /workspaces/.aaris-recovery
    BACKUP="$(mktemp -d /workspaces/.aaris-recovery/devcontainer.XXXXXXXX)" || exit 30
    if ! tar -czf "$BACKUP/devcontainer.tar.gz" -C "$PROJECT" .devcontainer; then
      echo 'AARIS_RECOVERY_PRIVATE_ARCHIVE_FAILED'
      exit 31
    fi
    if ! tar -tzf "$BACKUP/devcontainer.tar.gz" >/dev/null 2>&1; then
      echo 'AARIS_RECOVERY_PRIVATE_ARCHIVE_INVALID'
      exit 32
    fi
    (cd "$BACKUP" && sha256sum devcontainer.tar.gz > checksum.sha256 && sha256sum -c checksum.sha256 >/dev/null) || {
      echo 'AARIS_RECOVERY_PRIVATE_CHECKSUM_FAILED'
      exit 33
    }
    if ! git restore --source=HEAD --staged --worktree -- .devcontainer >/dev/null 2>/dev/null; then
      echo 'AARIS_RECOVERY_SCOPED_RESTORE_FAILED'
      exit 34
    fi
    echo 'AARIS_RECOVERY_PRIVATE_CONFIG_BACKUP_SAVED'
  fi
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
