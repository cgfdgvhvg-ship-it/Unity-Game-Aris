#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
# Isolated GitHub CLI authentication profiles; no embedded PAT or password.
REPO="$(printenv MAIN_REPO || echo sundamunda289-art/Unity-Game-Aris)"
BASE="$HOME/.config/aaris-ai"
MASTER="$BASE/master-gh"
WORKER="$BASE/codespace-gh"
command -v pkg >/dev/null || { echo 'Use Termux on Android'; exit 2; }
pkg install -y gh jq
umask 077
mkdir -p "$MASTER" "$WORKER"
chmod 700 "$BASE" "$MASTER" "$WORKER"
echo 'Authenticate the MAIN repo owner via official GitHub browser/device login (once).'
if ! GH_CONFIG_DIR="$MASTER" gh auth status -h github.com >/dev/null 2>&1; then
  GH_CONFIG_DIR="$MASTER" gh auth login -h github.com -p https -w -s 'repo,workflow'
fi
OWNER="$(GH_CONFIG_DIR="$MASTER" gh api user -q .login)"
PERM="$(GH_CONFIG_DIR="$MASTER" gh repo view "$REPO" --json viewerPermission -q .viewerPermission)"
case "$PERM" in ADMIN|MAINTAIN) ;; *) echo "Main account $OWNER cannot manage repo Secrets"; exit 3;; esac
echo 'Authorize the selected Codespace account via GitHub browser/device login.'
if GH_CONFIG_DIR="$WORKER" gh auth status -h github.com >/dev/null 2>&1; then
  GH_CONFIG_DIR="$WORKER" gh auth logout -h github.com -u "$(GH_CONFIG_DIR="$WORKER" gh api user -q .login)" >/dev/null 2>&1 || true
fi
GH_CONFIG_DIR="$WORKER" gh auth login -h github.com -p https -w -s 'codespace,repo'
CS_USER="$(GH_CONFIG_DIR="$WORKER" gh api user -q .login)"
if ! GH_CONFIG_DIR="$WORKER" gh api "/repos/$REPO/codespaces/machines" --jq '.machines[].name' >/dev/null; then
  echo 'Codespaces machine API not accessible. Old secret was left unchanged.'
  exit 4
fi
MASTER_TOKEN="$(GH_CONFIG_DIR="$MASTER" gh auth token)"
CS_TOKEN="$(GH_CONFIG_DIR="$WORKER" gh auth token)"
printf '%s' "$CS_TOKEN" | GH_TOKEN="$MASTER_TOKEN" gh secret set CODESPACE_PAT -R "$REPO"
unset MASTER_TOKEN CS_TOKEN
echo "Codespace account switched to $CS_USER; no repository transfer."
echo "Open: https://github.com/$REPO/actions/workflows/aaris-codespaces-control.yml"
echo 'Run workflow: machines, then start.'
