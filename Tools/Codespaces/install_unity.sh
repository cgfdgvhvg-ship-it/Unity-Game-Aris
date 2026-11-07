#!/usr/bin/env bash
# Official Unity CLI replaces the deprecated Unity Hub headless interface.
set -Eeuo pipefail
VERSION="6000.3.26f1"
CHANGESET="de8167e7440c"
RUNTIME="/tmp/aaris-unity-runtime"
EDITOR_ROOT="$RUNTIME/editors"
export UNITY_CLI_HOME="$RUNTIME/cli"
export UNITY_NON_INTERACTIVE=1
export DO_NOT_TRACK=1
CLI="$UNITY_CLI_HOME/bin/unity"
RUN="/tmp/aaris-codespaces"
mkdir -p "$RUN" "$EDITOR_ROOT" "$UNITY_CLI_HOME"
FREE_KB="$(df -Pk /tmp | awk 'NR==2{print $4}')"
if (( FREE_KB < 16000000 )); then echo "UNITY_TMP_DISK_INSUFFICIENT"; exit 7; fi
if test -x "$EDITOR_ROOT/$VERSION/Editor/Unity"; then
  echo "UNITY_EDITOR_ALREADY_INSTALLED"
  exit 0
fi
# The installer comes from the official Unity host. Never curl | bash or print tokens.
if ! test -x "$CLI"; then
  echo "UNITY_CLI_BOOTSTRAPPING"
  if ! curl -fsSL --connect-timeout 30 --max-time 120 https://unity.com/install.sh -o "$RUN/unity-cli-installer.sh"; then
    echo "UNITY_CLI_DOWNLOAD_FAILED"; exit 3
  fi
  if ! bash "$RUN/unity-cli-installer.sh" >"$RUN/unity-cli-setup.log" 2>&1; then
    echo "UNITY_CLI_INSTALL_FAILED"; exit 4
  fi
fi
if ! test -x "$CLI"; then echo "UNITY_CLI_BINARY_MISSING"; exit 5; fi
echo "UNITY_CLI_READY"
if ! "$CLI" install-path "$EDITOR_ROOT" >"$RUN/cli-install-path.log" 2>&1; then
  echo "UNITY_CLI_INSTALL_PATH_FAILED"
  exit 6
fi
echo "UNITY_EDITOR_INSTALL_START"
if ! "$CLI" install "$VERSION" --changeset "$CHANGESET" >"$RUN/cli-editor-install.log" 2>&1; then
  # Only sanitized classifications leave the Codespace.
  python3 - "$RUN/cli-editor-install.log" <<'PY'
from pathlib import Path
import sys,re
s=Path(sys.argv[1]).read_text(errors="replace")[-50000:]
pairs=[
("INSUFFICIENT_DISK",r"no space left|insufficient space|disk.*full"),
("AUTHORIZATION",r"unauthorized|authentication required|permission denied|not signed in|403"),
("NETWORK",r"timed out|TLS|certificate|network|connection reset|unable to connect"),
("UNKNOWN_CHANGESET",r"changeset.*not|not.*changeset|release.*not found|404"),
("ELEVATION",r"elevation|sudo|administrator|privilege"),
("CLI_USAGE",r"unknown command|unknown flag|unexpected argument|usage:"),
]
code=next((k for k,v in pairs if re.search(v,s,re.I)),"UNCLASSIFIED")
print("UNITY_EDITOR_INSTALL_CATEGORY_"+code)
PY
  exit 8
fi
if test ! -x "$EDITOR_ROOT/$VERSION/Editor/Unity"; then
  # Do not invent an Editor path if Unity changed its installer layout.
  echo "UNITY_EDITOR_BINARY_NOT_AT_EXPECTED_PATH"
  exit 9
fi
echo "UNITY_EDITOR_INSTALLED"
