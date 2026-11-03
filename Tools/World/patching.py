"""Guarded edits of saved core YAML. Native TerrainData writes use Unity, never hex edits."""
from __future__ import annotations

import difflib
import json
import math
import os
import re
import tempfile
from pathlib import Path

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
    if patch.get("schema_version") != 1 or not isinstance(patch.get("expected_files"), dict) or not patch["expected_files"]:
        raise WorldError("Patch requires schema_version=1 and expected_files {path: sha256}")
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
    if set(patch) - allowed:
        raise WorldError("Unknown patch fields")


def plan(root, patch):
    validate_patch(patch)
    root = Path(root).resolve()
    w = World(root)
    for path, expected in patch["expected_files"].items():
        p = safe_path(root, path)
        if not p.is_file() or digest(p) != expected:
            raise WorldError(f"Stale patch: {path}. Re-inspect the current core file before editing.")
    changes, edits, impacts, engine_ops = {}, {}, [], []

    def source(path):
        if path not in patch["expected_files"]:
            raise WorldError(f"Missing expected SHA256 for {path}")
        if path+".meta" not in patch["expected_files"]:
            raise WorldError(f"Missing expected SHA256 for identity metadata {path}.meta")
        if path not in changes:
            text, docs = documents(safe_path(root, path))
            changes[path] = (text, {d["file_id"]: d for d in docs})
        return changes[path]

    for op in patch["operations"]:
        kind = op.get("op")
        if kind == "set_transform":
            if set(op) - {"op", "target", "local_position", "local_rotation_xyzw", "local_scale"}:
                raise WorldError("Unknown set_transform fields")
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
        elif kind == "set_material_color":
            if set(op) != {"op", "path", "file_id", "property", "rgba"}:
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
        elif kind == "terrain_brush":
            if set(op) != {"op", "center_xz", "radius_m", "delta_m"}:
                raise WorldError("terrain_brush requires center_xz, radius_m, delta_m")
            vector(op["center_xz"], 2, "center_xz")
            r, dy = op["radius_m"], op["delta_m"]
            if not isinstance(r, (int, float)) or not isinstance(dy, (int, float)) or not math.isfinite(r) or not math.isfinite(dy) or not 0 < r <= 100 or abs(dy) > 20:
                raise WorldError("Brush radius must be 0..100m and vertical delta within +/-20m")
            # All four assets participate in seam verification, including brushes across a border.
            for t in w.terrains():
                path = t["asset"]["path"]
                if path not in patch["expected_files"] or path+".meta" not in patch["expected_files"]:
                    raise WorldError("Native edits require expected hashes for every terrain tile and the saved scene")
            if SCENE not in patch["expected_files"] or SCENE+".meta" not in patch["expected_files"]:
                raise WorldError("Native edits require the scene hash")
            engine_ops.append(op)
            impacts.append({"operation": kind, "review": "Unity SetHeights updates native LOD data; recheck seams, vegetation, roads, water and foundations."})
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
    return {"schema_version": 1, "backend": "unity" if engine_ops else "python_yaml", "dry_run": True,
            "reason": patch["reason"], "expected_files": patch["expected_files"], "diffs": diffs,
            "native_operations": engine_ops, "impacts": impacts,
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
        except BaseException:
            for path, data in originals.items():
                atomic_write(root/path, data)
            raise
    return {**report, "dry_run": False, "written_files": {p: digest(root/p) for p in outputs},
            "verification": "YAML identity and finite world transforms verified. Run verify and Unity/device tests before merge."}


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
