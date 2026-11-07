#!/usr/bin/env python3
"""Bounded, owner-only issue reply. Never publish arbitrary stdout, logs or secrets."""
import json
from pathlib import Path
import re
import sys
folder = Path(sys.argv[1])
try:
    data = json.loads((folder / 'result.json').read_text())
except (OSError, ValueError):
    data = {}
operations = set('machines info start status sync changes install editor license shot test stop'.split())
statuses = {'SUCCESS', 'FAILED', 'NO_CODESPACE', 'UNKNOWN'}
op = data.get('operation', 'unknown')
state = data.get('status', 'FAILED')
if op not in operations:
    op = 'unknown'
if state not in statuses:
    state = 'FAILED'
detail = data.get('detail', 'unavailable')
if not re.fullmatch(r'[a-zA-Z0-9_]{1,80}', detail):
    detail = 'unavailable'
print('**AARIS CODESPACE CONTROL**')
print('Operation: `%s` | Status: `%s` | Detail: `%s`' % (op, state, detail))
try:
    lines = (folder / 'terminal.txt').read_text().splitlines()
except OSError:
    lines = []
safe = []
for line in lines:
    if re.fullmatch(r'[A-Z][A-Z0-9_]{2,90}', line):
        safe.append(line)
    elif re.fullmatch(r'(commit|arch|cpus|memory_mb|workspace_free_kb|tmp_free_kb|changed_files_count|raw_identical_count|raw_different_count|state|idle_minutes|devcontainer|editor_installed|editor_running|display|scene|machine|codespace)=[A-Za-z0-9_.-]{1,80}', line):
        safe.append(line)
    elif op == 'machines' and re.fullmatch(r'[A-Za-z0-9-]{3,55}\t\d{1,2}\t\d{1,3}', line):
        safe.append(line)
    if len(safe) >= 22:
        break
if safe:
    print()
    print('```text')
    print(*safe, sep=chr(10))
    print('```')
print('Editor process and a nonblank image do not prove Unity Personal activation or valid scene rendering.')
