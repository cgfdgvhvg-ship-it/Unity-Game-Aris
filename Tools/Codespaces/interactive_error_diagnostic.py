#!/usr/bin/env python3
"""Bounded taxonomy of existing private native Unity test log.
Runs on OLD Codespace, reads only /tmp log, never exports lines or secrets.
"""
from collections import Counter
from pathlib import Path
import hashlib
import re

p=Path("/tmp/aaris-codespaces/interactive-house-probe/private-editor.log")
if not p.is_file():
    print("AARIS_NATIVE_PRIVATE_LOG_MISSING")
    raise SystemExit(0)
lines=p.read_text(encoding="utf-8",errors="replace").splitlines()
# This is the existing test's editor log, not an arbitrary user path.
anchors=[i for i,line in enumerate(lines) if "AARIS_EXPANSION_RESULT" in line]
start=anchors[-1] if anchors else max(0,len(lines)-400)
sample=lines[start:]
families=Counter()
sources=Counter()
types=("NullReferenceException","MissingReferenceException","ArgumentException",
    "InvalidOperationException","IndexOutOfRangeException","UnityException",
    "AssertionException","Shader error","FMOD","Audio","Display","GL_INVALID",
    "AARIS_EXPANSION_","Aaris","RenderTexture","PlayerLoop","Destroying assets",
    "The referenced script","ScriptableObject","Unable to","Error:")
for i,line in enumerate(sample):
    is_problem=(bool(re.search(r"\b(?:Exception|Error:|ERROR|Shader error)\b",line))
                or line.startswith("error CS") or line.startswith("AARIS_EXPANSION_"))
    if not is_problem:continue
    family=next((s for s in types if s.lower() in line.lower()),"OTHER_ERROR")
    families[family]+=1
    span="\n".join(sample[i:i+7])
    # Allowlisted source classes only. Never expose messages, full paths, hostnames,
    # paths of other user files or private Unity license information.
    for name in ("AarisBreakablePanel","AarisModularHouse",
        "AarisSettlementExpansion","AarisVehicleWorld",
        "AarisThirdPersonPlayer","AarisOfflineFragGrenade",
        "AarisInteractiveHouseProbe","UnityEngine","UnityEditor"):
        if name in span:
            sources[name]+=1
for key,count in families.most_common(6):
    name=re.sub("[^A-Z0-9_]","_",key.upper())[:50]
    print("AARIS_NATIVE_ERROR_FAMILY_"+name+"="+str(min(count,999)))
for key,count in sources.most_common(6):
    print("AARIS_NATIVE_ERROR_SOURCE_"+key.upper()+"="+str(min(count,999)))
print("AARIS_NATIVE_EDITOR_LINES_SAMPLED="+str(min(len(sample),999999)))
print("AARIS_NATIVE_LOG_ANCHOR="+("EXPANSION_RESULT" if anchors else "TAIL_FALLBACK"))
