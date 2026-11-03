"""Context capsules generated from the current saved core.

The functions here measure relationships.  They intentionally do not decide
whether a placement is artistically or strategically correct; that remains the
caller's decision.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from terrain import NativeTerrain
from unity_data import World, WorldError, bounds_json, digest, pointer, safe_path, xyz


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WorldError(f"{name} must be a finite number")
    return float(value)


def _distance_to_bounds(point, bounds):
    p = np.asarray(point, dtype=float)
    low, high = bounds
    closest = np.minimum(np.maximum(p, low), high)
    return float(np.linalg.norm(p - closest)), closest.tolist()


def _overlap(a, b):
    low = np.maximum(a[0], b[0])
    high = np.minimum(a[1], b[1])
    size = high - low
    if np.any(size <= 0):
        return None
    return {"min_m": low.tolist(), "max_m": high.tolist(), "size_m": size.tolist(),
            "volume_m3": float(np.prod(size))}


def _observation_hash(source_fingerprint, payload):
    raw = json.dumps([source_fingerprint, payload], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def inspect(w, request):
    radius = _finite(request.get("radius", 50), "radius")
    if not 0 < radius <= 500:
        raise WorldError("inspect radius must be >0 and <=500 metres")
    limit = request.get("limit", 100)
    if type(limit) is not int or not 1 <= limit <= 500:
        raise WorldError("inspect limit must be 1..500")
    include_native = request.get("native", True)
    geometry = request.get("geometry", True)
    if not isinstance(include_native, bool) or not isinstance(geometry, bool):
        raise WorldError("native and geometry must be boolean")

    target = request.get("target")
    target_go = None
    target_native = None
    native = NativeTerrain(w)
    if target:
        if not isinstance(target, str):
            raise WorldError("inspect target must be a stable id")
        if target.startswith("terrain:"):
            target_native = native.find_instance(target)
            center = list(target_native["position_m"])
            target_record = target_native
        else:
            target_go = w.resolve(target)
            target_record = w.object(target_go, geometry)
            center = list(target_record["world_position_m"])
    else:
        if "x" not in request or "z" not in request:
            raise WorldError("inspect requires target or x/z")
        x, z = _finite(request["x"], "x"), _finite(request["z"], "z")
        if request.get("y") is None:
            sample = native.height(x, z)
            y = sum(s["height_m"] for s in sample["samples"]) / len(sample["samples"])
        else:
            y = _finite(request["y"], "y")
        center = [x, y, z]
        target_record = {"id": None, "kind": "coordinate", "world_position_m": center}

    terrain_relation = None
    try:
        terrain_relation = native.height(center[0], center[2])
        heights = [s["height_m"] for s in terrain_relation["samples"]]
        terrain_relation["point_y_m"] = center[1]
        terrain_relation["point_minus_ground_m"] = center[1] - sum(heights) / len(heights)
    except (WorldError, ImportError) as error:
        terrain_relation = {"status": "unavailable", "reason": str(error)}

    candidates = []
    skipped = []
    unavailable_geometry = []
    excluded = set(w.descendants(target_go)) if target_go is not None else set()
    target_basis = w.world_rotation(w.go_transform[target_go]) if target_go is not None else np.eye(3)
    if target_native is not None:
        yaw = math.radians(target_native["yaw_degrees"])
        target_basis = np.array([[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0],
                                 [-math.sin(yaw), 0, math.cos(yaw)]])
    for go in w.gos:
        if go in excluded or go not in w.go_transform:
            continue
        try:
            position = w.world_matrix(w.go_transform[go])[:3, 3]
        except WorldError as error:
            skipped.append({"id": w.stable_id(go), "reason": str(error)})
            continue
        delta = position - np.asarray(center)
        distance = float(np.linalg.norm(delta))
        bounds, incomplete = w.aggregate_bounds(go) if geometry else (None, [])
        collider_bounds, collider_incomplete = w.aggregate_collider_bounds(go) if geometry else (None, [])
        shape_kinds={"MeshFilter","SkinnedMeshRenderer","BoxCollider","MeshCollider","SphereCollider","CapsuleCollider"}
        container_only=bool(w.children[go]) and not any(c["kind"] in shape_kinds for c in w.components(go))
        if container_only:
            # A group's union AABB may span a whole island, including empty air.
            # It is not an obstacle or a supporting surface. Child shapes are
            # indexed separately and retain their own identities.
            bounds,collider_bounds=None,None
        if geometry and not container_only and bounds is None and collider_bounds is None and any(c["kind"] in shape_kinds for c in w.components(go)):
            unavailable_geometry.append({"id":w.stable_id(go),"name":w.gos[go].get("m_Name"),"reasons":sorted(set(incomplete+collider_incomplete))})
        bound_kind = "renderer_mesh_aabb" if bounds is not None else "saved_collider_envelope" if collider_bounds is not None else "unavailable"
        if bounds is None:bounds=collider_bounds
        bounds_distance = _distance_to_bounds(center, bounds)[0] if bounds is not None else distance
        if min(distance, bounds_distance) > radius: continue
        row = {"id": w.stable_id(go), "name": w.gos[go].get("m_Name"),
               "world_position_m": position.tolist(), "relative_m": delta.tolist(),
               "distance_m": distance, "horizontal_distance_m": float(np.linalg.norm(delta[[0, 2]])),
               "world_forward":w.world_rotation(w.go_transform[go])[:,2].tolist(),
               "relative_in_target_axes_m":(target_basis.T @ delta).tolist(),
               "world_axis_scale":np.linalg.norm(w.world_matrix(w.go_transform[go])[:3,:3],axis=0).tolist(),
               "container_only":container_only,
               "components": [c["kind"] for c in w.components(go)]}
        if geometry:
            row["bounds"] = bounds_json(bounds)
            row["bounds_incomplete"] = incomplete
            row["bounds_source"] = bound_kind
            row["saved_collider_bounds"] = bounds_json(collider_bounds)
            row["collider_bounds_incomplete"] = collider_incomplete
            if bounds is not None:
                row["distance_to_bounds_m"], row["closest_bounds_point_m"] = _distance_to_bounds(center, bounds)
                row["contains_inspection_point"] = bool(np.all(np.asarray(center) >= bounds[0]) and np.all(np.asarray(center) <= bounds[1]))
                row["_raw_bounds"] = bounds
        candidates.append(row)
    candidates.sort(key=lambda row: (row.get("distance_to_bounds_m", row["distance_m"]), row["id"]))
    scene_candidate_total = len(candidates)
    candidates = candidates[:limit]

    target_bounds = None
    if target_go is not None and geometry:
        target_bounds, _ = w.aggregate_bounds(target_go)
    supports, overlaps = [], []
    if target_bounds is not None:
        bottom = float(target_bounds[0][1])
        if terrain_relation.get("samples"):
            ground = sum(s["height_m"] for s in terrain_relation["samples"]) / len(terrain_relation["samples"])
            supports.append({"kind": "terrain_height_grid", "surface_y_m": ground,
                             "target_bottom_minus_surface_m": bottom-ground,
                             "evidence": "native_decoded_bilinear_not_physics"})
        for row in candidates:
            bounds = row.pop("_raw_bounds", None)
            if bounds is None:
                continue
            hit = _overlap(target_bounds, bounds)
            if hit:
                overlaps.append({"object": {k: row[k] for k in ("id", "name")}, "intersection": hit,
                                 "evidence": "geometry_estimate_aabb"})
            horizontal = (target_bounds[1][0] >= bounds[0][0] and target_bounds[0][0] <= bounds[1][0]
                          and target_bounds[1][2] >= bounds[0][2] and target_bounds[0][2] <= bounds[1][2])
            if horizontal:
                gap = bottom-float(bounds[1][1])
                if abs(gap) <= max(5.0, radius*.1):
                    supports.append({"kind": row["bounds_source"]+"_top", "object": {k: row[k] for k in ("id", "name")},
                                     "surface_y_m": float(bounds[1][1]), "target_bottom_minus_surface_m": gap,
                                     "evidence": "geometry_estimate_aabb_not_physics"})
    else:
        for row in candidates:
            row.pop("_raw_bounds", None)
    supports.sort(key=lambda r: abs(r["target_bottom_minus_surface_m"]))

    native_rows = []
    native_errors = []
    native_candidate_total = 0
    if include_native:
        try:
            for row in native.instances():
                if target_native and row["id"] == target_native["id"]:
                    continue
                delta = np.asarray(row["position_m"]) - np.asarray(center)
                distance = float(np.linalg.norm(delta))
                if distance <= radius:
                    native_rows.append({**row, "relative_m": delta.tolist(), "distance_m": distance,
                                        "relative_in_target_axes_m":(target_basis.T @ delta).tolist(),
                                        "horizontal_distance_m": float(np.linalg.norm(delta[[0, 2]]))})
            native_rows.sort(key=lambda row: (row["distance_m"], row["id"]))
            native_candidate_total = len(native_rows)
            native_rows = native_rows[:limit]
            profiles = {}
            for row in native_rows:
                path = row.get("path")
                if path not in profiles:
                    try:
                        if not path: raise WorldError("Prototype metadata is unavailable")
                        prototype = World(w.root, path)
                        w.read_files.update(prototype.read_files)
                        colliders = []
                        for component in prototype.docs.values():
                            if component["kind"] not in ("CapsuleCollider", "BoxCollider", "SphereCollider"):continue
                            data=component["data"];tr=prototype.go_transform[data["m_GameObject"]["fileID"]]
                            colliders.append({"kind":component["kind"],"local_radius_m":data.get("m_Radius"),
                                              "local_height_m":data.get("m_Height"),"local_size":data.get("m_Size"),
                                              "prototype_axis_scale":np.linalg.norm(prototype.world_matrix(tr)[:3,:3],axis=0).tolist()})
                        profiles[path]={"status":"serialized_colliders","colliders":colliders}
                    except (WorldError, OSError, KeyError) as error:
                        profiles[path]={"status":"unavailable","reason":str(error)}
                row["prototype_geometry"]=profiles[path]
                row["collider_diameter_estimates_m"]=[2*c["local_radius_m"]*row["width_scale"]*max(c["prototype_axis_scale"][0],c["prototype_axis_scale"][2])
                    for c in profiles[path].get("colliders",[]) if c.get("local_radius_m") is not None]
                row["box_collider_size_estimates_m"]=[(xyz(c["local_size"])*np.asarray(c["prototype_axis_scale"])*[row["width_scale"],row["height_scale"],row["width_scale"]]).tolist()
                    for c in profiles[path].get("colliders",[]) if c.get("local_size")]
                row["diameter_evidence"]="saved_collider_envelope; visible trunk thickness is not established"
        except (WorldError, ImportError) as error:
            native_errors.append(str(error))

    source = w.fingerprint()
    facts = []
    for relation in supports[:10]:
        payload = {"kind": "support_relation", **relation}
        observation_hash = _observation_hash(source["sha256"], payload)
        facts.append({"id": "obs:"+observation_hash[:24], "observation_hash": observation_hash, **payload,
                      "decision": "AI/caller decides whether this relationship is intended"})
    for relation in overlaps[:25]:
        payload = {"kind": "aabb_overlap", **relation}
        observation_hash = _observation_hash(source["sha256"], payload)
        facts.append({"id": "obs:"+observation_hash[:24], "observation_hash": observation_hash, **payload,
                      "decision": "AI/caller decides whether this overlap is intended; use Unity physics/capture for exact geometry"})

    return {
        "center_world_m": center,
        "radius_m": radius,
        "target": target_record,
        "terrain_relation": terrain_relation,
        "nearby_scene_objects": candidates,
        "nearby_native_instances": native_rows,
        "grass_detail_context": _grass_context(native,center,include_native),
        "terrain_under_footprint": _footprint_context(native,target_bounds) if include_native and target_bounds is not None else {"status":"not_requested_or_no_target_bounds"},
        "support_candidates": supports[:25],
        "overlap_candidates": overlaps[:25],
        "observations": facts,
        "coverage": {
            "inline_scene_objects_indexed": len(w.gos),
            "scene_candidates_returned": len(candidates),
            "scene_candidates_total": scene_candidate_total,
            "scene_candidates_truncated": scene_candidate_total>limit,
            "native_candidates_returned": len(native_rows),
            "native_candidates_total": native_candidate_total,
            "native_candidates_truncated": native_candidate_total>limit,
            "skipped_scene_objects": skipped[:25],
            "scene_shape_bounds_unavailable_count":len(unavailable_geometry),
            "scene_shape_bounds_unavailable_sample":unavailable_geometry[:25],
            "neighbour_query_limit":"Origin distance or available shape envelopes; an object with unavailable geometry and a distant pivot may be missed",
            "native_errors": native_errors,
            "physics_tested": False,
            "render_tested": False,
            "bounds_are_renderer_mesh_aabb": geometry and all(r.get("bounds_source")!="saved_collider_envelope" for r in candidates),
            "bounds_evidence":"See each bounds_source; renderer and saved-collider AABBs are distinct estimates",
        },
        "source_fingerprint": source,
        "decision_owner":"AI/caller; tool reports measurements and never accepts/rejects a design",
        "relative_axes":"target right/up/forward; coordinate-only inspections use world X/Y/Z",
        "next": "Use Unity engine observe/probe/capture when exact collider, support, entrance or visible appearance evidence is required",
    }


def _grass_context(native,center,enabled):
    if not enabled:return {"status":"not_requested"}
    try:
        return native.detail_context(center[0],center[2])
    except (WorldError, ImportError, OSError) as error:
        return {"status":"unavailable","reason":str(error)}


def _footprint_context(native,bounds):
    samples=[]
    try:
        for x in np.linspace(bounds[0][0],bounds[1][0],3):
            for z in np.linspace(bounds[0][2],bounds[1][2],3):
                result=native.height(float(x),float(z))
                samples.append({"world_xz_m":[float(x),float(z)],"terrain":result,
                                "bounds_bottom_minus_ground_m":[float(bounds[0][1])-r["height_m"] for r in result["samples"]]})
        return {"samples":samples,"evidence":"nine bilinear terrain samples under the renderer AABB; not exact mesh-foot contact", "decision_owner":"AI/caller"}
    except (WorldError, ImportError, OSError) as error:
        return {"status":"unavailable","reason":str(error),"samples_completed":samples}


def usages(w, request):
    path = request.get("path")
    if not isinstance(path, str):
        raise WorldError("usages requires an asset path")
    safe_path(w.root, path)
    meta = w.root / (path + ".meta")
    if not meta.is_file():
        raise WorldError("Asset metadata is missing")
    match = re.search(r"(?m)^guid: ([0-9a-f]{32})$", meta.read_text(errors="replace"))
    if not match:
        raise WorldError("Asset metadata has no GUID")
    guid = match[1]
    hits, skipped = [], []
    suffixes = {".unity", ".prefab", ".mat", ".asset", ".controller", ".overridecontroller", ".playable", ".lighting", ".preset"}
    for candidate in (w.root / "Assets").rglob("*"):
        if not candidate.is_file() or candidate.suffix.lower() not in suffixes or candidate == meta:
            continue
        try:
            if candidate.stat().st_size > 32*1024*1024 or pointer(candidate):
                skipped.append(candidate.relative_to(w.root).as_posix())
                continue
            raw = candidate.read_bytes()
            count = raw.count(guid.encode())
            if count:
                rel = candidate.relative_to(w.root).as_posix()
                w.read_files.add(rel)
                hits.append({"path": rel, "reference_count": count, "sha256": digest(candidate)})
        except (OSError, UnicodeError):
            skipped.append(candidate.relative_to(w.root).as_posix())
    hits.sort(key=lambda row: (-row["reference_count"], row["path"]))
    return {"asset": path, "guid": guid, "text_serialized_usages": hits,
            "total_reference_occurrences": sum(r["reference_count"] for r in hits),
            "coverage": "Text-serialized project assets only; Unity AssetDatabase dependency export is required for importer/binary-only references",
            "skipped_binary_or_large_sample": skipped[:50], "source_fingerprint": w.fingerprint()}


RUNTIME_TERMS = re.compile(r"(Update\s*\(|LateUpdate\s*\(|FixedUpdate\s*\(|LoadScene|Addressables|Resources\.Load|targetFrameRate|treeDistance|detailObjectDistance|lodBias|stream|cull|Profiler|Memory|Application\.lowMemory)", re.I)


def runtime(root, request):
    root = Path(root).resolve()
    search = str(request.get("search", "")).casefold()
    limit = request.get("limit", 100)
    offset = request.get("offset", 0)
    if type(limit) is not int or type(offset) is not int or not 1 <= limit <= 500 or offset < 0:
        raise WorldError("runtime offset >=0 and limit 1..500 required")
    rows = []
    candidates = list((root / "Assets").rglob("*.cs"))
    candidates += [p for p in (root / "ProjectSettings").glob("*") if p.is_file()] if (root/"ProjectSettings").exists() else []
    for path in candidates:
        try:
            if path.stat().st_size > 2*1024*1024:
                continue
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if (search and search not in line.casefold()) or (not search and not RUNTIME_TERMS.search(line)):
                    continue
                rows.append({"path": path.relative_to(root).as_posix(), "line": number, "text": line.strip()[:500]})
        except OSError:
            pass
    rows.sort(key=lambda row: (row["path"], row["line"]))
    return {"total": len(rows), "offset": offset, "items": rows[offset:offset+limit],
            "next_offset": offset+limit if offset+limit < len(rows) else None,
            "evidence": "Static source/config evidence only. Actual load time, FPS, memory and crash behavior require Unity/device measurements."}
