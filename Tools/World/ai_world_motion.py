#!/usr/bin/env python3
"""Plan exact relative Unity world-space movement without changing scene files.

This sensor accepts stable scene/terrain IDs, never names or natural-language
guesses. It calculates deltas and a schema-v2 hash-guarded World Automation
patch. It does not commit, apply, launch Unity, or edit core assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

DEFAULT_ROOT = Path(os.environ.get("AARIS_WORLD_ROOT", "/workspaces/Unity-Game-Aris"))
SCENE_RE = re.compile(r"scene:[a-f0-9]{32}:-?[0-9]+\Z")
TERRAIN_RE = re.compile(r"terrain:[a-f0-9]{32}:[0-9]+\Z")
VECTORS = {
    "left": (-1., 0., 0.), "right": (1., 0., 0.),
    "forward": (0., 0., 1.), "backward": (0., 0., -1.),
    "up": (0., 1., 0.), "down": (0., -1., 0.),
}
MAX_DISTANCE = 500.0
MAX_RESULT = 10500


class MotionError(ValueError):
    pass


def finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise MotionError(label + " must be a finite number")
    return float(value)


def rounded(v):
    return [round(float(n), 6) for n in v]


def normalize(v):
    size = math.sqrt(sum(a*a for a in v))
    if size <= 1e-8:
        raise MotionError("Local axis projects vertically: cannot resolve horizontal move")
    return [a/size for a in v]


def delta(direction=None, meters=None, frame="world", rotation=None, xyz=None):
    """Unity +X right, +Y up, +Z forward. Local axes ignore parent scale."""
    if xyz is not None:
        if direction is not None or meters is not None:
            raise MotionError("Choose explicit dx/dy/dz OR direction/metres")
        d = [finite(a, "delta") for a in xyz]
    else:
        if direction not in VECTORS:
            raise MotionError("Choose one of left/right/forward/backward/up/down")
        distance = finite(meters, "metres")
        if not 0 < distance <= MAX_DISTANCE:
            raise MotionError("metres must be >0 and <=500")
        basis = VECTORS[direction]
        if frame == "target-local":
            if rotation is None:
                raise MotionError("Object-local movement requires resolved target rotation")
            # Rotation is orthonormal Unity world rotation, *not* its scaled matrix.
            basis = [sum(rotation[i][j]*basis[j] for j in range(3)) for i in range(3)]
            # Horizontal directions are projected onto the horizontal ground
            # plane; otherwise pitched/rolled houses unexpectedly change height.
            if direction in ("left", "right", "forward", "backward"):
                x, _, z = normalize([basis[0], 0., basis[2]])
                basis = [x, 0., z]
            else:
                basis = normalize(basis)
        elif frame != "world":
            raise MotionError("Invalid coordinate frame")
        d = [distance * n for n in basis]
    if math.sqrt(sum(n*n for n in d)) > MAX_DISTANCE + 1e-7:
        raise MotionError("Total displacement is limited to 500 metres")
    if not any(abs(n) >= 1e-7 for n in d):
        raise MotionError("Zero displacement does not create a transaction")
    return d


def native_rotation(yaw_degrees):
    angle = math.radians(finite(yaw_degrees, "yaw"))
    c, s = math.cos(angle), math.sin(angle)
    # Unity Quaternion.Euler(0, yaw, 0): world +Z becomes (+X,0,+Z)
    return [[c, 0., s], [0., 1., 0.], [-s, 0., c]]


def root_modules(root):
    import importlib
    root = Path(root).resolve()
    if not (root/"Tools/World/world.py").is_file():
        raise MotionError("No World Automation scripts at requested --root")
    path = str(root/"Tools/World")
    if path not in sys.path:
        sys.path.insert(0, path)
    return (
        importlib.import_module("unity_data"),
        importlib.import_module("terrain"),
        importlib.import_module("patching"),
        importlib.import_module("observations"),
    )


def height(native, x, z):
    result = native.height(x, z)
    rows = result["samples"]
    if not rows:
        raise MotionError("No terrain height at proposed location")
    return float(rows[0]["height_m"]), result


def adjacent_tiles(native, x, z):
    """Use recorded terrain origin and available decoded size, not a 2km guess."""
    tiles = []
    for t in native.tiles:
        d = native.load(t)
        ox, _, oz = t["origin_m"]
        if ox-1e-6 <= x <= ox+d["size_m"][0]+1e-6 and oz-1e-6 <= z <= oz+d["size_m"][2]+1e-6:
            tiles.append(t["asset"]["path"])
    return tiles


def surroundings(world, observations, xyz, radius, limit):
    data = observations.inspect(world, {"x": float(xyz[0]), "z": float(xyz[2]),
             "radius": radius, "limit": limit, "scene_offset": 0, "native_offset": 0,
             "native": True, "geometry": True, "appearance": False, "semantics": True})
    cover = data.get("coverage") or {}
    scene = []
    for obj in data.get("nearby_scene_objects", [])[:limit]:
        scene.append({"id": obj.get("id"), "name": obj.get("name"),
                      "world_position_m": obj.get("world_position_m"),
                      "distance_m": obj.get("distance_m"),
                      "size_m": (obj.get("bounds") or {}).get("size_m"),
                      "role": (obj.get("semantic") or {}).get("primary_role")})
    native = []
    for obj in data.get("nearby_native_instances", [])[:limit]:
        native.append({"id": obj.get("id"), "category": obj.get("category"),
                       "world_position_m": obj.get("position_m"),
                       "distance_m": obj.get("distance_m"),
                       "width_scale": obj.get("width_scale"),
                       "height_scale": obj.get("height_scale")})
    return {"scene_on_page": scene, "terrain_instances_on_page": native,
            "pagination": {"scene_next_offset": cover.get("scene_next_offset"),
                           "native_next_offset": cover.get("native_next_offset"),
                           "scene_candidates_total": cover.get("scene_candidates_total"),
                           "native_candidates_total": cover.get("native_candidates_total")},
            "not_a_collision_or_clearance_test": True}


def make_patch(target, before, after, scene, native_asset, root, digest):
    required = [scene, scene+".meta"]
    if native_asset:
        required.extend([native_asset, native_asset+".meta"])
    expected = {}
    for path in required:
        if path in expected:
            continue
        file = root/path
        if not file.is_file():
            raise MotionError("Cannot plan: missing required core source or metadata: " + path)
        expected[path] = digest(file)
    operation = ({"id": "move-selected", "op": "set_transform",
                  "target": target, "world_position": rounded(after)}
                 if target.startswith("scene:") else
                 {"id": "move-selected", "op": "terrain_instance_move",
                  "target": target, "world_xz": rounded([after[0], after[2]])})
    descriptor = json.dumps({"target": target, "before": rounded(before),
                              "after": rounded(after), "files": expected},
                             sort_keys=True, separators=(",", ":"))
    identity = hashlib.sha256(descriptor.encode()).hexdigest()[:24]
    return {"schema_version": 2, "transaction_id": "motion-"+identity,
            "idempotency_key": "motion-"+identity,
            "reason": "AI-authored explicit relative move of one stable map object",
            "expected_files": expected, "operations": [operation],
            "observe_after": [
                {"target": target, "radius": 35, "limit": 12},
                {"x": round(after[0],6), "z": round(after[2],6),
                 "radius": 35, "limit": 12}]}


def plan(root, target, *, direction=None, meters=None, frame="world",
         xyz=None, follow_terrain=False, inspect_radius=25.0, limit=5,
         inspect_sites=True, validate=False):
    worldmod, terrainmod, patchmod, observations = root_modules(root)
    if not (SCENE_RE.fullmatch(target) or TERRAIN_RE.fullmatch(target)):
        raise MotionError("Use exact scene:<guid>:<fileID> or terrain:<guid>:<index> from inspection")
    world = worldmod.World(root)
    native = terrainmod.NativeTerrain(world)
    is_native = bool(TERRAIN_RE.fullmatch(target))
    if is_native:
        row = native.find_instance(target)
        before = list(map(float, row["position_m"]))
        orientation = native_rotation(row["yaw_degrees"])
        native_asset = row["terrain_path"]
        kind = row.get("category", "native_instance")
        scene_file = worldmod.SCENE
    else:
        go = world.resolve(target)
        if go not in world.go_transform:
            raise MotionError("No inline Transform; requires Unity Editor import/export")
        tid = world.go_transform[go]
        before = list(map(float, world.world_matrix(tid)[:3,3]))
        orientation = world.world_rotation(tid)
        native_asset = None
        kind = world.gos[go].get("m_Name")
        scene_file = worldmod.SCENE
        doc = world.docs[tid]
        if doc.get("stripped") or doc["data"].get("m_PrefabInstance",{}).get("fileID"):
            raise MotionError("Connected prefab Transform requires Unity backend; no direct YAML move")
    move = delta(direction, meters, frame, orientation, xyz)
    if is_native and abs(move[1]) > 1e-8:
        raise MotionError("Native TerrainData instances cannot move vertically; terrain owns Y")
    after = [before[i] + move[i] for i in range(3)]
    old_tiles = adjacent_tiles(native, before[0], before[2])
    new_tiles = adjacent_tiles(native, after[0], after[2])
    if not new_tiles:
        raise MotionError("Destination lies outside the saved TerrainData world")
    if is_native:
        if native_asset not in new_tiles:
            raise MotionError("Move crosses TerrainData tile; explicit remove/add & identity review required")
        new_y, _ = height(native, after[0], after[2])
        after[1] = new_y  # reported expectation; Unity computes actual native support
    elif follow_terrain:
        previous_ground, _ = height(native, before[0], before[2])
        new_ground, _ = height(native, after[0], after[2])
        after[1] += new_ground - previous_ground
    before_ground, _ = height(native, before[0], before[2])
    after_ground, ground = height(native, after[0], after[2])
    transaction = make_patch(target, before, after, scene_file, native_asset,
                             Path(root), worldmod.digest)
    # Validate using the repo's *actual* authoritative schema/transform and
    # TerrainData precondition implementation. This DOES NOT apply any bytes.
    patchmod.validate_patch(transaction)
    verified = None
    if validate:
        report, outputs = patchmod.plan(root, transaction)
        verified = {"backend": report.get("backend"),
                    "predicted_written_files": report.get("predicted_written_files"),
                    "unity_operations": len(report.get("unity_operations") or []),
                    "validated_without_write": True}
    positions = {}
    if inspect_sites:
        positions = {
            "before": surroundings(world, observations, before, inspect_radius, limit),
            "destination_before_move": surroundings(world, observations, after, inspect_radius, limit),
        }
    return {
        "status": "planned_read_only", "target": target, "target_name_or_category": kind,
        "target_type": "terrain_instance" if is_native else "inline_scene_object",
        "coordinate_system": "Unity world metres; +X right, +Y up, +Z forward",
        "relative_frame": frame, "direction": direction, "distance_m": meters,
        "before_world_xyz_m": rounded(before), "delta_world_xyz_m": rounded([after[i]-before[i] for i in range(3)]),
        "proposed_world_xyz_m": rounded(after),
        "ground_before_m": round(before_ground, 6),
        "ground_destination_m": round(after_ground, 6),
        "height_above_terrain_before_m": round(before[1]-before_ground, 6),
        "height_above_terrain_destination_m": round(after[1]-after_ground, 6),
        "terrain_tiles_before": old_tiles, "terrain_tiles_destination": new_tiles,
        "ground_mode": "terrain_native_support" if is_native else
                       "follow_same_terrain_offset" if follow_terrain else "keep_absolute_world_y",
        "backend_needed_for_apply": "Unity Editor (native TerrainData)" if is_native else
                                    "Python saved YAML, then Unity Editor imports changed scene",
        "transaction": transaction, "authoritative_plan_check": verified,
        "nearby_saved_evidence": positions,
        "warning": "NOT APPLIED. Destination is observed before the move. Serialized AABBs/labels "
                   "do not prove physical clearance. Full Unity import, capture, collision, "
                   "and pathing checks remain mandatory when relevant.",
    }


def output(doc):
    # All 3D vectors remain untruncated. Reduce ONLY neighbourhood page lists.
    encoded = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded) <= MAX_RESULT:
        return encoded
    node = dict(doc)
    nearby = dict(node.get("nearby_saved_evidence") or {})
    for key in list(nearby):
        info = dict(nearby[key])
        for field in ("scene_on_page", "terrain_instances_on_page"):
            info[field] = list(info.get(field) or [])[:2]
        nearby[key] = info
    node["nearby_saved_evidence"] = nearby
    node["output_truncated"] = "Only 2 neighbours per location; paginate using ai_world_observe.py site"
    encoded = json.dumps(node, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded) <= MAX_RESULT:
        return encoded
    node["nearby_saved_evidence"] = {
        k: {"pagination": v.get("pagination"), "full_neighbours": "query site sensor"} for k,v in nearby.items()}
    return json.dumps(node, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan"])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--target", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--direction", choices=sorted(VECTORS))
    group.add_argument("--dx", type=float, help="Use with optional --dy and --dz; world metres")
    parser.add_argument("--dy", type=float, default=0.)
    parser.add_argument("--dz", type=float, default=0.)
    parser.add_argument("--metres", type=float)
    parser.add_argument("--frame", choices=("world","target-local"), default="world")
    parser.add_argument("--follow-terrain", action="store_true", help="Scene objects only")
    parser.add_argument("--radius", type=float, default=25.)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--no-neighbours", action="store_true")
    parser.add_argument("--validate-plan", action="store_true")
    parser.add_argument("--out", type=Path, help="Save patch to an OUT-OF-REPO scratch path, never a core asset")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.limit <= 12:
            raise MotionError("limit must be 1..12")
        if not 1 <= finite(args.radius,"radius") <= 100:
            raise MotionError("radius must be 1..100m")
        if args.direction and args.metres is None:
            raise MotionError("--direction requires --metres")
        if args.direction and (args.dy != 0 or args.dz != 0):
            raise MotionError("--direction cannot combine with --dy/--dz; use --dx/--dy/--dz instead")
        if args.dx is not None and args.metres is not None:
            raise MotionError("--metres must only be used with --direction")
        if args.dx is not None and args.frame != "world":
            raise MotionError("dx/dy/dz are already world-space; frame must be world")
        if args.follow_terrain and args.dy != 0:
            raise MotionError("Use follow-terrain OR explicit dy to avoid ambiguity")
        root = args.root.resolve()
        result = plan(root, args.target, direction=args.direction, meters=args.metres,
                      frame=args.frame, xyz=[args.dx,args.dy,args.dz] if args.dx is not None else None,
                      follow_terrain=args.follow_terrain, inspect_radius=args.radius,
                      limit=args.limit, inspect_sites=not args.no_neighbours, validate=args.validate_plan)
        if args.out:
            path = args.out.expanduser().resolve()
            if path.is_relative_to(root) or path.suffix != ".json":
                raise MotionError("Patch output must be .json OUTSIDE the Unity repo")
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise MotionError("Patch output exists; choose a fresh filename to avoid overwrite")
            path.write_text(json.dumps(result["transaction"],indent=2,allow_nan=False)+"\n")
            result["patch_written_to"] = str(path)
        print(output(result))
        return 0
    except (MotionError, ValueError, OSError, KeyError, ImportError) as exc:
        print(json.dumps({"status":"rejected_no_write", "error":str(exc)},ensure_ascii=False))
        return 2


if __name__ == "__main__":
    # The GitHub Issue worker invokes "python3" from its system environment;
    # the pinned Unity saved-data readers were deliberately installed into an
    # isolated venv so the global Python installation remains unchanged.
    venv = Path(os.environ.get("AARIS_WORLD_BRIDGE_HOME",
                             "/workspaces/.aaris-world-bridge")) / "venv/bin/python"
    if venv.is_file() and Path(sys.executable).resolve() != venv.resolve():
        os.execv(str(venv), [str(venv), *sys.argv])
    raise SystemExit(main())
