#!/usr/bin/env python3
"""AI entry point: saved core -> evidence -> guarded change -> verification."""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from unity_data import SCENE, World, WorldError, compact, digest, documents, pointer, safe_path
from terrain import NativeTerrain
from capabilities import PROTOCOL_VERSION, repository_inventory, schema as automation_schema
from observations import inspect as inspect_context, runtime as runtime_context, usages as asset_usages

ROOT = Path(__file__).resolve().parents[2]
VERSION = PROTOCOL_VERSION


def page(rows, offset=0, limit=100):
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 500:
        raise WorldError("offset >=0 and limit 1..500 required")
    return {"total": len(rows), "offset": offset, "items": rows[offset:offset+limit],
            "next_offset": offset+limit if offset+limit < len(rows) else None}


def context(w):
    import engine
    contract = automation_schema()
    return {"entrypoint": "python Tools/World/world.py", "protocol_version": VERSION,
            "guide": "Docs/WORLD_AUTOMATION.md", "agent_instructions": "AGENTS.md",
            "decision_owner": "AI/caller; tools measure and execute but do not choose map design",
            "coordinates": {"units": "metres", "axes": "Unity world: X right, Y up, Z forward", "terrain_interpolation": "native bilinear grid; Unity physics is a separate command"},
            "scene": w.scene_path, "scene_guid": w.scene_guid, "scene_sha256": digest(w.root/w.scene_path),
            "saved_game_objects": len(w.gos), "terrains": w.terrains(), "engine": engine.capabilities(w.root),
            "repository": repository_inventory(w.root),
            "read_commands": contract["read_commands"], "write_operations": contract["write_operations"],
            "write_commands": ["plan --patch change.json", "preview --patch change.json --backend auto",
                               "apply --patch change.json --backend auto --write"],
            "engine_commands": ["engine --request observe.json", "engine --request route.json",
                                "engine --request export.json", "engine --request capture.json --capture-dir <temporary-dir>"],
            "limits": ["No source inspection can measure real phone FPS or prove crash freedom.",
                       "Missing LFS objects are reported, never treated as empty geometry.",
                       "Material colors are serialized properties, not a rendered screenshot.",
                       "Probe tests chosen walking routes, not every possible building entrance.",
                       "Historical Docs reports are context; current saved core files are authoritative."],
            "retention": "Default stdout only, no report cache or daemon. Unity copies/bots deleted in finally. GitHub query runs are TTL-cleaned by a separate scheduled workflow."}


def scan(w, request):
    search = str(request.get("search", "")).casefold()
    ids = [i for i in w.gos if search in str(w.gos[i].get("m_Name", "")).casefold()]
    paged = page(ids, request.get("offset", 0), request.get("limit", 100))
    paged["items"] = [w.object(i, bool(request.get("details"))) for i in paged["items"]]
    result = {"scene": w.scene_path, "objects": paged,
              "component_counts": dict(Counter(d["kind"] for d in w.docs.values())),
              "terrain": NativeTerrain(w).summary(),
              "prefab_instances_requiring_engine": sum(d["kind"] == "PrefabInstance" for d in w.docs.values()),
              "coverage": "Every saved inline GameObject indexed; terrain instances queried separately. Mesh bounds/materials require object or asset. External prefab instances require engine export."}
    return result


def asset(w, request):
    path = request["path"]
    p = safe_path(w.root, path)
    if not p.is_file():
        raise WorldError("Asset is missing")
    w.read_files.add(path)
    if pointer(p):
        raise WorldError(f"Asset is a Git LFS pointer; git lfs pull --include='{path}'")
    with p.open("rb") as f:
        prefix = f.read(128)
    if prefix.startswith(b"%YAML"):
        _, rows = documents(p)
        rows = [{"file_id": r["file_id"], "type": r["kind"], "data": r["data"]} for r in rows]
    elif p.suffix.lower() in (".jpg", ".jpeg", ".png", ".tga", ".tif", ".tiff"):
        from PIL import Image
        with Image.open(p) as image:
            rows = [{"file_id": 0, "type": "SourceImage", "data": {"width": image.width, "height": image.height,
                     "mode": image.mode, "format": image.format, "note": "Source texture metadata. Use engine capture for material appearance."}}]
    elif p.suffix in (".cs", ".shader", ".hlsl", ".json", ".shadergraph", ".shadersubgraph", ".compute", ".meta", ".asmdef", ".asmref"):
        text = p.read_text()
        rows = [{"file_id": 0, "type": "Text", "data": {"text": text, "lines": text.splitlines()}}]
    else:
        import UnityPy
        try:
            env = UnityPy.load(str(p))
            rows = [{"file_id": o.path_id, "type": o.type.name, "reader": o} for o in env.objects]
        except Exception as e:
            raise WorldError(f"Decoder cannot read this format ({type(e).__name__}); use engine export or its source importer") from e
    selected = request.get("file_id")
    if selected is None:
        return {"path": path, "sha256": digest(p), "bytes": p.stat().st_size,
                "objects": [{"file_id": r["file_id"], "type": r["type"]} for r in rows],
                "next": "Use file_id and optional field (dot-separated keys/indices) for paginated data, e.g. m_Heightmap.m_Heights"}
    matches = [r for r in rows if r["file_id"] == selected]
    if len(matches) != 1:
        raise WorldError("Asset file_id must select exactly one serialized object")
    row = matches[0]
    data = row["data"] if "data" in row else row["reader"].parse_as_dict()
    field = request.get("field", "")
    try:
        for key in field.split(".") if field else []:
            data = data[int(key)] if isinstance(data, list) else data[key]
    except (KeyError, ValueError, IndexError, TypeError) as e:
        raise WorldError("Serialized field is absent; inspect its parent keys") from e
    if isinstance(data, list):
        result = page(data, request.get("offset", 0), request.get("limit", 100))
        result["items"] = [compact(x) for x in result["items"]]
    else:
        result = compact(data)
    return {"path": path, "sha256": digest(p), "file_id": selected, "field": field, "value": result}


def performance(path):
    p = Path(path)
    if not p.is_file() or p.stat().st_size > 8*1024*1024:
        raise WorldError("Expected a device JSONL report <=8MiB")
    rows = [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
    samples = [r for r in rows if r.get("reason") == "sample"]
    def maximum(key):
        values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        if key == "androidPssKB": values = [v for v in values if v >= 0]
        return max(values) if values else None
    return {"source_sha256": digest(p), "records": len(rows), "samples": len(samples),
            "build_guids": sorted({r.get("buildGuid", "unknown") for r in rows}),
            "devices": sorted({r.get("device", "unknown") for r in rows}),
            "versions": sorted({r.get("version", "unknown") for r in rows}),
            "average_sample_fps": sum(r.get("averageFps", 0) for r in samples)/len(samples) if samples else None,
            "worst_sample_p95_frame_ms": maximum("p95FrameMs"), "peak_android_pss_kb": maximum("androidPssKB"),
            "peak_unity_reserved_bytes": maximum("unityReservedBytes"),
            "low_memory_events": sum(r.get("reason") == "low-memory" for r in rows),
            "last_managed_errors": list(dict.fromkeys(r.get("lastError") for r in rows if r.get("lastError")))[-5:],
            "limits": "Sample windows overlap; this is not whole-run weighted FPS. A truncated log cannot identify a native crash/OOM; collect adb logcat and tombstone/exit reason."}


def verify(w, request):
    errors, warnings = [], []
    for i, t in w.transforms.items():
        try:
            w.world_matrix(i)
        except WorldError as e:
            errors.append(str(e))
        for child in t.get("m_Children", []):
            ci = child["fileID"]
            if ci not in w.transforms or w.transforms[ci].get("m_Father", {}).get("fileID") != i:
                errors.append(f"Broken transform child/parent {i}/{ci}")
    for go in w.gos:
        for r in w.gos[go].get("m_Component", []):
            c = w.docs.get(r["component"]["fileID"])
            if c is None or c["data"].get("m_GameObject", {}).get("fileID") != go:
                errors.append(f"Broken component binding at GameObject {go}")
    for i, d in w.docs.items():
        if d["stripped"]:
            warnings.append(f"Stripped prefab object {i} requires engine validation")
    if request.get("native"):
        terrains = NativeTerrain(w)
        seams = terrains.seams()
        errors.extend(f"Open terrain seam: {s}" for s in seams if s["max_delta_m"] > .05)
    else:
        seams = None
        warnings.append("Native seams not tested; rerun verify --native after LFS materialization")
    checks = []
    if request.get("project_checks"):
        # Historical validators write Docs reports. Give them private Docs/Tools,
        # and read-only-in-practice links to source; their outputs never overwrite source reports.
        with tempfile.TemporaryDirectory(prefix="aaris-verify-") as temp:
            temp = Path(temp)
            shutil.copytree(w.root/"Docs", temp/"Docs")
            shutil.copytree(w.root/"Tools", temp/"Tools", ignore=shutil.ignore_patterns("__pycache__", ".source-cache", ".model-cache", "*.npz"))
            for folder in ("Assets", "Packages", "ProjectSettings"):
                (temp/folder).symlink_to(w.root/folder, target_is_directory=True)
            for filename in (".gitattributes", "TRANSFER-MANIFEST.json", "README.md"):
                if (w.root/filename).is_file(): shutil.copy2(w.root/filename, temp/filename)
            for name in ("check_explorer", "check_road_markings", "check_world_review", "check_render_review", "check_material_import", "check_mobile_review"):
                script = temp/"Tools"/"Validation"/(name+".py")
                try:
                    r = subprocess.run([sys.executable, str(script)], cwd=temp, capture_output=True, text=True, timeout=180)
                    checks.append({"check": name, "exit": r.returncode, "output_tail": (r.stdout+r.stderr)[-3000:]})
                    if r.returncode:
                        errors.append(name + " failed")
                except subprocess.TimeoutExpired:
                    errors.append(name + " timed out")
    return {"passed": not errors, "errors": errors[:100], "warnings": sorted(set(warnings))[:100], "seams": seams,
            "project_checks": checks, "unity_import_or_physics_tested": False,
            "limits": "Saved-reference checks do not prove playability, shader compilation, Android memory stability or enterable interiors."}


READ_COMMANDS = {
    "context": set(), "schema": set(), "scan": {"search", "offset", "limit", "details"}, "object": {"target"},
    "inspect": {"target", "x", "y", "z", "radius", "limit", "native", "geometry"},
    "height": {"x", "z"}, "region": {"xmin", "zmin", "xmax", "zmax", "step"},
    "instances": {"category", "xmin", "zmin", "xmax", "zmax", "offset", "limit"},
    "asset": {"path", "file_id", "field", "offset", "limit"}, "usages": {"path"},
    "runtime": {"search", "offset", "limit"}, "verify": {"native"}
}


def dispatch(root, request, remote=False):
    if not isinstance(request, dict) or request.get("command") not in READ_COMMANDS:
        raise WorldError("Request command must be an allowed read-only command")
    cmd = request["command"]
    if set(request) - ({"command"} | READ_COMMANDS[cmd]):
        raise WorldError("Unknown request fields")
    if remote and cmd == "asset":
        path = request.get("path", "")
        if not path.startswith(("Assets/", "Packages/", "ProjectSettings/")):
            raise WorldError("Remote asset requests are limited to project core files")
    for key in ("x", "y", "z", "radius", "xmin", "zmin", "xmax", "zmax", "step"):
        if key in request and (isinstance(request[key], bool) or not isinstance(request[key], (int, float)) or not math.isfinite(request[key])):
            raise WorldError(f"{key} must be a finite number")
    for key in ("native", "details", "geometry"):
        if key in request and not isinstance(request[key], bool): raise WorldError(f"{key} must be boolean")
    w = World(root)
    if cmd == "context":
        result = context(w)
    elif cmd == "schema":
        result = automation_schema()
    elif cmd == "scan":
        result = scan(w, request)
    elif cmd == "object":
        result = w.object(w.resolve(request["target"]), True)
    elif cmd == "inspect":
        result = inspect_context(w, request)
    elif cmd == "height":
        result = NativeTerrain(w).height(request["x"], request["z"])
    elif cmd == "region":
        result = NativeTerrain(w).region(*[request[k] for k in ("xmin", "zmin", "xmax", "zmax", "step")])
    elif cmd == "instances":
        native = NativeTerrain(w)
        rows = []
        for tile in native.tiles:
            for r in native.load(tile)["instances"]:
                x, _, z = r["position_m"]
                if request.get("category") and r["category"] != request["category"]:
                    continue
                if (request.get("xmin", -math.inf) <= x <= request.get("xmax", math.inf)
                        and request.get("zmin", -math.inf) <= z <= request.get("zmax", math.inf)):
                    rows.append(r)
        result = page(rows, request.get("offset", 0), request.get("limit", 100))
    elif cmd == "asset":
        result = asset(w, request)
    elif cmd == "usages":
        result = asset_usages(w, request)
    elif cmd == "runtime":
        result = runtime_context(w.root, request)
    elif cmd == "verify":
        result = verify(w, request)
    return {"schema_version": VERSION, "command": cmd, "generated_utc": datetime.now(timezone.utc).isoformat(),
            "source_fingerprint": w.fingerprint(), "result": result}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out", type=Path, help="Explicit persistent report path; default stdout leaves no report file")
    subs = p.add_subparsers(dest="command", required=True)
    subs.add_parser("context")
    subs.add_parser("schema")
    s = subs.add_parser("scan")
    s.add_argument("--search", default=""); s.add_argument("--offset", type=int, default=0); s.add_argument("--limit", type=int, default=100)
    s.add_argument("--details", action="store_true")
    s = subs.add_parser("object"); s.add_argument("--target", required=True)
    s = subs.add_parser("inspect"); s.add_argument("--target")
    for name in ("x", "y", "z", "radius"):
        s.add_argument("--"+name, type=float)
    s.add_argument("--limit", type=int, default=100); s.add_argument("--no-native", dest="native", action="store_false")
    s.add_argument("--no-geometry", dest="geometry", action="store_false"); s.set_defaults(native=True, geometry=True)
    s = subs.add_parser("height"); s.add_argument("--x", type=float, required=True); s.add_argument("--z", type=float, required=True)
    s = subs.add_parser("region")
    for name in ("xmin", "zmin", "xmax", "zmax", "step"):
        s.add_argument("--"+name, type=float, required=True)
    s = subs.add_parser("instances")
    s.add_argument("--category", choices=["tree", "rock", "shrub", "unresolved"])
    for name in ("xmin", "zmin", "xmax", "zmax"):
        s.add_argument("--"+name, type=float)
    s.add_argument("--offset", type=int, default=0); s.add_argument("--limit", type=int, default=100)
    s = subs.add_parser("asset"); s.add_argument("--path", required=True); s.add_argument("--file-id", type=int)
    s.add_argument("--field", default=""); s.add_argument("--offset", type=int, default=0); s.add_argument("--limit", type=int, default=100)
    s = subs.add_parser("usages"); s.add_argument("--path", required=True)
    s = subs.add_parser("runtime"); s.add_argument("--search", default=""); s.add_argument("--offset", type=int, default=0); s.add_argument("--limit", type=int, default=100)
    s = subs.add_parser("verify"); s.add_argument("--native", action="store_true"); s.add_argument("--project-checks", action="store_true")
    for name in ("plan", "preview", "apply"):
        s = subs.add_parser(name); s.add_argument("--patch", required=True, type=Path)
        if name in ("preview", "apply"):
            s.add_argument("--backend", choices=["auto", "python", "unity"], default="auto")
        if name == "apply":
            s.add_argument("--write", action="store_true")
    s = subs.add_parser("engine"); s.add_argument("--request", type=Path, required=True); s.add_argument("--capture-dir", type=Path)
    s = subs.add_parser("performance"); s.add_argument("--report", type=Path, required=True)
    s = subs.add_parser("request"); s.add_argument("--json-env", default="WORLD_REQUEST")
    return p


def main():
    args = vars(parser().parse_args())
    root, out, cmd = args.pop("root"), args.pop("out"), args.pop("command")
    args = {k: v for k, v in args.items() if v is not None}
    try:
        if cmd == "request":
            raw = os.environ.get(args["json_env"], "")
            if len(raw.encode()) > 32768:
                raise WorldError("Request JSON exceeds 32KiB")
            result = dispatch(root, json.loads(raw), True)
        elif cmd in ("plan", "preview", "apply"):
            from patching import load_patch, plan, apply_yaml, preview_yaml
            patch = load_patch(args["patch"])
            if cmd == "plan":
                result = plan(root, patch)[0]
            else:
                report = plan(root, patch)[0]
                selected = args["backend"]
                if selected == "auto": selected = "unity" if report["backend"] == "unity" else "python"
                if selected == "python" and report["backend"] == "unity":
                    raise WorldError("Patch contains Unity-native operations; use --backend auto or unity")
                if cmd == "preview" and selected == "python":
                    result = preview_yaml(root, patch)
                elif cmd == "apply" and selected == "python":
                    result = apply_yaml(root, patch, args["write"])
                else:
                    import engine
                    action = "preview" if cmd == "preview" else "apply"
                    result = engine.run(root, {"command": action}, patch, cmd == "apply" and args.get("write", False))
        elif cmd == "engine":
            import engine
            req = json.loads(args["request"].read_text())
            if req.get("command") == "apply":
                raise WorldError("Use apply --patch ... --backend unity --write for engine mutations")
            result = engine.run(root, req, capture_dir=args.get("capture_dir"))
        elif cmd == "performance":
            result = performance(args["report"])
        elif cmd == "verify":
            w = World(root)
            result = {"result": verify(w, args), "source_fingerprint": w.fingerprint()}
        else:
            result = dispatch(root, {"command": cmd, **args})
        status = 1 if result.get("result", {}).get("passed") is False else 0
    except (WorldError, KeyError, OSError, json.JSONDecodeError, ImportError) as e:
        result, status = {"status": "error", "command": cmd, "error": str(e)}, 2
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if out:
        out.parent.mkdir(parents=True, exist_ok=True); out.write_text(encoded)
        print(json.dumps({"report": str(out), "exit": status}))
    else:
        print(encoded, end="")
    return status


if __name__ == "__main__":
    sys.exit(main())

