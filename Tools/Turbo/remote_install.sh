#!/usr/bin/env bash
# Streamed over owner-authorized GitHub Codespace SSH only; never print grants.
set -euo pipefail
umask 077
test -n "$AARIS_AGENT_TOKEN" || exit 20
test -n "$AARIS_ENDPOINT" || exit 20
test -n "$AARIS_AGENT_BASE64" || exit 20
[[ "$AARIS_AGENT_TOKEN" =~ ^[0-9a-f]{64}$ ]] || exit 20
[[ "$AARIS_ENDPOINT" =~ ^https://[a-z0-9.-]+/agent/[A-Za-z0-9-]+$ ]] || exit 21
command -v python3 >/dev/null || { echo "TURBO_REMOTE_PYTHON_MISSING"; exit 22; }
HOME_DIR="$(getent passwd "$(id -u)" | cut -d: -f6)"
if [[ ! -d "$HOME_DIR" || ! -w "$HOME_DIR" ]]; then HOME_DIR="$HOME"; fi
test -d "$HOME_DIR" && test -w "$HOME_DIR" || exit 23
BIN="$HOME_DIR/.local/share/aaris-turbo"
CONFIG="$HOME_DIR/.config/aaris-turbo"
mkdir -p "$BIN" "$CONFIG"
chmod 700 "$BIN" "$CONFIG"
printf '%s' "$AARIS_AGENT_BASE64" | base64 -d > "$BIN/agent.new.py"
python3 -m py_compile "$BIN/agent.new.py"
python3 "$BIN/agent.new.py" --selftest >/dev/null
mv "$BIN/agent.new.py" "$BIN/agent.py"
printf '%s\n' "$AARIS_AGENT_TOKEN" > "$CONFIG/token"
chmod 600 "$CONFIG/token"
if test -s "$CONFIG/agent.pid"; then
  OLD="$(cat "$CONFIG/agent.pid")"
  if [[ "$OLD" =~ ^[0-9]+$ ]] && [[ -r "/proc/$OLD/cmdline" ]] &&
     tr '\0' ' ' < "/proc/$OLD/cmdline" | grep -qF "$BIN/agent.py"; then
    kill "$OLD" 2>/dev/null || true
  fi
fi
: > "$CONFIG/agent.log"
nohup env AARIS_ENDPOINT="$AARIS_ENDPOINT" AARIS_TOKEN_FILE="$CONFIG/token" \
  python3 -u "$BIN/agent.py" >> "$CONFIG/agent.log" 2>&1 </dev/null &
PID="$!"
printf '%s\n' "$PID" > "$CONFIG/agent.pid"
sleep 3
kill -0 "$PID" 2>/dev/null || { echo "TURBO_AGENT_START_FAILED"; exit 24; }
if grep -qxF AARIS_TURBO_AGENT_STARTED "$CONFIG/agent.log"; then
  echo "TURBO_AGENT_LIVE"
else
  echo "TURBO_AGENT_PROCESS_ALIVE"
fi
# Prove that the credential works on this Codespace, not merely that a
# detached Python process exists. Never print a token or raw response.
python3 - "$BIN/agent.py" "$CONFIG/token" "$AARIS_ENDPOINT" <<'PY'
import importlib.util
from pathlib import Path
import sys
try:
    spec = importlib.util.spec_from_file_location("aaris_turbo_agent", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    token = Path(sys.argv[2]).read_text(encoding="ascii").strip()
    result = module.Bridge(sys.argv[3], token).post("ping")
    if result.get("ok") is not True:
        raise RuntimeError("handshake_not_acknowledged")
except Exception as exc:
    print("TURBO_CLOUDFLARE_HANDSHAKE_FAILED_" + type(exc).__name__.upper())
    sys.exit(26)
print("TURBO_CLOUDFLARE_HANDSHAKE_PASS")
PY
echo "TURBO_NONDESTRUCTIVE_BOOTSTRAP_OK"
