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
        for key in ("frames","terrainTiles","runtimeErrors","editorLifecycleWarnings"):
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
    # Inspect only the newest Play session, not a previous editor attempt.
    latest_marker=text.rfind("AARIS_NATIVE_PLAY_REQUESTED")
    active=text[latest_marker:] if latest_marker>=0 else text
    lines=active.splitlines()
    matching=[]
    for i,line in enumerate(lines):
        exception=next((label for name,label in error_types.items()
                        if re.search(r"\b"+name+r"\b",line)),None)
        source=None
        if exception:
            matching.append((i,exception))
        elif re.search(r"^\s*(?:Aaris(?:\s+(?:vehicles|world|map|player|terrain))?:|Saved player camera|ERROR:|Error:)",line,re.I):
            matching.append((i,"REPORTED_GAME_ERROR"))
    # Exact known public errors reveal missing authored resources without
    # leaking arbitrary exception text or credentials.
    message_types={
        "LOOT_SOURCE_MISSING":r"Aaris: no embedded offline authored loot locations",
        "LOOT_INVALID_JSON":r"Aaris: invalid loot JSON",
        "LOOT_WRONG_MAP":r"Aaris: loot candidates do not describe the 2km map",
        "VEHICLE_SOURCE_MISSING":r"Aaris vehicles: authored offline candidates/catalog are missing",
        "VEHICLE_INVALID_DATA":r"Aaris vehicles: malformed offline data",
        "VEHICLE_WRONG_MAP":r"Aaris vehicles: source data does not match the 2km authored world",
        "VEHICLE_MODELS_MISSING":r"Aaris vehicles: not all required local CC0",
        "VEHICLE_SHADER_MISSING":r"Aaris vehicles: verified URP palette/shader missing",
        "PLAYER_CAMERA_MISSING":r"Saved player camera is missing",
        "ANIMATION_CLIPS_INVALID":r"Aaris: imported animation clips invalid",
        "WEAPON_STATE_INVALID":r"Aaris: invalid weapon state configured",
    }
    for name,pattern in message_types.items():
        if re.search(pattern,text,re.I):
            print("AARIS_PLAY_MESSAGE_"+name)
    if matching:
        print("AARIS_PLAY_LOG_ERROR_CANDIDATES")
        for index,kind in matching[-4:]:
            print("AARIS_PLAY_ERROR_KIND_"+kind)
            context="\n".join(lines[index:index+16])
            scripts=sorted(x for x in known_scripts if re.search(r"\b"+x+r"\b",context))
            for script in scripts[:4]:
                print("AARIS_PLAY_ERROR_SOURCE_"+script.upper())
        # Inspect the latest exception using ONLY fixed public stack
        # families. Never emit full methods, raw traces, paths or messages.
        exceptions=[i for i,kind in matching if kind!="REPORTED_GAME_ERROR"]
        if exceptions:
            context_lines=lines[exceptions[-1]+1:exceptions[-1]+37]
            stack="\n".join(context_lines)
            frames=[]
            for line in context_lines:
                m=re.match(r"^\s*(?:at\s+)?((?:UnityEditor|UnityEngine|Aaris|System|Unity)\.[A-Za-z_][A-Za-z0-9_.+]+)\s*\(",line)
                if m: frames.append(m.group(1))
            if frames:
                first=frames[0]
                if first.startswith("Aaris."): family="AARIS"
                elif first.startswith("UnityEditor."): family="UNITY_EDITOR"
                elif first.startswith("UnityEngine."): family="UNITY_ENGINE"
                elif first.startswith("System."): family="SYSTEM"
                elif first.startswith("Unity."): family="UNITY_PACKAGE"
                else: family="OTHER"
            else: family="NO_FRAME"
            print("AARIS_PLAY_EXCEPTION_FIRST_FRAME_FAMILY_"+family)
            print("AARIS_PLAY_EXCEPTION_STACK_FRAMES="+str(min(len(frames),36)))
            known_subsystems=(
                ("UnityEditor.UIElements","UI_ELEMENTS"),
                ("UnityEditor.GameView","GAME_VIEW"),
                ("UnityEditor.GUIView","GUI_VIEW"),
                ("UnityEditor.SceneView","SCENE_VIEW"),
                ("UnityEditor.IMGUI","IMGUI"),
                ("UnityEditor.EditorGUI","IMGUI"),
                ("UnityEditor.EditorGUILayout","IMGUI"),
                ("UnityEditor.Terrain","TERRAIN_EDITOR"),
                ("UnityEditor.AssetDatabase","ASSET_DATABASE"),
                ("UnityEditor.PrefabUtility","PREFAB_EDITOR"),
                ("UnityEditor.Animation","ANIMATION_EDITOR"),
                ("UnityEditor.PackageManager","PACKAGE_MANAGER"),
                ("UnityEditor.EditorApplication","EDITOR_LIFECYCLE"),
                ("UnityEditor.PlayMode","PLAY_MODE"),
                ("UnityEditor.Rendering","RENDER_PIPELINE"),
                ("UnityEditor.Shader","SHADER_IMPORT"),
                ("UnityEditor.Serialized","SERIALIZATION"),
                ("UnityEditorInternal.ReorderableList","REORDERABLE_LIST"),
                ("UnityEngine.UIElements","RUNTIME_UI"),
            )
            found=[label for source,label in known_subsystems if source in stack]
            if found:
                for label in dict.fromkeys(found[:3]):
                    print("AARIS_PLAY_EXCEPTION_SUBSYSTEM_"+label)
            elif "UnityEditor." in stack or "UnityEditorInternal." in stack:
                print("AARIS_PLAY_EXCEPTION_SUBSYSTEM_OTHER_UNITY_EDITOR")
            elif any(f.startswith("Aaris.") for f in frames):
                print("AARIS_PLAY_EXCEPTION_SUBSYSTEM_GAME_SCRIPT")
            else:
                print("AARIS_PLAY_EXCEPTION_SUBSYSTEM_UNCLASSIFIED")
    elif re.search(r"\b(?:LogType\.Error|Exception)\b",active):
        print("AARIS_PLAY_LOG_ERROR_UNCLASSIFIED")
else:
    print("AARIS_PLAY_DIAG_UNITY_LOG_MISSING")
PY


# Diagnose the offline aircraft/parachute video probe WITHOUT exposing private
# Unity/SSH logs, credentials or user-editable source content.  It is run inside
# the SAME authorized Codespace as CS DROP VIDEO.
OFFLINE=/tmp/aaris-codespaces/offline-drop-probe
if test -d "$OFFLINE"; then
python3 - "$OFFLINE" <<'PYDROP'
import json,re,sys
from pathlib import Path
folder=Path(sys.argv[1])
report=folder/"report.json"
log=folder/"unity-private.log"
frames=folder/"frames"
shot_dir=folder/"shots"
video=folder/"drop.mp4"
print("AARIS_DROP_DIAG_DIRECTORY_FOUND")
jpg_count=sum(1 for _ in frames.glob("frame_*.jpg")) if frames.is_dir() else 0
print("AARIS_DROP_DIAG_FRAMES_PRESENT" if jpg_count else "AARIS_DROP_DIAG_FRAMES_MISSING")
if video.is_file() and video.stat().st_size>=32768:
    print("AARIS_DROP_DIAG_VIDEO_PRESENT")
else:
    print("AARIS_DROP_DIAG_VIDEO_MISSING")
if report.is_file():
    try:
        d=json.loads(report.read_text(errors="replace"))
        if d.get("mode")=="offline_drop_video":
            print("AARIS_DROP_DIAG_REPORT_FOUND")
            print("play_status="+("passed" if d.get("status")=="passed" else "failed"))
            safe_error=str(d.get("errorCode",""))
            if safe_error in {"NULL_REFERENCE","MISSING_REFERENCE","RUNTIME_EXCEPTION","UNITY_LOG_ERROR","UNASSIGNED_REFERENCE","INVALID_OPERATION"}:
                print("AARIS_DROP_RUNTIME_"+safe_error)
            if isinstance(d.get("frames"),int) and 0<=d["frames"]<=30000:
                print("frames="+str(d["frames"]))
            if isinstance(d.get("errors"),int) and 0<=d["errors"]<=10000:
                print("runtimeErrors="+str(d["errors"]))
            reason=str(d.get("reason",""))
            if re.fullmatch(r"[A-Z0-9_]{2,60}",reason):
                print("play_reason="+reason)
            for prop in ("observedInPlane","observedFreefall","observedOpening",
                         "observedGliding","observedLanded","existingMotorRestored",
                         "canopyActuallyRendered"):
                if isinstance(d.get(prop),bool):
                    print("AARIS_DROP_"+prop.upper()+"_"+("YES" if d[prop] else "NO"))
        else: print("AARIS_DROP_DIAG_REPORT_TYPE_INVALID")
    except (OSError,ValueError,TypeError):
        print("AARIS_DROP_DIAG_REPORT_INVALID")
else: print("AARIS_DROP_DIAG_REPORT_MISSING")
if log.is_file():
    print("AARIS_DROP_DIAG_UNITY_LOG_FOUND")
    size=log.stat().st_size
    # Scan bounded tail only; raw lines are NEVER emitted.
    with log.open("rb") as stream:
        # A Unity 6 reimport can write many megabytes of asset messages AFTER
        # the first gameplay exception. Keep a strictly bounded 32 MiB tail.
        stream.seek(max(0,size-32*1024*1024))
        content=stream.read().decode("utf-8","replace")
    print("AARIS_DROP_LOG_LARGE" if size > 600000 else "AARIS_DROP_LOG_SMALL")
    if "AARIS_OFFLINE_DROP_VIDEO_PLAYMODE_REQUESTED" in content:
        print("AARIS_DROP_PLAY_REQUEST_MARKER_FOUND")
    else:
        print("AARIS_DROP_PLAY_REQUEST_MARKER_NOT_IN_TAIL")
    signatures={
        "UNITY_COMPILE_ERROR":r"error CS\d{4}|Compilation failed|Script Compilation Error",
        "UNITY_BOOT_ERROR":r"Unity Editor.*failed|failed to load native|Editor initialization failed",
        "UNITY_LICENSE_ERROR":r"no valid.{0,24}licen[sc]e|licen[sc]e.{0,45}(invalid|failed|expired)",
        "UNITY_OOM":r"out of memory|failed to allocate|malloc failed|oom killer",
        "UNITY_CRASH":r"segmentation fault|SIGSEGV|signal 11|crash handler",
        "UNITY_PLAY_REQUESTED":r"AARIS_OFFLINE_DROP_VIDEO_PLAYMODE_REQUESTED",
        "UNITY_PROBE_PASSED":r"AARIS_OFFLINE_DROP_VIDEO_PROBE_PASSED",
        "UNITY_PROBE_FAILED":r"AARIS_OFFLINE_DROP_VIDEO_PROBE_FAILED",
        "UNITY_BATCH_EXIT":r"Exiting batchmode|EditorApplication.Exit",
        "UNITY_SCENE_IMPORT":r"Importing.*assets|AssetDatabase.*Refresh",
        "UNITY_PACKAGE_ERROR":r"Package Manager.*error|Resolution failed|error.*PackageCache",
        "UNITY_NULL_REFERENCE":r"NullReferenceException",
        "UNITY_INVALID_OPERATION":r"InvalidOperationException",
        "UNITY_ASSET_IMPORT_ERROR":r"Asset import failed|Import Error",
    }
    for name,pattern in signatures.items():
        if re.search(pattern,content,re.I):print("AARIS_DROP_LOG_"+name)
    codes=sorted(set(re.findall(r"error (CS\d{4})",content,re.I)))
    for code in codes[:8]:
        print("AARIS_DROP_COMPILER_"+code.upper())

    # Emit only whitelisted class identifiers near the first runtime error.
    # Never print raw error messages, Unity private logs, paths or stack content.
    lines=content.splitlines()
    candidates=[]
    whitelist={
       "AarisOfflineDrop":"AERIAL_CONTROLLER",
       "AarisOfflineDropVisuals":"CANOPY_VISUALS",
       "AarisOfflineDropPlayProbe":"DROP_PROBE",
       "AarisOfflineTacticalHUD":"TACTICAL_UI",
       "AarisThirdPersonPlayer":"PLAYER_MOTOR",
       "AarisCharacterVisual":"CHARACTER_VISUALS",
       "AarisBattleActions":"BATTLE_ACTIONS",
       "AarisWeaponLootWorld":"LOOT_SYSTEM",
       "AarisVehicleWorld":"VEHICLE_SYSTEM",
       "AarisWeaponInventory":"WEAPON_INVENTORY",
       "UnityEngine.UI":"UNITY_UI",
       "UnityEngine.EventSystems":"UNITY_EVENTS"
    }
    for i,line in enumerate(lines):
        if re.search(r"Exception(?::|\b)|\berror CS\d{4}|Aaris.*ERROR|Aaris.*FAILED",line,re.I):
            candidates.append(i)
    if candidates:
        i=candidates[-1]
        stack_context="\n".join(lines[i:min(len(lines),i+23)])
        for name,label in whitelist.items():
            if re.search(r"\b"+re.escape(name)+r"\b",stack_context):
                print("AARIS_DROP_ERROR_SOURCE_"+label)
    # Analyze the FIRST gameplay error in a bounded window after the explicit
    # Play Mode start marker. The last "probe failed" message is a consequence,
    # not necessarily the root cause. Do not output any raw line or stack text.
    # Exact command logs can include both a Unity CLI banner and the gameplay
    # marker; the LAST marker isolates the most recent actual Play Mode.
    start_marker=content.rfind("AARIS_OFFLINE_DROP_VIDEO_PLAYMODE_REQUESTED")
    finish_marker=content.find("AARIS_OFFLINE_DROP_VIDEO_PROBE_FAILED",start_marker) if start_marker>=0 else -1
    section=content[start_marker:finish_marker if finish_marker>=0 else len(content)] if start_marker>=0 else content[-85000:]
    error_lines=section.splitlines()
    whitelist_types={
        "System.NullReferenceException":"NULL_REFERENCE",
        "NullReferenceException":"NULL_REFERENCE",
        "MissingReferenceException":"MISSING_REFERENCE",
        "MissingMethodException":"MISSING_METHOD",
        "InvalidOperationException":"INVALID_OPERATION",
        "UnityException":"UNITY_EXCEPTION",
        "ArgumentException":"INVALID_ARGUMENT",
        "ArgumentNullException":"NULL_ARGUMENT",
        "TypeInitializationException":"STATIC_INITIALIZER",
        "TypeLoadException":"TYPE_LOAD",
        "NotSupportedException":"NOT_SUPPORTED",
        "IndexOutOfRangeException":"INDEX_ERROR",
        "IOException":"IO_EXCEPTION",
        "FileNotFoundException":"FILE_NOT_FOUND",
        "Exception":"OTHER_EXCEPTION",
    }
    for i,line in enumerate(error_lines):
        if not re.search(r"Exception(?=[:\s]|$)|error CS\d{4}|Aaris.*ERROR|Aaris.*FAILED",line,re.I):
            continue
        window="\n".join(error_lines[i:min(len(error_lines),i+19)])
        for literal,label in whitelist_types.items():
            if re.search(r"\b"+re.escape(literal)+r"\b",line):
                print("AARIS_DROP_FIRST_ERROR_KIND_"+label)
                break
        for name,label in whitelist.items():
            if re.search(r"\b"+re.escape(name)+r"\b",window):
                print("AARIS_DROP_FIRST_ERROR_SOURCE_"+label)
        # Only inspect the first relevant error in the active gameplay window.
        break

    # Recognize fixed, known runtime complaints without copying their text.
    signature={
       "MISSING_LOCAL_ASSET":r"Resources.Load.*null|Missing Prefab|model.*not found",
       "ASSET_SHADER_ERROR":r"Shader.*unsupported|Shader.*not found|pink material",
       "PLAYER_CAMERA_ERROR":r"Saved player camera is missing",
       "LOOT_DATA_ERROR":r"no embedded offline authored loot locations|invalid loot JSON",
       "VEHICLE_DATA_ERROR":r"authored offline candidates/catalog are missing|malformed offline data",
       "GAME_ASSET_EXCEPTION":r"ArgumentException|InvalidOperationException",
       "UNIT_TEST_EXCEPTION":r"AarisOfflineDropPlayProbe.*Exception",
    }
    for category,pattern in signature.items():
        if re.search(pattern,content,re.I):print("AARIS_DROP_KNOWN_"+category)
else: print("AARIS_DROP_DIAG_UNITY_LOG_MISSING")
PYDROP
fi
