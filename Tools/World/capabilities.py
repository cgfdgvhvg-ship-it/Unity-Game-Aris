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
        "transaction": {
            "compare_and_swap": "expected_files SHA256",
            "idempotency": "schema v2 transaction_id + idempotency_key",
            "semantic_override": "acknowledgements bind an observation id/hash/reason; integrity failures are never overrideable",
            "post_edit": "observe_after requests are returned from preview/apply",
        },
        "evidence_levels": {
            "serialized_exact": "Read directly from current saved core bytes",
            "native_decoded": "Read from materialized binary Unity data",
            "geometry_estimate": "Bounds/numeric estimate, not a physics or rendered result",
            "unity_engine": "Matching Unity Editor physics/import/render evidence",
            "device_measurement": "Target device telemetry tied to a build GUID",
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
