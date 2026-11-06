#!/usr/bin/env python3
"""Image diagnostics: do not report a blank frame as a successful map render."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageStat

def audit(folder):
    images = sorted(folder.glob("*.png"))
    if not images:
        raise RuntimeError("No PNG photographs: render NOT verified")
    frames, suspicious = [], []
    for path in images:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.size != (1920,1080):
                raise RuntimeError(f"{path.name}: expected HD 1920x1080; got {image.size}")
            thumb = image.convert("RGB").resize((160,90))
            pixels = list(thumb.getdata())
            black = sum(max(p)<18 for p in pixels)/len(pixels)
            white = sum(min(p)>242 for p in pixels)/len(pixels)
            stddev = ImageStat.Stat(thumb).stddev
            frame = {"name":path.name,"bytes":path.stat().st_size,
                     "black_fraction":round(black,4),"white_fraction":round(white,4),
                     "rgb_stddev":[round(x,2) for x in stddev]}
            if black>.93 or white>.93 or max(stddev)<3:
                suspicious.append(path.name)
            frames.append(frame)
    report={"count":len(frames),"frames":frames,"suspected_blank":suspicious,
            "result":"suspect" if suspicious else "passed"}
    (folder/"photo-audit.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    if suspicious:
        raise RuntimeError("Potential black/white/flat frame: "+", ".join(suspicious))

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",default="ci-photos")
    args=parser.parse_args()
    audit(Path(args.directory))
