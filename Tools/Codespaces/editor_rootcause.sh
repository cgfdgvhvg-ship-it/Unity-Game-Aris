#!/usr/bin/env bash
# Read-only crash triage on the exact EXISTING project, no temp project/worktree/clone.
# Only bounded, enum-style diagnostics leave the Codespace; raw logs stay private.
set -Eeuo pipefail
ROOT=/workspaces/Unity-Game-Aris
RUN=/tmp/aaris-codespaces
mkdir -p "$RUN"
test -d "$ROOT/.git" || { echo AARIS_ROOTCAUSE_PROJECT_MISSING; exit 41; }
EDITOR=""
for candidate in "$HOME/.local/share/aaris-unity-editors/6000.3.26f1/Editor/Unity" \
    /workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity \
    /tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity; do
  if test -x "$candidate"; then EDITOR="$candidate"; break; fi
done
test -n "$EDITOR" || { echo AARIS_ROOTCAUSE_EDITOR_BINARY_MISSING; exit 42; }
if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
  echo AARIS_ROOTCAUSE_EDITOR_ALREADY_RUNNING
  exit 43
fi
echo AARIS_ROOTCAUSE_EXISTING_CODESPACE_ONLY
echo AARIS_ROOTCAUSE_EDITOR_BINARY_PRESENT
if DISPLAY=:99 xdpyinfo >/dev/null 2>&1; then echo AARIS_ROOTCAUSE_DISPLAY_READY; else echo AARIS_ROOTCAUSE_DISPLAY_MISSING; fi
if head -c 100 "$ROOT/Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity" 2>/dev/null |
    grep -q 'git-lfs.github.com/spec'; then
  echo AARIS_ROOTCAUSE_NATIVE_SCENE_LFS_POINTER
else
  echo AARIS_ROOTCAUSE_NATIVE_SCENE_NOT_POINTER
fi
if test -L "$ROOT/Library"; then echo AARIS_ROOTCAUSE_LIBRARY_IS_SYMLINK; elif test -d "$ROOT/Library"; then echo AARIS_ROOTCAUSE_LIBRARY_IS_DIRECTORY; else echo AARIS_ROOTCAUSE_LIBRARY_ABSENT; fi
if command -v ldd >/dev/null 2>&1; then
  ldout="$(ldd "$EDITOR" 2>/dev/null || true)"
  if grep -q 'not found' <<< "$ldout"; then
    echo AARIS_ROOTCAUSE_LINKER_MISSING_LIBRARY
    grep 'not found' <<< "$ldout" | sed -En 's/^[[:space:]]*([A-Za-z0-9._+-]+)[[:space:]]*=>[[:space:]]*not found.*/MISSING_LIBRARY_\1/p' | head -n 15
  else echo AARIS_ROOTCAUSE_LINKER_NO_MISSING_DIRECT_LIBRARIES; fi
fi
if command -v glxinfo >/dev/null 2>&1; then
  if timeout 12 env DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1 glxinfo -B >/dev/null 2>&1; then
    echo AARIS_ROOTCAUSE_SOFTWARE_GLX_WORKS
  else echo AARIS_ROOTCAUSE_SOFTWARE_GLX_FAILED; fi
fi
if test -f "$RUN/editor-exit-code.txt"; then
  exitcode="$(cat "$RUN/editor-exit-code.txt" 2>/dev/null || true)"
  case "$exitcode" in
    0|1|2|3|11|12|13|127|134|137|139|143) echo "AARIS_ROOTCAUSE_PREVIOUS_EDITOR_EXIT_$exitcode" ;;
    *) echo AARIS_ROOTCAUSE_PREVIOUS_EDITOR_EXIT_UNKNOWN ;;
  esac
fi
# -version is not a project open, test only the actual installed Editor executable.
# Do not mutate /workspaces, Unity license, game sources, or caches.
VOUT="$(mktemp "$RUN/version-check.XXXXXXXX")"
VERR="$(mktemp "$RUN/version-error.XXXXXXXX")"
trap 'rm -f "$VOUT" "$VERR"' EXIT
rc=0
timeout --kill-after=5s 45s env TMPDIR="$RUN" "$EDITOR" -version \
  >"$VOUT" 2>"$VERR" || rc=$?
case "$rc" in
  0) echo AARIS_ROOTCAUSE_VERSION_EXEC_OK ;;
  124) echo AARIS_ROOTCAUSE_VERSION_EXEC_TIMEOUT ;;
  127) echo AARIS_ROOTCAUSE_VERSION_EXEC_LINK_FAILURE ;;
  134) echo AARIS_ROOTCAUSE_VERSION_EXEC_ABORT ;;
  137) echo AARIS_ROOTCAUSE_VERSION_EXEC_KILLED ;;
  139) echo AARIS_ROOTCAUSE_VERSION_EXEC_SEGFAULT ;;
  *) echo AARIS_ROOTCAUSE_VERSION_EXEC_OTHER ;;
esac
python3 - "$RUN" "$VERR" <<'PY'
from pathlib import Path
import re,sys
logs=[
 Path(sys.argv[1])/'Editor.log',
 Path(sys.argv[1])/'editor-launch-stderr.log',
 Path.home()/'.config/unity3d/Editor.log',
 Path(sys.argv[2]),
]
found=False
for i,p in enumerate(logs):
    if not p.is_file() or not p.stat().st_size: continue
    found=True
    s=p.read_bytes()[-3000000:].decode('utf-8','replace')
    checks={
      "LIBRARY":r'error while loading shared libraries|cannot open shared object file',
      "LICENSE":r'no valid.*licen[sc]e|licen[sc]e.*(?:failed|expired|invalid)',
      "DISPLAY":r'cannot open display|X11.*(?:error|failed)',
      "GFX":r'GfxDevice|initialize graphics|initialize.*opengl|Vulkan',
      "GL_MESA":r'Mesa|llvmpipe|GLX|OpenGL',
      "IMPORT":r'AssetDatabase|importing assets|refreshing assets|ImportWorker',
      "COMPILATION":r'compil|BeeBuild|ScriptCompilation',
      "PACKAGE":r'Package Manager|UPM|package resolution',
      "PROJECT_LOCK":r'already open|project.*lock',
      "SEGFAULT":r'SIGSEGV|signal 11|segmentation fault|crash handler',
      "MEMORY":r'out of memory|std::bad_alloc|allocation failed',
      "SHADER":r'shader compil|ShaderLab',
      "ASSERT":r'Assertion failed|assertion',
      "DOUBLE_FREE":r'double free|corrupted size|malloc.*corruption',
      "BUS_ERROR":r'bus error|SIGBUS',
      "MONO":r'mono.*(?:crash|exception)|scripting backend',
      "BURST":r'BurstCompiler|lib_burst',
    }
    labels=[name for name,pat in checks.items() if re.search(pat,s,re.I)]
    print(f'AARIS_ROOTCAUSE_LOG_{i}_PRESENT')
    for lab in labels: print(f'AARIS_ROOTCAUSE_LOG_{i}_{lab}')
    # Most recently reached stage, not a generic trigger. No private log text.
    stages=[('INIT',r'Initialize|Launching Unity|Unity Editor'),('LICENSE',r'Licen[sc]'),('PACKAGE',checks['PACKAGE']),('IMPORT',checks['IMPORT']),('COMPILE',checks['COMPILATION']),('GRAPHICS',checks['GFX'])]
    pos=[(m.start(),name) for name,pat in stages for m in re.finditer(pat,s,re.I)]
    if pos: print('AARIS_ROOTCAUSE_LOG_'+str(i)+'_LAST_STAGE_'+max(pos)[1])
if not found: print('AARIS_ROOTCAUSE_LOGS_UNAVAILABLE')
PY
echo AARIS_ROOTCAUSE_READONLY_COMPLETE
