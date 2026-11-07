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
remote=(r/'Tools/Codespaces/remote.sh').read_text()
assert 'eval ' not in remote
assert 'git merge --ff-only' in remote
assert 'scrot -o' in remote
assert 'machine-id' not in remote
assert 'Unity_auth_vault' not in remote
controller=(r/'Tools/Codespaces/controller.sh').read_text()
assert "'CS MACHINES')" in controller
assert 'REMOTE_CMD=' in controller
termux=(r/'Tools/Codespaces/termux_switch.sh').read_text()
assert 'gh secret set CODESPACE_PAT' in termux
assert 'printf ' in termux and '"$CS_TOKEN"' in termux
print('CODESPACE_PROTOCOL_SELFTEST_PASS')
