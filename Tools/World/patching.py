"""Guarded edits of saved core YAML. Native TerrainData writes use Unity, never hex edits."""
from __future__ import annotations

import difflib
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
import yaml

from unity_data import SCENE, World, WorldError, digest, documents, safe_path


class Dumper(yaml.SafeDumper):
    pass


def mapping(dumper, value):
    node = dumper.represent_mapping("tag:yaml.org,2002:map", value)
    keys = set(value)
    node.flow_style = ("fileID" in keys and keys <= {"fileID", "guid", "type"}) or keys in (
        {"x", "y"}, {"x", "y", "z"}, {"x", "y", "z", "w"}, {"r", "g", "b", "a"})
    return node


Dumper.add_representer(dict, mapping)


def vector(value, size, name, positive=False):
    if not isinstance(value, list) or len(value) != size or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise WorldError(f"{name} requires {size} finite numbers")
    if positive and any(v <= 0 or v > 100 for v in value):
        raise WorldError("Scale must be >0 and <=100; negative/mirrored transforms require a custom reviewed edit")
    return [float(v) for v in value]


def load_patch(path):
    patch = json.loads(Path(path).read_text())
    validate_patch(patch)
    return patch


def validate_patch(patch):
    if not isinstance(patch, dict): raise WorldError("Patch must be a JSON object")
    version = patch.get("schema_version")
    if version not in (1, 2) or not isinstance(patch.get("expected_files"), dict) or not patch["expected_files"]:
        raise WorldError("Patch requires schema_version 1 or 2 and expected_files {path: sha256}")
    ops = patch.get("operations")
    if not isinstance(ops, list) or not 1 <= len(ops) <= 100:
        raise WorldError("Patch requires 1..100 operations")
    if any(not isinstance(o, dict) for o in ops): raise WorldError("Each operation must be an object")
    if any(not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v)
           for k,v in patch["expected_files"].items()):
        raise WorldError("expected_files requires project path keys and lowercase SHA256 values")
    if not isinstance(patch.get("reason"), str) or not patch["reason"].strip():
        raise WorldError("Patch needs a concrete reason")
    allowed = {"schema_version", "expected_files", "operations", "reason"}
    if version == 2:
        allowed |= {"transaction_id", "idempotency_key", "observe_after", "acknowledgements"}
        for name in ("transaction_id", "idempotency_key"):
            value = patch.get(name)
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", value):
                raise WorldError(f"Schema v2 requires {name} (8..128 safe characters)")
        ids = [o.get("id") for o in ops]
        if any(not isinstance(i, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,96}", i) for i in ids) or len(set(ids)) != len(ids):
            raise WorldError("Schema v2 operations require unique safe id values")
        observe = patch.get("observe_after", [])
        if not isinstance(observe, list) or len(observe) > 32 or any(not isinstance(r, dict) for r in observe):
            raise WorldError("observe_after must be an array of at most 32 inspection requests")
        acknowledgements = patch.get("acknowledgements", [])
        if not isinstance(acknowledgements, list) or len(acknowledgements) > 100:
            raise WorldError("acknowledgements must be an array of at most 100 entries")
        for row in acknowledgements:
            if (not isinstance(row, dict) or set(row) != {"observation_id", "observation_hash", "reason"}
                    or not all(isinstance(row[k], str) and row[k].strip() for k in row)):
                raise WorldError("Each acknowledgement requires observation_id, observation_hash and reason")
            if (not re.fullmatch(r"obs:[a-f0-9]{24}", row["observation_id"])
                    or not re.fullmatch(r"[a-f0-9]{64}", row["observation_hash"])
                    or row["observation_id"] != "obs:"+row["observation_hash"][:24]):
                raise WorldError("Acknowledgement id/hash do not identify the same measured observation")
    if set(patch) - allowed:
        raise WorldError("Unknown patch fields")


def observation_requests(patch):
    explicit = patch.get("observe_after", [])
    if explicit:
        return explicit
    requests = []
    seen = set()
    for op in patch["operations"]:
        target = op.get("target")
        if target and op.get("op") not in ("delete_object", "terrain_instance_remove"):
            key = ("target", target)
            if key not in seen:
                requests.append({"target": target, "radius": 35, "limit": 100,
                                 "native": False, "geometry": True})
                seen.add(key)
        position = op.get("world_position")
        xz = op.get("world_xz") or op.get("center_xz")
        if position:
            key = ("point", *map(float, position))
            if key not in seen:
                requests.append({"x": position[0], "y": position[1], "z": position[2],
                                 "radius": 35, "limit": 100, "native": False, "geometry": True})
                seen.add(key)
        elif xz:
            key = ("xz", *map(float, xz))
            if key not in seen:
                requests.append({"x": xz[0], "z": xz[1], "radius": 35, "limit": 100,
                                 "native": False, "geometry": True})
                seen.add(key)
    return requests[:32]


def plan(root, patch):
    validate_patch(patch)
    root = Path(root).resolve()
    w = World(root)
    for path, expected in patch["expected_files"].items():
        p = safe_path(root, path)
        if not p.is_file() or digest(p) != expected:
            raise WorldError(f"Stale patch: {path}. Re-inspect the current core file before editing.")
    changes, edits, impacts, engine_ops = {}, {}, [], []
    version = patch["schema_version"]

    def op_fields(op):
        return set(op) - ({"id"} if version == 2 else set())

    def require_identity(path):
        if path not in patch["expected_files"]:
            raise WorldError(f"Missing expected SHA256 for {path}")
        if path + ".meta" not in patch["expected_files"]:
            raise WorldError(f"Missing expected SHA256 for identity metadata {path}.meta")
        return safe_path(root, path)

    def source(path):
        require_identity(path)
        if path not in changes:
            text, docs = documents(safe_path(root, path))
            changes[path] = (text, {d["file_id"]: d for d in docs})
        return changes[path]

    for op in patch["operations"]:
        kind = op.get("op")
        if kind == "set_transform":
            if op_fields(op) - {"op", "target", "world_position", "local_position", "local_rotation_xyzw", "local_scale"}:
                raise WorldError("Unknown set_transform fields")
            if "world_position" in op and "local_position" in op:
                raise WorldError("Choose world_position or local_position, not both")
            go = w.resolve(op["target"])
            if not op["target"].startswith("scene:"):
                raise WorldError("Writes require stable scene IDs, not names")
            transform = w.go_transform[go]
            _, docs = source(SCENE)
            doc = docs[transform]
            if doc["stripped"] or doc["data"].get("m_PrefabInstance", {}).get("fileID"):
                raise WorldError("Prefab instances need Unity edits; inline saved objects only")
            fields = {"local_position": ("m_LocalPosition", 3, "xyz"),
                      "local_rotation_xyzw": ("m_LocalRotation", 4, "xyzw"),
                      "local_scale": ("m_LocalScale", 3, "xyz")}
            count = 0
            if "world_position" in op:
                world_position = np.asarray(vector(op["world_position"], 3, "world_position") + [1.0])
                parent = doc["data"].get("m_Father", {}).get("fileID", 0)
                local = np.linalg.inv(w.world_matrix(parent)) @ world_position if parent else world_position
                if not np.isfinite(local).all() or abs(local[3]) < 1e-9:
                    raise WorldError("Parent matrix cannot resolve the requested world position")
                local = local[:3] / local[3]
                doc["data"]["m_LocalPosition"] = dict(zip("xyz", map(float, local)))
                count += 1
            for key, (prop, size, axes) in fields.items():
                if key in op:
                    values = vector(op[key], size, key, key == "local_scale")
                    if key == "local_rotation_xyzw":
                        norm = math.sqrt(sum(v*v for v in values))
                        if abs(norm-1) > .001:
                            raise WorldError("Rotation quaternion must be normalized")
                    doc["data"][prop] = dict(zip(axes, values))
                    count += 1
            if not count:
                raise WorldError("set_transform has no fields to change")
            edits.setdefault(SCENE, set()).add(transform)
            impacts.append({"target": op["target"], "name": w.gos[go]["m_Name"], "core_file": SCENE,
                            "review": "Recheck ground contact, road access, vehicle pads and source-derived layout reports."})
        elif kind == "set_object_state":
            if op_fields(op) - {"op", "target", "active", "name"}:
                raise WorldError("Unknown set_object_state fields")
            go = w.resolve(op["target"])
            if not op["target"].startswith("scene:"):
                raise WorldError("Writes require stable scene IDs")
            _, docs = source(SCENE)
            doc = docs.get(go)
            if not doc or doc["kind"] != "GameObject" or doc["stripped"]:
                raise WorldError("Object state writes require an inline saved GameObject")
            changed = 0
            if "active" in op:
                if not isinstance(op["active"], bool):
                    raise WorldError("active must be boolean")
                doc["data"]["m_IsActive"] = 1 if op["active"] else 0
                changed += 1
            if "name" in op:
                if (not isinstance(op["name"], str) or not op["name"].strip() or len(op["name"]) > 128
                        or any(ord(c) < 32 for c in op["name"])):
                    raise WorldError("name must be a non-empty printable string <=128 characters")
                doc["data"]["m_Name"] = op["name"].strip()
                changed += 1
            if not changed:
                raise WorldError("set_object_state has no fields to change")
            edits.setdefault(SCENE, set()).add(go)
            impacts.append({"target": op["target"], "core_file": SCENE,
                            "review": "State/name changed on the selected saved scene object only."})
        elif kind == "set_material_color":
            if op_fields(op) != {"op", "path", "file_id", "property", "rgba"}:
                raise WorldError("set_material_color requires path, file_id, property, rgba")
            path = op["path"]
            if not path.startswith("Assets/") or not path.endswith(".mat"):
                raise WorldError("Material color writes require an Assets/*.mat file")
            rgba = vector(op["rgba"], 4, "rgba")
            if any(v < 0 or v > 16 for v in rgba[:3]) or not 0 <= rgba[3] <= 1:
                raise WorldError("Color requires RGB in 0..16 and alpha in 0..1")
            _, docs = source(path)
            doc = docs.get(op["file_id"])
            if not doc or doc["kind"] != "Material":
                raise WorldError("Material fileID unresolved")
            colors = doc["data"].get("m_SavedProperties", {}).get("m_Colors", [])
            matching = [r for r in colors if op["property"] in r]
            if len(matching) != 1:
                raise WorldError("Color property must already exist exactly once; inspect the material first")
            matching[0][op["property"]] = dict(zip("rgba", rgba))
            edits.setdefault(path, set()).add(op["file_id"])
            impacts.append({"core_file": path, "review": "Shared material: affects every renderer using this GUID."})
        elif kind == "set_material_float":
            if op_fields(op) != {"op", "path", "file_id", "property", "value"}:
                raise WorldError("set_material_float requires path, file_id, property, value")
            path = op["path"]
            if not path.startswith("Assets/") or not path.endswith(".mat"):
                raise WorldError("Material writes require an Assets/*.mat file")
            value = op["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e6:
                raise WorldError("Material float must be finite and within +/-1e6")
            _, docs = source(path)
            doc = docs.get(op["file_id"])
            if not doc or doc["kind"] != "Material":
                raise WorldError("Material fileID unresolved")
            floats = doc["data"].get("m_SavedProperties", {}).get("m_Floats", [])
            matching = [r for r in floats if op["property"] in r]
            if len(matching) != 1:
                raise WorldError("Float property must already exist exactly once; inspect the material first")
            matching[0][op["property"]] = float(value)
            edits.setdefault(path, set()).add(op["file_id"])
            impacts.append({"core_file": path, "review": "Shared material: affects every renderer using this GUID."})
        elif kind == "terrain_brush":
            if op_fields(op) != {"op", "center_xz", "radius_m", "delta_m"}:
                raise WorldError("terrain_brush requires center_xz, radius_m, delta_m")
            vector(op["center_xz"], 2, "center_xz")
            r, dy = op["radius_m"], op["delta_m"]
            if not isinstance(r, (int, float)) or not isinstance(dy, (int, float)) or not math.isfinite(r) or not math.isfinite(dy) or not 0 < r <= 100 or abs(dy) > 20:
                raise WorldError("Brush radius must be 0..100m and vertical delta within +/-20m")
            # All four assets participate in seam verification, including brushes across a border.
            for t in w.terrains():
                path = t["asset"]["path"]
                require_identity(path)
            require_identity(SCENE)
            engine_ops.append(dict(op))
            impacts.append({"operation": kind, "review": "Unity SetHeights updates native LOD data; recheck seams, vegetation, roads, water and foundations."})
        elif kind.startswith("terrain_instance_"):
            allowed = {
                "terrain_instance_move": {"op", "target", "world_xz"},
                "terrain_instance_scale": {"op", "target", "width_scale", "height_scale"},
                "terrain_instance_rotate": {"op", "target", "yaw_degrees"},
                "terrain_instance_remove": {"op", "target"},
                "terrain_instance_add": {"op", "terrain", "prototype_index", "world_xz", "width_scale", "height_scale", "yaw_degrees"},
            }.get(kind)
            if allowed is None or op_fields(op) != allowed:
                raise WorldError(f"Invalid fields for {kind}")
            from terrain import NativeTerrain
            native = NativeTerrain(w)
            resolved = dict(op)
            if kind == "terrain_instance_add":
                matches = [t for t in native.tiles if op["terrain"] in (t["id"], t["asset"]["path"], t["asset"]["guid"])]
                if len(matches) != 1:
                    raise WorldError("terrain_instance_add terrain must resolve one saved terrain tile")
                tile = matches[0]
                data = native.load(tile)
                if type(op["prototype_index"]) is not int or not 0 <= op["prototype_index"] < len(data["prototypes"]):
                    raise WorldError("prototype_index is outside this terrain's prototype table")
                position = vector(op["world_xz"], 2, "world_xz")
                ox, _, oz = tile["origin_m"]
                if not (ox <= position[0] <= ox+data["size_m"][0] and oz <= position[1] <= oz+data["size_m"][2]):
                    raise WorldError("New native instance lies outside the selected terrain tile")
                for name in ("width_scale", "height_scale"):
                    vector([op[name]], 1, name, True)
                if isinstance(op["yaw_degrees"], bool) or not isinstance(op["yaw_degrees"], (int, float)) or not math.isfinite(op["yaw_degrees"]):
                    raise WorldError("yaw_degrees must be finite")
                resolved["terrain_path"] = tile["asset"]["path"]
                resolved["terrain_guid"] = tile["asset"]["guid"]
                require_identity(tile["asset"]["path"])
            else:
                row = native.find_instance(op["target"])
                require_identity(row["terrain_path"])
                resolved["terrain_path"] = row["terrain_path"]
                resolved["terrain_guid"] = row["terrain_guid"]
                resolved["original_index"] = row["instance_index"]
                resolved["expected"] = {"prototype_index": row["prototype_index"], "position_m": row["position_m"],
                                        "width_scale": row["width_scale"], "height_scale": row["height_scale"],
                                        "yaw_degrees": row["yaw_degrees"]}
                if kind == "terrain_instance_move":
                    position = vector(op["world_xz"], 2, "world_xz")
                    tile = next(t for t in native.tiles if t["asset"]["path"] == row["terrain_path"])
                    data = native.load(tile); ox, _, oz = tile["origin_m"]
                    if not (ox <= position[0] <= ox+data["size_m"][0] and oz <= position[1] <= oz+data["size_m"][2]):
                        raise WorldError("Move crosses a TerrainData tile; use remove + add so ownership is explicit")
                elif kind == "terrain_instance_scale":
                    for name in ("width_scale", "height_scale"):
                        vector([op[name]], 1, name, True)
                elif kind == "terrain_instance_rotate":
                    if isinstance(op["yaw_degrees"], bool) or not isinstance(op["yaw_degrees"], (int, float)) or not math.isfinite(op["yaw_degrees"]):
                        raise WorldError("yaw_degrees must be finite")
            require_identity(SCENE)
            engine_ops.append(resolved)
            impacts.append({"operation": kind, "target": op.get("target"), "core_file": resolved["terrain_path"],
                            "review": "Native TerrainData instance edit; re-observe prototype, position, scale, neighbours and terrain support."})
        elif kind in ("instantiate_prefab", "duplicate_object", "delete_object"):
            allowed = {
                "instantiate_prefab": {"op", "prefab_path", "world_position", "world_rotation_euler", "local_scale", "parent", "name"},
                "duplicate_object": {"op", "target", "world_position", "world_rotation_euler", "local_scale", "name"},
                "delete_object": {"op", "target"},
            }[kind]
            required = {"op", "prefab_path", "world_position"} if kind == "instantiate_prefab" else {"op", "target"}
            if op_fields(op) - allowed or not required <= op_fields(op):
                raise WorldError(f"Invalid fields for {kind}")
            resolved = dict(op)
            require_identity(SCENE)
            if kind == "instantiate_prefab":
                path = op["prefab_path"]
                if not isinstance(path, str) or not path.startswith("Assets/") or not path.endswith(".prefab"):
                    raise WorldError("instantiate_prefab requires an Assets/*.prefab path")
                require_identity(path)
                vector(op["world_position"], 3, "world_position")
                if op.get("parent"):
                    w.resolve(op["parent"])
            else:
                if not isinstance(op["target"], str) or not op["target"].strip():
                    raise WorldError(f"{kind} requires a stable target")
                if op["target"].startswith("scene:"):
                    w.resolve(op["target"])
            for field in ("world_position", "world_rotation_euler", "local_scale"):
                if field in op:
                    vector(op[field], 3, field, field == "local_scale")
            if "name" in op and (not isinstance(op["name"], str) or not op["name"].strip() or len(op["name"]) > 128):
                raise WorldError("Scene object name must be non-empty and <=128 characters")
            engine_ops.append(resolved)
            impacts.append({"operation": kind, "target": op.get("target"), "core_file": SCENE,
                            "review": "Unity will save the actual scene and return new/resolved object identities."})
        else:
            raise WorldError(f"Unsupported operation {kind!r}; no generic byte or arbitrary serialized-field writes")
    outputs, diffs = {}, {}
    for path, ids in edits.items():
        text, docs = changes[path]
        out = text
        for i in sorted(ids, key=lambda i: docs[i]["body_start"], reverse=True):
            d = docs[i]
            body = yaml.dump({d["kind"]: d["data"]}, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=100000)
            out = out[:d["body_start"]] + body + out[d["end"]:]
        outputs[path] = out
        diffs[path] = "".join(difflib.unified_diff(text.splitlines(True), out.splitlines(True), fromfile=path, tofile=path))
    observe_after = observation_requests(patch)
    return {"schema_version": version, "protocol_version": 2,
            "transaction_id": patch.get("transaction_id"), "idempotency_key": patch.get("idempotency_key"),
            "backend": "unity" if engine_ops else "python_yaml", "dry_run": True,
            "reason": patch["reason"], "expected_files": patch["expected_files"], "diffs": diffs,
            "native_operations": [o for o in engine_ops if o["op"] == "terrain_brush"],
            "unity_operations": engine_ops, "impacts": impacts,
            "observe_after": observe_after, "acknowledgements": patch.get("acknowledgements", []),
            "note": "Core assets change only on apply --write. Historical Docs/*REPORT.json are not refreshed or treated as current proof."}, outputs


def apply_yaml(root, patch, write=False):
    report, outputs = plan(root, patch)
    if not write:
        return report
    if report["backend"] != "python_yaml":
        raise WorldError("Native TerrainData edits require apply --backend unity --write and a complete Unity checkout")
    root = Path(root)
    originals = {p: (root/p).read_bytes() for p in outputs}
    # Stage complete documents and parse them before replacing any real core file.
    with tempfile.TemporaryDirectory(prefix="aaris-patch-") as tmp:
        for index, (path, text) in enumerate(outputs.items()):
            p = Path(tmp)/str(index)
            p.write_text(text)
            _, after = documents(p)
            _, before = documents(root/path)
            if [(d["class_id"], d["file_id"], d["kind"]) for d in before] != [(d["class_id"], d["file_id"], d["kind"]) for d in after]:
                raise WorldError("Patch changed saved object identity")
        # Re-check the preconditions immediately before mutation.
        for path, expected in patch["expected_files"].items():
            if digest(safe_path(root, path)) != expected:
                raise WorldError("Source changed while planning; no files written")
        try:
            for path, text in outputs.items():
                atomic_write(root/path, text.encode())
            world = World(root)
            for t in world.transforms:
                world.world_matrix(t)
            from observations import inspect
            observed = []
            for request in report["observe_after"]:
                try:
                    observed.append({"request": request, "result": inspect(world, request)})
                except (WorldError, ImportError, OSError) as error:
                    observed.append({"request": request, "status": "unavailable", "reason": str(error)})
        except BaseException:
            for path, data in originals.items():
                atomic_write(root/path, data)
            raise
    return {**report, "dry_run": False, "written_files": {p: digest(root/p) for p in outputs},
            "post_edit_observations": observed,
            "verification": "YAML identity and finite world transforms verified. Run verify and Unity/device tests before merge."}


def _copy_project_hardlinked(source, destination):
    source, destination = Path(source), Path(destination)
    for folder in ("Assets", "Packages", "ProjectSettings"):
        src = source / folder
        if not src.exists():
            continue
        try:
            shutil.copytree(src, destination / folder, copy_function=os.link)
        except OSError:
            shutil.rmtree(destination / folder, ignore_errors=True)
            shutil.copytree(src, destination / folder)


def preview_yaml(root, patch):
    """Apply a YAML-only patch to an isolated hard-linked project and observe it."""
    report, _ = plan(root, patch)
    if report["backend"] != "python_yaml":
        raise WorldError("Unity-native operations require preview --backend unity")
    with tempfile.TemporaryDirectory(prefix="aaris-preview-") as temp:
        project = Path(temp) / "project"
        project.mkdir()
        _copy_project_hardlinked(root, project)
        result = apply_yaml(project, patch, True)
        return {**result, "dry_run": True, "preview": True, "written_files": {},
                "temporary_project_deleted_on_return": True,
                "note": "Preview mutated only an isolated project copy; source core bytes were not changed."}


def atomic_write(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".world-stage-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)

