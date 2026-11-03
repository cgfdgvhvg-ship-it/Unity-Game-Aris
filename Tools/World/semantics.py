"""Evidence-backed semantic and appearance descriptions for saved Unity core.

Names, hierarchy, geometry and materials are signals, not ground truth.  Every
classification therefore carries its evidence and confidence; ambiguous panels
remain ambiguous instead of being silently promoted to a door or window.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

import numpy as np

from unity_data import WorldError, bounds_json, compact, digest, pointer, references, safe_path


ROLE_TERMS = {
    "building": {"building", "house", "home", "hut", "cabin", "garage", "hangar", "warehouse", "tower"},
    "door": {"door", "doorway", "entrance", "entry", "gate", "hatch"},
    "window": {"window", "glass", "glazing", "pane"},
    "roof": {"roof", "rooftop", "canopy", "awning"},
    "wall": {"wall", "facade", "partition", "fence"},
    "floor": {"floor", "ground", "foundation", "slab", "deck"},
    "stairs": {"stairs", "stair", "steps", "ladder", "ramp"},
    "cabinet": {"cabinet", "cupboard", "wardrobe", "shelf", "shelves", "locker", "drawer"},
    "road": {"road", "street", "lane", "track", "path", "bridge", "runway"},
    "tree": {"tree", "trunk", "bark", "branch", "foliage", "leaf", "leaves", "pine", "cypress"},
    "rock": {"rock", "stone", "boulder", "cliff"},
    "grass": {"grass", "shrub", "bush", "groundcover", "meadow"},
    "water": {"water", "river", "lake", "ocean", "sea", "pond"},
    "prop": {"prop", "crate", "barrel", "wreck", "dish", "furniture"},
}


def _tokens(*values):
    result = set()
    for value in values:
        if not value:
            continue
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value)).casefold()
        result.update(token for token in re.split(r"[^a-z0-9]+", text) if token)
    return result


def _add(scores, evidence, role, score, reason):
    scores[role] = max(scores[role], float(score))
    evidence[role].append(reason)


def classify(name, components=(), bounds=None, parent_bounds=None, material_names=(), paths=()):
    """Return ranked roles from explicit labels first, conservative geometry second."""
    tokens = _tokens(name, *material_names, *paths)
    scores, evidence = defaultdict(float), defaultdict(list)
    for role, terms in ROLE_TERMS.items():
        matches = sorted(tokens & terms)
        if matches:
            _add(scores, evidence, role, .96, {"kind": "explicit_name_or_material_token", "tokens": matches})

    component_set = set(components)
    if "Terrain" in component_set:
        _add(scores, evidence, "terrain", .99, {"kind": "serialized_component", "component": "Terrain"})
    if "Light" in component_set:
        _add(scores, evidence, "light", .99, {"kind": "serialized_component", "component": "Light"})
    if "Camera" in component_set:
        _add(scores, evidence, "camera", .99, {"kind": "serialized_component", "component": "Camera"})

    if bounds is not None:
        size = np.asarray(bounds[1]) - np.asarray(bounds[0])
        sx, sy, sz = map(float, size)
        horizontal_min, horizontal_max = min(sx, sz), max(sx, sz)
        thin_y = sy <= max(.35, horizontal_min * .16)
        thin_horizontal = horizontal_min <= max(.35, horizontal_max * .12)
        vertical_panel = 1.2 <= sy <= 6 and thin_horizontal
        relative_height = None
        if parent_bounds is not None and parent_bounds[1][1] - parent_bounds[0][1] > 1e-6:
            center_y = (bounds[0][1] + bounds[1][1]) / 2
            relative_height = float((center_y-parent_bounds[0][1])/(parent_bounds[1][1]-parent_bounds[0][1]))
        if thin_y and horizontal_min >= .5:
            role = "roof" if relative_height is not None and relative_height >= .72 else "floor_or_roof_slab"
            _add(scores, evidence, role, .62 if role == "roof" else .42,
                 {"kind": "geometry_heuristic", "size_m": size.tolist(), "relative_height": relative_height})
        if vertical_panel:
            _add(scores, evidence, "wall_or_vertical_panel", .5,
                 {"kind": "geometry_heuristic", "size_m": size.tolist()})
            panel_width = horizontal_max
            if .35 <= panel_width <= 4 and 1.4 <= sy <= 3.8:
                _add(scores, evidence, "door_or_window_panel", .45,
                     {"kind": "ambiguous_geometry_heuristic", "size_m": size.tolist(),
                      "note": "Geometry alone cannot distinguish a door, closed window or decorative panel"})
        if sy <= .5 and horizontal_max >= 4 and horizontal_min >= 1:
            _add(scores, evidence, "road_or_floor_surface", .38,
                 {"kind": "geometry_heuristic", "size_m": size.tolist()})

    if not scores:
        return {"primary_role": "unknown", "confidence": 0.0, "candidates": [],
                "evidence": [], "status": "unclassified",
                "note": "No reliable saved label/component/geometry signal identifies this part"}
    ranked = sorted(scores, key=lambda role: (-scores[role], role))
    primary = ranked[0]
    return {
        "primary_role": primary,
        "confidence": scores[primary],
        "candidates": [{"role": role, "confidence": scores[role], "evidence": evidence[role]} for role in ranked[:5]],
        "evidence": evidence[primary],
        "status": "labelled" if scores[primary] >= .9 else "inferred",
        "note": "Roles below 0.9 are hypotheses for AI review, not authored semantic truth",
    }


def _union(items):
    if not items:
        return None
    return [np.min([item[0] for item in items], axis=0), np.max([item[1] for item in items], axis=0)]


def _script_bindings(w, go):
    ignored = {"m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance", "m_PrefabAsset",
               "m_GameObject", "m_Enabled", "m_EditorHideFlags", "m_Script", "m_Name", "m_EditorClassIdentifier"}
    rows = []
    for component in w.components(go):
        if component["kind"] != "MonoBehaviour":
            continue
        data = component["data"]
        script = w.reference(data.get("m_Script", {}))
        source = None
        path = script.get("path")
        if path:
            p = safe_path(w.root, path)
            if p.is_file() and not pointer(p) and p.suffix.lower() == ".cs" and p.stat().st_size <= 2*1024*1024:
                text = p.read_text(errors="replace")
                w.read_files.add(path)
                classes = re.findall(r"\b(?:class|struct)\s+([A-Za-z_][A-Za-z0-9_]*)", text)
                methods = re.findall(r"\b(?:public|private|protected|internal)?\s*(?:static\s+)?[A-Za-z_][A-Za-z0-9_<>,\[\]? ]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)
                source = {"sha256": digest(p), "classes": classes[:20], "methods": list(dict.fromkeys(methods))[:50],
                          "lines": len(text.splitlines()),
                          "evidence": "static source symbols only; runtime branches/state are not executed"}
        rows.append({"component_file_id": component["file_id"], "enabled": bool(data.get("m_Enabled", 1)),
                     "script": script, "editor_class_identifier": data.get("m_EditorClassIdentifier"),
                     "serialized_fields": {key: compact(value) for key, value in data.items() if key not in ignored},
                     "source_summary": source,
                     "evidence": "serialized MonoBehaviour fields plus optional static C# symbols; use Unity/runtime tests for behavior"})
    return rows


def _part(w, go, root_bounds, slots_by_node):
    own, missing = w.own_bounds(go)
    own_bounds = _union(own)
    collider_bounds, collider_missing = w.aggregate_collider_bounds(go)
    # A leaf collider aggregate is its own collider. A container's aggregate is
    # useful context but is not mislabeled as the part's renderer geometry.
    chosen = own_bounds if own_bounds is not None else collider_bounds if not w.children[go] else None
    transform = w.go_transform.get(go)
    matrix = w.world_matrix(transform) if transform is not None else None
    slots = slots_by_node.get(w.stable_id(go), [])
    material_names = [slot["material"].get("name") for slot in slots]
    paths = [slot["material"].get("path") for slot in slots]
    semantic = classify(w.gos[go].get("m_Name"), [c["kind"] for c in w.components(go)],
                        chosen, root_bounds, material_names, paths)
    parent_transform = w.transforms.get(w.transforms[transform].get("m_Father", {}).get("fileID", 0), {}) if transform else {}
    parent_go = parent_transform.get("m_GameObject", {}).get("fileID")
    return {
        "id": w.stable_id(go), "name": w.gos[go].get("m_Name"),
        "parent_id": w.stable_id(parent_go) if parent_go else None,
        "child_ids": [w.stable_id(child) for child in w.children[go]],
        "world_position_m": matrix[:3, 3].tolist() if matrix is not None else None,
        "world_axis_scale": np.linalg.norm(matrix[:3, :3], axis=0).tolist() if matrix is not None else None,
        "components": [c["kind"] for c in w.components(go)],
        "renderer_or_leaf_collider_bounds": bounds_json(chosen),
        "renderer_bounds_incomplete": sorted(set(missing)),
        "collider_bounds": bounds_json(collider_bounds),
        "collider_bounds_incomplete": collider_missing,
        "semantic": semantic, "material_slots": slots, "script_bindings": _script_bindings(w, go),
    }


def describe(w, request):
    target = request.get("target")
    if not isinstance(target, str):
        raise WorldError("describe requires a stable target")
    if target.startswith("prefab-instance:"):
        matches = [row for row in w.prefab_instances(resolve_source=True,
                                                     texture_analysis=request.get("texture_analysis", False),
                                                     override_offset=request.get("override_offset", 0),
                                                     override_limit=request.get("override_limit", 100))
                   if row["id"] == target]
        if len(matches) != 1:
            raise WorldError("Expected one serialized prefab instance")
        row = matches[0]
        return {"target": row, "parts": {"total": 0, "offset": 0, "items": [], "next_offset": None},
                "coverage": "Serialized PrefabInstance source and overrides only; use materialized source dependency or Unity export for exact imported hierarchy",
                "source_fingerprint": w.fingerprint()}
    go = w.resolve(target)
    offset, limit = request.get("offset", 0), request.get("limit", 100)
    depth = request.get("dependency_depth", 2)
    texture_analysis = request.get("texture_analysis", False)
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 500:
        raise WorldError("describe offset >=0 and limit 1..500 required")
    if not isinstance(texture_analysis, bool):
        raise WorldError("texture_analysis must be boolean")
    root_bounds, root_missing = w.aggregate_bounds(go)
    slots = w.material_slots(go, texture_analysis)
    slots_by_node = defaultdict(list)
    for slot in slots:
        slots_by_node[slot["node_id"]].append(slot)
    descendants = list(w.descendants(go))
    items = [_part(w, node, root_bounds, slots_by_node) for node in descendants[offset:offset+limit]]
    material_names = [slot["material"].get("name") for slot in slots]
    material_paths = [slot["material"].get("path") for slot in slots]
    root_semantic = classify(w.gos[go].get("m_Name"), [c["kind"] for c in w.components(go)],
                             root_bounds, None, material_names, material_paths)
    roots = []
    for node in descendants:
        for component in w.components(node):
            for ref in references(component["data"]):
                path = w.guid_paths.get(str(ref.get("guid", "")))
                if path:
                    roots.append(path)
    dependencies = w.dependency_graph(list(dict.fromkeys(roots)), depth)
    logic = []
    for node in descendants:
        for binding in _script_bindings(w, node):
            logic.append({"node_id": w.stable_id(node), "node_name": w.gos[node].get("m_Name"), **binding})
    dimensions = bounds_json(root_bounds)
    if dimensions:
        sx, sy, sz = dimensions["size_m"]
        dimensions.update(height_m=sy, footprint_xz_m=[sx, sz], footprint_area_m2=sx*sz,
                          aabb_volume_m3=sx*sy*sz,
                          evidence="world renderer AABB union; not exact occupied mesh volume")
    return {
        "target": {
            "id": w.stable_id(go), "name": w.gos[go].get("m_Name"),
            "world_position_m": w.world_matrix(w.go_transform[go])[:3, 3].tolist(),
            "dimensions": dimensions, "bounds_incomplete": root_missing,
            "semantic": root_semantic,
            "editability": {"transform_and_scale": "python_yaml_inline_scene_object",
                            "materials": "shared_asset; inspect usages before editing",
                            "geometry_shape": "source mesh/prefab or Unity authoring required"},
        },
        "parts": {"total": len(descendants), "offset": offset, "items": items,
                  "next_offset": offset+limit if offset+limit < len(descendants) else None},
        "appearance": {"material_slot_count": len(slots), "slots": slots,
                       "texture_analysis_requested": texture_analysis,
                       "rendered_pixels": False,
                       "note": "Texture statistics describe source rasters; Unity capture is required for lit appearance and stains at exact UV positions"},
        "logic": {"binding_count": len(logic), "bindings": logic[:200], "truncated": len(logic) > 200,
                  "note": "Serialized fields and static symbols are not executed runtime behavior"},
        "dependencies": dependencies,
        "source_fingerprint": w.fingerprint(),
        "coverage": {"inline_descendants": len(descendants), "parts_returned": len(items),
                     "parts_complete": offset+len(items) >= len(descendants),
                     "missing_geometry_reasons": root_missing,
                     "semantic_truth": "labels are exact strings; inferred roles retain confidence/evidence"},
    }
