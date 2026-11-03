"""Native TerrainData decoder; no sampled CSV is substituted for missing LFS."""
from __future__ import annotations

import gc
import math
from collections import Counter

import numpy as np

from unity_data import WorldError, digest, pointer, safe_path


def color_record(value):
    """Preserve native TreeInstance tint bytes/floats and add a normalized view."""
    if not isinstance(value, dict) or not all(k in value for k in ("r", "g", "b")):
        return {"status": "unavailable"}
    raw = [float(value.get(k, 1 if k == "a" else 0)) for k in ("r", "g", "b", "a")]
    if not all(math.isfinite(v) for v in raw):
        return {"status": "invalid_non_finite", "serialized": value}
    divisor = 255.0 if max(raw) > 1.0 else 1.0
    return {"status": "decoded", "serialized": value, "normalized_rgba": [v/divisor for v in raw],
            "encoding": "color32_0_255" if divisor == 255 else "float_0_1"}


def interpolate(h, origin, spacing, x, z):
    fx, fz = (x-origin[0])/spacing[0], (z-origin[2])/spacing[1]
    rows, cols = h.shape
    if not -1e-7 <= fx <= cols-1+1e-7 or not -1e-7 <= fz <= rows-1+1e-7:
        raise WorldError("Coordinate outside terrain")
    fx, fz = float(np.clip(fx, 0, cols-1)), float(np.clip(fz, 0, rows-1))
    ix, iz = min(int(fx), cols-2), min(int(fz), rows-2)
    tx, tz = fx-ix, fz-iz
    a, b, c, d = map(float, (h[iz, ix], h[iz, ix+1], h[iz+1, ix], h[iz+1, ix+1]))
    y = (a*(1-tx)+b*tx)*(1-tz)+(c*(1-tx)+d*tx)*tz
    dx = ((b-a)*(1-tz)+(d-c)*tz)/spacing[0]
    dz = ((c-a)*(1-tx)+(d-b)*tx)/spacing[1]
    return {"height_m": y, "slope_degrees": math.degrees(math.atan(math.hypot(dx, dz))),
            "gradient_dy_dx_dz": [dx, dz], "normal": (np.array([-dx, 1, -dz])/math.sqrt(dx*dx+dz*dz+1)).tolist(),
            "grid_cell": [ix, iz], "cell_spacing_xz_m": list(spacing)}


class NativeTerrain:
    def __init__(self, world):
        self.world = world
        self.tiles = world.terrains()
        if not hasattr(world,"_native_terrain_cache"):
            world._native_terrain_cache = {}
        self.cache = world._native_terrain_cache

    def load(self, tile):
        path = tile["asset"]["path"]
        if path in self.cache:
            p = safe_path(self.world.root,path)
            if (p.stat().st_mtime_ns,p.stat().st_size,p.stat().st_ino) != self.cache[path]["file_signature"]:
                raise WorldError("TerrainData changed during this World snapshot; re-query current files")
            return self.cache[path]
        if not path or not (self.world.root / path).is_file():
            raise WorldError(f"TerrainData missing: {path}; fetch the original LFS asset and .meta")
        p = safe_path(self.world.root, path)
        signature=(p.stat().st_mtime_ns,p.stat().st_size,p.stat().st_ino)
        self.world.read_files.add(path)
        if (self.world.root / (path + ".meta")).is_file():
            self.world.read_files.add(path + ".meta")
        if pointer(p):
            raise WorldError(f"LFS pointer is not TerrainData. Run git lfs pull --include='{path}'")
        import UnityPy
        env = UnityPy.load(str(p))
        obj = next((o for o in env.objects if o.type.name == "TerrainData" and o.path_id == tile["asset"]["file_id"]), None)
        if obj is None:
            raise WorldError("TerrainData fileID not found in binary")
        data = obj.parse_as_dict()
        hm = data["m_Heightmap"]
        n, scale = hm["m_Resolution"], hm["m_Scale"]
        # This project's serialized TerrainData contract is unsigned 15-bit / 32766.
        raw = np.asarray(hm["m_Heights"], dtype=np.float64).reshape(n, n)
        if raw.min() < 0 or raw.max() > 32766:
            raise WorldError("Unsupported native height encoding; use the Unity bridge")
        h = raw * (scale["y"]/32766.) + tile["origin_m"][1]
        db = data["m_DetailDatabase"]
        externals = {}
        for i, item in enumerate(obj.assets_file.externals, 1):
            s = item.guid.hex()
            guid = "".join(s[a+1]+s[a] for a in range(0, 32, 2))
            externals[i] = {"guid": guid, "path": self.world.guid_paths.get(guid)}
        prototypes = []
        for prototype_index, proto in enumerate(db["m_TreePrototypes"]):
            ref = proto["prefab"]
            ext = externals.get(ref["m_FileID"], {})
            path_name = ext.get("path") or ""
            category = "tree" if "/Trees/" in path_name else "rock" if "/Rocks/" in path_name else "shrub" if path_name else "unresolved"
            prototypes.append({**ext, "file_id": ref["m_PathID"], "category": category,
                               "prototype_index": prototype_index})
        instances = []
        for k, inst in enumerate(db["m_TreeInstances"]):
            v = inst["position"]
            instances.append({"id": f"terrain:{tile['asset']['guid']}:{k}",
                              "instance_index": k, "terrain_id": tile["id"],
                              "terrain_path": path, "terrain_guid": tile["asset"]["guid"],
                              **prototypes[inst["index"]],
                              "position_m": [tile["origin_m"][0]+v["x"]*(n-1)*scale["x"],
                                             tile["origin_m"][1]+v["y"]*scale["y"],
                                             tile["origin_m"][2]+v["z"]*(n-1)*scale["z"]],
                              "yaw_degrees": math.degrees(inst["rotation"]), "width_scale": inst["widthScale"],
                              "height_scale": inst["heightScale"],
                              "color": color_record(inst.get("color")),
                              "lightmap_color": color_record(inst.get("lightmapColor")),
                              "appearance_evidence": "native TerrainData TreeInstance tint; prototype texture/shader/lighting not applied"})
        textures = []
        for o in env.objects:
            if o.type.name == "Texture2D":
                t = o.parse_as_dict()
                textures.append({"name": t.get("m_Name"), "width": t["m_Width"], "height": t["m_Height"],
                                 "mip_count": t["m_MipCount"], "readable": t["m_IsReadable"],
                                 "image_bytes": len(t.get("image data", b""))})
        result = {"heights": h, "spacing": (scale["x"], scale["z"]), "instances": instances,
                  "prototypes": prototypes,
                  "size_m": [(n-1)*scale["x"], scale["y"], (n-1)*scale["z"]], "resolution": n,
                  "version": obj.assets_file.unity_version, "sha256": digest(p), "textures": textures,
                  "detail_prototypes": db["m_DetailPrototypes"], "native_name": data["m_Name"]}
        result["detail_patches"] = db.get("m_Patches", [])
        result["detail_patch_count"] = db.get("m_PatchCount", 0)
        result["detail_patch_samples"] = db.get("m_PatchSamples", 0)
        if (p.stat().st_mtime_ns,p.stat().st_size,p.stat().st_ino)!=signature:
            raise WorldError("TerrainData changed while decoding")
        result["file_signature"] = signature
        self.cache[path] = result
        del raw, data, db, env, obj
        gc.collect()
        return result

    def detail_context(self, x, z):
        """Saved grass/detail patch occupancy, never invented blade positions."""
        rows = []
        for tile in self.tiles:
            d = self.load(tile); ox, _, oz = tile["origin_m"]; sx, _, sz = d["size_m"]
            if not (ox <= x <= ox+sx and oz <= z <= oz+sz):
                continue
            count = d["detail_patch_count"]
            if not count or len(d["detail_patches"]) != count*count:
                rows.append({"terrain_id":tile["id"],"status":"unsupported_detail_patch_layout"});continue
            ix = min(int((x-ox)/sx*count),count-1); iz = min(int((z-oz)/sz*count),count-1)
            patch = d["detail_patches"][iz*count+ix]
            rows.append({"terrain_id":tile["id"], "patch_xz":[ix,iz], "patch_width_depth_m":[sx/count,sz/count],
                         "saved_patch":patch, "detail_prototype_count":len(d["detail_prototypes"]),
                         "evidence":"decoded_native_detail_patch", "individual_grass_blades_available":False,
                         "note":"Patch occupancy is not exact grass beneath a model, and does not prove rendered grass."})
        return rows

    def instances(self):
        """Yield every native TerrainData instance from the current core bytes."""
        for tile in self.tiles:
            yield from self.load(tile)["instances"]

    def find_instance(self, target):
        if not isinstance(target, str) or not target.startswith("terrain:"):
            raise WorldError("Native target must be terrain:<terrain-guid>:<original-index>")
        matches = [row for row in self.instances() if row["id"] == target]
        if len(matches) != 1:
            raise WorldError(f"Expected one native terrain instance; found {len(matches)}")
        return matches[0]

    def height(self, x, z):
        matches = []
        for tile in self.tiles:
            d = self.load(tile)
            ox, _, oz = tile["origin_m"]
            if ox-1e-7 <= x <= ox+d["size_m"][0]+1e-7 and oz-1e-7 <= z <= oz+d["size_m"][2]+1e-7:
                matches.append({"tile_id": tile["id"], **interpolate(d["heights"], tile["origin_m"], d["spacing"], x, z),
                                "source_sha256": d["sha256"]})
        if not matches:
            raise WorldError("Coordinate lies outside all saved TerrainData bounds")
        return {"world_xz_m": [x, z], "samples": matches,
                "seam_height_delta_m": max(r["height_m"] for r in matches)-min(r["height_m"] for r in matches),
                "method": "bilinear native height grid; not a Physics.Raycast or triangle-surface measurement",
                "height_encoding_denominator": 32766, "unity_physics_verified": False}

    def summary(self):
        result = []
        for tile in self.tiles:
            try:
                d = self.load(tile)
                result.append({**tile, "status": "decoded", "source_sha256": d["sha256"], "unity_serialized_version": d["version"],
                               "size_m": d["size_m"], "grid_resolution": d["resolution"], "spacing_xz_m": list(d["spacing"]),
                               "min_height_m": float(d["heights"].min()), "max_height_m": float(d["heights"].max()),
                               "height_quantization_m": d["size_m"][1]/32766,
                               "instances": dict(Counter(i["category"] for i in d["instances"])),
                               "embedded_textures": d["textures"], "detail_prototypes": d["detail_prototypes"]})
            except (WorldError, ImportError) as e:
                result.append({**tile, "status": "unavailable", "reason": str(e)})
        return result

    def region(self, xmin, zmin, xmax, zmax, step):
        if not all(math.isfinite(v) for v in (xmin, zmin, xmax, zmax, step)) or step <= 0 or xmax < xmin or zmax < zmin:
            raise WorldError("Invalid region/step")
        nx, nz = int((xmax-xmin)/step)+1, int((zmax-zmin)/step)+1
        if nx*nz > 4096:
            raise WorldError("Region is limited to 4096 samples per request; increase step or divide the region")
        return {"samples": [self.height(xmin+ix*step, zmin+iz*step) for iz in range(nz) for ix in range(nx)]}

    def seams(self):
        out = []
        for a in self.tiles:
            da = self.load(a)
            for b in self.tiles:
                if a["id"] >= b["id"]:
                    continue
                db = self.load(b)
                if da["heights"].shape != db["heights"].shape:
                    continue
                ax, _, az = a["origin_m"]
                bx, _, bz = b["origin_m"]
                pairs = None
                if abs(az-bz) < 1e-6:
                    if abs(ax+da["size_m"][0]-bx) < 1e-6:
                        pairs = da["heights"][:, -1], db["heights"][:, 0]
                    elif abs(bx+db["size_m"][0]-ax) < 1e-6:
                        pairs = db["heights"][:, -1], da["heights"][:, 0]
                if abs(ax-bx) < 1e-6:
                    if abs(az+da["size_m"][2]-bz) < 1e-6:
                        pairs = da["heights"][-1, :], db["heights"][0, :]
                    elif abs(bz+db["size_m"][2]-az) < 1e-6:
                        pairs = db["heights"][-1, :], da["heights"][0, :]
                if pairs:
                    out.append({"tiles": [a["id"], b["id"]], "max_delta_m": float(np.max(np.abs(pairs[0]-pairs[1])))})
        return out


