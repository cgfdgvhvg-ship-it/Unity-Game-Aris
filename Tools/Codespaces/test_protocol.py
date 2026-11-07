#!/usr/bin/env python3
"""Public CI tests; no live token, Unity seat or Codespace quota required."""
import json
from pathlib import Path
r=Path(__file__).resolve().parents[2]
d=json.loads((r/'.devcontainer/devcontainer.json').read_text())
assert d['postCreateCommand']=='bash .devcontainer/bootstrap.sh'
assert d['postStartCommand']=='bash .devcontainer/start_screen.sh'
wf=(r/'.github/workflows/aaris-codespaces-control.yml').read_text()
assert "github.event.comment.user.login == 'sundamunda289-art'" in wf
assert "github.event.issue.number == 77" in wf
assert 'secrets.CODESPACE_PAT' in wf
assert 'actions/upload-artifact@v4' in wf
assert 'id-token: write' in wf
assert "'CS PROBE')" in (r/'Tools/Codespaces/controller.sh').read_text()
assert 'RELAY_PROBE_HTTP_' in (r/'Tools/Codespaces/relay_probe.py').read_text()
assert 'CS AUTH' in (r/'Tools/Codespaces/controller.sh').read_text()
assert 'UNITY_PRIVATE_APPROVAL_LINK_READY' in (r/'Tools/Codespaces/auth_bridge.py').read_text()
remote=(r/'Tools/Codespaces/remote.sh').read_text()
assert 'eval ' not in remote
assert 'merge --ff-only' in remote
assert 'SYNC_WORKTREE_VERIFIED_RAW_IDENTICAL' in remote
assert 'scrot -o' in remote
assert 'changed_files_count=' in remote
assert 'LFS_FAIL_CATEGORY_' in remote
assert 'lfs_unhydrated_pointer_count=' in remote
assert 'lfs_error_kind=' in remote
assert 'UNITY_CLI_HOME' in (r/'Tools/Codespaces/install_unity.sh').read_text()
assert 'unityhub --headless' not in (r/'Tools/Codespaces/install_unity.sh').read_text()
assert 'lfs.storage' in remote
assert '/workspaces/.aaris-unity-editors' in remote
assert 'project-cache' in remote
assert 'EDITOR_ROOT="/workspaces/.aaris-unity-editors"' in (r/'Tools/Codespaces/install_unity.sh').read_text()
assert '--download-directory "$EDITOR_ROOT"' in (r/'Tools/Codespaces/install_unity.sh').read_text()
assert '--resume' in (r/'Tools/Codespaces/install_unity.sh').read_text()
assert 'machine-id' not in remote
assert 'Unity_auth_vault' not in remote
controller=(r/'Tools/Codespaces/controller.sh').read_text()
assert "'CS MACHINES')" in controller
assert 'bash -s -- $OP' in controller
assert "'CS INFO')" in controller
assert 'gh codespace view -c' in controller
assert 'safe_error_summary' in controller
assert 'trap \'finish; rm -f' in controller
termux=(r/'Tools/Codespaces/termux_switch.sh').read_text()
assert 'gh secret set CODESPACE_PAT' in termux
assert 'printf ' in termux and '"$CS_TOKEN"' in termux
print('CODESPACE_PROTOCOL_SELFTEST_PASS')


# Smoke-test the real controller with a mocked GitHub CLI; no external token or paid VM.
import os
import subprocess
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    working=Path(tmp)
    bindir=working/'bin'
    bindir.mkdir()
    mock=bindir/'gh'
    mock.write_text("""#!/usr/bin/env bash
set -e
case "$1" in
  api)
    if [[ "$2" == */machines ]]; then
      if [[ "$3" == "--jq" ]]; then printf 'standardLinux32gb\\t4\\t16\\n'; else
        printf '{"machines":[{"name":"standardLinux32gb","cpus":4,"memory_in_bytes":17179869184}]}\\n'; fi
    else exit 9; fi ;;
  codespace)
    case "$2" in
      list) echo '[]' ;;
      create) echo 'mock-codespace' ;;
      *) exit 9 ;;
    esac ;;
  *) exit 9 ;;
esac
""")
    mock.chmod(0o700)
    env={**os.environ,
         'PATH':str(bindir)+os.pathsep+os.environ['PATH'],
         'GITHUB_WORKSPACE':str(working),
         'GITHUB_REPOSITORY':'sundamunda289-art/Unity-Game-Aris',
         'GH_TOKEN':'mock-not-real',
         'ISSUE_COMMAND':'',
         'REQUEST_MACHINE':'',
         'REQUEST_OPERATION':'machines'}
    controller=str(r/'Tools/Codespaces/controller.sh')
    run=subprocess.run(['bash',controller],env=env,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    result=json.loads((working/'codespace-results/result.json').read_text())
    assert result['status']=='SUCCESS' and result['operation']=='machines'
    text=(working/'codespace-results/terminal.txt').read_text()
    assert 'standardLinux32gb' in text
    env['REQUEST_OPERATION']='start'
    run=subprocess.run(['bash',controller],env=env,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    result=json.loads((working/'codespace-results/result.json').read_text())
    assert result['status']=='SUCCESS' and result['codespace']=='mock-codespace'
direct=(r/'Tools/Codespaces/termux_unity_allow.sh').read_text()
assert 'termux-open-url' in direct
assert 'GH_CONFIG_DIR' in direct
assert 'mobile_license.py' in direct
assert 'gh codespace ssh' in direct
assert 'cloudflare' not in direct.lower()
print('CODESPACE_CONTROLLER_MOCK_PASS')
