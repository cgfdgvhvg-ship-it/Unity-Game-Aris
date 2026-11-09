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

# Reproduce the Unity Editor play-mode transition WITHOUT project gameplay.
# This is an independent, temporary-project diagnostic. A passing result does
# NOT excuse or suppress a failing native game scene Play probe.
mkdir -p "$PROJECT/Assets/Editor"
cat >"$PROJECT/Assets/Editor/AarisEmptyPlayTransitionProbe.cs" <<'CSHARP'
using System;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class AarisEmptyPlayTransitionProbe
{
    private const string State = "aaris.empty.play.state";
    private const string Errors = "aaris.empty.play.errors";
    private const string Deadline = "aaris.empty.play.deadline";
    private static bool exiting;

    static AarisEmptyPlayTransitionProbe()
    {
        EditorApplication.update += Tick;
        Application.logMessageReceived += OnLog;
    }

    public static void Begin()
    {
        SessionState.SetInt(Errors, 0);
        SessionState.SetFloat(Deadline,
            (float)EditorApplication.timeSinceStartup + 75f);
        SessionState.SetString(State, "starting");
        EditorApplication.isPlaying = true;
        Debug.Log("AARIS_EMPTY_PLAY_REQUESTED");
    }

    private static void OnLog(string message, string trace, LogType kind)
    {
        if (SessionState.GetString(State, "") == "") return;
        if (kind == LogType.Error || kind == LogType.Exception || kind == LogType.Assert)
            SessionState.SetInt(Errors, SessionState.GetInt(Errors, 0) + 1);
    }

    private static void Tick()
    {
        string state = SessionState.GetString(State, "");
        if (state == "" || exiting) return;
        if (EditorApplication.timeSinceStartup > SessionState.GetFloat(Deadline, 0f))
        {
            exiting = true;
            Debug.Log("AARIS_EMPTY_PLAY_TIMED_OUT");
            EditorApplication.Exit(3);
            return;
        }
        if (state == "starting" && EditorApplication.isPlaying)
        {
            SessionState.SetString(State, "running");
            return;
        }
        if (state == "running" && EditorApplication.isPlaying && Time.frameCount >= 60)
        {
            SessionState.SetString(State, "stopping");
            EditorApplication.isPlaying = false;
            return;
        }
        if (state == "stopping" && !EditorApplication.isPlayingOrWillChangePlaymode)
        {
            exiting = true;
            int errors = SessionState.GetInt(Errors, 0);
            if (errors == 0) Debug.Log("AARIS_EMPTY_PLAY_60_FRAMES_PASS");
            else Debug.Log("AARIS_EMPTY_PLAY_60_FRAMES_ERRORS");
            SessionState.SetString(State, "");
            EditorApplication.Exit(errors == 0 ? 0 : 2);
        }
    }
}
CSHARP

rc=0
timeout --kill-after=10s 115s env DISPLAY=:99 TMPDIR="$WORK/UnityTemp" LIBGL_ALWAYS_SOFTWARE=1 \
  "$EDITOR" -batchmode -force-glcore -projectPath "$PROJECT" \
  -executeMethod AarisEmptyPlayTransitionProbe.Begin \
  -logFile "$WORK/empty-play.log.private" \
  >"$WORK/empty-play.stdout.private" 2>"$WORK/empty-play.stderr.private" || rc=$?
report EMPTY_PLAY "$rc"
if grep -Fq 'IndexOutOfRangeException' "$WORK/empty-play.log.private" 2>/dev/null; then
  echo EDITOR_ISOLATE_EMPTY_PLAY_ARRAY_INDEX_EXCEPTION
fi
if grep -Fq 'AARIS_EMPTY_PLAY_60_FRAMES_PASS' "$WORK/empty-play.log.private" 2>/dev/null &&
   ((rc == 0)); then
  echo EDITOR_ISOLATE_EMPTY_PLAY_60_FRAMES_VERIFIED
else
  echo EDITOR_ISOLATE_EMPTY_PLAY_NOT_VERIFIED
fi
