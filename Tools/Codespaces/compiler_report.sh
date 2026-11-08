#!/usr/bin/env bash
# Read-only bounded report: never publish raw Unity Editor.log, OAuth URLs, or tokens.
set -Eeuo pipefail
python3 - <<'PY'
from pathlib import Path
import re
paths=[
    Path('/tmp/aaris-codespaces/Editor.log'),
    Path.home()/'.config/unity3d/Editor.log',
]
logs=[p for p in paths if p.is_file()]
if not logs:
    print('UNITY_COMPILER_LOG_NOT_FOUND')
    raise SystemExit(0)
print('UNITY_COMPILER_LOG_FOUND')
seen=set()
matches=[]
pattern=re.compile(r'(?P<file>(?:Assets|Packages|Library/PackageCache)/[A-Za-z0-9_./+\-]+\.cs)\((?P<line>\d+),(?P<col>\d+)\):\s*error\s+(?P<code>CS\d{4}):\s*(?P<msg>[^\r\n]*)')
generic=re.compile(r'\berror\s+(CS\d{4})\s*:')
for p in logs:
    s=p.read_bytes()[-6000000:].decode('utf-8','replace')
    for m in pattern.finditer(s):
        key=(m.group('file'),m.group('line'),m.group('col'),m.group('code'))
        if key in seen: continue
        seen.add(key)
        matches.append((key,m.group('msg')))
    if not matches:
        for code in generic.findall(s):
            key=('unknown','0','0',code)
            if key not in seen:
                seen.add(key)
                matches.append((key,''))
print('UNITY_COMPILER_ERROR_COUNT_'+str(len(matches)))
for (file,line,col,code),msg in matches[:24]:
    if not re.fullmatch(r'(Assets|Packages|Library/PackageCache)/[A-Za-z0-9_./+\-]+\.cs|unknown',file):
        continue
    print('compiler_error='+file+':'+line+':'+col+':'+code)
    # Detailed text is intentionally not sent to the public GitHub issue.
    # The following descriptor stays in this Actions artifact for short retention.
    msg=re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+|[A-Za-z0-9+/]{44,}={0,2}','[redacted]',msg)
    msg=re.sub(r'[^a-zA-Z0-9 .,;:_\-+()\'\[\]<>?=!/]', '?',msg)[:170]
    if msg:
        print('compiler_detail='+msg)
if not matches:
    print('UNITY_COMPILER_ERRORS_NOT_IN_AVAILABLE_LOGS')
PY
