#!/usr/bin/env bash
# Safe, fixed Unity native-crash isolation on the approved EXISTING Codespace.
# Uses ONLY a new disposable /tmp project, never /workspaces or Unity source.
# Results contain fixed tokens/exit codes; all raw logs remain private locally.
set -Eeuo pipefail
EDITOR=""
for candidate in "$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity" \
                 "/workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity" \
                 "/tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity"; do
  if [[ -x "$candidate" ]]; then EDITOR="$candidate"; break; fi
done
if [[ -z "$EDITOR" || ! -x "$EDITOR" ]]; then
  echo EDITOR_ISOLATE_BINARY_MISSING
  exit 21
fi
if pgrep -f '[E]ditor/Unity.*-projectPath /workspaces/Unity-Game-Aris' >/dev/null 2>&1; then
  echo EDITOR_ISOLATE_BLOCKED_LIVE_GAME_EDITOR
  exit 22
fi
umask 077
BASE=/tmp/aaris-codespaces
mkdir -p "$BASE"
WORK="$(mktemp -d "$BASE/editor-isolation.XXXXXXXX")"
case "$WORK" in "$BASE"/editor-isolation.*) ;; *) echo EDITOR_ISOLATE_INVALID_TMP_PATH; exit 23 ;; esac
trap 'rm -rf -- "$WORK"' EXIT
PROJECT="$WORK/EmptyUnityProject"
mkdir -p "$PROJECT/Assets" "$PROJECT/ProjectSettings" "$WORK/UnityTemp"
printf 'm_EditorVersion: 6000.3.26f1\n' > "$PROJECT/ProjectSettings/ProjectVersion.txt"
echo EDITOR_ISOLATE_TEMP_ONLY

report() {
  local name="$1" code="$2"
  if ((code<0 || code>255)); then code=255; fi
  echo "EDITOR_ISOLATE_${name}_EXIT_${code}"
  case "$code" in
    0) echo "EDITOR_ISOLATE_${name}_OK" ;;
    124) echo "EDITOR_ISOLATE_${name}_TIMEOUT" ;;
    137) echo "EDITOR_ISOLATE_${name}_KILLED_OR_OOM" ;;
    139) echo "EDITOR_ISOLATE_${name}_SEGFAULT" ;;
    *) echo "EDITOR_ISOLATE_${name}_NOT_OK" ;;
  esac
}
# Exclude log text and machine-specific paths from public output.
rc=0
timeout --kill-after=10s 40s env TMPDIR="$WORK/UnityTemp" "$EDITOR" -version \
  >"$WORK/version.stdout.private" 2>"$WORK/version.stderr.private" || rc=$?
report VERSION "$rc"
if ((rc==139)); then
  echo EDITOR_ISOLATE_BINARY_CRASHES_WITHOUT_PROJECT
  exit 0
fi
rc=0
timeout --kill-after=10s 210s env TMPDIR="$WORK/UnityTemp" "$EDITOR" \
  -batchmode -nographics -quit -projectPath "$PROJECT" \
  -logFile "$WORK/headless.log.private" \
  >"$WORK/headless.stdout.private" 2>"$WORK/headless.stderr.private" || rc=$?
report HEADLESS "$rc"
if ((rc!=0)); then
  echo EDITOR_ISOLATE_HEADLESS_NOT_PROVEN
  exit 0
fi
if ! DISPLAY=:99 xdpyinfo >/dev/null 2>&1; then
  echo EDITOR_ISOLATE_DISPLAY_UNAVAILABLE
  exit 0
fi
# A GUI-backed batch process initializes the software GL path without
# opening or modifying the real terrain scene or the dirty working tree.
rc=0
timeout --kill-after=10s 150s env DISPLAY=:99 TMPDIR="$WORK/UnityTemp" LIBGL_ALWAYS_SOFTWARE=1 "$EDITOR" \
  -batchmode -quit -force-glcore -projectPath "$PROJECT" \
  -logFile "$WORK/graphics.log.private" \
  >"$WORK/graphics.stdout.private" 2>"$WORK/graphics.stderr.private" || rc=$?
report GRAPHICS "$rc"
if ((rc==139)); then echo EDITOR_ISOLATE_SOFTWARE_GL_CRASH_CANDIDATE; fi
if ((rc==0)); then echo EDITOR_ISOLATE_EMPTY_PROJECT_SUCCEEDED; fi
