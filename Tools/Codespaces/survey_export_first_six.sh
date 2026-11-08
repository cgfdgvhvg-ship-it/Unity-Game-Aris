#!/usr/bin/env bash
# Transmit one six-frame contact sheet of actual native Unity PNG pixels.
# Fixed file list; never executes untrusted paths or edits Unity source.
set -euo pipefail
python3 - <<'PY'
import base64,pathlib,shutil,subprocess,sys
root=pathlib.Path('/tmp/aaris-codespaces/scene-probe')
files=[root/f'survey-{i:02}-{kind}.png' for i in range(1,4) for kind in ('detail','context')]
for path in files:
    if not path.is_file() or not 8192<path.stat().st_size<8*1024*1024:
        raise SystemExit(31)
    with path.open('rb') as f:
        if f.read(8)!=b'\x89PNG\r\n\x1a\n':raise SystemExit(32)
exe=shutil.which('ffmpeg')
if not exe:raise SystemExit(33)
out=root/'survey-first-six-preview.png'
filter_parts=[f'[{n}:v]scale=640:360:flags=lanczos[v{n}]' for n in range(6)]
filter_parts.append(''.join(f'[v{n}]' for n in range(6))+
    'xstack=inputs=6:layout=0_0|640_0|1280_0|0_360|640_360|1280_360[v]')
cmd=[exe,'-nostdin','-hide_banner','-loglevel','error','-y']
for path in files:cmd+=['-i',str(path)]
cmd+=['-filter_complex',';'.join(filter_parts),'-map','[v]','-frames:v','1','-update','1',str(out)]
try:
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)
except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError):
    raise SystemExit(34)
if not out.is_file() or out.stat().st_size<8192 or out.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':
    raise SystemExit(35)
print(base64.b64encode(out.read_bytes()).decode('ascii'))
PY
