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

# Every displayed category below is selected from a static reviewed string in
# this project's source. Never reveal raw Unity messages or arbitrary paths.
known={
 "INVALID_CHARACTER_CLIPS":"Aaris: imported animation clips invalid.",
 "OFFLINE_DROP_MOTOR_OR_CAMERA_MISSING":"Aaris offline drop: existing motor, capsule or game camera missing.",
 "INVALID_WEAPON_STATE":"Aaris: invalid weapon state configured.",
 "PLAYER_CAMERA_MISSING":"Saved player camera is missing.",
 "VEHICLE_CATALOG_MISSING":"Aaris vehicles: authored offline candidates/catalog are missing.",
 "VEHICLE_WORLD_MISMATCH":"Aaris vehicles: source data does not match the 2km authored world.",
 "VEHICLE_3D_MODEL_MISSING":"Aaris vehicles: not all required local CC0 3D vehicles imported",
 "VEHICLE_URP_SHADER_MISSING":"Aaris vehicles: verified URP palette/shader missing",
 "WEAPON_CATALOG_MISSING":"Aaris: missing embedded AarisWeapons/weapon_catalog.json.",
 "WEAPON_CATALOG_INVALID":"Aaris: invalid local weapon catalog:",
 "NO_GUN_VISIBLE_MESH":"Aaris: gun has no visible mesh:",
 "LOOT_DATA_MISSING":"Aaris: no embedded offline authored loot locations.",
 "LOOT_JSON_INVALID":"Aaris: invalid loot JSON:",
 "LOOT_WORLD_MISMATCH":"Aaris: loot candidates do not describe the 2km map.",
 "LOCAL_WEAPON_FBX_MISSING":"Missing local weapon FBX:",
 "EXPANSION_CATALOG_MISSING":"AARIS_EXPANSION_LOCAL_CATALOG_MISSING",
 "EXPANSION_JSON_INVALID":"AARIS_EXPANSION_INVALID_PLAN_JSON",
 "EXPANSION_WORLD_MISMATCH":"AARIS_EXPANSION_SCHEMA_OR_WORLD_MISMATCH",
}
for kind,phrase in known.items():
    count=sum(phrase in line for line in sample)
    if count: print("AARIS_NATIVE_KNOWN_ERROR_"+kind+"="+str(min(count,999)))

# Unity exception callbacks sometimes happen BEFORE the last expansion summary.
# Search the entire private log, but export ONLY known bounded classifications.
exception_patterns={
 "NULL_REFERENCE":r"\bNullReferenceException\b",
 "MISSING_REFERENCE":r"\bMissingReferenceException\b",
 "INVALID_OPERATION":r"\bInvalidOperationException\b",
 "ARGUMENT":r"\bArgumentException\b",
 "INDEX_OUT_OF_RANGE":r"\bIndexOutOfRangeException\b",
 "NOT_SUPPORTED":r"\bNotSupportedException\b",
 "TYPE_INITIALIZATION":r"\bTypeInitializationException\b",
 "TARGET_INVOCATION":r"\bTargetInvocationException\b",
 "UNITY":r"\bUnityException\b",
 "UNASSIGNED_REFERENCE":r"\bUnassignedReferenceException\b",
 "FORMAT":r"\bFormatException\b",
 "MISSING_COMPONENT":r"\bMissingComponentException\b",
 "OTHER_GENERIC_EXCEPTION":r"(?<![a-zA-Z])Exception:(?![a-zA-Z])",
}
for category,pattern in exception_patterns.items():
    cnt=sum(bool(re.search(pattern,line)) for line in lines)
    if cnt:
        print("AARIS_NATIVE_GLOBAL_EXCEPTION_"+category+"="+str(min(cnt,999)))
# Whitelist explicit source class tokens to diagnose which subsystem emitted
# an exception. These are literal owned script names, not paths or free text.
classes=(
 "AarisCharacterVisual","AarisOfflineDrop","AarisVehicleWorld",
 "AarisVehicleMotor","AarisWeaponCatalog","AarisWeaponInventory",
 "AarisSettlementExpansion","AarisModularHouse",
 "AarisBreakablePanel","AarisInteractiveHouseProbe",
 "AarisNearbyColliders","AarisBattleActions",
 "AarisEquippedGun","AarisOfflineGlooWall",
)
for category in classes:
    cnt=sum(category in row for row in lines)
    if cnt:
        print("AARIS_NATIVE_GLOBAL_STACK_"+category.upper()+"="+str(min(cnt,999)))
# Some Unity callback errors are not named *Exception in the log.
# Group only reviewed Unity engine phrases; no raw error text.
known_unity={
 "DESTROY_IMMEDIATE_PLAY_MODE":"DestroyImmediate in play mode",
 "UNLOAD_ASSET_IN_USE":"Cannot unload asset",
 "RENDER_TEXTURE_FAILURE":"RenderTexture creation failed",
 "CALLBACK_EXCEPTION":"Exception while",
 "SCENE_CAMERA_MISSING":"No cameras rendering",
 "NATIVE_GRAPHICS_FAILURE":"Graphics device is null",
 "PLAY_MODE_DOMAIN_ERROR":"An error occurred while entering play mode",
 "ASSET_IMPORT_ERROR":"An error occurred during",
 "INVALID_OPERATION_RUNTIME":"operation is not allowed",
 "EDITOR_THREAD_ERROR":"can only be called from the main thread",
}
for name,phrase in known_unity.items():
    num=sum(phrase.lower() in row.lower() for row in lines)
    if num:
        print("AARIS_NATIVE_GLOBAL_ENGINE_"+name+"="+str(min(num,999)))
print("AARIS_NATIVE_GLOBAL_LOG_LINES="+str(min(len(lines),999999)))

# Debugging outside a running Editor: expose fixed vocabulary only for the
# first few non-boilerplate error headings, including those before startup.
words=(
 "unity","editor","runtime","render","rendertexture","graphics","pipeline",
 "game","object","component","script","camera","physics","collider","terrain",
 "animation","animator","avatar","model","texture","material","mesh","shader",
 "prefab","scene","asset","import","load","reload","unload","null","reference",
 "missing","invalid","exception","error","failed","cannot","disabled","unsupported",
 "unassigned","code","compile","assembly","domain","play","mode","startup",
 "warning","abort","destroy","instance","create","memory","stack","overflow",
 "thread","main","access","denied","device","time","timeout","read","write",
 "file","directory","path","permission","transform","renderer","lights",
 "audio","fmod","input","camera","window","door","gui","assert","assertion",
 "logging","internal","system","unknown","unsupported","not","found","is",
 "notallowed","referenceexception","missingreferenceexception",
)
approved=set(words)
heads=[]
for i,line in enumerate(lines):
    if "AARIS_EXPANSION_RESULT" in line or "AARIS_NATIVE_" in line:
        continue
    if re.search(r"(exception|(?:^|\s)error(?::|\s)|fatal|assertion)",line,re.I):
        if len(heads)>=8:break
        if i and "Exception: " in lines[i-1]:continue
        heads.append((i,line))
print("AARIS_NATIVE_DIAGNOSTIC_HEADINGS="+str(len(heads)))
for ordinal,(idx,line) in enumerate(heads):
    tokens=[w.lower() for w in re.findall(r"[A-Za-z]{2,35}",line)]
    allowed=sorted(set(w for w in tokens if w in approved))
    print("AARIS_NATIVE_HEADING_"+str(ordinal)+"_ROW="+str(idx))
    print("AARIS_NATIVE_HEADING_"+str(ordinal)+"_LENGTH="+str(min(len(line),9999)))
    print("AARIS_NATIVE_HEADING_"+str(ordinal)+"_WORDS="+("_".join(allowed[:16]) or "NONE"))
    print("AARIS_NATIVE_HEADING_"+str(ordinal)+"_SHA10="+
          hashlib.sha256(line.encode("utf-8")).hexdigest()[:10])
