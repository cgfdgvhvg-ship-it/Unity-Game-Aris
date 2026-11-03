"""Fetch only the core data needed by a read request, with a 1GiB LFS budget."""
import json
import os
import subprocess
from pathlib import Path

from unity_data import World, WorldError, pointer, safe_path
from world import ROOT, READ_COMMANDS, page


def refs(value):
    if isinstance(value, dict):
        if "guid" in value and "fileID" in value: yield value
        for v in value.values(): yield from refs(v)
    elif isinstance(value, list):
        for v in value: yield from refs(v)


def required(w, request):
    if not isinstance(request, dict) or request.get("command") not in READ_COMMANDS:
        raise WorldError("Only read requests can materialize assets")
    cmd = request["command"]; paths = set()
    if cmd in ("scan", "height", "region", "instances", "verify") or (cmd in ("inspect", "site") and request.get("native", True)):
        paths.update(t["asset"]["path"] for t in w.terrains() if t["asset"]["path"])
    if cmd == "asset": paths.add(request["path"])
    ids = []
    if cmd in ("object", "describe") and not str(request.get("target", "")).startswith("prefab-instance:"):
        ids = [w.resolve(request["target"])]
    if cmd == "inspect" and request.get("geometry", True):
        # Until meshes are available, a distant pivot cannot exclude a large
        # building whose bounds reach this neighbourhood. Fetch the scene's
        # referenced shape geometry before measuring neighbours. The existing
        # 1GiB budget still bounds downloads; texture pixels are not needed.
        ids = list(w.gos)
    if cmd == "scan" and request.get("details"):
        ids = page([i for i,d in w.gos.items() if str(request.get("search", "")).casefold() in d.get("m_Name", "").casefold()],
                   request.get("offset", 0), request.get("limit",100))["items"]
    for go in ids:
        for node in w.descendants(go):
            for c in w.components(node):
                # Mesh geometry supplies real AABBs. Material YAML is ordinary Git;
                # source texture pixels are fetched by an explicit asset request, not all at once.
                if c["kind"] in ("MeshFilter", "MeshCollider", "MeshRenderer", "SkinnedMeshRenderer"):
                    for ref in refs(c["data"]):
                        path = w.guid_paths.get(str(ref.get("guid")))
                        if path: paths.add(path)
    if cmd == "inspect" and request.get("geometry", True):
        # Stripped PrefabInstance documents are not inline GameObjects. Their
        # source must still be materialized so they are never counted as empty.
        paths.update(row["source"]["path"] for row in w.prefab_instances() if row["source"].get("path"))
    if cmd == "describe" and str(request.get("target", "")).startswith("prefab-instance:"):
        matches = [row for row in w.prefab_instances() if row["id"] == request["target"]]
        paths.update(row["source"]["path"] for row in matches if row["source"].get("path"))
    # YAML materials/prefabs are already ordinary Git files. Walk their bounded
    # serialized closure; include source texture pixels only when explicitly
    # requested, avoiding an accidental whole-project texture download.
    depth = request.get("dependency_depth", 2) if cmd == "describe" else 1
    graph = w.dependency_graph(sorted(paths), depth)
    for node in graph["nodes"]:
        suffix = Path(node["path"]).suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp") or request.get("texture_analysis"):
            paths.add(node["path"])
    return sorted(paths)


def main():
    raw = os.environ.get("WORLD_REQUEST", "")
    if len(raw.encode()) > 32768: raise WorldError("Request exceeds 32KiB")
    request = json.loads(raw); w = World(ROOT); paths = required(w,request)
    size = 0; pointers = []
    for path in paths:
        p = safe_path(ROOT,path)
        if p.is_file() and pointer(p):
            text=p.read_text(); line=next((s for s in text.splitlines() if s.startswith("size ")),None)
            if line is None: raise WorldError("Invalid LFS pointer")
            size += int(line.split()[1]);pointers.append(path)
    if size > 1024**3:
        raise WorldError("Request needs more than 1GiB of LFS data; query a smaller object/page")
    if pointers:
        # Arg list, never shell interpolation. Paths come from current repository metadata.
        subprocess.run(["git","lfs","pull","--include="+",".join(pointers),"--exclude="],cwd=ROOT,check=True)
    if any(pointer(safe_path(ROOT,p)) for p in pointers): raise WorldError("LFS transfer returned unresolved pointers")
    print(json.dumps({"materialized_files":len(pointers),"advertised_lfs_bytes":size}))


if __name__=="__main__": main()


