"""Read saved Unity objects without importing the project or changing any bytes."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import yaml

SCENE = "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
HEADER = re.compile(r"(?m)^--- !u!(\d+) &(-?\d+)([^\n]*)\n")
class UnityLoader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    def construct_mapping(self, node, deep=False):
        # Unity uses unquoted hex scalars. A digits-only index buffer or GUID
        # must not be parsed as an octal/integer and lose leading zeroes.
        for key, value in node.value:
            if isinstance(key,yaml.ScalarNode) and key.value in ("guid","m_IndexBuffer","_typelessdata") and isinstance(value,yaml.ScalarNode):
                value.tag = "tag:yaml.org,2002:str"
        return super().construct_mapping(node,deep=deep)


LOADER = UnityLoader
BUILTINS = {"0000000000000000e000000000000000", "0000000000000000f0000000000000000"}


class WorldError(ValueError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def pointer(path):
    with Path(path).open("rb") as f:
        return f.read(80).startswith(b"version https://git-lfs.github.com/spec/v1")


def safe_path(root, relative):
    p = (Path(root) / relative).resolve()
    if not p.is_relative_to(Path(root).resolve()) or p == Path(root).resolve() or p.parts[len(Path(root).resolve().parts)] not in (
        "Assets", "Packages", "ProjectSettings"
    ):
        raise WorldError("Expected a project-relative Assets/, Packages/ or ProjectSettings/ path")
    return p


def documents(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    matches = list(HEADER.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        obj = yaml.load(text[m.end():end], Loader=LOADER)
        if not isinstance(obj, dict) or len(obj) != 1:
            raise WorldError(f"Invalid Unity document: {path} &{m[2]}")
        kind = next(iter(obj))
        out.append({"class_id": int(m[1]), "file_id": int(m[2]), "kind": kind,
                    "data": obj[kind], "stripped": "stripped" in m[3],
                    "start": m.start(), "body_start": m.end(), "end": end})
    if not out:
        raise WorldError(f"No Unity YAML documents: {path}")
    return text, out


def xyz(v):
    return np.array([v.get(k, 0) for k in ("x", "y", "z")], dtype=float)


def matrix(d):
    q = d.get("m_LocalRotation", {})
    x, y, z, w = [float(q.get(k, 1 if k == "w" else 0)) for k in ("x", "y", "z", "w")]
    n = math.sqrt(x*x + y*y + z*z + w*w)
    if n < 1e-10:
        raise WorldError("Zero transform quaternion")
    x, y, z, w = x/n, y/n, z/n, w/n
    r = np.array([[1-2*y*y-2*z*z, 2*x*y-2*z*w, 2*x*z+2*y*w],
                  [2*x*y+2*z*w, 1-2*x*x-2*z*z, 2*y*z-2*x*w],
                  [2*x*z-2*y*w, 2*y*z+2*x*w, 1-2*x*x-2*y*y]])
    m = np.eye(4)
    m[:3, :3] = r @ np.diag(xyz(d.get("m_LocalScale", {"x": 1, "y": 1, "z": 1})))
    m[:3, 3] = xyz(d.get("m_LocalPosition", {}))
    if not np.isfinite(m).all():
        raise WorldError("Non-finite transform")
    return m


def bounds_transform(center, extent, m):
    c = (m @ np.append(xyz(center), 1))[:3]
    e = np.abs(m[:3, :3]) @ xyz(extent)
    return [c-e, c+e]


def bounds_json(b):
    return None if b is None else {"min_m": b[0].tolist(), "max_m": b[1].tolist(),
                                  "size_m": (b[1]-b[0]).tolist()}


def compact(v, depth=0):
    if isinstance(v, bytes):
        return {"type": "bytes", "length": len(v)}
    if isinstance(v, list):
        return {"type": "array", "length": len(v), "sample": [compact(x, depth+1) for x in v[:3]]}
    if isinstance(v, dict):
        if depth > 5:
            return {"type": "object", "keys": list(v)}
        return {str(k): compact(x, depth+1) for k, x in v.items()}
    if isinstance(v, str) and len(v) > 512:
        return {"type": "string", "length": len(v), "prefix": v[:80]}
    return v


class World:
    def __init__(self, root, scene=SCENE):
        self.root = Path(root).resolve()
        self.scene_path = scene
        self.text, docs = documents(safe_path(self.root, scene))
        self.docs = {d["file_id"]: d for d in docs}
        if len(self.docs) != len(docs):
            raise WorldError("Duplicate scene fileIDs")
        self.guid_paths = {}
        for p in (self.root / "Assets").rglob("*.meta"):
            m = re.search(r"(?m)^guid: ([0-9a-f]{32})$", p.read_text(errors="replace"))
            if m:
                rel = p.relative_to(self.root).as_posix()[:-5]
                if m[1] in self.guid_paths and self.guid_paths[m[1]] != rel:
                    raise WorldError(f"Duplicate asset GUID {m[1]}")
                self.guid_paths[m[1]] = rel
        meta = self.root / (scene + ".meta")
        m = re.search(r"(?m)^guid: ([0-9a-f]{32})$", meta.read_text()) if meta.exists() else None
        if not m:
            raise WorldError("Scene .meta GUID is required for stable object IDs")
        self.scene_guid = m[1]
        self.gos = {i: d["data"] for i, d in self.docs.items() if d["kind"] == "GameObject"}
        self.transforms = {i: d["data"] for i, d in self.docs.items() if d["kind"] in ("Transform", "RectTransform")}
        self.go_transform = {d["m_GameObject"]["fileID"]: i for i, d in self.transforms.items()}
        self.children = {i: [] for i in self.gos}
        for t in self.transforms.values():
            parent = t.get("m_Father", {}).get("fileID", 0)
            if parent in self.transforms:
                self.children[self.transforms[parent]["m_GameObject"]["fileID"]].append(t["m_GameObject"]["fileID"])
        self._matrices, self._assets, self._bounds, self._collider_bounds = {}, {}, {}, {}
        self.read_files = {scene, scene + ".meta"}

    def stable_id(self, go):
        return f"scene:{self.scene_guid}:{go}"

    def resolve(self, target):
        if not isinstance(target, str): raise WorldError("Target must be a stable object ID or exact name string")
        if target.startswith("scene:"):
            parts = target.split(":")
            if len(parts) != 3 or parts[1] != self.scene_guid or not parts[2].lstrip("-").isdigit():
                raise WorldError("Object ID must belong to this scene")
            found = [int(parts[2])] if int(parts[2]) in self.gos else []
        else:
            found = [i for i, d in self.gos.items() if d.get("m_Name") == target]
        if len(found) != 1:
            raise WorldError(f"Expected one object; found {len(found)}. Use a stable scene GUID + fileID.")
        return found[0]

    def world_matrix(self, transform, trail=None):
        if transform in self._matrices:
            return self._matrices[transform]
        trail = set() if trail is None else trail
        if transform in trail:
            raise WorldError("Transform parent cycle")
        trail.add(transform)
        d = self.transforms[transform]
        m = matrix(d)
        parent = d.get("m_Father", {}).get("fileID", 0)
        if parent:
            if parent not in self.transforms:
                raise WorldError(f"Unresolved transform parent {parent}; use Unity export for prefab instances")
            m = self.world_matrix(parent, trail) @ m
        self._matrices[transform] = m
        return m

    def components(self, go):
        return [self.docs[r["component"]["fileID"]] for r in self.gos[go].get("m_Component", [])
                if r["component"]["fileID"] in self.docs]

    def world_rotation(self, transform):
        # Unity Transform.forward ignores parent scale, including non-uniform scale.
        d = self.transforms[transform]
        r = matrix({"m_LocalRotation": d.get("m_LocalRotation", {})})[:3, :3]
        parent = d.get("m_Father", {}).get("fileID", 0)
        return self.world_rotation(parent) @ r if parent else r

    def asset_docs(self, path):
        if path not in self._assets:
            p = safe_path(self.root, path)
            self.read_files.add(path)
            if not p.exists():
                self._assets[path] = {"status": "missing_file"}
            elif pointer(p):
                self._assets[path] = {"status": "lfs_pointer", "download": f"git lfs pull --include='{path}'"}
            else:
                with p.open("rb") as f:
                    prefix = f.read(128)
                if not prefix.startswith(b"%YAML"):
                    self._assets[path] = {"status": "binary_requires_decoder"}
                    return self._assets[path]
                try:
                    _, docs = documents(p)
                    self._assets[path] = {"status": "read", "docs": docs}
                except (UnicodeError, WorldError, yaml.YAMLError):
                    self._assets[path] = {"status": "binary_requires_decoder"}
        return self._assets[path]

    def reference(self, ref):
        guid = str(ref.get("guid", ""))
        path = self.guid_paths.get(guid)
        result = {"guid": guid, "file_id": ref.get("fileID", 0), "path": path}
        if not ref.get("fileID"):
            return {**result, "status": "null"}
        if guid in BUILTINS:
            return {**result, "status": "unity_builtin"}
        if not guid and ref.get("fileID") in self.docs:
            return {**result, "status": "scene_object"}
        if not path:
            return {**result, "status": "missing_meta_or_external"}
        self.read_files.add(path + ".meta")
        a = self.asset_docs(path)
        return {**result, "status": a["status"]}

    def material(self, ref):
        info = self.reference(ref)
        if info["status"] != "read":
            return info
        docs = self.asset_docs(info["path"])["docs"]
        d = next((r["data"] for r in docs if r["kind"] == "Material" and r["file_id"] == ref["fileID"]), None)
        if d is None:
            return {**info, "status": "material_file_id_unresolved"}
        props = d.get("m_SavedProperties", {})
        return {**info, "name": d.get("m_Name"), "shader": self.reference(d.get("m_Shader", {})),
                "colors_serialized": props.get("m_Colors", []), "floats": props.get("m_Floats", []),
                "textures": [{k: {**v, "reference": self.reference(v.get("m_Texture", {}))} for k, v in row.items()}
                             for row in props.get("m_TexEnvs", [])],
                "appearance_note": "Serialized material values, not the final lit pixel color. Use Unity capture for appearance."}

    def own_bounds(self, go):
        if go not in self.go_transform:
            return [], ["missing_transform"]
        m = self.world_matrix(self.go_transform[go])
        found, missing = [], []
        for c in self.components(go):
            d = c["data"]
            if c["kind"] == "MeshFilter":
                ref = d.get("m_Mesh", {})
                info = self.reference(ref)
                if info["status"] == "read":
                    mesh = next((r["data"] for r in self.asset_docs(info["path"])["docs"]
                                 if r["kind"] == "Mesh" and r["file_id"] == ref["fileID"]), None)
                    aabb = mesh.get("m_LocalAABB") if mesh else None
                    if aabb:
                        found.append(bounds_transform(aabb["m_Center"], aabb["m_Extent"], m))
                    else:
                        missing.append("mesh_bounds_unresolved:" + str(info["path"]))
                elif info["status"] == "unity_builtin" and ref["fileID"] == 10202:
                    found.append(bounds_transform({}, {"x": .5, "y": .5, "z": .5}, m))
                else:
                    missing.append("mesh:" + info["status"] + ":" + str(info["path"]))
        return found, missing

    def aggregate_bounds(self, go):
        if go in self._bounds:
            return self._bounds[go]
        found, missing = self.own_bounds(go)
        for child in self.children[go]:
            b, unknown = self.aggregate_bounds(child)
            if b is not None:
                found.append(b)
            missing.extend(unknown)
        b = [np.min([v[0] for v in found], axis=0), np.max([v[1] for v in found], axis=0)] if found else None
        self._bounds[go] = (b, sorted(set(missing)))
        return b, sorted(set(missing))

    def descendants(self, go):
        stack, visited = [go], set()
        while stack:
            node = stack.pop()
            if node in visited:
                raise WorldError("Scene hierarchy cycle")
            visited.add(node)
            yield node
            stack.extend(reversed(self.children[node]))

    def aggregate_collider_bounds(self, go):
        """Saved collider envelopes; no claim about physics activation or contacts."""
        if go in self._collider_bounds:return self._collider_bounds[go]
        found, missing = [], []
        for node in self.descendants(go):
            if node not in self.go_transform:continue
            m = self.world_matrix(self.go_transform[node])
            for c in self.components(node):
                d=c["data"];kind=c["kind"]
                if kind=="BoxCollider":
                    found.append(bounds_transform(d.get("m_Center",{}),dict(zip("xyz",xyz(d["m_Size"])/2)),m))
                elif kind in ("SphereCollider","CapsuleCollider"):
                    ext=np.full(3,float(d["m_Radius"]))
                    if kind=="CapsuleCollider":
                        axis=int(d.get("m_Direction",1));ext[axis]=max(ext[axis],float(d["m_Height"])/2)
                    found.append(bounds_transform(d.get("m_Center",{}),dict(zip("xyz",ext)),m))
                elif kind=="MeshCollider":
                    ref=d.get("m_Mesh",{});info=self.reference(ref)
                    mesh=next((r["data"] for r in self.asset_docs(info["path"])["docs"] if r["kind"]=="Mesh" and r["file_id"]==ref["fileID"]),None) if info["status"]=="read" else None
                    if mesh and mesh.get("m_LocalAABB"):
                        b=mesh["m_LocalAABB"];found.append(bounds_transform(b["m_Center"],b["m_Extent"],m))
                    else:missing.append("mesh_collider_geometry_unavailable:"+str(info.get("path")))
        bounds=[np.min([v[0] for v in found],axis=0),np.max([v[1] for v in found],axis=0)] if found else None
        self._collider_bounds[go]=(bounds,sorted(set(missing)))
        return self._collider_bounds[go]

    def object(self, go, details=False):
        d = self.gos[go]
        transform = self.go_transform.get(go)
        if transform is None:
            return {"id": self.stable_id(go), "name": d.get("m_Name"), "status": "requires_unity_prefab_resolution"}
        t = self.transforms[transform]
        m = self.world_matrix(transform)
        parent = self.transforms.get(t.get("m_Father", {}).get("fileID", 0), {}).get("m_GameObject", {}).get("fileID")
        comps = self.components(go)
        result = {"id": self.stable_id(go), "name": d.get("m_Name"), "parent_id": self.stable_id(parent) if parent else None,
                  "active_self": bool(d.get("m_IsActive")), "world_position_m": m[:3, 3].tolist(),
                  "world_forward": self.world_rotation(transform)[:, 2].tolist(), "components": [c["kind"] for c in comps]}
        if details:
            b, unknown = self.aggregate_bounds(go)
            result.update(local_transform={k: t.get(k) for k in ("m_LocalPosition", "m_LocalRotation", "m_LocalScale")},
                          world_matrix=m.tolist(), renderer_bounds=bounds_json(b), bounds_incomplete=unknown,
                          child_ids=[self.stable_id(i) for i in self.children[go]],
                          serialized_components=[{"file_id": c["file_id"], "kind": c["kind"], "data": compact(c["data"])} for c in comps],
                          materials=[])
            materials = {}
            for node in self.descendants(go):
                for c in self.components(node):
                    if c["kind"] not in ("MeshRenderer", "SkinnedMeshRenderer"):
                        continue
                    for ref in c["data"].get("m_Materials", []):
                        key = (ref.get("guid"), ref.get("fileID"))
                        if key not in materials:
                            materials[key] = self.material(ref)
            result["materials"] = list(materials.values())
            collider_bounds, collider_unknown = self.aggregate_collider_bounds(go)
            result["saved_collider_bounds"] = bounds_json(collider_bounds)
            result["collider_bounds_incomplete"] = collider_unknown
            result["collider_evidence"] = "serialized_envelopes; enabled state, collision cooking and actual contacts are not simulated"
        return result

    def terrains(self):
        result = []
        for c in self.docs.values():
            if c["kind"] != "Terrain":
                continue
            d = c["data"]
            go = d["m_GameObject"]["fileID"]
            ref = d["m_TerrainData"]
            info = self.reference(ref)
            m = self.world_matrix(self.go_transform[go])
            if not np.allclose(m[:3, :3], np.eye(3), atol=1e-6):
                raise WorldError("Native height queries require unrotated, unit-scale Terrain transforms; use Unity bridge")
            result.append({"id": self.stable_id(go), "name": self.gos[go]["m_Name"],
                           "origin_m": m[:3, 3].tolist(), "asset": info})
        return result

    def fingerprint(self):
        rows = []
        for path in sorted(self.read_files):
            p = self.root / path
            rows.append([path, digest(p) if p.is_file() else "missing"])
        return {"sha256": hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest(), "files": rows}
