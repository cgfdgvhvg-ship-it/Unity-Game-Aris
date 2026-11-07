#!/usr/bin/env bash
# GitHub Actions entrypoint. Never interpret arbitrary text as terminal commands.
set -euo pipefail
OUT="$GITHUB_WORKSPACE/codespace-results"
mkdir -p "$OUT"
REPO="$GITHUB_REPOSITORY"
OP="$REQUEST_OPERATION"
MACHINE="$REQUEST_MACHINE"
ISSUE="$ISSUE_COMMAND"
STATE="FAILED"
DETAIL="not_started"
CS=""
: > "$OUT/terminal.txt"
finish() {
  local rc="$?"
  python3 - "$OUT/result.json" "$OP" "$STATE" "$DETAIL" "$CS" "$rc" <<'PY'
import json,sys
p,op,state,detail,cs,rc=sys.argv[1:]
with open(p,'w') as f:
    json.dump(dict(operation=op,status=state,detail=detail,codespace=cs,exit_code=int(rc)),f,indent=2)
PY
}
trap finish EXIT
if test -n "$ISSUE"; then
  case "$ISSUE" in
    'CS MACHINES') OP=machines ;;
    'CS START') OP=start ;;
    'CS REBUILD') OP=rebuild ;;
    'CS STATUS') OP=status ;;
    'CS LOGS') OP=logs ;;
    'CS INFO') OP=info ;;
    'CS SYNC') OP=sync ;;
    'CS LFS') OP=lfs ;;
    'CS LFS REPORT') OP=lfs_report ;;
    'CS CHANGES') OP=changes ;;
    'CS INSTALL') OP=install ;;
    'CS EDITOR') OP=editor ;;
    'CS LICENSE') OP=license ;;
    'CS AUTH') OP=auth ;;
    'CS PROBE') OP=probe ;;
    'CS SHOT') OP=shot ;;
    'CS TEST') OP=test ;;
    'CS STOP') OP=stop ;;
    *) DETAIL="unsupported_issue_command"; exit 2 ;;
  esac
fi
case "$OP" in
  machines|info|start|rebuild|status|logs|sync|lfs|lfs_report|changes|install|editor|license|auth|probe|shot|test|stop) ;;
  *) DETAIL="unsupported_operation"; exit 2 ;;
esac
if test -z "$GH_TOKEN"; then DETAIL="CODESPACE_PAT_missing"; exit 3; fi
if test -n "$MACHINE" && [[ ! "$MACHINE" =~ ^[A-Za-z0-9-]+$ ]]; then DETAIL="bad_machine"; exit 4; fi
if test "$OP" = probe; then
  if python3 "$GITHUB_WORKSPACE/Tools/Codespaces/relay_probe.py" >"$OUT/terminal.txt" 2>/dev/null; then
    STATE="SUCCESS"; DETAIL="oidc_relay_preflight_ok"; exit 0
  fi
  DETAIL="oidc_relay_preflight_failed"; exit 19
fi
if test "$OP" = machines; then
  if gh api "/repos/$REPO/codespaces/machines" --jq '.machines[] | [.name, (.cpus|tostring), ((.memory_in_bytes/1073741824|floor)|tostring)] | @tsv' > "$OUT/terminal.txt" 2>/dev/null; then
    STATE="SUCCESS"; DETAIL="machine_types_CPU_RAM_GiB"; exit 0
  fi
  DETAIL="machine_API_unavailable"; exit 5
fi
LIST="$(gh codespace list -R "$REPO" --json name,displayName,machineName,state --limit 30 2>/dev/null)" || {
  DETAIL="codespace_list_failed_token_scope"; exit 6
}
CS="$(jq -r '[.[] | select(.displayName=="aaris-ai-unity")][0].name // .[0].name // ""' <<< "$LIST")"
if test -z "$CS" && test "$OP" = start; then
  if test -z "$MACHINE"; then
    TYPES="$(gh api "/repos/$REPO/codespaces/machines" 2>/dev/null)" || { DETAIL="machine_API_unavailable"; exit 5; }
    MACHINE="$(jq -r '[.machines[] | select(.cpus>=4 and .memory_in_bytes>=16000000000)] | sort_by(.cpus) | .[0].name // ""' <<< "$TYPES")"
  fi
  test -n "$MACHINE" || { DETAIL="no_available_4core_16gb_machine"; exit 7; }
  CS="$(gh codespace create -R "$REPO" -b main -m "$MACHINE" --idle-timeout 240m --display-name aaris-ai-unity --default-permissions 2>/dev/null)" || {
    DETAIL="codespace_create_failed_quota_or_permissions"; exit 8
  }
  CS="$(printf '%s' "$CS" | tail -n 1 | tr -d '[:space:]')"
  [[ "$CS" =~ ^[A-Za-z0-9-]+$ ]] || { DETAIL="bad_codespace_response"; exit 9; }
  printf 'codespace=%s\nmachine=%s\n' "$CS" "$MACHINE" > "$OUT/terminal.txt"
  STATE="SUCCESS"; DETAIL="codespace_created"; exit 0
fi
if test -z "$CS"; then STATE="NO_CODESPACE"; DETAIL="run_CS_START"; exit 0; fi
[[ "$CS" =~ ^[A-Za-z0-9-]+$ ]] || { DETAIL="bad_codespace_name"; exit 9; }
# Read Codespace machine and state without SSH. Safe when the old container is unavailable.
if test "$OP" = logs; then
  if timeout 110 python3 "$GITHUB_WORKSPACE/Tools/Codespaces/codespace_logs.py" "$CS" > "$OUT/terminal.txt" 2>/dev/null; then
    STATE="SUCCESS"; DETAIL="codespace_logs_classified_without_raw_output"; exit 0
  fi
  DETAIL="codespace_logs_command_failed"; exit 25
fi
if test "$OP" = info; then
  if gh codespace view -c "$CS" --json name,machineName,state,idleTimeoutMinutes,devcontainerPath \
      --jq '[("codespace=" + .name), ("machine=" + .machineName), ("state=" + .state), ("idle_minutes=" + (.idleTimeoutMinutes|tostring)), ("devcontainer=" + (.devcontainerPath // "default"))] | .[]' > "$OUT/terminal.txt" 2>/dev/null; then
    STATE="SUCCESS"; DETAIL="codespace_machine_and_state"; exit 0
  fi
  DETAIL="codespace_view_failed"; exit 14
fi
if test "$OP" = stop; then
  gh codespace stop -c "$CS" >/dev/null 2>&1 || { DETAIL="codespace_stop_failed"; exit 10; }
  STATE="SUCCESS"; DETAIL="codespace_stopped"; exit 0
fi
if test "$OP" = start; then
  # Existing Codespaces are started through GitHub's supported API; files are retained.
  gh api -X POST "/user/codespaces/$CS/start" >/dev/null 2>&1 || {
    # It may already be running; the next STATUS will verify.
    echo 'START_API_NOT_CONFIRMED_CHECK_STATUS' > "$OUT/terminal.txt"
    STATE="UNKNOWN"; DETAIL="check_status"; exit 0
  }
  echo "codespace=$CS" > "$OUT/terminal.txt"
  STATE="SUCCESS"; DETAIL="existing_codespace_start_requested"; exit 0
fi
# GitHub Codespaces preserves /workspaces on devcontainer rebuild.
# Only the repository owner's exact CS REBUILD operation reaches this block.
if test "$OP" = rebuild; then
  if ! jq -e '.image == "mcr.microsoft.com/devcontainers/base:ubuntu-22.04" and .remoteUser == "vscode"' "$GITHUB_WORKSPACE/.devcontainer/devcontainer.json" >/dev/null; then
    DETAIL="ubuntu_devcontainer_configuration_missing"; exit 21
  fi
  if ! timeout 120 gh codespace ssh -c "$CS" -- "bash -s" < "$GITHUB_WORKSPACE/Tools/Codespaces/rebuild_preflight.sh" > "$OUT/terminal.txt" 2>/dev/null; then
    DETAIL="rebuild_preflight_workspace_unverified"; exit 22
  fi
  if ! grep -qxF "AARIS_REBUILD_PREFLIGHT_READY" <(tail -n 1 "$OUT/terminal.txt"); then
    DETAIL="rebuild_preflight_not_ready"; exit 23
  fi
  # Non-full rebuild; do not reset Git or overwrite /workspaces/LFS.
  if timeout 2400 gh codespace rebuild -c "$CS" >/dev/null 2>/dev/null; then
    echo "AARIS_UBUNTU_REBUILD_REQUEST_COMPLETED" >> "$OUT/terminal.txt"
    STATE="SUCCESS"; DETAIL="rebuild_command_completed_verify_status"; exit 0
  fi
  echo "AARIS_UBUNTU_REBUILD_COMMAND_FAILED" >> "$OUT/terminal.txt"
  DETAIL="codespace_rebuild_failed_or_timed_out"; exit 24
fi
# Stream the approved checked-in script over SSH stdin. No SCP or old remote checkout needed.
PRIVATE_ERRORS="$RUNNER_TEMP/aaris-codespace-ssh-errors.log"
trap 'finish; rm -f "$PRIVATE_ERRORS"' EXIT

safe_error_summary() {
  python3 - "$PRIVATE_ERRORS" "$OUT/ssh-diagnostic.txt" <<'PY'
from pathlib import Path
import re,sys
s=Path(sys.argv[1]).read_text(errors="replace") if Path(sys.argv[1]).exists() else ""
if not s.strip():
    reason="no_stderr_from_gh_cli"
elif re.search(r"permission denied|not authorized|forbidden|unauthorized|HTTP 403",s,re.I):
    reason="permission_or_token_denied"
elif re.search(r"connection refused|connect.*failed|connect.*error|unable to connect",s,re.I):
    reason="ssh_connection_failed"
elif re.search(r"no such file|not found|missing",s,re.I):
    reason="missing_binary_or_file"
elif re.search(r"unknown flag|unknown command|invalid argument|usage:",s,re.I):
    reason="gh_cli_invocation_invalid"
elif re.search(r"timed out|timeout|deadline exceeded",s,re.I):
    reason="ssh_timeout"
elif re.search(r"could not resolve|lookup|DNS",s,re.I):
    reason="dns_or_network"
elif re.search(r"public key|ssh key|agent",s,re.I):
    reason="ssh_key_failure"
else:
    reason="unclassified_gh_cli_error"
# Preserve diagnostic shape without logging credentials or arbitrary remote stderr.
Path(sys.argv[2]).write_text("diagnostic_category="+reason+"\nerror_bytes="+str(len(s.encode()))+"\n")
PY
}

REMOTE_TIMEOUT=130
case "$OP" in
  install) REMOTE_TIMEOUT=3000 ;;
  sync|lfs) REMOTE_TIMEOUT=1200 ;;
  test) REMOTE_TIMEOUT=500 ;;
  editor) REMOTE_TIMEOUT=350 ;;
esac
if test "$OP" = auth; then
  # Intercept the remote Unity OAuth URL, keep it OFF all public logs/artifacts.
  if timeout 825 python3 "$GITHUB_WORKSPACE/Tools/Codespaces/auth_bridge.py" "$CS" > "$OUT/terminal.txt" 2>"$PRIVATE_ERRORS"; then
    STATE="SUCCESS"; DETAIL="unity_license_checked"; exit 0
  fi
  safe_error_summary
  DETAIL="unity_auth_incomplete_see_private_link"
  exit 17
fi
SCRIPT_FILE="$GITHUB_WORKSPACE/Tools/Codespaces/remote.sh"
REMOTE_SHELL="bash -s -- $OP"
if test "$OP" = install; then
  SCRIPT_FILE="$GITHUB_WORKSPACE/Tools/Codespaces/install_unity.sh"
  REMOTE_SHELL="bash -s"
fi
for attempt in 1 2; do
  if timeout "$REMOTE_TIMEOUT" gh codespace ssh -c "$CS" -- "$REMOTE_SHELL" \
      < "$SCRIPT_FILE" \
      > "$OUT/terminal.txt" 2>"$PRIVATE_ERRORS"; then
    rm -f "$PRIVATE_ERRORS"
    if test "$OP" = shot; then
      if timeout 90 gh codespace ssh -c "$CS" -- 'base64 /tmp/aaris-codespaces/screen.png' \
          > "$OUT/screen.b64" 2>"$PRIVATE_ERRORS"; then
        base64 --decode "$OUT/screen.b64" > "$OUT/screen.png"
        rm -f "$OUT/screen.b64"
        if ! file "$OUT/screen.png" | grep -q 'PNG image data'; then
          DETAIL="screen_invalid_png"; exit 16
        fi
        DETAIL="screen_in_actions_artifact"
      else DETAIL="screen_transfer_failed"; safe_error_summary; exit 13; fi
    else DETAIL="remote_task_complete"; fi
    STATE="SUCCESS"; exit 0
  fi
  test "$OP" = status || break
  sleep 7
done
safe_error_summary
DETAIL="SSH_execution_failed_see_diagnostic_category"
exit 11
