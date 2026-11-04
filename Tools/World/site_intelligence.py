"""Evidence-scoped, AI-readable site capsule built from an existing inspect query.

Never describe an unmaterialized mesh, a non-returned page, a material tint,
or a guessed semantic role as established visible/physical reality.
"""
from __future__ import annotations

import math
from collections import Counter


def _direction(delta):
    x, z = float(delta[0]), float(delta[2])
    if math.hypot(x, z) < 1e-6:
        return "overlapping_xz"
    names = ("+Z", "+X+Z", "+X", "+X-Z", "-Z", "-X-Z", "-X", "-X+Z")
    sector = int((math.degrees(math.atan2(x, z)) + 22.5) // 45) % 8
    return names[sector]


def _colors(row):
    """Return exact saved material tints/references, not rendered pixel colors."""
    out = []
    slots = (row.get("appearance") or {}).get("material_slots") or []
    for slot in slots[:48]:
        mat = slot.get("material") or {}
        if not isinstance(mat, dict):
            continue
        colors = [
            {"property": c.get("property"), "rgba": c.get("rgba")}
            for c in mat.get("color_properties", [])
            if c.get("rgba") is not None
        ]
        textures = [
            {"property": t.get("property"),
             "path": (t.get("reference") or {}).get("path"),
             "status": (t.get("source") or {}).get("status")}
            for t in mat.get("textures", [])
        ]
        out.append({
            "node_id": slot.get("node_id"), "node_name": slot.get("node_name"),
            "slot_index": slot.get("slot_index"), "material": mat.get("name"),
            "submesh_geometry": slot.get("submesh_geometry"),
            "material_path": mat.get("path"), "serialized_rgba": colors[:24],
            "texture_references": textures[:24],
            "color_evidence": "saved material properties; not final visible pixels",
        })
    return out


def site_summary(inspection):
    """Summarize a coordinate/target inspection without inventing missing evidence."""
    coverage = inspection.get("coverage") or {}
    center = inspection.get("center_world_m") or [0, 0, 0]
    scene = inspection.get("nearby_scene_objects") or []
    native = inspection.get("nearby_native_instances") or []
    native_summary = inspection.get("native_radius_summary") or {}
    nearest_roles = {}
    page_role_counts = Counter()
    directions = Counter()
    object_records = []
    for item in scene:
        semantic = item.get("semantic") or {}
        role = semantic.get("primary_role") or "unknown"
        page_role_counts[role] += 1
        direction = _direction(item.get("relative_m") or [0, 0, 0])
        directions[direction] += 1
        distance = item.get("distance_to_bounds_m", item.get("distance_m"))
        record = {
            "id": item.get("id"), "name": item.get("name"), "role": role,
            "semantic_confidence": semantic.get("confidence", 0),
            "semantic_status": semantic.get("status", "unclassified"),
            "position_m": item.get("world_position_m"),
            "relative_m": item.get("relative_m"),
            "direction_world_xz": direction,
            "distance_m": distance,
            "world_axis_scale": item.get("world_axis_scale"),
            "bounds": item.get("bounds"),
            "bounds_source": item.get("bounds_source"),
            "bounds_incomplete": item.get("bounds_incomplete", []),
            "material_surfaces": _colors(item),
        }
        object_records.append(record)
        if role not in nearest_roles or (
            distance is not None and (nearest_roles[role].get("distance_m") is None or
                                      distance < nearest_roles[role]["distance_m"])
        ):
            nearest_roles[role] = {
                "id": record["id"], "name": record["name"],
                "distance_m": distance, "direction_world_xz": direction,
                "semantic_confidence": record["semantic_confidence"],
                "evidence_scope": "returned scene page only",
            }
    native_details = []
    for item in native:
        native_details.append({
            "id": item.get("id"), "category": item.get("category"),
            "prototype_path": item.get("path"), "position_m": item.get("position_m"),
            "distance_m": item.get("distance_m"),
            "direction_world_xz": _direction(item.get("relative_m") or [0, 0, 0]),
            "width_scale": item.get("width_scale"),
            "height_scale": item.get("height_scale"),
            "estimated_renderer_size_m": item.get("estimated_renderer_size_m"),
            "collider_diameter_estimates_m": item.get("collider_diameter_estimates_m"),
            "color": item.get("color"), "lightmap_color": item.get("lightmap_color"),
            "geometry_status": (item.get("prototype_geometry") or {}).get("status"),
        })

    scene_complete = (coverage.get("scene_next_offset") is None and
                      not coverage.get("scene_candidates_truncated", False))
    native_complete = (coverage.get("native_next_offset") is None and
                       not coverage.get("native_candidates_truncated", False) and
                       not coverage.get("native_errors") and
                       native_summary.get("evidence_scope") != "not_requested")
    geometry_issues = coverage.get("scene_shape_bounds_unavailable_count", 0)
    skipped = coverage.get("skipped_scene_objects") or []
    unresolved_prefabs = (inspection.get("unresolved_serialized_prefab_instances") or {}).get("total", 0)
    terrain = inspection.get("terrain_relation") or {}
    complete_saved_index = bool(
        scene_complete and native_complete and not geometry_issues and
        not skipped and not unresolved_prefabs and terrain.get("status") != "unavailable"
    )
    return {
        "center_world_m": center,
        "radius_m": inspection.get("radius_m"),
        "ground": {
            "terrain_relation": terrain,
            "grass_detail_context": inspection.get("grass_detail_context"),
            "target_footprint_terrain": inspection.get("terrain_under_footprint"),
            "evidence": "native sampled terrain and saved detail patches, not physics or exact grass blades",
        },
        "scene": {
            "total_in_radius": coverage.get("scene_candidates_total"),
            "count_by_semantic_role_on_page": dict(sorted(page_role_counts.items())),
            "counts_are_page_scoped": True,
            "directions_on_page": dict(sorted(directions.items())),
            "nearest_by_role_on_page": nearest_roles,
            "objects_on_page": object_records,
        },
        "native": {
            "total_in_radius": coverage.get("native_candidates_total"),
            "counts_by_category_in_full_radius": native_summary.get("counts_by_category"),
            "scale_ranges_in_full_radius": native_summary.get("scale_ranges"),
            "instances_on_page": native_details,
            "diameters_are_collider_estimates_not_visible_trunk_thickness": True,
        },
        "target": inspection.get("target"),
        "support_candidates": inspection.get("support_candidates", []),
        "overlap_candidates": inspection.get("overlap_candidates", []),
        "coverage": {
            "scene_page_complete": scene_complete, "native_page_complete": native_complete,
            "scene_next_offset": coverage.get("scene_next_offset"),
            "native_next_offset": coverage.get("native_next_offset"),
            "missing_scene_geometry_count": geometry_issues,
            "skipped_scene_count_sampled": len(skipped),
            "unresolved_prefab_sources_global": unresolved_prefabs,
            "native_errors": coverage.get("native_errors", []),
            "serialized_candidate_coverage_complete": complete_saved_index,
            "can_assert_no_other_serialized_obstacles": False,
            "clearance_note": (
                "Saved indexed candidates are covered inside this radius; this is never proof of free physical space"
                if complete_saved_index else
                "Incomplete pages, unknown geometry, unresolved prefabs or native data prohibit a clear-space claim"
            ),
            "scene_index_count": coverage.get("inline_scene_objects_indexed"),
            "nearest_roles_are_page_scoped": True,
            "free_space_verified_by_physics": False,
            "native_category_counts_are_radius_wide": True,
        },
        "source_fingerprint": inspection.get("source_fingerprint"),
        "interpretation": {
            "placements": "AI/caller decides; this report never auto-selects a location",
            "colors": "RGBA values are material tints or native tint, not UV/shader/lighted surface colors",
            "geometry": "Mesh/collider world AABBs estimate extent; not visible topology or physical contact",
            "labels": "Names/material labels are evidence; low-confidence roles remain hypotheses",
            "followup": "Follow scene_next_offset and native_next_offset, then describe particular objects and request Unity capture/physics when needed",
        },
    }
