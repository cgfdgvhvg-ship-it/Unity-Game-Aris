#!/usr/bin/env bash
# Only predetermined terminal tasks; no shell commands from public issue comments.
set -euo pipefail
TASK="$1"
PROJECT="/workspaces/Unity-Game-Aris"
RUN="/tmp/aaris-codespaces"
EDITOR="/workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity"
OLD_EDITOR="/tmp/aaris-unity-runtime/editors/6000.3.26f1/Editor/Unity"
if ! test -x "$EDITOR" && test -x "$OLD_EDITOR"; then EDITOR="$OLD_EDITOR"; fi
mkdir -p "$RUN"
cd "$PROJECT"
case "$TASK" in
  status)
    echo 'AARIS_CODESPACE_STATUS'
    printf 'commit=%s\n' "$(git rev-parse --short HEAD)"
    printf 'arch=%s\n' "$(uname -m)"
    printf 'cpus=%s\n' "$(nproc)"
    printf 'memory_mb=%s\n' "$(awk '/MemTotal:/ {printf "%.0f", $2/1024}' /proc/meminfo)"
    printf 'workspace_free_kb=%s\n' "$(df -Pk /workspaces | awk 'NR==2{print $4}')"
    printf 'tmp_free_kb=%s\n' "$(df -Pk /tmp | awk 'NR==2{print $4}')"
    if test -x "$EDITOR"; then echo 'editor_installed=yes'; else echo 'editor_installed=no'; fi
    if test -x /workspaces/.aaris-unity-editors/6000.3.26f1/Editor/Unity; then echo 'persistent_editor=yes'; else echo 'persistent_editor=no'; fi
    if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then echo 'editor_running=yes'; else echo 'editor_running=no'; fi
    if DISPLAY=:99 xdpyinfo >/dev/null 2>&1; then echo 'display=ready'; else echo 'display=stopped'; fi
    if head -c 100 Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity 2>/dev/null | grep -q 'git-lfs.github.com/spec'; then
      echo 'scene=lfs_pointer'
    else echo 'scene=hydrated_or_missing'; fi
    ;;
  changes)
    # Read-only filenames; never expose diff contents or files outside normal project paths.
    python3 - <<'PY'
import subprocess
r=subprocess.run(['git','status','--porcelain=v1','--untracked-files=no','-z'],stdout=subprocess.PIPE,check=True)
entries=r.stdout.decode('utf-8','replace').split(chr(0))
files=[]
for entry in entries:
    if len(entry)>=4 and entry[:2].strip():
        path=entry[3:]
        if path and path.startswith(('Assets/','Docs/','Tools/','Packages/','ProjectSettings/','.github/')):
            files.append(path)
raw_identical = 0
raw_different = 0
for path in files:
    try:
        index = subprocess.check_output(['git','ls-files','-s','--',path],text=True)
        expected = index.split(chr(9))[0].split()[1]
        current = subprocess.check_output(['git','hash-object','--no-filters','--',path],text=True).strip()
        if current == expected:
            raw_identical += 1
        else:
            raw_different += 1
    except (IndexError, subprocess.CalledProcessError):
        raw_different += 1
print('changed_files_count='+str(len(files)))
print('raw_identical_count='+str(raw_identical))
print('raw_different_count='+str(raw_different))
for path in sorted(files)[:70]:
    if all(c.isalnum() or c in ' /._-()' for c in path):
        print('change='+path)
PY
    ;;
  sync)
    # Never discard unsaved work. The legacy repo contains exactly 11 checked-in
    # full blobs mistakenly matched by a later git-lfs clean filter. Allow these
    # only after proving raw byte-for-byte equality with the current Git index.
    test "$(git branch --show-current)" = main || { echo 'SYNC_REQUIRES_MAIN_BRANCH'; exit 8; }
    python3 - <<'PY'
import subprocess,sys
allowed={
'Assets/AarisWorld/Props/ClimbableTower/Geometry.asset',
'Assets/AarisWorld/Props/ClimbableTower/Geometry_LOD1.asset',
'Assets/AarisWorld/Props/ClimbableTower/Geometry_LOD2.asset',
'Assets/AarisWorld/Props/RockCover/Geometry.asset',
'Assets/AarisWorld/Props/RockCover/Geometry_LOD1.asset',
'Assets/AarisWorld/Props/RockCover/Geometry_LOD2.asset',
'Assets/AarisWorld/Props/Shared/rock_09_ARM.png',
'Assets/AarisWorld/Props/Shared/rusty_metal_02_ARM.png',
'Assets/AarisWorld/Props/StaticWreck/Geometry.asset',
'Assets/AarisWorld/Props/StaticWreck/Geometry_LOD1.asset',
'Assets/AarisWorld/Props/StaticWreck/Geometry_LOD2.asset'}
data=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=no','-z'])
entries=[e for e in data.split(b'\0') if e]
for e in entries:
    status=e[:2].decode('ascii','replace')
    path=e[3:].decode('utf-8','replace')
    if status not in {' M','M '} or path not in allowed:
        print('SYNC_BLOCKED_REAL_OR_UNEXPECTED_CHANGE')
        sys.exit(8)
    index=subprocess.check_output(['git','ls-files','-s','--',path],text=True).split('\t')[0].split()[1]
    raw=subprocess.check_output(['git','hash-object','--no-filters','--',path],text=True).strip()
    if raw!=index:
        print('SYNC_BLOCKED_CHANGED_BYTES')
        sys.exit(8)
print('SYNC_WORKTREE_VERIFIED_RAW_IDENTICAL='+str(len(entries)))
PY
    git fetch --quiet origin main
    # Suppress only the already-proven LFS clean-filter false positives.
    git -c filter.lfs.process= -c filter.lfs.clean=cat \
        -c filter.lfs.required=false merge --ff-only --quiet origin/main || {
      echo 'SYNC_NON_FAST_FORWARD_OR_FILTER_CONFLICT'; exit 9;
    }
    git lfs pull >/dev/null 2>&1 || { echo 'SYNC_LFS_FAILED'; exit 10; }
    echo 'SYNC_LFS_READY'
    ;;
  lfs_report)
    # Report pointer hydration and diagnostics without printing any raw network logs.
    python3 - <<'PY'
import pathlib,subprocess,re
root=pathlib.Path('.')
res=subprocess.run(['git','lfs','ls-files','--name-only'],capture_output=True,text=True,timeout=25)
if res.returncode:
    print('LFS_ENUMERATION_FAILED')
    raise SystemExit(2)
files=[x for x in res.stdout.splitlines() if x]
pointers=[]
for item in files:
    p=root/item
    if p.is_file():
        try:
            if p.open('rb').read(110).startswith(b'version https://git-lfs.github.com/spec/v1'):
                pointers.append(item)
        except OSError:
            pass
log=pathlib.Path('/tmp/aaris-codespaces/lfs-pull.log')
s=log.read_text(errors='replace')[-300000:] if log.is_file() else ''
def kind(s):
    if re.search(r'\[404\]|Object does not exist on the server|batch response: Repository or object not found',s,re.I):
        return 'REMOTE_404'
    if re.search(r'\[403\]|not authorized|permission denied|unauthorized',s,re.I):
        return 'REMOTE_403'
    if re.search(r'bandwidth|quota|billing|exceeded',s,re.I):
        return 'QUOTA'
    if re.search(r'no such file or directory|not found',s,re.I):
        return 'LOCAL_PATH_OR_REMOTE_NOT_FOUND'
    if re.search(r'certificate|dns|connection|timeout|TLS',s,re.I):
        return 'NETWORK'
    return 'UNKNOWN'
print('lfs_tracked_count='+str(len(files)))
print('lfs_unhydrated_pointer_count='+str(len(pointers)))
print('lfs_error_kind='+kind(s))
print('lfs_log_recorded='+('yes' if s else 'no'))
critical='Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity'
p=root/critical
if not p.is_file(): scene='missing'
elif critical in pointers: scene='pointer'
else: scene='file_not_pointer'
print('scene='+scene)
# LFS errors may identify object OIDs, which are public content hashes, not credentials.
sha=list(dict.fromkeys(re.findall(r'\b[a-f0-9]{64}\b',s,re.I)))
print('lfs_error_hash_count='+str(len(sha)))
for i,oid in enumerate(sha[:3],1):
    print('lfs_object_hash_'+str(i)+'='+oid.lower())
PY
    ;;
  lfs)
    mkdir -p /tmp/aaris-unity-runtime/lfs
    if ! git lfs version >/dev/null 2>&1; then
      echo 'GIT_LFS_CLI_MISSING'
      exit 19
    fi
    echo 'GIT_LFS_CLI_PRESENT'
    git config --local lfs.storage /tmp/aaris-unity-runtime/lfs
    if git lfs pull > "$RUN/lfs-pull.log" 2>&1; then
      echo 'LFS_DOWNLOAD_OK'
    else
      python3 - "$RUN/lfs-pull.log" <<'PY'
import sys,re,pathlib
s=pathlib.Path(sys.argv[1]).read_text(errors='replace')[-20000:]
if re.search(r'quota|bandwidth|data transfer limit|billing|over its data',s,re.I):
    reason='quota_or_bandwidth'
elif re.search(r'403|permission denied|not authorized|authentication|unauthorized',s,re.I):
    reason='authorization'
elif re.search(r'404|not found|does not exist',s,re.I):
    reason='missing_lfs_object'
elif re.search(r'no space left|insufficient space',s,re.I):
    reason='disk_full'
elif re.search(r'network|connection|timeout|TLS|certificate',s,re.I):
    reason='network'
elif re.search(r'not a git command|git-lfs is not installed',s,re.I):
    reason='lfs_cli_missing'
else:
    reason='unclassified'
print('LFS_FAIL_CATEGORY_'+reason.upper())
PY
      exit 20
    fi
    ;;
  install)
    bash "$PROJECT/Tools/Codespaces/install_unity.sh"
    ;;
  editor)
    if ! test -x "$EDITOR"; then
      echo 'EDITOR_ABSENT_INSTALLING_ON_TMP_DISK'
      echo 'EDITOR_NOT_INSTALLED_USE_CS_INSTALL_FIRST'
      exit 11
    fi
    # Put Unity's large import cache on /tmp and preserve checked-in source files.
    mkdir -p /tmp/aaris-unity-runtime/project-cache
    for name in Library Temp Logs obj; do
      target="$PROJECT/$name"
      if test -L "$target"; then continue; fi
      if test -d "$target"; then
        if test -n "$(ls -A "$target" 2>/dev/null)"; then
          echo "CACHE_DIRECTORY_NONEMPTY_$name"
          continue
        fi
        rmdir "$target"
      fi
      if ! test -e "$target"; then
        mkdir -p "/tmp/aaris-unity-runtime/project-cache/$name"
        ln -s "/tmp/aaris-unity-runtime/project-cache/$name" "$target"
      fi
    done
    bash "$PROJECT/.devcontainer/start_screen.sh" >/dev/null
    if ! pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
      mkdir -p "$RUN/UnityTemp"
      nohup setsid env DISPLAY=:99 TMPDIR="$RUN/UnityTemp" LIBGL_ALWAYS_SOFTWARE=1 "$EDITOR" -projectPath "$PROJECT" -logFile "$RUN/Editor.log" </dev/null >/dev/null 2>&1 &
      sleep 8
    fi
    if pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null 2>&1; then
      echo 'EDITOR_PROCESS_STARTED_LICENSE_NOT_VERIFIED'
    else echo 'EDITOR_LAUNCH_FAILED'; exit 12; fi
    ;;
  license)
    if test -x "$EDITOR"; then
      echo 'UNITY_EDITOR_BINARY_PRESENT_CHECK_HUB_LICENSE_MANUALLY'
    else echo 'UNITY_EDITOR_NOT_INSTALLED'; fi
    ;;
  shot)
    pgrep -f '[E]ditor/Unity.*-projectPath' >/dev/null || { echo 'SHOT_BLOCKED_EDITOR_NOT_RUNNING'; exit 14; }
    DISPLAY=:99 xdpyinfo >/dev/null 2>&1 || { echo 'SHOT_BLOCKED_NO_DISPLAY'; exit 15; }
    scrot -o "$RUN/screen.png" || { echo 'SHOT_FAILED'; exit 16; }
    test -s "$RUN/screen.png" || exit 16
    VARIANCE="$(convert "$RUN/screen.png" -colorspace Gray -format '%[fx:standard_deviation]' info: 2>/dev/null || echo 0)"
    python3 - "$VARIANCE" <<'PY'
import sys
try: ok=float(sys.argv[1])>=0.015
except ValueError: ok=False
if not ok: raise SystemExit("SHOT_BLANK_REJECTED")
PY
    echo 'SHOT_CREATED_NEEDS_VISUAL_REVIEW'
    ;;
  test)
    python3 Tools/CI/ai_world_commands.py
    python3 Tools/CI/session_store.py selftest
    echo 'SELFTEST_OK'
    ;;
  *)
    echo 'INVALID_TASK'; exit 2 ;;
esac
