#!/usr/bin/env bash
# Reuse the same Unity Editor installation after Codespace stop/start.
# Supported Unity CLI 'install --download-directory' avoids Hub global install-path state.
set -Eeuo pipefail
VERSION="6000.3.26f1"
CHANGESET="de8167e7440c"
RUN="/tmp/aaris-codespaces"
EDITOR_ROOT="$HOME/.local/share/aaris-unity-editors"
CLI_HOME="$HOME/.local/share/aaris-unity-cli"
# Unity's official Linux installer normally puts the executable in ~/.local/bin.
# UNITY_CLI_HOME stores configuration/session; it does not set executable location.
find_cli() {
  local file
  for file in "$CLI_HOME/bin/unity" "$HOME/.local/bin/unity" "$HOME/.unity/bin/unity" \
              "/home/vscode/.local/bin/unity" "/tmp/aaris-unity-runtime/cli/bin/unity"; do
    if test -x "$file"; then printf '%s\n' "$file"; return 0; fi
  done
  command -v unity || return 1
}
CLI="$(find_cli || true)"
mkdir -p "$RUN" "$EDITOR_ROOT" "$CLI_HOME"
chmod 700 "$CLI_HOME"
if test -x "$EDITOR_ROOT/$VERSION/Editor/Unity"; then
  echo "UNITY_PERSISTENT_EDITOR_READY"
  exit 0
fi
FREE_KB="$(df -Pk "$HOME" | awk 'NR==2{print $4}')"
if (( FREE_KB < 8000000 )); then
  echo "UNITY_PERSISTENT_SPACE_INSUFFICIENT"
  echo "UNITY_REQUIRED_FREE_KB_MIN=8000000"
  exit 7
fi
export UNITY_CLI_HOME="$CLI_HOME"
export UNITY_NON_INTERACTIVE=1
export DO_NOT_TRACK=1
if test -z "$CLI"; then
  echo "UNITY_CLI_BOOTSTRAPPING"
  if ! curl -fsSL --retry 2 --connect-timeout 30 --max-time 150 https://unity.com/install.sh -o "$RUN/unity-cli-installer.sh"; then
    echo "UNITY_CLI_DOWNLOAD_FAILED"; exit 3
  fi
  if ! bash "$RUN/unity-cli-installer.sh" >"$RUN/unity-cli-setup.log" 2>&1; then
    echo "UNITY_CLI_INSTALL_FAILED"; exit 4
  fi
  CLI="$(find_cli || true)"
fi
if test -z "$CLI" || ! test -x "$CLI"; then echo "UNITY_CLI_BINARY_MISSING"; exit 5; fi
echo "UNITY_CLI_READY"
echo "UNITY_EDITOR_PERSISTENT_INSTALL_START"
# Unity installer downloads to a portable Editor directory and can resume partial downloads.
if ! "$CLI" install "$VERSION" --changeset "$CHANGESET" --download-directory "$EDITOR_ROOT" --resume --non-interactive >"$RUN/cli-editor-install.log" 2>&1; then
  python3 - "$RUN/cli-editor-install.log" <<'PY'
from pathlib import Path
import sys,re
s=Path(sys.argv[1]).read_text(errors="replace")[-30000:]
k=[
("EULA",r"accept-eula|terms.*not accepted|eula|TERMS_ACCEPT"),
("LOW_DISK",r"no space left|insufficient space|disk.*full"),
("AUTHORIZATION",r"authentication required|not signed in|unauthorized|403"),
("NETWORK",r"timed out|TLS|certificate|network|connection reset"),
("VERSION",r"changeset.*not|not.*changeset|release.*not found|404"),
("CLI_USAGE",r"unknown command|unknown flag|unexpected argument|usage:"),
("INSTALL_BUSY",r"install.*lock|another install|waiting for another"),
]
print("UNITY_EDITOR_INSTALL_CATEGORY_"+next((name for name,pat in k if re.search(pat,s,re.I)),"UNCLASSIFIED"))
PY
  exit 8
fi
test -x "$EDITOR_ROOT/$VERSION/Editor/Unity" || {
  echo "UNITY_EDITOR_BINARY_NOT_AT_EXPECTED_PATH"; exit 9;
}
echo "UNITY_PERSISTENT_EDITOR_READY"
