"""Launch the installed Unity editor in a disposable copy; never borrow an open project."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from patching import apply_yaml, atomic_write, plan
from unity_data import SCENE, World, WorldError, digest, pointer, safe_path


def capabilities(root):
    root = Path(root).resolve()
    executable = os.environ.get("UNITY_EDITOR_PATH", "")
    missing = [p.relative_to(root).as_posix() for p in (Path(root)/"Assets").rglob("*")
               if p.is_file() and pointer(p)]
    inventory = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "Assets"], capture_output=True, check=False)
    tracked = inventory.stdout.decode().split("\0") if inventory.returncode == 0 else []
    absent = [p for p in tracked if p and not (root/p).is_file()]
    inventory_ok = len(tracked) > 1
    available = bool(executable and Path(executable).is_file())
    return {"editor_available": available, "editor_path_configured": bool(executable),
            "lfs_pointer_count": len(missing), "missing_sample": missing[:12],
            "tracked_inventory_available": inventory_ok, "absent_tracked_count": len(absent),
            "ready": available and not missing and inventory_ok and not absent,
            "requires": "Installed/licensed project-matching Unity, complete git lfs pull, isolated project import. A GitHub connection alone supplies neither an editor nor a runner."}


def run(root, request, patch=None, write=False, capture_dir=None):
    root = Path(root).resolve()
    cap = capabilities(root)
    if not cap["ready"]:
        raise WorldError("Unity engine is unavailable or LFS checkout is incomplete: " + json.dumps(cap))
    action = request.get("command")
    if action not in ("export", "observe", "probe", "capture", "preview", "apply"):
        raise WorldError("Unsupported Unity command")
    patch_report, outputs = (plan(root, patch) if patch else (None, {}))
    if action == "apply" and (not patch or not write):
        raise WorldError("Unity apply requires a validated patch and --write")
    if action == "preview" and not patch:
        raise WorldError("Unity preview requires a validated patch")
    allowed = set(outputs)
    if patch_report:
        unity_ops = patch_report["unity_operations"]
        if any(o["op"] == "terrain_brush" for o in unity_ops):
            allowed.update(t["asset"]["path"] for t in World(root).terrains())
        allowed.update(o["terrain_path"] for o in unity_ops if o["op"].startswith("terrain_instance_"))
        if any(o["op"] in ("instantiate_prefab", "duplicate_object", "delete_object") for o in unity_ops):
            allowed.add(SCENE)
    with tempfile.TemporaryDirectory(prefix="aaris-unity-", dir=os.environ.get("AARIS_WORLD_TEMP")) as temp:
        temp = Path(temp)
        project = temp/"project"
        for folder in ("Assets", "Packages", "ProjectSettings"):
            shutil.copytree(root/folder, project/folder)
        # YAML edits use the same guarded, identity-preserving Python implementation in the copy.
        if outputs:
            yaml_kinds = {"set_transform", "set_object_state", "set_material_color", "set_material_float", "remove_mesh_triangles", "set_prefab_lod_thresholds"}
            yaml_patch = {**patch, "operations": [o for o in patch["operations"] if o["op"] in yaml_kinds]}
            if yaml_patch["operations"]:
                apply_yaml(project, yaml_patch, True)
        req = {**request, "scene": SCENE}
        if patch_report:
            req["brushes"] = [{"x": o["center_xz"][0], "z": o["center_xz"][1],
                              "radius": o["radius_m"], "delta": o["delta_m"]} for o in patch_report["native_operations"]]
            req["terrainEdits"] = [_terrain_edit(o) for o in patch_report["unity_operations"]
                                   if o["op"].startswith("terrain_instance_")]
            req["sceneEdits"] = [_scene_edit(o) for o in patch_report["unity_operations"]
                                 if o["op"] in ("instantiate_prefab", "duplicate_object", "delete_object")]
            req["observations"] = [_observation_request(o) for o in patch_report["observe_after"]]
        req_path, response = temp/"request.json", temp/"response.json"
        req["capturePath"] = str(temp/"capture.png")
        req_path.write_text(json.dumps(req))
        env = dict(os.environ, AARIS_WORLD_REQUEST=str(req_path), AARIS_WORLD_RESPONSE=str(response))
        args = [os.environ["UNITY_EDITOR_PATH"], "-batchmode", "-quit", "-projectPath", str(project),
                "-executeMethod", "Aaris.WorldAutomation.WorldBridge.Run", "-logFile", str(temp/"unity.log")]
        if action != "capture":
            args.insert(1, "-nographics")
        proc = None
        previous_handler = signal.getsignal(signal.SIGTERM)
        def cancelled(signum, frame):
            raise WorldError("Unity query cancelled; terminating the isolated editor and removing its project")
        signal.signal(signal.SIGTERM, cancelled)
        try:
            proc = subprocess.Popen(args, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                code = proc.wait(timeout=1800)
            except subprocess.TimeoutExpired as e:
                raise WorldError("Unity import/query exceeded 30 minutes; temporary project removed") from e
        finally:
            if proc is not None and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            signal.signal(signal.SIGTERM, previous_handler)
        if code or not response.is_file():
            log = (temp/"unity.log").read_text(errors="replace")[-12000:] if (temp/"unity.log").exists() else "No editor log"
            raise WorldError(f"Unity failed (exit {code}); {log}")
        result = json.loads(response.read_text())
        if result.get("status") != "ok":
            raise WorldError("Unity rejected request: " + json.dumps(result))
        if action == "apply":
            originals = {p: (root/p).read_bytes() for p in allowed}
            for p, expected in patch["expected_files"].items():
                if digest(safe_path(root, p)) != expected:
                    raise WorldError("Original checkout changed during Unity run; no files copied back")
            if patch_report["native_operations"]:
                from terrain import NativeTerrain
                seams = NativeTerrain(World(project)).seams()
                if any(s["max_delta_m"] > .05 for s in seams):
                    raise WorldError("Unity result has a terrain seam >5cm; no files copied back")
                result["seam_verification"] = seams
            try:
                for p in sorted(allowed):
                    atomic_write(root/p, (project/p).read_bytes())
            except BaseException:
                for p, data in originals.items():
                    atomic_write(root/p, data)
                raise
            result["written_files"] = {p: digest(root/p) for p in sorted(allowed)}
            result["historical_layout_reports"] = "May be stale. Regenerate/review before merge; this tool does not forge authoring reports."
            from observations import inspect
            post = World(root)
            result["serialized_post_edit_observations"] = []
            for observation in patch_report["observe_after"]:
                try:
                    result["serialized_post_edit_observations"].append({"request": observation, "result": inspect(post, observation)})
                except (WorldError, ImportError, OSError) as error:
                    result["serialized_post_edit_observations"].append({"request": observation, "status": "unavailable", "reason": str(error)})
        elif action == "preview":
            result["preview"] = True
            result["dry_run"] = True
            result["written_files"] = {}
            result["note"] = "Unity changed only the disposable project. Review observations before applying the same current-hash transaction."
        if action == "capture":
            if not capture_dir:
                raise WorldError("Capture requires an explicit output directory")
            out = Path(capture_dir)
            out.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp/"capture.png", out/"capture.png")
            result["capture"] = str(out/"capture.png")
        result["temporary_project_deleted_on_return"] = True
        source = World(root)
        source.terrains()
        result["source_fingerprint"] = source.fingerprint()
        return result


def _vec3(values):
    if values is None:
        return None
    return {"x": values[0], "y": values[1], "z": values[2]}


def _terrain_edit(op):
    expected = op.get("expected", {})
    position = expected.get("position_m", [0, 0, 0])
    xz = op.get("world_xz", [0, 0])
    return {"id": op.get("id", ""), "action": op["op"].removeprefix("terrain_instance_"),
            "target": op.get("target", ""), "terrainGuid": op.get("terrain_guid", ""),
            "originalIndex": op.get("original_index", -1), "prototypeIndex": op.get("prototype_index", -1),
            "worldX": xz[0], "worldZ": xz[1], "widthScale": op.get("width_scale", 0),
            "heightScale": op.get("height_scale", 0), "yawDegrees": op.get("yaw_degrees", 0),
            "expectedPrototypeIndex": expected.get("prototype_index", -1),
            "expectedWorldPosition": _vec3(position), "expectedWidthScale": expected.get("width_scale", 0),
            "expectedHeightScale": expected.get("height_scale", 0), "expectedYawDegrees": expected.get("yaw_degrees", 0)}


def _scene_edit(op):
    return {"id": op.get("id", ""), "action": op["op"].removesuffix("_object").removesuffix("_prefab"),
            "target": op.get("target", ""), "prefabPath": op.get("prefab_path", ""),
            "parent": op.get("parent", ""), "name": op.get("name", ""),
            "hasWorldPosition": "world_position" in op, "worldPosition": _vec3(op.get("world_position")),
            "hasWorldRotation": "world_rotation_euler" in op, "worldRotationEuler": _vec3(op.get("world_rotation_euler")),
            "hasLocalScale": "local_scale" in op, "localScale": _vec3(op.get("local_scale"))}


def _observation_request(request):
    return {"target": request.get("target", ""), "hasPoint": "x" in request and "z" in request,
            "hasY": "y" in request,
            "point": {"x": request.get("x", 0), "y": request.get("y", 0), "z": request.get("z", 0)},
            "radius": request.get("radius", 35), "limit": request.get("limit", 100)}

