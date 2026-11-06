"""Build verified LOD triangle-winding candidates WITHOUT modifying game assets.

Read-only by default. Optional --candidate-dir must be OUTSIDE the repo, and
writes only candidate .asset meshes for Unity Editor before/after visual QA.
No scene, LOD0, prefab, .meta, GUID, material or terrain writes. Candidate
orientation is a hypothesis until the exact camera captures are compared.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "MapBuild"))
from lod_winding import candidate_winding
from check_building_mesh_health import inspect_mesh, MeshHealthError


MESH_HEADER = re.compile(r"(?m)^--- !u!43 &\d+\s*\n")
INDEX_LINE = re.compile(r"(?m)^(  m_IndexBuffer: )([0-9a-fA-F]+)\r?$")


def candidate(source, expected_bounds, max_triangles, material_slots):
    before = inspect_mesh(source, expected_bounds, max_triangles, material_slots)
    header = MESH_HEADER.search(source)
    if header is None:
        raise MeshHealthError("Mesh YAML header missing")
    mesh = yaml.load(source[header.end():], Loader=yaml.CSafeLoader)["Mesh"]
    vb = mesh["m_VertexData"]
    vertices = np.frombuffer(bytes.fromhex(vb["_typelessdata"]), dtype="<f4").reshape(-1, 12)
    original = np.frombuffer(bytes.fromhex(mesh["m_IndexBuffer"]), dtype="<u4")
    corrected = original.copy()
    by_slot = []
    for slot, sub in enumerate(mesh["m_SubMeshes"]):
        n = int(sub["indexCount"])
        if n == 0:
            continue
        start = int(sub["firstByte"]) // 4
        t = corrected[start:start+n].reshape(-1, 3)
        revised, counts = candidate_winding(vertices, t)
        corrected[start:start+n] = revised.reshape(-1)
        by_slot.append({"slot": slot, **counts})
    count = sum(v["flipped"] for v in by_slot)
    matches = INDEX_LINE.findall(source)
    if len(matches) != 1:
        raise MeshHealthError("Expected exactly one inline m_IndexBuffer line")
    revised = INDEX_LINE.sub(lambda match: match.group(1) + corrected.tobytes().hex(), source)
    after = inspect_mesh(revised, expected_bounds, max_triangles, material_slots)
    for field in ("vertices", "triangles", "submeshes", "empty_submeshes", "max_triangle_edge_m",
                  "degenerate_area_triangles"):
        if before[field] != after[field]:
            raise MeshHealthError("Candidate changed protected mesh property: " + field)
    if after["face_normal_opposing_triangles"] > before["face_normal_opposing_triangles"]:
        raise MeshHealthError("Candidate increased normal opposition")
    if len(revised) != len(source) or (count == 0 and revised != source):
        raise MeshHealthError("Candidate unexpectedly changed serialized asset length")
    return revised, {
        "flipped_faces": count,
        "opposing_before": before["face_normal_opposing_triangles"],
        "opposing_after": after["face_normal_opposing_triangles"],
        "original_triangles": before["triangles"],
        "submesh_stats": by_slot,
        "sha256_before": hashlib.sha256(source.encode()).hexdigest(),
        "sha256_candidate": hashlib.sha256(revised.encode()).hexdigest(),
    }


def run(root, candidate_dir=None):
    root = Path(root).resolve()
    if candidate_dir is not None:
        candidate_dir = Path(candidate_dir).resolve()
        if candidate_dir == root or root in candidate_dir.parents:
            raise MeshHealthError("Candidate output MUST be outside Unity repo")
    layout = json.loads((root / "Docs/MAP_LAYOUT.json").read_text())
    report = json.loads((root / "Docs/GROUND_REVIEW_REPORT.json").read_text())
    records = []
    for name, model in sorted(layout["models"].items()):
        for level in (1, 2):
            rel = Path(f"Assets/AarisWorld/Models/{name}/Geometry_LOD{level}.asset")
            source = (root / rel).read_text(encoding="utf-8")
            triangles = report["building_lod_triangles"][name][f"lod{level}_triangles"]
            revised, result = candidate(source, model["bounds"], triangles, model["submeshes"])
            if candidate_dir is not None and result["flipped_faces"]:
                output = candidate_dir / rel
                output.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation prevents silently replacing an earlier review candidate.
                with output.open("x", encoding="utf-8", newline="\n") as fh:
                    fh.write(revised)
            records.append({"path": rel.as_posix(), "lod": level, **result})
    return {
        "status": "candidate_only", "assets_examined": len(records),
        "candidate_assets_changed": sum(r["flipped_faces"] > 0 for r in records),
        "total_faces_reoriented": sum(r["flipped_faces"] for r in records),
        "remaining_opposing_faces": sum(r["opposing_after"] for r in records),
        "original_repo_modified": False,
        "unity_render_tested": False, "android_device_tested": False,
        "warnings": ["Face-normal alignment is not a Unity GPU render or a texture/material diagnosis.",
                     "Do not use candidate .asset bytes in main before matched native Unity and Android visual QA."],
        "meshes": records}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--candidate-dir", default=None, help="Optional isolated directory outside the repo")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    report = run(args.root, args.candidate_dir)
    encoded = json.dumps(report, indent=2) + "\n"
    print(encoded)
    if args.json_out:
        Path(args.json_out).write_text(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
