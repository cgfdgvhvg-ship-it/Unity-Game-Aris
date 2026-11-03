"""Guarded edits of saved core YAML. Native TerrainData writes use Unity, never hex edits."""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
import yaml

from unity_data import SCENE, World, WorldError, digest, documents, safe_path, references, matrix


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


def observation_requests(patch, world=None):
    """Always retain automatic change-site probes alongside caller probes.

    An explicit observe_after augments rather than disables automatic validation.
    Shared material usages are sampled from the saved scene; pagination/limits
    must not be mistaken for evidence that every other material user was checked.
    """
    explicit = patch.get("observe_after", [])
    requests = []
    seen = set()
    for op in patch["operations"]:
        target = op.get("target")
        if target and op.get("op") not in ("delete_object", "terrain_instance_remove"):
            key = ("target", target)
            if key not in seen:
                requests.append({"target": target, "radius": 35, "limit": 100,
                                 "native": True, "geometry": True, "appearance": True, "semantics": True})
                seen.add(key)
        position = op.get("world_position")
        xz = op.get("world_xz") or op.get("center_xz")
        if position:
            key = ("point", *map(float, position))
            if key not in seen:
                requests.append({"x": position[0], "y": position[1], "z": position[2],
                                 "radius": 35, "limit": 100, "native": True, "geometry": True,
                                 "appearance": True, "semantics": True})
                seen.add(key)
        elif xz:
            key = ("xz", *map(float, xz))
            if key not in seen:
                requests.append({"x": xz[0], "z": xz[1], "radius": 35, "limit": 100,
                                 "native": True, "geometry": True, "appearance": True, "semantics": True})
                seen.add(key)
    if world is not None:
        for op in patch["operations"]:
            if op.get("op") not in ("set_material_color", "set_material_float"):
                continue
            guids = {guid for guid, path in world.guid_paths.items() if path == op.get("path")}
            if not guids:
                continue
            users = set()
            for component in world.docs.values():
                if component["kind"] not in ("MeshRenderer", "SkinnedMeshRenderer"):
                    continue
                if not any(ref.get("guid") in guids for ref in
                           references(component["data"].get("m_Materials", []))):
                    continue
                go = component["data"].get("m_GameObject", {}).get("fileID")
                if go in world.gos and go in world.go_transform and ("material_user", go) not in seen:
                    users.add(go)
            ordered = sorted(users)
            budget = min(6, 32 - len(explicit) - len(requests))
            if ordered and budget < 1:
                raise WorldError("No remaining observation budget for shared material users; split this edit")
            # A shared material may be used by hundreds of objects. Sample up
            # to six users per material to keep the repeated full-map inspection
            # workload bounded, and keep the full usage count in operation state.
            # Keep a
            # deterministic spread of saved fileIDs rather than rejecting
            # ordinary material edits or pretending the sample is exhaustive.
            if len(ordered) > budget:
                ordered = [ordered[(index * len(ordered)) // budget] for index in range(budget)]
            for go in ordered:
                requests.append({"target": world.stable_id(go), "radius": 35, "limit": 100,
                                 "native": True, "geometry": True,
                                 "appearance": True, "semantics": True})
                seen.add(("material_user", go))
    # The requested observations are never suppressed by the automatic probes.
    # Cap expensive inspection work and disclose this bound to the AI.
    combined = []
    keys = set()
    for item in [*explicit, *requests]:
        signature = json.dumps(item, sort_keys=True)
        if signature not in keys:
            combined.append(item)
            keys.add(signature)
    if len(combined) > 32:
        raise WorldError("More than 32 observations needed; split the edit into smaller transactions")
    return combined


def _operation_state(world, operation, resolved=None):
    """Small exact state capsule used for automatic before/after edit evidence."""
    kind = operation.get("op")
    operation_id = operation.get("id", kind)
    try:
        if kind in ("set_transform", "set_object_state", "duplicate_object", "delete_object"):
            go = world.resolve(operation["target"])
            return {"operation_id": operation_id, "status": "available", "state": world.object(go, True)}
        if kind in ("set_material_color", "set_material_float"):
            docs = world.asset_docs(operation["path"])
            if docs.get("status") != "read":
                return {"operation_id": operation_id, "status": "unavailable", "reason": docs.get("status")}
            doc = next((d for d in docs["docs"] if d["file_id"] == operation["file_id"] and d["kind"] == "Material"), None)
            if doc is None:
                raise WorldError("Material state fileID is unavailable")
            collection = "m_Colors" if kind == "set_material_color" else "m_Floats"
            rows = doc["data"].get("m_SavedProperties", {}).get(collection, [])
            matches = [row[operation["property"]] for row in rows if operation["property"] in row]
            from observations import usages
            usage_report = usages(world, {"path": operation["path"]})
            return {"operation_id": operation_id, "status": "available", "state": {
                "path": operation["path"], "file_id": operation["file_id"], "property": operation["property"],
                "value": matches[0] if len(matches) == 1 else {"status": "not_exactly_one", "matches": len(matches)},
                "shared_usages": usage_report["text_serialized_usages"],
                "total_reference_occurrences": usage_report["total_reference_occurrences"]}}
        if kind == "place_static_prefab" and resolved:
            go = world.resolve(resolved["id"])
            return {"operation_id": operation_id, "status": "available", "state": world.object(go, True)}
        if kind and kind.startswith("terrain_instance_") and operation.get("target"):
            from terrain import NativeTerrain
            return {"operation_id": operation_id, "status": "available",
                    "state": NativeTerrain(world).find_instance(operation["target"])}
    except (WorldError, ImportError, OSError, KeyError) as error:
        return {"operation_id": operation_id, "status": "unavailable", "reason": str(error)}
    return {"operation_id": operation_id, "status": "not_applicable_before_or_requires_unity"}


def _collect_observations(world, requests):
    from observations import inspect
    rows = []
    for request in requests:
        try:
            rows.append({"request": request, "result": inspect(world, request)})
        except (WorldError, ImportError, OSError, KeyError) as error:
            rows.append({"request": request, "status": "unavailable", "reason": str(error)})
    return rows


def _observation_metrics(row):
    result = row.get("result")
    if not isinstance(result, dict):
        return {"status": row.get("status", "unavailable"), "reason": row.get("reason")}
    target = result.get("target") or {}
    bounds = target.get("renderer_bounds") or target.get("bounds") or {}
    scene = {item["id"]: item.get("distance_to_bounds_m", item.get("distance_m"))
             for item in result.get("nearby_scene_objects", [])}
    native = {item["id"]: item.get("distance_m") for item in result.get("nearby_native_instances", [])}
    terrain = result.get("terrain_relation") or {}
    appearance = {}
    positions = {}
    sizes = {}
    semantics = {}
    for item in result.get("nearby_scene_objects", []):
        identifier = item["id"]
        positions[identifier] = item.get("world_position_m")
        sizes[identifier] = (item.get("bounds") or {}).get("size_m")
        semantics[identifier] = (item.get("semantic") or {}).get("primary_role")
        slots = (item.get("appearance") or {}).get("material_slots", [])
        appearance[identifier] = [
            {"node_id": slot.get("node_id"), "slot_index": slot.get("slot_index"),
             "material_path": (slot.get("material") or {}).get("path"),
             "color_properties": (slot.get("material") or {}).get("color_properties"),
             "texture_references": [
                 (texture.get("reference") or {}).get("path")
                 for texture in (slot.get("material") or {}).get("textures", [])]}
            for slot in slots[:48]]
    native_shape = {
        item["id"]: {"position_m": item.get("position_m"),
                      "width_scale": item.get("width_scale"),
                      "height_scale": item.get("height_scale"),
                      "color": item.get("color"),
                      "lightmap_color": item.get("lightmap_color")}
        for item in result.get("nearby_native_instances", [])
    }
    return {"status": "available", "target_id": target.get("id"), "target_name": target.get("name"),
            "target_position_m": target.get("world_position_m"), "target_size_m": bounds.get("size_m"),
            "target_semantic": (target.get("semantic") or {}).get("primary_role"),
            "point_minus_ground_m": terrain.get("point_minus_ground_m"),
            "scene_neighbour_distance_m": scene, "native_neighbour_distance_m": native,
            "scene_neighbour_positions_m": positions, "scene_neighbour_bounds_sizes_m": sizes,
            "scene_neighbour_semantics": semantics, "scene_neighbour_materials": appearance,
            "native_neighbour_shapes": native_shape,
            "coverage": result.get("coverage")}


def _vector_delta(before, after):
    if (isinstance(before, list) and isinstance(after, list) and len(before) == len(after)
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in before+after)):
        return [float(b)-float(a) for a, b in zip(before, after)]
    return None


def _observation_deltas(before_rows, after_rows):
    rows = []
    for index in range(max(len(before_rows), len(after_rows))):
        before = _observation_metrics(before_rows[index]) if index < len(before_rows) else {"status": "missing"}
        after = _observation_metrics(after_rows[index]) if index < len(after_rows) else {"status": "missing"}
        before_scene, after_scene = before.get("scene_neighbour_distance_m", {}), after.get("scene_neighbour_distance_m", {})
        before_native, after_native = before.get("native_neighbour_distance_m", {}), after.get("native_neighbour_distance_m", {})
        rows.append({
            "request": after_rows[index].get("request") if index < len(after_rows) else before_rows[index].get("request"),
            "before": before, "after": after,
            "target_position_delta_m": _vector_delta(before.get("target_position_m"), after.get("target_position_m")),
            "target_size_delta_m": _vector_delta(before.get("target_size_m"), after.get("target_size_m")),
            "scene_neighbours_added": sorted(set(after_scene)-set(before_scene)),
            "scene_neighbours_removed": sorted(set(before_scene)-set(after_scene)),
            "native_neighbours_added": sorted(set(after_native)-set(before_native)),
            "native_neighbours_removed": sorted(set(before_native)-set(after_native)),
            "scene_neighbour_distance_changes_m": {
                key: float(after_scene[key] - before_scene[key])
                for key in sorted(set(before_scene) & set(after_scene))
                if before_scene[key] is not None and after_scene[key] is not None
                and abs(after_scene[key] - before_scene[key]) > 1e-6},
            "native_neighbour_distance_changes_m": {
                key: float(after_native[key] - before_native[key])
                for key in sorted(set(before_native) & set(after_native))
                if before_native[key] is not None and after_native[key] is not None
                and abs(after_native[key] - before_native[key]) > 1e-6},
            "scene_neighbours_with_position_changes": sorted(
                key for key in (set(before.get("scene_neighbour_positions_m", {})) &
                                set(after.get("scene_neighbour_positions_m", {})))
                if before["scene_neighbour_positions_m"][key] != after["scene_neighbour_positions_m"][key]),
            "scene_neighbours_with_shape_changes": sorted(
                key for key in (set(before.get("scene_neighbour_bounds_sizes_m", {})) &
                                set(after.get("scene_neighbour_bounds_sizes_m", {})))
                if before["scene_neighbour_bounds_sizes_m"][key] != after["scene_neighbour_bounds_sizes_m"][key]),
            "scene_neighbours_with_material_changes": sorted(
                key for key in (set(before.get("scene_neighbour_materials", {})) &
                                set(after.get("scene_neighbour_materials", {})))
                if before["scene_neighbour_materials"][key] != after["scene_neighbour_materials"][key]),
            "native_neighbours_with_shape_or_tint_changes": sorted(
                key for key in (set(before.get("native_neighbour_shapes", {})) &
                                set(after.get("native_neighbour_shapes", {})))
                if before["native_neighbour_shapes"][key] != after["native_neighbour_shapes"][key]),
            "interpretation": "Neighbour added/removed means entered/left the returned query page, not necessarily asset creation/deletion. Pagination, unknown geometry and physics/render limits still apply.",
        })
    return rows


def _resolve_final_positions(world, docs, requested):
    """Resolve explicit world positions through the final parent graph, in any op order."""
    resolved = {}
    def visit(transform, trail):
        if transform in resolved:
            return resolved[transform]
        if transform in trail or transform not in world.transforms:
            raise WorldError("Unresolved or cyclic planned transform parent")
        data = docs[transform]["data"]
        parent = data.get("m_Father", {}).get("fileID", 0)
        parent_matrix = visit(parent, trail | {transform}) if parent else np.eye(4)
        if transform in requested:
            try:
                local = np.linalg.solve(parent_matrix, np.r_[requested[transform], 1.0])
            except np.linalg.LinAlgError as error:
                raise WorldError("Final parent matrix cannot resolve world position") from error
            if not np.isfinite(local).all() or abs(local[3]) < 1e-9:
                raise WorldError("Final parent matrix produced an invalid local position")
            data["m_LocalPosition"] = dict(zip("xyz", map(float, local[:3] / local[3])))
        resolved[transform] = parent_matrix @ matrix(data)
        return resolved[transform]
    for transform in requested:
        visit(transform, set())


def _verify_transform_postconditions(world, patch):
    """A finite, parseable file is insufficient: verify the caller's actual intent."""
    for operation in patch["operations"]:
        if operation["op"] != "set_transform":
            continue
        go = world.resolve(operation["target"])
        transform = world.go_transform[go]
        data = world.transforms[transform]
        checks = []
        if "world_position" in operation:
            checks.append(("world_position", world.world_matrix(transform)[:3, 3], operation["world_position"]))
        for field, prop, axes in (("local_position", "m_LocalPosition", "xyz"),
                                  ("local_scale", "m_LocalScale", "xyz"),
                                  ("local_rotation_xyzw", "m_LocalRotation", "xyzw")):
            if field in operation:
                checks.append((field, [data[prop][axis] for axis in axes], operation[field]))
        for field, actual, expected in checks:
            if not np.allclose(actual, expected, rtol=0, atol=1e-5):
                raise WorldError(f"Postcondition failed: {operation['target']} {field}; expected {expected}, got {list(actual)}")


def plan(root, patch):
    validate_patch(patch)
    root = Path(root).resolve()
    w = World(root)
    for path, expected in patch["expected_files"].items():
        p = safe_path(root, path)
        if not p.is_file() or digest(p) != expected:
            raise WorldError(f"Stale patch: {path}. Re-inspect the current core file before editing.")
    changes, edits, impacts, engine_ops = {}, {}, [], []
    additions, resolved_objects = [], []
    world_positions, transform_fields = {}, set()
    reserved_ids = set(w.docs)
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
            for field in ("world_position", "local_position", "local_rotation_xyzw", "local_scale"):
                if field not in op:
                    continue
                key = (transform, "position" if field.endswith("position") else field)
                if key in transform_fields:
                    raise WorldError("Conflicting transform field writes; use one final value per transaction")
                transform_fields.add(key)
            fields = {"local_position": ("m_LocalPosition", 3, "xyz"),
                      "local_rotation_xyzw": ("m_LocalRotation", 4, "xyzw"),
                      "local_scale": ("m_LocalScale", 3, "xyz")}
            count = 0
            if "world_position" in op:
                world_positions[transform] = vector(op["world_position"], 3, "world_position")
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
        elif kind == "place_static_prefab":
            if version != 2:
                raise WorldError("place_static_prefab requires schema v2")
            from static_prefabs import expand
            _, docs = source(SCENE)
            added, modified, resolved = expand(w, patch, op, docs, require_identity, reserved_ids)
            for doc in added:
                docs[doc["file_id"]] = doc
            additions.extend(added)
            edits.setdefault(SCENE, set()).update(modified)
            resolved_objects.append(resolved)
            impacts.append({"operation":kind, "core_file":SCENE, "target":resolved["id"],
                            "review":"Explicit inline static copy; placement judgment remains with AI/caller."})
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
    if additions and engine_ops:
        raise WorldError("Use a separate Python transaction for inline static placement; do not mix engine operations")
    if world_positions:
        _resolve_final_positions(w, changes[SCENE][1], world_positions)
    outputs, diffs = {}, {}
    for path, ids in edits.items():
        text, docs = changes[path]
        out = text
        for i in sorted(ids, key=lambda i: docs[i]["body_start"], reverse=True):
            d = docs[i]
            body = yaml.dump({d["kind"]: d["data"]}, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=100000)
            out = out[:d["body_start"]] + body + out[d["end"]:]
        if path == SCENE:
            for d in additions:
                out += f'--- !u!{d["class_id"]} &{d["file_id"]}\n'
                out += yaml.dump({d["kind"]:d["data"]}, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=100000)
        outputs[path] = out
        diffs[path] = "".join(difflib.unified_diff(text.splitlines(True), out.splitlines(True), fromfile=path, tofile=path))
    observe_after = observation_requests(patch, w)
    for resolved in resolved_objects:
        observe_after.append({"target":resolved["id"], "radius":50, "limit":100, "native":True, "geometry":True})
    operation_before = [_operation_state(w, operation) for operation in patch["operations"]]
    pre_edit_observations = _collect_observations(w, observe_after)
    return {"schema_version": version, "protocol_version": 2,
            "transaction_id": patch.get("transaction_id"), "idempotency_key": patch.get("idempotency_key"),
            "backend": "unity" if engine_ops else "python_yaml", "dry_run": True,
            "reason": patch["reason"], "expected_files": patch["expected_files"], "diffs": diffs,
            "native_operations": [o for o in engine_ops if o["op"] == "terrain_brush"],
            "unity_operations": engine_ops, "impacts": impacts,
            "resolved_objects": resolved_objects,
            "added_scene_file_ids": [d["file_id"] for d in additions],
            "observe_after": observe_after, "acknowledgements": patch.get("acknowledgements", []),
            "operation_before": operation_before,
            "pre_edit_observations": pre_edit_observations,
            "predicted_written_files": sorted(outputs),
            "note": "Core assets change only on apply --write. Material users are sampled when >32 probes are needed; operation state reports total serialized usages. Historical Docs/*REPORT.json are not refreshed or treated as current proof."}, outputs


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
            added = set(report["added_scene_file_ids"]) if path == SCENE else set()
            if ([(d["class_id"], d["file_id"], d["kind"]) for d in before]
                    != [(d["class_id"], d["file_id"], d["kind"]) for d in after if d["file_id"] not in added]
                    or {d["file_id"] for d in after} != {d["file_id"] for d in before} | added):
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
            _verify_transform_postconditions(world, patch)
            observed = _collect_observations(world, report["observe_after"])
            resolved_by_operation = {row["operation_id"]: row for row in report["resolved_objects"]}
            operation_after = [_operation_state(world, operation, resolved_by_operation.get(operation.get("id")))
                               for operation in patch["operations"]]
        except BaseException:
            for path, data in originals.items():
                atomic_write(root/path, data)
            raise
    file_changes = {path: {"before_sha256": hashlib.sha256(data).hexdigest(),
                           "after_sha256": digest(root/path), "bytes_before": len(data),
                           "bytes_after": (root/path).stat().st_size}
                    for path, data in originals.items()}
    operation_deltas = [{"operation_id": after.get("operation_id"), "before": before, "after": after,
                         "changed": before.get("state") != after.get("state")}
                        for before, after in zip(report["operation_before"], operation_after)]
    return {**report, "dry_run": False, "written_files": {p: digest(root/p) for p in outputs},
            "written_file_changes": file_changes,
            "post_edit_observations": observed,
            "observation_deltas": _observation_deltas(report["pre_edit_observations"], observed),
            "operation_after": operation_after, "operation_deltas": operation_deltas,
            "verification": "Saved YAML identities and finite world transforms checked. Neighbourhood measurements are for AI judgment; physics, rendering and device measurements are not part of this Python authoring result."}


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


