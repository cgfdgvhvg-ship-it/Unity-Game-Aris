"""Expand explicit static prefab YAML into saved scene objects, without an Editor.

This is an inline copy, not a connected Unity PrefabInstance. Unsupported
components, overrides and missing dependencies fail before any source write.
"""
from __future__ import annotations

import copy
import hashlib
import math

import numpy as np

from unity_data import BUILTINS, SCENE, WorldError, documents, pointer, safe_path

SUPPORTED = {"GameObject", "Transform", "MeshFilter", "MeshRenderer", "MeshCollider", "BoxCollider", "CapsuleCollider", "SphereCollider", "LODGroup"}
CLASS_IDS={"GameObject":1,"Transform":4,"MeshFilter":33,"MeshRenderer":23,"MeshCollider":64,"BoxCollider":65,"CapsuleCollider":136,"SphereCollider":135,"LODGroup":205}


def references(value):
    if isinstance(value, dict):
        if "fileID" in value:
            yield value
        for item in value.values():
            yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)


def dependencies(world, path):
    """Materialize and fingerprint the prefab's mesh/material/texture closure."""
    todo, seen = [path], set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        p = safe_path(world.root, rel)
        if not p.is_file() or pointer(p):
            raise WorldError(f"Static prefab dependency bytes missing: {rel}")
        if not (world.root / (rel + ".meta")).is_file():
            raise WorldError(f"Static prefab dependency metadata missing: {rel}.meta")
        world.read_files.update((rel, rel + ".meta"))
        if p.read_bytes()[:5] != b"%YAML":
            continue
        _, docs = documents(p)
        for doc in docs:
            for ref in references(doc["data"]):
                if not ref.get("guid") or not ref.get("fileID"):
                    continue
                if ref["guid"] in BUILTINS:
                    continue
                # Pipeline shader implementations are package dependencies. Other
                # missing external GUIDs cannot be fabricated as zero-size assets.
                if doc["kind"] == "Material" and ref == doc["data"].get("m_Shader"):
                    continue
                target = world.guid_paths.get(ref["guid"])
                if not target:
                    raise WorldError(f"Unresolved static prefab dependency GUID: {ref['guid']}")
                todo.append(target)
    return sorted(seen)


def _quaternion(r):
    # Proper orthonormal rotation -> xyzw; parent scale is deliberately excluded.
    t = float(np.trace(r))
    if t > 0:
        s = math.sqrt(t + 1) * 2
        q = [(r[2, 1]-r[1, 2])/s, (r[0, 2]-r[2, 0])/s, (r[1, 0]-r[0, 1])/s, s/4]
    else:
        i = int(np.argmax(np.diag(r))); j, k = (i+1)%3, (i+2)%3
        s = math.sqrt(1 + r[i, i] - r[j, j] - r[k, k]) * 2
        q = [0., 0., 0., 0.]; q[i] = s/4
        q[j] = (r[j, i]+r[i, j])/s; q[k] = (r[k, i]+r[i, k])/s
        q[3] = (r[k, j]-r[j, k])/s
    q = np.asarray(q); q /= np.linalg.norm(q)
    return dict(zip("xyzw", map(float, q)))


def expand(world, patch, op, scene_docs, require_identity, reserved_ids):
    from patching import vector
    allowed = {"id", "op", "prefab_path", "world_position", "yaw_degrees", "local_scale", "parent", "name", "collider_registry_file_id"}
    if set(op)-allowed or not {"id", "prefab_path", "world_position", "name"} <= set(op):
        raise WorldError("place_static_prefab needs id, prefab_path, world_position and name")
    path = op["prefab_path"]
    if not isinstance(path, str) or not path.startswith("Assets/") or not path.endswith(".prefab"):
        raise WorldError("place_static_prefab requires an Assets/*.prefab")
    name = op["name"]
    if not isinstance(name, str) or not name.strip() or len(name) > 128 or any(ord(c)<32 for c in name):
        raise WorldError("Static prop name must be printable and <=128 characters")
    if any(d["kind"]=="GameObject" and d["data"].get("m_Name")==name for d in scene_docs.values()):
        raise WorldError("Static prop name already exists; inspect its stable ID instead of duplicating it")
    for dependency in dependencies(world, path):
        require_identity(dependency)
    _, source_docs = documents(safe_path(world.root, path))
    if len({d['file_id'] for d in source_docs}) != len(source_docs):
        raise WorldError("Duplicate prefab fileIDs")
    if any(d["kind"] not in SUPPORTED or d["class_id"]!=CLASS_IDS.get(d["kind"]) or d["stripped"]
           or d["data"].get("m_PrefabInstance", {}).get("fileID")
           or d["data"].get("m_CorrespondingSourceObject", {}).get("fileID") for d in source_docs):
        raise WorldError("Only explicit static YAML prefabs are supported; no scripts, skins, nested PrefabInstances or overrides")
    roots = [d for d in source_docs if d["kind"]=="Transform" and not d["data"].get("m_Father", {}).get("fileID")]
    if len(roots)!=1:
        raise WorldError("Static prefab must have exactly one root Transform")
    # The complete prefab hierarchy is read with the same transform validator as a scene.
    from unity_data import World
    prefab = World(world.root, path)
    for transform in prefab.transforms:
        prefab.world_matrix(transform)
        data=prefab.transforms[transform]
        children=[r.get("fileID") for r in data.get("m_Children",[])]
        expected_children=[prefab.go_transform[child] for child in prefab.children[data["m_GameObject"]["fileID"]]]
        if len(children)!=len(set(children)) or set(children)!=set(expected_children):
            raise WorldError("Static prefab has inconsistent serialized parent/child links")
    for go,data in prefab.gos.items():
        components=[r.get("component",{}).get("fileID") for r in data.get("m_Component",[])]
        if len(components)!=len(set(components)) or prefab.go_transform.get(go) not in components:
            raise WorldError("Static prefab has invalid component bindings")
        for ident in components:
            component=prefab.docs.get(ident)
            if not component or component["data"].get("m_GameObject",{}).get("fileID")!=go:
                raise WorldError("Static prefab component belongs to a different GameObject")
    root = roots[0]; root_go = root["data"]["m_GameObject"]["fileID"]
    if len(list(prefab.descendants(root_go))) != len(prefab.gos):
        raise WorldError("Disconnected prefab hierarchy")
    position = vector(op["world_position"], 3, "world_position")
    scale = vector(op.get("local_scale", [1, 1, 1]), 3, "local_scale", True)
    yaw = op.get("yaw_degrees", 0.)
    if isinstance(yaw, bool) or not isinstance(yaw, (int, float)) or not math.isfinite(yaw):
        raise WorldError("yaw_degrees must be finite")
    parent = 0
    if op.get("parent"):
        if not op["parent"].startswith("scene:"):
            raise WorldError("Parent requires a stable scene ID")
        parent = world.go_transform[world.resolve(op["parent"])]
        if scene_docs[parent]["stripped"]:
            raise WorldError("Parent must be an inline Transform")
    local = np.linalg.solve(world.world_matrix(parent), position+[1.])[:3] if parent else np.asarray(position)
    a = math.radians(yaw); rotation = np.array([[math.cos(a),0,math.sin(a)],[0,1,0],[-math.sin(a),0,math.cos(a)]])
    if parent:
        rotation = world.world_rotation(parent).T @ rotation
    seed = hashlib.sha256((patch["transaction_id"]+":"+op["id"]).encode()).digest()
    next_id = 1_000_000 + int.from_bytes(seed[:7], "big")
    mapping = {}
    for doc in source_docs:
        while next_id in reserved_ids:
            next_id += 1
        mapping[doc["file_id"]] = next_id; reserved_ids.add(next_id); next_id += 1
    additions = []
    for doc in source_docs:
        d = copy.deepcopy(doc)
        for ref in references(d["data"]):
            if ref.get("guid") or not ref.get("fileID"):
                continue
            if ref["fileID"] not in mapping:
                raise WorldError("Static prefab contains an unresolved local reference")
            ref["fileID"] = mapping[ref["fileID"]]
        d["file_id"] = mapping[doc["file_id"]]
        additions.append(d)
    by_id = {d["file_id"]:d for d in additions}
    go, tr = mapping[root_go], mapping[root["file_id"]]
    by_id[go]["data"]["m_Name"] = name
    by_id[tr]["data"].update(m_Father={"fileID":parent}, m_LocalPosition=dict(zip("xyz",map(float,local))),
                             m_LocalRotation=_quaternion(rotation), m_LocalScale=dict(zip("xyz",scale)),
                             m_LocalEulerAnglesHint={"x":0.,"y":float(yaw),"z":0.})
    modified = set()
    if parent:
        scene_docs[parent]["data"].setdefault("m_Children", []).append({"fileID":tr}); modified.add(parent)
    else:
        scene_roots = [d for d in scene_docs.values() if d["kind"]=="SceneRoots"]
        if len(scene_roots)!=1:
            raise WorldError("Saved SceneRoots is required for root-level placement")
        scene_roots[0]["data"]["m_Roots"].append({"fileID":tr}); modified.add(scene_roots[0]["file_id"])
    colliders = [d["file_id"] for d in additions if d["kind"].endswith("Collider")]
    registry = op.get("collider_registry_file_id")
    if registry is not None:
        d = scene_docs.get(registry) if type(registry) is int else None
        if not d or d["kind"]!="MonoBehaviour" or "AarisNearbyColliders" not in d["data"].get("m_EditorClassIdentifier", ""):
            raise WorldError("Explicit collider registry must identify AarisNearbyColliders")
        d["data"]["obstacles"].extend({"fileID":i} for i in colliders); modified.add(registry)
    return additions, modified, {"operation_id":op["id"], "id":world.stable_id(go), "name":name,
        "transform_file_id":tr, "added_file_ids":sorted(by_id), "collider_file_ids":colliders,
        "representation":"saved_inline_static_objects", "prefab_connection":False,
        "decision_owner":"AI/caller", "source_prefab":path}
