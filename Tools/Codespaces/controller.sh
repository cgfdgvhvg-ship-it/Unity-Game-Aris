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
    'CS STATUS') OP=status ;;
    'CS INFO') OP=info ;;
    'CS SYNC') OP=sync ;;
    'CS INSTALL') OP=install ;;
    'CS EDITOR') OP=editor ;;
    'CS LICENSE') OP=license ;;
    'CS SHOT') OP=shot ;;
    'CS TEST') OP=test ;;
    'CS STOP') OP=stop ;;
    *) DETAIL="unsupported_issue_command"; exit 2 ;;
  esac
fi
case "$OP" in
  machines|info|start|status|sync|install|editor|license|shot|test|stop) ;;
  *) DETAIL="unsupported_operation"; exit 2 ;;
esac
if test -z "$GH_TOKEN"; then DETAIL="CODESPACE_PAT_missing"; exit 3; fi
if test -n "$MACHINE" && [[ ! "$MACHINE" =~ ^[A-Za-z0-9-]+$ ]]; then DETAIL="bad_machine"; exit 4; fi
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
# For older Codespaces, place this already-reviewed script into /tmp first.
# Avoid assuming the existing checkout already contains today's new controller files.
PRIVATE_ERRORS="$RUNNER_TEMP/aaris-codespace-ssh-errors.log"
trap 'finish; rm -f "$PRIVATE_ERRORS"' EXIT
REMOTE_PATH="/tmp/aaris-control-remote.sh"
if ! timeout 75 gh codespace cp -c "$CS" \
    "$GITHUB_WORKSPACE/Tools/Codespaces/remote.sh" "remote:$REMOTE_PATH" \
    >/dev/null 2>"$PRIVATE_ERRORS"; then
  if grep -Eqi 'permission denied|authentication|forbidden|HTTP 403|unauthorized' "$PRIVATE_ERRORS"; then
    DETAIL="codespace_copy_authorization_denied"
  elif grep -Eqi 'timeout|timed out|deadline exceeded' "$PRIVATE_ERRORS"; then
    DETAIL="codespace_copy_timeout"
  elif grep -Eqi 'SSH|ssh|connection|not running|startup' "$PRIVATE_ERRORS"; then
    DETAIL="codespace_copy_ssh_not_ready"
  else DETAIL="codespace_copy_failed"; fi
  rm -f "$PRIVATE_ERRORS"
  exit 12
fi
REMOTE_CMD="bash $REMOTE_PATH $OP"
for attempt in 1 2; do
  if timeout 85 gh codespace ssh -c "$CS" -- "$REMOTE_CMD" \
      > "$OUT/terminal.txt" 2>"$PRIVATE_ERRORS"; then
    rm -f "$PRIVATE_ERRORS"
    if test "$OP" = shot; then
      if timeout 75 gh codespace cp -c "$CS" \
          'remote:/tmp/aaris-codespaces/screen.png' "$OUT/screen.png" \
          >/dev/null 2>"$PRIVATE_ERRORS"; then
        DETAIL="screen_in_actions_artifact"
      else DETAIL="screen_copy_failed"; rm -f "$PRIVATE_ERRORS"; exit 13; fi
    else DETAIL="remote_task_complete"; fi
    STATE="SUCCESS"; exit 0
  fi
  test "$OP" = status || break
  sleep 7
done
if grep -Eqi 'permission denied|authentication|forbidden|unauthorized|HTTP 403' "$PRIVATE_ERRORS"; then
  DETAIL="SSH_auth_or_permissions"
elif grep -Eqi 'No such file or directory|not found|cannot access' "$PRIVATE_ERRORS"; then
  DETAIL="SSH_remote_file_missing"
elif grep -Eqi 'timeout|timed out|deadline exceeded' "$PRIVATE_ERRORS"; then
  DETAIL="SSH_timeout"
else DETAIL="SSH_remote_task_failed"; fi
rm -f "$PRIVATE_ERRORS"
exit 11
