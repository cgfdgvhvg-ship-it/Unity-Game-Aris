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
from unity_data import WorldError, bounds_json, digest, pointer, safe_path


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
    for go in w.gos:
        if go == target_go or go not in w.go_transform:
            continue
        try:
            position = w.world_matrix(w.go_transform[go])[:3, 3]
        except WorldError as error:
            skipped.append({"id": w.stable_id(go), "reason": str(error)})
            continue
        delta = position - np.asarray(center)
        distance = float(np.linalg.norm(delta))
        if distance > radius:
            continue
        row = {"id": w.stable_id(go), "name": w.gos[go].get("m_Name"),
               "world_position_m": position.tolist(), "relative_m": delta.tolist(),
               "distance_m": distance, "horizontal_distance_m": float(np.linalg.norm(delta[[0, 2]])),
               "components": [c["kind"] for c in w.components(go)]}
        if geometry:
            bounds, incomplete = w.aggregate_bounds(go)
            row["bounds"] = bounds_json(bounds)
            row["bounds_incomplete"] = incomplete
            if bounds is not None:
                row["distance_to_bounds_m"], row["closest_bounds_point_m"] = _distance_to_bounds(center, bounds)
                row["contains_inspection_point"] = bool(np.all(np.asarray(center) >= bounds[0]) and np.all(np.asarray(center) <= bounds[1]))
                row["_raw_bounds"] = bounds
        candidates.append(row)
    candidates.sort(key=lambda row: (row.get("distance_to_bounds_m", row["distance_m"]), row["id"]))
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
                    supports.append({"kind": "renderer_aabb_top", "object": {k: row[k] for k in ("id", "name")},
                                     "surface_y_m": float(bounds[1][1]), "target_bottom_minus_surface_m": gap,
                                     "evidence": "geometry_estimate_aabb_not_physics"})
    else:
        for row in candidates:
            row.pop("_raw_bounds", None)
    supports.sort(key=lambda r: abs(r["target_bottom_minus_surface_m"]))

    native_rows = []
    native_errors = []
    if include_native:
        try:
            for row in native.instances():
                if target_native and row["id"] == target_native["id"]:
                    continue
                delta = np.asarray(row["position_m"]) - np.asarray(center)
                distance = float(np.linalg.norm(delta))
                if distance <= radius:
                    native_rows.append({**row, "relative_m": delta.tolist(), "distance_m": distance,
                                        "horizontal_distance_m": float(np.linalg.norm(delta[[0, 2]]))})
            native_rows.sort(key=lambda row: (row["distance_m"], row["id"]))
            native_rows = native_rows[:limit]
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
        "support_candidates": supports[:25],
        "overlap_candidates": overlaps[:25],
        "observations": facts,
        "coverage": {
            "inline_scene_objects_indexed": len(w.gos),
            "scene_candidates_returned": len(candidates),
            "native_candidates_returned": len(native_rows),
            "skipped_scene_objects": skipped[:25],
            "native_errors": native_errors,
            "physics_tested": False,
            "render_tested": False,
            "bounds_are_renderer_mesh_aabb": geometry,
        },
        "source_fingerprint": source,
        "next": "Use Unity engine observe/probe/capture when exact collider, support, entrance or visible appearance evidence is required",
    }


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
