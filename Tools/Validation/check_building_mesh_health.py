"""Read-only LFS-hydrated Unity building mesh/LOD diagnostic; never edits assets.

This validates saved native buffers and authored geometric envelopes, NOT GPU,
shader, sky color, mobile device rendering, occlusion, or collision behavior.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

import numpy as np
import yaml


class MeshHealthError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise MeshHealthError(message)


def vec3(d):
    require(isinstance(d, dict), "invalid vector mapping")
    try:
        v = np.asarray([float(d[k]) for k in ("x", "y", "z")], dtype=np.float64)
    except (TypeError, ValueError, KeyError) as e:
        raise MeshHealthError("invalid vector values") from e
    require(bool(np.isfinite(v).all()), "nonfinite vector")
    return v


def bounds(b):
    centre, extent = vec3(b["m_Center"]), vec3(b["m_Extent"])
    require(bool((extent >= 0).all()), "negative mesh bound extent")
    return centre - extent, centre + extent


def inspect_mesh(source, expected_bounds, expected_triangles=None, expected_submeshes=None):
    if isinstance(source, bytes):
        source = source.decode("utf-8")
    require(not source.startswith("version https://git-lfs.github.com/spec/v1"),
            "Git LFS pointer only: hydrate real asset bytes using git lfs pull")
    require(source.startswith("%YAML"), "not a native readable Unity YAML mesh")
    marker = re.search(r"(?m)^--- !u!43 &\d+\s*\n", source)
    require(marker is not None, "Unity Mesh object !u!43 not found")
    try:
        d = yaml.load(source[marker.end():], Loader=yaml.CSafeLoader)["Mesh"]
        vd = d["m_VertexData"]
        n = vd["m_VertexCount"]
        require(type(n) is int and 3 <= n <= 1_000_000, "invalid vertex count")
        require(d["m_IndexFormat"] == 1, "expected 32-bit native mesh indices")
        channels = vd["m_Channels"]
        for idx, offset, dim in ((0, 0, 3), (1, 12, 3), (2, 24, 4), (4, 40, 2)):
            c = channels[idx]
            require(c["stream"] == 0 and c["format"] == 0 and c["offset"] == offset
                    and c["dimension"] == dim, f"unsupported channel {idx}")
        raw = bytes.fromhex(str(vd["_typelessdata"]))
        require(len(raw) == n * 48 and vd["m_DataSize"] == len(raw),
                "vertex stride, count, or data size mismatch")
        vertices = np.frombuffer(raw, dtype="<f4").reshape(n, 12)
        require(bool(np.isfinite(vertices).all()), "NaN/Inf in vertex buffer")
        pos = vertices[:, :3].astype(np.float64)
        ix_bytes = bytes.fromhex(str(d["m_IndexBuffer"]))
        require(len(ix_bytes) > 0 and len(ix_bytes) % 4 == 0, "invalid index buffer")
        ix = np.frombuffer(ix_bytes, dtype="<u4")
        subs = d["m_SubMeshes"]
        require(isinstance(subs, list) and bool(subs), "no mesh submeshes")
        if expected_submeshes is not None:
            require(len(subs) == expected_submeshes, "authored material/submesh slots changed")
        spans, total, max_edge, empty_slots = [], 0, 0.0, []
        for slot, sub in enumerate(subs):
            start, size = sub["firstByte"], sub["indexCount"]
            require(type(start) is int and type(size) is int and start >= 0 and
                    start % 4 == 0 and size >= 0 and size % 3 == 0 and
                    start // 4 + size <= len(ix),
                    f"LOD submesh {slot}: invalid index range; firstByte={start} indexCount={size} totalIndices={len(ix)} topology={sub.get('topology')}")
            require(sub["topology"] == 0 and sub.get("baseVertex", 0) == 0,
                    f"LOD submesh {slot}: unsupported topology/baseVertex")
            a, b = start // 4, start // 4 + size
            require(all(b <= x or a >= y for x, y in spans),
                    f"LOD submesh {slot}: overlapping index windows")
            if size == 0:
                empty_slots.append(slot)
                continue  # A reserved unused material slot is valid Unity mesh data.
            spans.append((a, b))
            ids = ix[a:b]
            require(int(ids.max()) < n,
                    f"LOD submesh {slot}: triangle index out of vertex range")
            tris = pos[ids].reshape(-1, 3, 3)
            total += len(tris)
            for i, j in ((0, 1), (0, 2), (1, 2)):
                max_edge = max(max_edge, float(np.linalg.norm(
                    tris[:, i] - tris[:, j], axis=1).max()))
            low, high = bounds(sub["localAABB"])
            p = tris.reshape(-1, 3)
            require(bool((p.min(axis=0) >= low - .01).all() and
                         (p.max(axis=0) <= high + .01).all()),
                    f"LOD submesh {slot}: triangles escape saved localAABB")
        if expected_triangles is not None:
            require(total == expected_triangles,
                    f"triangle count {total} differs from authored {expected_triangles}")
        low, high = bounds(d["m_LocalAABB"])
        actual_low, actual_high = pos.min(axis=0), pos.max(axis=0)
        require(bool((actual_low >= low - .02).all() and
                     (actual_high <= high + .02).all()),
                "mesh positions escape native local AABB")
        ref_low, ref_high = bounds(expected_bounds)
        require(bool((actual_low >= ref_low - .08).all() and
                     (actual_high <= ref_high + .08).all()),
                "mesh positions escape original model bounds (possible spikes)")
        require(max_edge <= float(np.linalg.norm(ref_high - ref_low)) + .16,
                "triangle edge longer than original building diagonal")
        return {"status": "ok", "vertices": n, "triangles": total,
                "submeshes": len(subs), "empty_submeshes": empty_slots,
                "max_triangle_edge_m": round(max_edge, 3)}
    except (KeyError, IndexError, TypeError, ValueError, yaml.YAMLError) as e:
        if isinstance(e, MeshHealthError):
            raise
        raise MeshHealthError("invalid native Unity mesh structure: " + str(e)[:160]) from e


def inspect_project(root, require_native=True):
    root = Path(root)
    layout = json.loads((root / "Docs/MAP_LAYOUT.json").read_text())
    report = json.loads((root / "Docs/GROUND_REVIEW_REPORT.json").read_text())
    rows, failures = [], []
    for name, model in sorted(layout["models"].items()):
        expected = report["building_lod_triangles"].get(name, {})
        for lod in (0, 1, 2):
            suffix = "" if lod == 0 else f"_LOD{lod}"
            rel = f"Assets/AarisWorld/Models/{name}/Geometry{suffix}.asset"
            try:
                path = root / rel
                require(path.is_file(), "missing native mesh asset")
                row = inspect_mesh(path.read_bytes(), model["bounds"],
                                   model["triangles"] if lod == 0
                                   else expected.get(f"lod{lod}_triangles"),
                                   model["submeshes"])
                rows.append({"file": rel, **row})
            except (MeshHealthError, UnicodeError) as exc:
                if not require_native and str(exc).startswith("Git LFS pointer"):
                    rows.append({"file": rel, "status": "requires_LFS_hydration"})
                else:
                    failures.append({"file": rel, "error": str(exc)})
    return {"status": "failed" if failures else "passed", "meshes": rows,
            "failures": failures, "unity_render_tested": False,
            "android_device_tested": False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--require-native", action="store_true")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    report = inspect_project(args.root, require_native=args.require_native)
    encoded = json.dumps(report, indent=2) + "\n"
    print(encoded)
    if args.json_out:
        Path(args.json_out).write_text(encoded)
    return int(report["status"] == "failed")


if __name__ == "__main__":
    sys.exit(main())
