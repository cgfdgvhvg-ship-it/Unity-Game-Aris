"""Deterministic orientation guard for collapsed static-mesh LOD triangles.

Preserves vertex positions, UVs, normals, tangents, triangle membership and
material slots. ONLY swaps order of existing indices whose geometric face
normal strongly opposes the averaged source vertex normals. It is a candidate
visual correction, not an engine/device render test or a universal mesh repair.
"""
from __future__ import annotations
import numpy as np


def face_normal_counts(vertices, triangles, threshold=.2):
    v = np.asarray(vertices)
    t = np.asarray(triangles)
    if v.ndim != 2 or v.shape[1] < 6 or t.ndim != 2 or t.shape[1] != 3:
        raise ValueError("Expected vertex rows with xyz + normals and Mx3 triangles")
    if t.size and (t.min() < 0 or t.max() >= len(v)):
        raise ValueError("Triangle index beyond vertex buffer")
    if not t.size:
        return {"opposing": 0, "agreeing": 0, "unreliable": 0, "cosines": np.empty(0), "trusted": np.empty(0, dtype=bool)}
    pos = v[t, :3].astype(np.float64)
    face = np.cross(pos[:, 1] - pos[:, 0], pos[:, 2] - pos[:, 0])
    avgnorm = v[t, 3:6].astype(np.float64).mean(axis=1)
    flen, nlen = np.linalg.norm(face, axis=1), np.linalg.norm(avgnorm, axis=1)
    trusted = (flen > 1e-9) & (nlen > 1e-8)
    cosine = np.zeros(len(t))
    cosine[trusted] = np.einsum("ij,ij->i", face[trusted], avgnorm[trusted]) / (flen[trusted] * nlen[trusted])
    return {"opposing": int((trusted & (cosine < -threshold)).sum()),
            "agreeing": int((trusted & (cosine > threshold)).sum()),
            "unreliable": int((~trusted).sum()),
            "cosines": cosine, "trusted": trusted}


def candidate_winding(vertices, triangles, opposite_threshold=-.55):
    """Return corrected index order and diagnostics without mutating inputs.

    Threshold is intentionally conservative; mixed/near-orthogonal source
    vertex normals must not be guessed into a different front face.
    """
    t = np.array(triangles, dtype=np.uint32, copy=True)
    before = face_normal_counts(vertices, t)
    flip = before["trusted"] & (before["cosines"] <= opposite_threshold)
    if np.any(flip):
        t[flip] = t[flip][:, [0, 2, 1]]
    after = face_normal_counts(vertices, t)
    if after["opposing"] > before["opposing"]:
        raise ValueError("Winding candidate increased opposed triangles")
    return t, {"triangles": int(len(t)), "flipped": int(flip.sum()),
               "opposing_before": before["opposing"], "opposing_after": after["opposing"],
               "unreliable_faces": before["unreliable"]}
