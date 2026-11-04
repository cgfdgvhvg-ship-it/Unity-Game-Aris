"""Read saved Unity objects without importing the project or changing any bytes."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, deque
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
BUILTIN_MESH_GUID = "0000000000000000e000000000000000"
BUILTINS = {BUILTIN_MESH_GUID, "0000000000000000f000000000000000"}
# Unity's default primitive mesh envelopes in local metres. These are source
# AABBs, not collision/contact measurements. Unknown built-ins stay unavailable.
# https://docs.unity3d.com/6000.0/Documentation/Manual/PrimitiveObjects.html
BUILTIN_MESH_EXTENTS = {
    10202: (.5, .5, .5),  # Cube
    10206: (.5, 1., .5),  # Cylinder
    10207: (.5, .5, .5),  # Sphere
    10208: (.5, 1., .5),  # Capsule
    10209: (5., 0., 5.),  # Plane (XZ)
    10210: (.5, .5, 0.),  # Quad (XY)
}


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


def references(value):
    """Yield serialized Unity object references without guessing their role."""
    if isinstance(value, dict):
        if "fileID" in value and ("guid" in value or set(value) <= {"fileID", "guid", "type"}):
            yield value
        for item in value.values():
            yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)


def _rgba(value):
    if not isinstance(value, dict):
        return None
    keys = ("r", "g", "b", "a")
    if not all(k in value for k in keys[:3]):
        return None
    result = [float(value.get(k, 1 if k == "a" else 0)) for k in keys]
    return result if all(math.isfinite(v) for v in result) else None


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
        self.gos = {i: d["data"] for i, d in self.docs.items()
                    if d["kind"] == "GameObject" and not d["stripped"] and "m_Name" in d["data"]}
        raw_transforms = {i: d["data"] for i, d in self.docs.items() if d["kind"] in ("Transform", "RectTransform")}
        # Stripped imported-prefab Transform documents intentionally omit
        # m_GameObject. Keep them visible as unresolved prefab evidence instead
        # of crashing the entire saved-scene index.
        self.transforms = {i: d for i, d in raw_transforms.items()
                           if d.get("m_GameObject", {}).get("fileID") in self.gos}
        self.unbound_transform_documents = sorted(set(raw_transforms) - set(self.transforms))
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

    def texture(self, ref, analyze=False):
        """Return source-texture facts; optional pixels remain non-render evidence."""
        info = self.reference(ref)
        result = dict(info)
        path = info.get("path")
        if not path:
            return result
        p = safe_path(self.root, path)
        if not p.is_file():
            return {**result, "status": "missing_file"}
        if pointer(p):
            return {**result, "status": "lfs_pointer", "download": f"git lfs pull --include='{path}'"}
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp"):
            return {**result, "status": "source_pixels_require_importer_or_unity"}
        try:
            from PIL import Image
            with Image.open(p) as image:
                result.update(status="source_image", width=image.width, height=image.height,
                              mode=image.mode, format=image.format, sha256=digest(p))
                if analyze:
                    image.thumbnail((96, 96), Image.Resampling.LANCZOS)
                    pixels = np.asarray(image.convert("RGBA"), dtype=np.float64)
                    opaque = pixels[..., 3] > 0
                    rgb = pixels[..., :3][opaque] if np.any(opaque) else pixels[..., :3].reshape(-1, 3)
                    if len(rgb):
                        quantized = (np.clip(rgb, 0, 255).astype(np.uint8) // 32) * 32 + 16
                        counts = Counter(map(tuple, quantized.tolist()))
                        swatches = [{"srgb8": list(color), "fraction": count/len(rgb)}
                                    for color, count in counts.most_common(5)]
                        result["source_color_statistics"] = {
                            "sample_pixels": int(len(rgb)),
                            "mean_srgb8": rgb.mean(axis=0).tolist(),
                            "median_srgb8": np.median(rgb, axis=0).tolist(),
                            "stddev_srgb8": rgb.std(axis=0).tolist(),
                            "p10_srgb8": np.percentile(rgb, 10, axis=0).tolist(),
                            "p90_srgb8": np.percentile(rgb, 90, axis=0).tolist(),
                            "dominant_quantized_swatches": swatches,
                            "evidence": "bounded source-raster sample; importer color space, UVs, shader, lighting and weather are not applied",
                        }
        except (OSError, ValueError, ImportError) as error:
            result.update(status="source_image_unavailable", reason=str(error))
        return result

    def material(self, ref, texture_analysis=False):
        info = self.reference(ref)
        if info["status"] != "read":
            return info
        docs = self.asset_docs(info["path"])["docs"]
        d = next((r["data"] for r in docs if r["kind"] == "Material" and r["file_id"] == ref["fileID"]), None)
        if d is None:
            return {**info, "status": "material_file_id_unresolved"}
        props = d.get("m_SavedProperties", {})
        colors = props.get("m_Colors", [])
        color_summary = []
        for row in colors:
            for name, value in row.items():
                color_summary.append({"property": name, "rgba": _rgba(value), "serialized": value})
        textures = []
        for row in props.get("m_TexEnvs", []):
            for name, value in row.items():
                texture_ref = value.get("m_Texture", {})
                textures.append({"property": name, "scale": value.get("m_Scale"), "offset": value.get("m_Offset"),
                                 "reference": self.reference(texture_ref),
                                 "source": self.texture(texture_ref, texture_analysis)})
        base = next((r["rgba"] for r in color_summary if r["property"] in ("_BaseColor", "_Color") and r["rgba"]), None)
        base_texture = next((r for r in textures if r["property"] in ("_BaseMap", "_MainTex")), None)
        estimate = None
        stats = (base_texture or {}).get("source", {}).get("source_color_statistics")
        if base and stats:
            estimate = [base[i] * stats["mean_srgb8"][i] / 255.0 for i in range(3)] + [base[3]]
        return {**info, "name": d.get("m_Name"), "shader": self.reference(d.get("m_Shader", {})),
                "colors_serialized": colors, "color_properties": color_summary,
                "floats": props.get("m_Floats", []), "textures": textures,
                "base_color_times_source_mean_estimate": estimate,
                "appearance_evidence": {
                    "serialized_material": True,
                    "source_texture_pixels_analyzed": bool(stats),
                    "rendered_pixels": False,
                },
                "appearance_note": "Serialized tint and optional source-raster statistics are not final lit pixels. Use Unity capture for final appearance."}

    def submesh_geometry(self, mesh_ref, slot):
        """Distinguish an empty saved slot from a remaining material reference."""
        info = self.reference(mesh_ref)
        if info.get("status") != "read" or not info.get("path"):
            return {"status":info.get("status", "unavailable"), "triangle_count":None,
                    "evidence":"No decoded saved submesh table; not evidence of empty geometry"}
        asset = self.asset_docs(info["path"])
        if asset.get("status") != "read":
            return {"status":asset.get("status", "unavailable"), "triangle_count":None}
        mesh = next((d["data"] for d in asset["docs"] if d["kind"] == "Mesh" and d["file_id"] == mesh_ref.get("fileID")), None)
        groups = mesh.get("m_SubMeshes", []) if mesh else []
        if not 0 <= slot < len(groups):
            return {"status":"saved_submesh_unresolved", "triangle_count":None}
        submesh = groups[slot];count = submesh.get("indexCount")
        if type(count) is not int or count < 0:
            return {"status":"invalid_saved_index_count", "triangle_count":None}
        return {"status":"empty" if count == 0 else "present", "index_count":count,
                "triangle_count":count//3 if submesh.get("topology") == 0 else None,
                "evidence":"Exact saved submesh index count; not a rendered-pixel or physics result"}

    def material_slots(self, go, texture_analysis=False, descendants=True):
        """Bind each material slot to the exact renderer/mesh part using it."""
        slots = []
        for node in self.descendants(go) if descendants else (go,):
            components = self.components(node)
            mesh_ref = None
            for component in components:
                if component["kind"] == "MeshFilter":
                    mesh_ref = component["data"].get("m_Mesh", {})
                elif component["kind"] == "SkinnedMeshRenderer":
                    mesh_ref = component["data"].get("m_Mesh", mesh_ref or {})
            for component in components:
                if component["kind"] not in ("MeshRenderer", "SkinnedMeshRenderer"):
                    continue
                for index, ref in enumerate(component["data"].get("m_Materials", [])):
                    slots.append({
                        "node_id": self.stable_id(node), "node_name": self.gos[node].get("m_Name"),
                        "renderer_file_id": component["file_id"], "renderer_kind": component["kind"],
                        "slot_index": index, "mesh": self.reference(mesh_ref or {}),
                        "submesh_geometry": self.submesh_geometry(mesh_ref or {}, index),
                        "material": self.material(ref, texture_analysis),
                        "evidence": "saved renderer binding; submesh_geometry reports decoded face counts where available, not final pixels",
                    })
        return slots

    def dependency_graph(self, roots, max_depth=2, max_nodes=256):
        """Traverse current serialized GUID dependencies with bounded coverage."""
        if type(max_depth) is not int or not 0 <= max_depth <= 8:
            raise WorldError("dependency depth must be 0..8")
        roots = list(dict.fromkeys(str(path) for path in roots if path))
        queue = deque((path, 0) for path in roots)
        nodes, edges, seen, truncated = [], [], set(), False
        while queue:
            path, depth = queue.popleft()
            if path in seen:
                continue
            if len(seen) >= max_nodes:
                truncated = True
                break
            seen.add(path)
            info = self.asset_docs(path)
            node = {"path": path, "status": info["status"], "depth": depth}
            p = safe_path(self.root, path)
            if p.is_file() and not pointer(p):
                node.update(sha256=digest(p), bytes=p.stat().st_size)
            nodes.append(node)
            if depth >= max_depth or info["status"] != "read":
                continue
            for doc in info["docs"]:
                for ref in references(doc["data"]):
                    target = self.guid_paths.get(str(ref.get("guid", "")))
                    if not target:
                        continue
                    edges.append({"from": path, "to": target, "source_file_id": doc["file_id"],
                                  "target_file_id": ref.get("fileID")})
                    if target not in seen:
                        queue.append((target, depth+1))
        return {"roots": roots, "nodes": nodes, "edges": edges,
                "max_depth": max_depth, "max_nodes": max_nodes, "truncated": truncated,
                "coverage": "Current serialized GUID references. Importer-generated and code-loaded dependencies require Unity AssetDatabase/runtime evidence."}

    def prefab_source(self, path, texture_analysis=False):
        """Resolve YAML prefabs fully and FBX source geometry conservatively."""
        info = self.asset_docs(path)
        if info["status"] != "read":
            if Path(path).suffix.lower() != ".fbx" or info["status"] != "binary_requires_decoder":
                return {"path": path, "status": info["status"]}
        if Path(path).suffix.lower() == ".prefab" and info["status"] == "read":
            try:
                source = World(self.root, path)
                self.read_files.update(source.read_files)
                roots = []
                for go, transform in source.go_transform.items():
                    if not source.transforms[transform].get("m_Father", {}).get("fileID"):
                        roots.append(source.object(go, True))
                return {"path": path, "status": "yaml_prefab_resolved", "root_objects": roots,
                        "inline_game_objects": len(source.gos), "unbound_stripped_transforms": source.unbound_transform_documents,
                        "evidence": "saved prefab YAML; nested/imported dependencies retain their own status"}
            except (WorldError, OSError, KeyError) as error:
                return {"path": path, "status": "yaml_prefab_unavailable", "reason": str(error)}
        if Path(path).suffix.lower() == ".fbx":
            p = safe_path(self.root, path)
            if not p.is_file() or pointer(p):
                return {"path": path, "status": "lfs_pointer_or_missing"}
            try:
                importer = None
                meta_path = Path(str(p)+".meta")
                if meta_path.is_file():
                    meta_data = yaml.safe_load(meta_path.read_text(errors="replace")) or {}
                    model = meta_data.get("ModelImporter", {})
                    meshes = model.get("meshes", {}) if isinstance(model, dict) else {}
                    materials = model.get("materials", {}) if isinstance(model, dict) else {}
                    importer = {"global_scale": meshes.get("globalScale"),
                                "use_file_scale": meshes.get("useFileScale"),
                                "material_import_mode": materials.get("materialImportMode") if isinstance(materials, dict) else None}
                import assimp_py as assimp
                flags = (assimp.Process_Triangulate | assimp.Process_PreTransformVertices |
                         assimp.Process_JoinIdenticalVertices | assimp.Process_GenSmoothNormals)
                scene = assimp.import_file(str(p), flags)
                meshes, lows, highs = [], [], []
                for index, mesh in enumerate(scene.meshes):
                    vertices = np.asarray(mesh.vertices, dtype=float).reshape(-1, 3)
                    if not len(vertices):
                        continue
                    low, high = vertices.min(axis=0), vertices.max(axis=0)
                    lows.append(low); highs.append(high)
                    meshes.append({"index": index, "name": getattr(mesh, "name", None),
                                   "vertices": int(len(vertices)), "faces": int(getattr(mesh, "num_faces", 0)),
                                   "source_aabb_units": {"min": low.tolist(), "max": high.tolist(),
                                                         "size": (high-low).tolist()},
                                   "material_index": getattr(mesh, "material_index", None)})
                combined = None if not lows else {"min": np.min(lows, axis=0).tolist(),
                                                  "max": np.max(highs, axis=0).tolist(),
                                                  "size": (np.max(highs, axis=0)-np.min(lows, axis=0)).tolist()}
                return {"path": path, "status": "fbx_source_decoded", "meshes": meshes,
                        "mesh_count": len(meshes), "material_count": int(getattr(scene, "num_materials", 0)),
                        "combined_source_aabb_units": combined, "unity_model_importer": importer,
                        "evidence": "Assimp source model after hierarchy pre-transform; Unity ModelImporter scale, mesh splitting, materials and final bounds are not applied"}
            except (ImportError, RuntimeError, ValueError, OSError) as error:
                return {"path": path, "status": "fbx_source_unavailable", "reason": str(error)}
        return {"path": path, "status": info["status"]}

    def prefab_instances(self, resolve_source=False, texture_analysis=False, override_offset=0, override_limit=100):
        """Expose imported/nested prefab evidence without fabricating inline GameObjects."""
        if type(override_offset) is not int or type(override_limit) is not int or override_offset < 0 or not 1 <= override_limit <= 500:
            raise WorldError("Prefab override offset >=0 and limit 1..500 required")
        result = []
        for doc in self.docs.values():
            if doc["kind"] != "PrefabInstance":
                continue
            data = doc["data"]
            modification = data.get("m_Modification", {})
            source = self.reference(data.get("m_SourcePrefab", {}))
            overrides = []
            transform_fields = {}
            for row in modification.get("m_Modifications", []):
                target_ref = row.get("target", {})
                prop = row.get("propertyPath")
                target_id = target_ref.get("fileID")
                if isinstance(prop, str) and target_id and re.fullmatch(r"m_Local(Position|Rotation|Scale)\.[xyzw]", prop):
                    try:
                        transform_fields.setdefault(target_id, {})[prop] = float(row.get("value"))
                    except (TypeError, ValueError):
                        pass
                overrides.append({"target": self.reference(row.get("target", {})),
                                  "property_path": row.get("propertyPath"), "value": row.get("value"),
                                  "object_reference": self.reference(row.get("objectReference", {}))})
            transform_summary = None
            if transform_fields:
                target_id, fields = max(transform_fields.items(), key=lambda item: len(item[1]))
                local = {"m_LocalPosition": {}, "m_LocalRotation": {"w": 1}, "m_LocalScale": {"x": 1, "y": 1, "z": 1}}
                for prop, value in fields.items():
                    group, axis = prop.rsplit(".", 1)
                    local[group][axis] = value
                try:
                    local_matrix = matrix(local)
                    parent_id = modification.get("m_TransformParent", {}).get("fileID", 0)
                    world_matrix = self.world_matrix(parent_id) @ local_matrix if parent_id in self.transforms else local_matrix
                    transform_summary = {"source_transform_file_id": target_id, "serialized_overrides": fields,
                                         "world_position_m": world_matrix[:3, 3].tolist(),
                                         "world_axis_scale": np.linalg.norm(world_matrix[:3, :3], axis=0).tolist(),
                                         "evidence": "composed serialized root-like transform overrides; exact nested transform identity requires Unity GlobalObjectId export"}
                except (WorldError, ValueError, KeyError) as error:
                    transform_summary = {"status": "unavailable", "reason": str(error), "serialized_overrides": fields}
            row = {
                "id": f"prefab-instance:{self.scene_guid}:{doc['file_id']}",
                "prefab_instance_file_id": doc["file_id"], "source": source,
                "transform_parent_file_id": modification.get("m_TransformParent", {}).get("fileID", 0),
                "override_count": len(overrides),
                "overrides": {"total": len(overrides), "offset": override_offset,
                              "items": overrides[override_offset:override_offset+override_limit],
                              "next_offset": override_offset+override_limit if override_offset+override_limit < len(overrides) else None},
                "status": "serialized_instance_evidence",
                "exact_hierarchy_geometry": "requires source dependency decoding or Unity export",
                "instance_transform": transform_summary,
            }
            if resolve_source and source.get("path"):
                row["source_details"] = self.prefab_source(source["path"], texture_analysis)
            result.append(row)
        return result

    def mesh_aabb(self, ref):
        """Resolve a saved mesh or a known Unity primitive without inventing bounds."""
        info = self.reference(ref)
        if info["status"] == "unity_builtin" and info["guid"] == BUILTIN_MESH_GUID:
            extent = BUILTIN_MESH_EXTENTS.get(ref["fileID"])
            if extent is not None:
                return {"m_Center": {}, "m_Extent": dict(zip("xyz", extent))}, None
        if info["status"] == "read":
            mesh = next((r["data"] for r in self.asset_docs(info["path"])["docs"]
                         if r["kind"] == "Mesh" and r["file_id"] == ref["fileID"]), None)
            if mesh and mesh.get("m_LocalAABB"):
                return mesh["m_LocalAABB"], None
        return None, "mesh_bounds_unresolved:"+str(info["status"])+":"+str(info["path"])+":"+str(ref.get("fileID"))

    def own_bounds(self, go):
        if go not in self.go_transform:
            return [], ["missing_transform"]
        m = self.world_matrix(self.go_transform[go])
        found, missing = [], []
        for c in self.components(go):
            d = c["data"]
            if c["kind"] == "MeshFilter":
                ref = d.get("m_Mesh", {})
                aabb, reason = self.mesh_aabb(ref)
                if aabb is not None:
                    found.append(bounds_transform(aabb["m_Center"], aabb["m_Extent"], m))
                else:
                    missing.append(reason)
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
                    b, reason = self.mesh_aabb(d.get("m_Mesh", {}))
                    if b is not None:
                        found.append(bounds_transform(b["m_Center"], b["m_Extent"], m))
                    else:
                        missing.append("mesh_collider_geometry_unavailable:"+reason)
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
            slots = self.material_slots(go)
            materials = {}
            for slot in slots:
                material = slot["material"]
                key = (material.get("guid"), material.get("file_id"))
                materials.setdefault(key, material)
            result["materials"] = list(materials.values())
            result["material_slots"] = slots
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


