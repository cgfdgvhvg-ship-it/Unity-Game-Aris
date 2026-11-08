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
    is_problem=(bool(re.search(r"Exception|Error:|ERROR|Shader error|error CS",line,re.I))
                or ("AARIS_EXPANSION_" in line and "AARIS_EXPANSION_RESULT" not in line))
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

# Identify the single log-error callback via its following safe stack signature.
markers=("UnityEngine.Debug:LogError", "UnityEngine.Debug:LogException",
         "UnityEngine.Debug:LogAssertion", "Debug.LogError", "UnityEngine.Debug.LogError")
hits=[i for i,s in enumerate(sample) if any(t in s for t in markers)]
print("AARIS_NATIVE_LOGERROR_STACK_MARKERS="+str(min(len(hits),999)))
for i in hits[:3]:
    previous="\n".join(sample[max(0,i-4):i])
    whitelist=("AARIS_EXPANSION_LOCAL_CATALOG_MISSING",
      "AARIS_EXPANSION_INVALID_PLAN_JSON","AARIS_EXPANSION_SCHEMA_OR_WORLD_MISMATCH",
      "AARIS_BATTLE", "AARIS_VEHICLE", "AARIS_PLAYER", "AARIS_WORLDBUILD",
      "NullReferenceException","MissingReferenceException","ArgumentException",
      "InvalidOperationException","UnityException","Shader error","FMOD",
      "Audio","Renderer","Material","Collision","Collider","Time","Physics",
      "Invalid","Object","Missing","Failed","Error","Exception")
    family=next((w for w in whitelist if w.lower() in previous.lower()),
                "OTHER_LOGERROR")
    print("AARIS_NATIVE_LOGERROR_PRECEDING_FAMILY="+
          re.sub(r"[^A-Z0-9_]", "_", family.upper()))
    print("AARIS_NATIVE_LOGERROR_MESSAGE_SHA256_10="+
          hashlib.sha256(previous.encode("utf-8")).hexdigest()[:10])
