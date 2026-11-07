#!/data/data/com.termux/files/usr/bin/bash
# Phone-only Unity approval. Does not use Cloudflare, public logs, GitHub Issues or ULF files.
set -euo pipefail
umask 077
REPO="$(printenv MAIN_REPO || echo sundamunda289-art/Unity-Game-Aris)"
PROFILE="$HOME/.config/aaris-ai/codespace-gh"
command -v pkg >/dev/null || { echo 'Please run inside Termux'; exit 2; }
pkg install -y gh python openssh jq curl
if ! GH_CONFIG_DIR="$PROFILE" gh auth status -h github.com >/dev/null 2>&1; then
  echo 'Codespace GitHub login missing. Run aaris-switch.sh once first.'
  exit 3
fi
export GH_CONFIG_DIR="$PROFILE"
# Prevent tokens from a different shell environment overriding the selected profile.
unset GH_TOKEN GITHUB_TOKEN
LIST="$(gh codespace list -R "$REPO" --json name,displayName,state --limit 30)" || {
  echo 'Cannot list Codespaces'; exit 4;
}
CS="$(printf '%s' "$LIST" | jq -r '([.[]|select(.displayName=="aaris-ai-unity")][0].name) // .[0].name // empty')"
[[ "$CS" =~ ^[A-Za-z0-9-]+$ ]] || { echo 'Codespace not found; use CS START first'; exit 5; }
printf 'Using Codespace: %s\n' "$CS"
WORK="$(mktemp -d "$HOME/.aaris-unity-allow.XXXXXXXX")"
trap 'rm -rf "$WORK"' EXIT
curl -fsSL --retry 2 "https://raw.githubusercontent.com/$REPO/main/Tools/Codespaces/mobile_license.py" -o "$WORK/remote.py"
grep -q 'AARIS_AUTH_LINK=' "$WORK/remote.py" || { echo 'Remote helper not recognized'; exit 6; }
echo 'Starting official Unity sign-in on your Codespace...'
# The URL travels only between your Codespace and your own phone.
set +e
gh codespace ssh -c "$CS" -- 'python3 -u -' < "$WORK/remote.py" 2>"$WORK/ssh-errors.log" |
while IFS= read -r line; do
  case "$line" in
    AARIS_AUTH_LINK=*)
      URL="$(printf '%s' "$line" | cut -c17-)"
      if python3 - "$URL" <<'PY'
import sys
from urllib.parse import urlsplit
try:
    p=urlsplit(sys.argv[1]); h=(p.hostname or '').lower()
    ok=p.scheme=='https' and not p.username and not p.password and len(sys.argv[1])<4000 and any(h==s or h.endswith('.'+s) for s in ('unity.com','unity3d.com'))
except ValueError: ok=False
sys.exit(0 if ok else 1)
PY
      then
        printf '\nUnity official login link (only visible on your phone):\n%s\n\n' "$URL"
        if command -v termux-open-url >/dev/null 2>&1; then
          termux-open-url "$URL" || true
        fi
        echo 'Sign in with your Unity account/Google and tap Allow. Return to Termux afterward.'
      else echo 'Rejected unexpected login URL.'; fi
      ;;
    UNITY_AUTH_STARTED) echo 'Unity sign-in started.' ;;
    UNITY_AUTH_ALREADY_VALID) echo 'Existing Unity account login valid.' ;;
    UNITY_AUTH_VERIFIED) echo 'Unity browser login verified on Codespace.' ;;
    UNITY_LICENSE_ALREADY_ACTIVE|UNITY_PERSONAL_LICENSE_VERIFIED)
      echo 'SUCCESS: Unity license verified on the Codespace.' ;;
    UNITY_PERSONAL_ACTIVATION_START) echo 'Unity Personal activation started.' ;;
    UNITY_PERSONAL_NOT_ACTIVE_HUB_MAY_BE_REQUIRED) echo 'Unity Personal activation was not accepted; Unity Hub may be needed.' ;;
    UNITY_AUTH_NOT_COMPLETED) echo 'Unity Allow/login not completed in time.' ;;
    UNITY_CLI_MISSING_RUN_CS_INSTALL_FIRST) echo 'Unity CLI is not installed on Codespace.' ;;
    UNITY_PERSONAL_ACTIVATION_ERROR) echo 'Unity Personal activation failed.' ;;
    *) : ;; # Never echo arbitrary remote output containing credentials
  esac
done
PIPE_EXIT=$?
set -e
if (( PIPE_EXIT != 0 )); then
  echo 'Unity auth was not verified. Check your Codespace, SSH connection and login.'
  exit "$PIPE_EXIT"
fi
