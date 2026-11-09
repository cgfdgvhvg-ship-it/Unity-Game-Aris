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
# Prefer the SIX-FRAME contact sheet that Unity itself already assembled.
# A completed survey has verified all 24 source frames and 4 native sheets:
# no ffmpeg, ImageMagick or Pillow is needed in the lightweight Codespace.
import json,struct
native=root/'survey-sheet-1.png'
report=root/'survey-report.json'
if native.is_file() and report.is_file():
    try:
        d=json.loads(report.read_text())
        raw=native.read_bytes()
        correct=(d.get('status')=='passed' and d.get('frameCount')==24
                 and d.get('terrainTiles')==4 and d.get('locationCount')==12
                 and 8192<len(raw)<8*1024*1024
                 and raw[:8]==bytes([137,80,78,71,13,10,26,10])
                 and raw[12:16]==b'IHDR'
                 and struct.unpack('>II',raw[16:24])==(1920,720))
        if correct:
            print(base64.b64encode(raw).decode('ascii'))
            raise SystemExit(0)
    except (OSError,ValueError,TypeError,struct.error):
        pass
# Early partial surveys can still use ffmpeg when present.
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
