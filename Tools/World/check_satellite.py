"""Integration checks against the three saved Python-authored satellite props.

Checks source identity, shape references and terrain estimates, never rendering
or physics. The authored positions are deliberate regression expectations.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from observations import inspect
from static_prefabs import dependencies
from terrain import NativeTerrain
from unity_data import World, digest, documents
from world import ROOT


PLACEMENTS = {
    "SatelliteDish_HighlandObservatory": ([662, 23.74010318338803, -650], 225, 8),
    "SatelliteDish_SouthernAirfield": ([275, 24.95513642190076, -495], 315, 8),
    "SatelliteDish_ForestLookout": ([-685, 6.7655496551303145, -140], 60, 6),
}


def check(root, native=False):
    w = World(root)
    folder = Path("Assets/WorldImports/SatelliteDish")
    manifest = json.loads((root/folder/"Import.json").read_text())
    assert manifest["source_sha256"] == "9bdc6eb0add877e142ead2edcc83159a5e310a290ec2c1ba58bdcf879427504a"
    paths = dependencies(w, manifest["prefab_path"])
    before = {p: digest(root/p) for p in [w.scene_path, *paths]}
    _, mesh_docs = documents(root/folder/"Geometry.asset")
    mesh = mesh_docs[0]["data"]
    vertices = np.frombuffer(bytes.fromhex(mesh["m_VertexData"]["_typelessdata"]), dtype="<f4").reshape(-1, 12)
    indices = np.frombuffer(bytes.fromhex(mesh["m_IndexBuffer"]), dtype="<u4")
    assert len(vertices) == manifest["mesh"]["vertices"] == 4000
    assert len(indices)//3 == manifest["mesh"]["triangles"] == 5538
    assert np.isfinite(vertices).all() and indices.max() < len(vertices)
    np.testing.assert_allclose(np.ptp(vertices[:, :3], axis=0), manifest["dimensions_m"], atol=1e-6)
    mesh_guid = manifest["mesh"]["guid"]
    gate = w.docs[401402]["data"]["obstacles"]
    gated = [r["fileID"] for r in gate]
    assert len(gated) == len(set(gated))
    assert set(gated) == {i for i, d in w.docs.items() if d["kind"] in ("MeshCollider", "BoxCollider")}
    results = []
    for name, (position, yaw, scale) in PLACEMENTS.items():
        matches = [i for i, d in w.gos.items() if d.get("m_Name") == name]
        assert len(matches) == 1, name
        go = matches[0]
        record = w.object(go, True)
        np.testing.assert_allclose(record["world_position_m"], position, atol=1e-6)
        np.testing.assert_allclose(record["world_forward"], [math.sin(math.radians(yaw)), 0, math.cos(math.radians(yaw))], atol=1e-6)
        np.testing.assert_allclose(list(w.transforms[w.go_transform[go]]["m_LocalScale"].values()), [scale]*3)
        components = w.components(go)
        filters = [c["data"]["m_Mesh"] for c in components if c["kind"] == "MeshFilter"]
        colliders = [c for c in components if c["kind"] == "MeshCollider"]
        assert len(filters) == len(colliders) == 1 and filters[0]["guid"] == mesh_guid
        assert colliders[0]["data"]["m_Mesh"] == filters[0]
        assert record["renderer_bounds"] and not record["bounds_incomplete"]
        item = {"name": name, "id": w.stable_id(go), "position_m": position}
        if native:
            facts = inspect(w, {"target": w.stable_id(go), "radius": 50, "limit": 100})
            samples = facts["terrain_under_footprint"]["samples"]
            assert len(samples) == 9
            gaps = [v for sample in samples for v in sample["bounds_bottom_minus_ground_m"]]
            assert max(map(abs, gaps)) < .02, (name, gaps)
            assert facts["coverage"]["scene_shape_bounds_unavailable_count"] == 0, "Fetch all referenced scene geometry before claiming complete neighbourhood coverage"
            item.update(terrain_sample_max_gap_m=max(map(abs, gaps)),
                        scene_neighbours=len(facts["nearby_scene_objects"]),
                        native_neighbours=len(facts["nearby_native_instances"]),
                        unavailable_scene_shapes=facts["coverage"]["scene_shape_bounds_unavailable_count"],
                        nearest_shapes=[{k: row.get(k) for k in ("name", "distance_to_bounds_m", "bounds_source", "bounds", "container_only")}
                                        for row in facts["nearby_scene_objects"] if row.get("bounds")][:15],
                        overlap_candidates=facts["overlap_candidates"])
        results.append(item)
    assert before == {p: digest(root/p) for p in before}, "Inspection mutated source"
    print(json.dumps({"saved_satellites_checked": results, "native_terrain_sampled": native,
                      "core_bytes_unchanged": True, "unity_import_render_or_physics_tested": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--native", action="store_true")
    check(ROOT, parser.parse_args().native)
