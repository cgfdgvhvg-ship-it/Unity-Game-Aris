"""Machine-readable automation contract and repository coverage.

This module describes what the tool can observe or mutate.  It never chooses a
placement or silently falls back to a different representation of the world.
"""
from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path

from unity_data import pointer


PROTOCOL_VERSION = 2


OPERATIONS = {
    "set_prefab_lod_thresholds": {
        "backend": "python_yaml", "targets": ["explicit_yaml_prefab_lod_group"], "scope": "shared_asset",
        "fields": ["path", "file_id", "screen_relative_heights"],
        "notes": "Changes only existing transition scalars. Same LOD count and final culling threshold required; renderer sets, geometry and identities preserved. Not a measured FPS result.",
    },
    "remove_mesh_triangles": {
        "backend":"python_yaml", "targets":["uncompressed_static_yaml_mesh"], "scope":"shared_asset",
        "fields":["path","file_id","selections"],
        "notes":"Explicit original triangle indices per submesh. Preserves material slots, vertex attributes, GUIDs and collider references; not automatic door recognition or a physics result.",
    },
    "place_static_prefab": {
        "backend":"python_yaml", "targets":["explicit_static_yaml_prefab"], "scope":"new_scene_instance",
        "fields":["prefab_path","world_position","yaw_degrees","local_scale","parent","name","collider_registry_file_id"],
        "notes":"Saved inline static objects; no Editor or Codespace. Does not retain a PrefabInstance connection. AI supplies the location; all dependency hashes are required.",
    },
    "set_transform": {
        "backend": "python_yaml",
        "targets": ["inline_scene_object"],
        "scope": "instance",
        "fields": ["world_position", "local_position", "local_rotation_xyzw", "local_scale"],
        "notes": "world_position is converted through the current parent matrix; prefab instances require Unity",
    },
    "set_object_state": {
        "backend": "python_yaml",
        "targets": ["inline_scene_object"],
        "scope": "instance",
        "fields": ["active", "name"],
    },
    "set_material_color": {
        "backend": "python_yaml",
        "targets": ["yaml_material"],
        "scope": "shared_asset",
        "fields": ["path", "file_id", "property", "rgba"],
    },
    "set_material_float": {
        "backend": "python_yaml",
        "targets": ["yaml_material"],
        "scope": "shared_asset",
        "fields": ["path", "file_id", "property", "value"],
    },
    "terrain_brush": {
        "backend": "unity",
        "targets": ["native_terrain_data"],
        "scope": "world_region",
        "fields": ["center_xz", "radius_m", "delta_m"],
    },
    "terrain_instance_move": {
        "backend": "unity",
        "targets": ["native_tree", "native_rock", "native_shrub"],
        "scope": "instance",
        "fields": ["target", "world_xz"],
        "notes": "The native instance remains terrain-supported; roof props should be scene objects",
    },
    "terrain_instance_scale": {
        "backend": "unity",
        "targets": ["native_tree", "native_rock", "native_shrub"],
        "scope": "instance",
        "fields": ["target", "width_scale", "height_scale"],
    },
    "terrain_instance_rotate": {
        "backend": "unity",
        "targets": ["native_tree", "native_rock", "native_shrub"],
        "scope": "instance",
        "fields": ["target", "yaw_degrees"],
    },
    "terrain_instance_remove": {
        "backend": "unity",
        "targets": ["native_tree", "native_rock", "native_shrub"],
        "scope": "instance",
        "fields": ["target"],
    },
    "terrain_instance_add": {
        "backend": "unity",
        "targets": ["native_terrain_data"],
        "scope": "instance",
        "fields": ["terrain", "prototype_index", "world_xz", "width_scale", "height_scale", "yaw_degrees"],
    },
    "instantiate_prefab": {
        "backend": "unity",
        "targets": ["prefab_asset"],
        "scope": "new_scene_instance",
        "fields": ["prefab_path", "world_position", "world_rotation_euler", "local_scale", "parent", "name"],
    },
    "duplicate_object": {
        "backend": "unity",
        "targets": ["scene_object", "prefab_instance"],
        "scope": "new_scene_instance",
        "fields": ["target", "world_position", "world_rotation_euler", "local_scale", "name"],
    },
    "delete_object": {
        "backend": "unity",
        "targets": ["scene_object", "prefab_instance"],
        "scope": "instance",
        "fields": ["target"],
    },
}


READ_COMMANDS = {
    "context": "World/repository manifest and current execution coverage",
    "schema": "Machine-readable command and operation contract",
    "scan": "Paged inline scene GameObjects",
    "object": "One stable scene object with hierarchy, bounds, components and materials",
    "inspect": "Target/coordinate neighbourhood, terrain relation, nearby scene/native objects and support evidence",
    "site": "AI-ready local site capsule: terrain, full-radius native counts, paged scene roles, directional neighbors, saved colors and coverage",
    "describe": "Paged hierarchy parts, evidence-backed semantic roles, dimensions, material slots, texture statistics and dependencies",
    "height": "Native terrain height, gradient, slope and normal",
    "region": "Paged-size native terrain grid sampling",
    "instances": "Native terrain tree/rock/shrub records",
    "asset": "Paged serialized asset/source fields",
    "usages": "Reverse references to an asset GUID in text-serialized core files",
    "runtime": "Static runtime/loading/performance evidence from source and project settings",
    "verify": "Saved-reference/native/project checks",
    "performance": "Actual device JSONL measurements",
}


def schema():
    return {
        "protocol_version": PROTOCOL_VERSION,
        "decision_owner": "AI/caller",
        "tool_role": "Observe facts, execute an explicit typed operation, preserve identity, and report the resulting facts",
        "read_commands": READ_COMMANDS,
        "write_operations": OPERATIONS,
        "local_import":{"command":"import-model", "formats":["ZIP with one binary FBX and explicit PBR textures"],
                        "backend":"python", "chooses_location":False, "requires_editor":False},
        "tree_source_authoring":{"entrypoint":"Tools/World/tree_shapes.py", "scope":"shared SpeedTree source prototype",
                                 "python_writes":"Existing importer metadata and matching saved prototype colliders",
                                 "mesh_deformation_requires_unity_import":True, "runtime_generator":False},
        "local_watch": {"command": "watch", "mode": "foreground_json_lines", "polls_saved_core": True,
                        "automatically_runs": False, "before_after_context": True,
                        "limitations": "Must remain running on a local checkout; no remote daemon or Unity rendering"},
    "transaction": {
            "compare_and_swap": "expected_files SHA256",
            "idempotency": "schema v2 transaction_id + idempotency_key",
            "semantic_override": "acknowledgements bind an observation id/hash/reason; integrity failures are never overrideable",
            "post_edit": "explicit observe_after augments (never replaces) automatic per-edit observations",
            "change_report": "Python edits return automatic pre/post observations, exact file hashes and structured deltas",
        },
        "evidence_levels": {
            "serialized_exact": "Read directly from current saved core bytes",
            "native_decoded": "Read from materialized binary Unity data",
            "geometry_estimate": "Bounds/numeric estimate, not a physics or rendered result",
            "unity_engine": "Matching Unity Editor physics/import/render evidence",
            "device_measurement": "Target device telemetry tied to a build GUID",
        },
        "semantic_contract": {
            "authored_labels": "Exact saved names/material paths are high-confidence evidence",
            "inference": "Geometry-based wall/roof/door-or-window hypotheses retain confidence and evidence",
            "no_fabrication": "Ambiguous parts remain unknown or combined roles until source/Unity evidence resolves them",
            "appearance": "Serialized tint plus optional source-raster statistics; final lit color requires Unity capture",
        },
    }


def repository_inventory(root):
    root = Path(root).resolve()
    proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False)
    if proc.returncode == 0 and proc.stdout:
        paths = [Path(p) for p in proc.stdout.decode(errors="replace").split("\0") if p]
        source = "git_tracked"
    else:
        paths = [p.relative_to(root) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
        source = "filesystem"
    extensions = Counter((p.suffix.lower() or "[none]") for p in paths)
    top = Counter(p.parts[0] if p.parts else "[root]" for p in paths)
    missing = [p.as_posix() for p in paths if not (root / p).is_file()]
    lfs = []
    for rel in paths:
        path = root / rel
        try:
            if path.is_file() and path.stat().st_size <= 1024 and pointer(path):
                lfs.append(rel.as_posix())
        except OSError:
            pass
    return {
        "source": source,
        "files": len(paths),
        "top_level_counts": dict(top.most_common()),
        "extension_counts": dict(extensions.most_common()),
        "missing_tracked_count": len(missing),
        "missing_sample": missing[:25],
        "lfs_pointer_count": len(lfs),
        "lfs_pointer_sample": lfs[:25],
    }

