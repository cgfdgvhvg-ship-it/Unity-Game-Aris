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
    if cmd in ("scan", "height", "region", "instances", "verify") or (cmd == "inspect" and request.get("native", True)):
        paths.update(t["asset"]["path"] for t in w.terrains() if t["asset"]["path"])
    if cmd == "asset": paths.add(request["path"])
    ids = []
    if cmd == "object": ids = [w.resolve(request["target"])]
    if cmd == "inspect" and request.get("target") and not str(request["target"]).startswith("terrain:"):
        ids = [w.resolve(request["target"])]
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

