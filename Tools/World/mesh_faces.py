"""Explicit triangle removal from the project's saved, uncompressed static YAML meshes.

Material slots, vertices, UVs, normals, tangents, fileIDs and metadata stay intact.
Renderers and non-convex MeshColliders referencing the mesh use the same opening.
This does not implement mesh CSG, arbitrary native writes, or a physics verdict.
"""
from __future__ import annotations

import copy
import hashlib
import numpy as np

from unity_data import WorldError


def arrays(mesh):
    if any(mesh.get(k) for k in ('m_BakedConvexCollisionMesh','m_BakedTriangleCollisionMesh')) or mesh.get('m_StreamData',{}).get('size',0):
        raise WorldError('Cooked or externally streamed mesh data requires Unity authoring')
    vd = mesh.get("m_VertexData", {})
    count = vd.get("m_VertexCount", 0)
    try:
        raw = bytes.fromhex(vd["_typelessdata"])
        index_bytes = bytes.fromhex(mesh["m_IndexBuffer"])
        channel = vd["m_Channels"][0]
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise WorldError("Explicit uncompressed inline mesh buffers are required") from error
    if (type(count) is not int or count < 1 or len(raw) % count or
            channel.get("stream") != 0 or channel.get("format") != 0 or channel.get("dimension") != 3 or
            mesh.get("m_IndexFormat") not in (0, 1)):
        raise WorldError("Unsupported vertex/index encoding; use Unity authoring")
    stride = len(raw) // count
    if channel.get("offset", -1) < 0 or channel["offset"] + 12 > stride:
        raise WorldError("Invalid position channel stride")
    if any(v.get("m_NumItems", 0) for v in mesh.get("m_CompressedMesh", {}).values() if isinstance(v, dict)):
        raise WorldError("Compressed meshes require Unity authoring")
    positions = np.ndarray((count, 3), dtype="<f4", buffer=raw,
                           offset=channel["offset"], strides=(stride, 4)).copy()
    dtype = np.dtype("<u4" if mesh["m_IndexFormat"] == 1 else "<u2")
    if len(index_bytes) % dtype.itemsize or not np.isfinite(positions).all():
        raise WorldError("Invalid mesh buffers")
    indices = np.frombuffer(index_bytes, dtype=dtype)
    groups, used_ranges = [], []
    for submesh in mesh.get("m_SubMeshes", []):
        start, n = submesh.get("firstByte"), submesh.get("indexCount")
        if (type(start) is not int or type(n) is not int or start < 0 or n < 0 or
                start % dtype.itemsize or n % 3 or submesh.get("topology") != 0 or
                submesh.get("baseVertex", 0) != 0 or start // dtype.itemsize + n > len(indices)):
            raise WorldError("Unsupported or invalid triangle submesh range")
        a = start // dtype.itemsize
        if n and any(a < hi and a+n > lo for lo, hi in used_ranges):
            raise WorldError("Overlapping submesh index ranges")
        if n: used_ranges.append((a,a+n))
        group = indices[a:a+n].reshape(-1, 3).copy()
        if group.size and int(group.max()) >= count:
            raise WorldError("Mesh index lies outside the vertex buffer")
        groups.append(group)
    if not groups:
        raise WorldError("Mesh has no submeshes")
    return positions, groups, dtype


def summary(mesh):
    positions, groups, _ = arrays(mesh)
    return {"vertices": len(positions), "triangles_by_submesh": [len(g) for g in groups],
            "vertex_buffer_sha256": hashlib.sha256(bytes.fromhex(mesh["m_VertexData"]["_typelessdata"])).hexdigest(),
            "index_buffer_sha256": hashlib.sha256(bytes.fromhex(mesh["m_IndexBuffer"])).hexdigest(),
            "bounds": mesh.get("m_LocalAABB")}


def _bounds(points):
    lo, hi = points.min(0), points.max(0)
    return {"m_Center": dict(zip("xyz", map(float,(lo+hi)*.5))),
            "m_Extent": dict(zip("xyz", map(float,(hi-lo)*.5)))}


def remove_triangles(mesh, selections):
    positions, groups, dtype = arrays(mesh)
    if not isinstance(selections, list) or not 1 <= len(selections) <= len(groups):
        raise WorldError("Supply explicit per-submesh triangle selections")
    seen = set(); removed = 0
    for selection in selections:
        if not isinstance(selection, dict) or set(selection) != {"submesh", "triangles"}:
            raise WorldError("Each selection requires submesh and triangles")
        slot, ids = selection["submesh"], selection["triangles"]
        if type(slot) is not int or not 0 <= slot < len(groups) or slot in seen:
            raise WorldError("Submesh index is invalid or repeated")
        seen.add(slot)
        if (not isinstance(ids,list) or not ids or any(type(i) is not int or not 0 <= i < len(groups[slot]) for i in ids)
                or len(set(ids)) != len(ids)):
            raise WorldError("Triangle indices must be unique and inside the selected original submesh")
        keep = np.ones(len(groups[slot]),dtype=bool);keep[ids] = False
        groups[slot] = groups[slot][keep];removed += len(ids)
    if not any(len(g) for g in groups):
        raise WorldError("Cannot remove the entire mesh")
    result = copy.deepcopy(mesh); offset = 0
    for submesh, group in zip(result["m_SubMeshes"], groups):
        submesh["firstByte"] = offset * dtype.itemsize; submesh["indexCount"] = int(group.size)
        submesh["firstVertex"] = int(group.min()) if group.size else 0
        submesh["vertexCount"] = int(group.max()-group.min()+1) if group.size else 0
        submesh["localAABB"] = _bounds(positions[group.ravel()]) if group.size else {
            "m_Center":dict.fromkeys("xyz",0.0),"m_Extent":dict.fromkeys("xyz",0.0)}
        offset += group.size
    result["m_IndexBuffer"] = np.concatenate(groups).astype(dtype).tobytes().hex()
    result["m_LocalAABB"] = _bounds(positions[np.concatenate(groups).ravel()])
    after = summary(result)
    if summary(mesh)["vertex_buffer_sha256"] != after["vertex_buffer_sha256"]:
        raise WorldError("Triangle edit changed protected vertex attributes")
    return result, removed
