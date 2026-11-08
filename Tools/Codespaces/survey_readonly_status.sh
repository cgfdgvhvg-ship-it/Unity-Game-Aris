#!/usr/bin/env bash
# Owner-authorized read-only survey progress, no license/raw logs/secrets.
set -euo pipefail
python3 - <<'PY'
import json,re
from pathlib import Path
r=Path('/tmp/aaris-codespaces/scene-probe')
def ispng(p):
    try:
        with p.open('rb') as f:
            return p.stat().st_size>8192 and f.read(8)==b'\x89PNG\r\n\x1a\n'
    except OSError:return False
frames=[f'survey-{i:02}-{k}.png' for i in range(1,13) for k in ('detail','context')]
sheets=[f'survey-sheet-{i}.png' for i in range(1,5)]
ready=[f for f in frames if ispng(r/f)]
made=[f for f in sheets if ispng(r/f)]
report=r/'survey-report.json'
status='not_created';count=0;reason='NOT_REPORTED'
if report.is_file():
    try:
        d=json.loads(report.read_text())
        status=d.get('status','unknown') if d.get('mode')=='survey' else 'unexpected_mode'
        count=d.get('frameCount',0)
        reason=d.get('reason','NOT_REPORTED')
        if not isinstance(count,int) or count<0 or count>24:count=0
        if not isinstance(reason,str) or not re.fullmatch('[A-Z0-9_]{1,100}',reason):reason='REDACTED'
        if status not in ('passed','failed'):status='unexpected_state'
    except (OSError,ValueError,TypeError):status='unreadable'
log=r/'unity-probe-editor.log'
kind='LOG_NOT_FOUND';bytes_count=0
if log.is_file():
    try:
        bytes_count=log.stat().st_size
        with log.open('rb') as f:
            f.seek(max(0,bytes_count-75000))
            s=f.read().decode('utf-8','replace')
        if re.search(r'error CS[0-9]{4}',s):kind='CSHARP_COMPILE_ERROR'
        elif re.search(r'licen[sc]e.{0,80}(missing|invalid|expired|failed)',s,re.I):kind='LICENSE_ERROR'
        elif 'AARIS_NATIVE_SURVEY_PASSED' in s:kind='SURVEY_METHOD_PASSED'
        elif 'AARIS_NATIVE_SURVEY_FAILED' in s:kind='SURVEY_METHOD_FAILED'
        elif 'Refresh completed' in s:kind='ASSET_IMPORT_SEEN'
        else:kind='LOG_PRESENT_UNCLASSIFIED'
    except OSError:kind='LOG_UNREADABLE'
print('AARIS_SURVEY_READ_ONLY_DIAG')
print('report_status='+status)
print('report_reason='+reason)
print('report_frames='+str(count))
print('verified_raw_frames='+str(len(ready)))
print('verified_sheets='+str(len(made)))
print('editor_log_bytes='+str(bytes_count))
print('editor_log_category='+kind)
print('first_six_ready='+('yes' if all(x in ready for x in frames[:6]) else 'no'))
print('all_24_ready='+('yes' if len(ready)==24 else 'no'))
print('all_four_sheets_ready='+('yes' if len(made)==4 else 'no'))
PY
