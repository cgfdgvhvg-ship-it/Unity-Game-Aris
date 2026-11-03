"""Reproducible read-only context audit; previews alter disposable copies only."""
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np

from observations import inspect, usages, runtime
from patching import plan, preview_yaml
from terrain import NativeTerrain
from unity_data import World, digest
from world import ROOT, asset


def material_summary(record):
    return [{k: row.get(k) for k in ("name", "path", "file_id", "status", "shader", "colors_serialized", "textures")}
            for row in record.get("materials", [])]


def brief(facts):
    coverage = facts["coverage"]
    scene_keys = ("id", "name", "world_position_m", "relative_in_target_axes_m", "distance_m", "distance_to_bounds_m", "bounds", "bounds_source", "container_only", "components")
    native_keys = ("id", "category", "path", "position_m", "relative_in_target_axes_m", "distance_m", "yaw_degrees", "width_scale", "height_scale", "collider_diameter_estimates_m", "diameter_evidence")
    scene = [r for r in facts["nearby_scene_objects"] if not r["container_only"]]
    native = facts["nearby_native_instances"]
    return {"center_world_m": facts["center_world_m"], "radius_m": facts["radius_m"],
            "terrain": facts["terrain_relation"], "relative_axes": facts["relative_axes"],
            "scene_sample": [{k: r.get(k) for k in scene_keys} for r in scene[:5]],
            "native_sample": [{k: r.get(k) for k in native_keys} for r in native[:5]],
            "returned_native_categories": dict(Counter(r["category"] for r in native)),
            "coverage": coverage,
            "target_materials": material_summary(facts["target"]),
            "support_candidates": facts["support_candidates"][:3],
            "overlap_candidates": facts["overlap_candidates"][:3],
            "grass_detail_status": [{k: r.get(k) for k in ("terrain_id", "status", "patch_xz", "patch_width_depth_m", "detail_prototype_count", "individual_grass_blades_available")}
                                    for r in facts["grass_detail_context"]] if isinstance(facts["grass_detail_context"], list) else facts["grass_detail_context"],
            "source_file_count": len(facts["source_fingerprint"]["files"]),
            "source_sha256": facts["source_fingerprint"]["sha256"]}


def core_hashes(root):
    return {p.relative_to(root).as_posix(): digest(p)
            for folder in ("Assets", "Packages", "ProjectSettings")
            for p in (root/folder).rglob("*") if p.is_file()}


def run(root):
    root = Path(root).resolve()
    before = core_hashes(root)
    w = World(root)
    native = NativeTerrain(w)
    rng = random.Random(20261103)
    queries = []
    for index, tile in enumerate(native.tiles):
        data = native.load(tile)
        x = round(tile["origin_m"][0] + rng.uniform(.12, .88)*data["size_m"][0], 3)
        z = round(tile["origin_m"][2] + rng.uniform(.12, .88)*data["size_m"][2], 3)
        facts = inspect(w, {"x": x, "z": z, "radius": 60, "limit": 100})
        queries.append({"label": "seeded_random_tile_"+str(index+1), **brief(facts)})
    instances = list(native.instances())
    for category in ("tree", "rock"):
        chosen = rng.choice([r for r in instances if r["category"] == category])
        facts = inspect(w, {"target": chosen["id"], "radius": 60, "limit": 100})
        row = {"label": "seeded_random_"+category, "target": chosen, **brief(facts)}
        prototype = World(root, chosen["path"])
        prototype_root = next(go for go in prototype.gos if not prototype.transforms[prototype.go_transform[go]].get("m_Father", {}).get("fileID"))
        row["prototype_materials"] = material_summary(prototype.object(prototype_root, True))
        queries.append(row)
    houses = [go for go, row in w.gos.items() if "house" in row.get("m_Name", "").lower()
              and "foundation" not in row["m_Name"].lower() and not row["m_Name"].startswith("ReviewLOD_")
              and any(c["kind"] == "MeshFilter" for c in w.components(go))]
    chosen_house = rng.choice(houses)
    house = w.object(chosen_house, True)
    house_facts = inspect(w, {"target": house["id"], "radius": 60, "limit": 100})
    queries.append({"label": "seeded_random_house", "name": house["name"], **brief(house_facts)})
    # Explicit vertical probes at one random map coordinate, not invented surfaces.
    point = queries[0]["center_world_m"]
    for delta in (5, -2):
        facts = inspect(w, {"x": point[0], "y": point[1]+delta, "z": point[2], "radius": 60, "limit": 100})
        queries.append({"label": "same_point_vertical_offset_"+str(delta), **brief(facts)})

    first_tile = native.tiles[0]
    raw_native = asset(w, {"path": first_tile["asset"]["path"], "file_id": first_tile["asset"]["file_id"],
                           "field": "m_DetailDatabase.m_TreeInstances", "limit": 1})
    prefab = asset(w, {"path": next(r for r in instances if r["category"] == "tree")["path"]})
    meta = asset(w, {"path": w.scene_path+".meta", "file_id": 0, "field": "lines", "limit": 5})

    move_position = [house["world_position_m"][i]+v for i, v in enumerate((2, 1.25, -1))]
    move = {"schema_version": 2, "transaction_id": "audit-move-20261103", "idempotency_key": "audit-move-20261103",
            "reason": "Measure a temporary source-only move without changing the saved world",
            "expected_files": {p: digest(root/p) for p in (w.scene_path, w.scene_path+".meta")},
            "operations": [{"id": "move-house", "op": "set_transform", "target": house["id"], "world_position": move_position}],
            "observe_after": [{"target": house["id"], "native": True, "geometry": True, "radius": 60}]}
    move_plan, _ = plan(root, move)
    moved = preview_yaml(root, move)
    moved_facts = moved["post_edit_observations"][0]["result"]

    material = next(r for r in house["materials"] if any("_BaseColor" in v for v in r.get("colors_serialized", [])))
    color_path = material["path"]
    original_color = next(r["_BaseColor"] for r in material["colors_serialized"] if "_BaseColor" in r)
    requested = [.31, .42, .53, 1]
    color = {"schema_version": 2, "transaction_id": "audit-color-20261103", "idempotency_key": "audit-color-20261103",
             "reason": "Read back a temporary material tint edit without changing the saved material",
             "expected_files": {p: digest(root/p) for p in (color_path, color_path+".meta")},
             "operations": [{"id": "change-tint", "op": "set_material_color", "path": color_path,
                              "file_id": material["file_id"], "property": "_BaseColor", "rgba": requested}],
             "observe_after": [{"target": house["id"], "native": True, "geometry": True, "radius": 60}]}
    color_plan, _ = plan(root, color)
    colored = preview_yaml(root, color)
    colored_record = colored["post_edit_observations"][0]["result"]["target"]
    after_color = next(r for r in colored_record["materials"] if r["path"] == color_path)["colors_serialized"]
    shared = usages(w, {"path": color_path})
    report = {"seed": 20261103, "queries": queries,
              "native_counts": dict(Counter(r["category"] for r in instances)),
              "raw_native_instance_sample": raw_native["value"], "prefab_sample": prefab, "meta_sample": meta,
              "move_preview": {"target": house["name"], "would_change_files": list(move_plan["diffs"]),
                               "before_position_m": house["world_position_m"], "after_position_m": moved_facts["target"]["world_position_m"],
                               "before_ground_relation": house_facts["terrain_relation"], "after_ground_relation": moved_facts["terrain_relation"],
                               "post_edit_observation_keys": list(moved_facts), "temporary_copy_deleted": moved["temporary_project_deleted_on_return"]},
              "color_preview": {"would_change_files": list(color_plan["diffs"]), "before_BaseColor": original_color,
                                "requested_rgba": requested, "after_colors_serialized": after_color,
                                "shared_material_reference_occurrences": shared["total_reference_occurrences"],
                                "shared_usage_file_count": len(shared["text_serialized_usages"]),
                                "post_edit_observation_requests": color_plan["observe_after"],
                                "temporary_copy_deleted": colored["temporary_project_deleted_on_return"]},
              "runtime_source_sample": runtime(root, {"limit": 15}),
              "core_files_hashed": len(before), "core_bytes_unchanged": before == core_hashes(root),
              "unity_render_or_physics_executed": False}
    assert report["core_bytes_unchanged"], "Audit altered original project files"
    np.testing.assert_allclose(moved_facts["target"]["world_position_m"], move_position, atol=1e-9)
    assert any(row.get("_BaseColor") == dict(zip("rgba", requested)) for row in after_color)
    print(json.dumps(report, separators=(",", ":")))


if __name__ == "__main__":
    run(ROOT)
