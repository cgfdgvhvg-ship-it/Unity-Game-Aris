#!/usr/bin/env bash
# Read only private native Unity Play probe diagnostics; print fixed safe categories.
set -euo pipefail
ROOT=/tmp/aaris-codespaces/scene-probe
test -d "$ROOT" || { echo AARIS_PLAY_DIAG_FOLDER_MISSING; exit 0; }
python3 - "$ROOT" <<'PY'
import json,re,sys
from pathlib import Path
folder=Path(sys.argv[1])
report=folder/"play-report.json"
log=folder/"unity-probe-editor.log"
allowed_reasons={
"PLAY_PREFLIGHT_FAILED","EDITOR_ALREADY_PLAYING","PLAY_MODE_TIMED_OUT",
"PLAY_RUNTIME_ASSERTIONS_FAILED","PLAY_MODE_SCENE_AND_CAMERA_VERIFIED",
"FRAME_NEARLY_UNIFORM","FRAME_MAGENTA_SHADER_FAILURE",
"SCENE_FILE_MISSING","SCENE_IS_LFS_POINTER","NATIVE_SCENE_NOT_LOADED",
"FOUR_NATIVE_TERRAINS_REQUIRED","NO_GRAPHICS_DEVICE",
}
if report.is_file():
    try:
        d=json.loads(report.read_text(errors="replace"))
        if d.get("mode")!="play":raise ValueError()
        print("AARIS_PLAY_DIAG_REPORT_FOUND")
        print("play_status="+("passed" if d.get("status")=="passed" else "failed"))
        reason=str(d.get("reason",""))
        print("play_reason="+(reason if reason in allowed_reasons else "OTHER"))
        for key in ("frames","terrainTiles","runtimeErrors"):
            val=d.get(key)
            if type(val)==int and 0<=val<=200000:
                print(key+"="+str(val))
        for key in ("playerPresent","cameraPresent","vehicleManagerPresent"):
            if type(d.get(key))==bool:
                print(key+"="+("yes" if d[key] else "no"))
    except (OSError,ValueError,TypeError):
        print("AARIS_PLAY_DIAG_REPORT_INVALID")
else:
    print("AARIS_PLAY_DIAG_REPORT_MISSING")
if log.is_file():
    text=log.read_text(errors="replace")[-300000:]
    print("AARIS_PLAY_DIAG_UNITY_LOG_FOUND")
    signatures={
        "LICENSE":r"no valid.{0,24}licen[sc]e|licen[sc]e.{0,45}(invalid|failed|expired)",
        "COMPILE":r"(error CS\d{4}|Compilation failed|Script Compilation Error)",
        "PLAY_REQUESTED":r"AARIS_NATIVE_PLAY_REQUESTED",
        "PLAY_TIMED_OUT":r"PLAY_MODE_TIMED_OUT",
        "PROBE_ERROR":r"AARIS_NATIVE_SCENE_CAPTURE_FAILED|AARIS_NATIVE_PLAY.*FAILED",
        "PLAYER_MISSING":r"PLAY_PREFLIGHT_FAILED",
        "GRAPHICS":r"GfxDevice.*fail|Failed to create GL|framebuffer incomplete",
        "OOM":r"out of memory|failed to allocate",
        "CRASH":r"segmentation fault|SIGSEGV|crash handler",
        "EDITOR_EXIT":r"Exiting batchmode|EditorApplication.Exit",
    }
    for k,pattern in signatures.items():
        if re.search(pattern,text,re.I):print("AARIS_PLAY_LOG_"+k)

    # Only classify exception types and public, known game-script names. Never
    # print the underlying error line, stack trace, paths or user data.
    error_types={
        "NullReferenceException":"NULL_REFERENCE",
        "MissingReferenceException":"MISSING_REFERENCE",
        "ArgumentException":"INVALID_ARGUMENT",
        "InvalidOperationException":"INVALID_OPERATION",
        "IndexOutOfRangeException":"ARRAY_INDEX",
        "ArgumentOutOfRangeException":"ARRAY_INDEX",
        "UnassignedReferenceException":"UNASSIGNED_REFERENCE",
        "MissingComponentException":"MISSING_COMPONENT",
        "UnityException":"UNITY_EXCEPTION",
        "NotSupportedException":"UNSUPPORTED_OPERATION",
        "TypeLoadException":"TYPE_LOAD",
        "FileNotFoundException":"FILE_NOT_FOUND",
    }
    known_scripts={
        "AarisVehicleWorld","AarisVehicleMotor","AarisVehicleSession",
        "AarisThirdPersonPlayer","AarisNearbyColliders","AarisBattleActions",
        "AarisMobileRuntime","AarisVehicleHUD","AarisExplorerBuild",
        "AarisCodespaceSceneProbe","AarisCICapture","AarisTreeColliderManager",
    }
    lines=text.splitlines()
    matching=[]
    for i,line in enumerate(lines):
        exception=next((label for name,label in error_types.items()
                        if re.search(r"\b"+name+r"\b",line)),None)
        source=None
        if exception:
            matching.append((i,exception))
        elif re.search(r"^\s*(?:Aaris (?:vehicles|world|map|player|terrain)|ERROR:|Error:)",line,re.I):
            matching.append((i,"REPORTED_GAME_ERROR"))
    if matching:
        print("AARIS_PLAY_LOG_ERROR_CANDIDATES")
        for index,kind in matching[-4:]:
            print("AARIS_PLAY_ERROR_KIND_"+kind)
            context="\n".join(lines[index:index+16])
            scripts=sorted(x for x in known_scripts if re.search(r"\b"+x+r"\b",context))
            for script in scripts[:4]:
                print("AARIS_PLAY_ERROR_SOURCE_"+script.upper())
    elif re.search(r"\b(?:LogType\.Error|Exception)\b",text):
        print("AARIS_PLAY_LOG_ERROR_UNCLASSIFIED")
else:
    print("AARIS_PLAY_DIAG_UNITY_LOG_MISSING")
PY
