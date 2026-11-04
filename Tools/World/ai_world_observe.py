#!/usr/bin/env python3
"""Read-only, output-bounded Unity saved-world observations for GitHub Issue #37.

This wrapper is deliberately a sensor, not a map editor. It works when launched
from the remote issue worker even if the project's checked-out Git branch is
not the command-bridge branch. It never invokes a shell, Unity or Git writes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE_REPO = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get(
    "AARIS_WORLD_ROOT",
    str(SOURCE_REPO if (SOURCE_REPO / "Tools/World/world.py").is_file()
        else Path("/workspaces/Unity-Game-Aris")),
))
STATE = Path("/workspaces/.aaris-world-bridge")
MAX_JSON = 9500  # issue worker retains at most ~12000 output characters
COMMANDS = {
    "schema": (),
    "context": (),
    "scan": ("search", "offset", "limit", "details"),
    "object": ("target",),
    "inspect": ("target", "x", "y", "z", "radius", "limit", "scene_offset", "native_offset",
                "texture_analysis"),
    "site": ("target", "x", "y", "z", "radius", "limit", "scene_offset", "native_offset",
             "texture_analysis"),
    "describe": ("target", "offset", "limit", "texture_analysis", "dependency_depth"),
    "height": ("x", "z"),
    "instances": ("category", "xmin", "zmin", "xmax", "zmax", "offset", "limit"),
    "usages": ("path",),
    "runtime": ("search", "offset", "limit"),
}
TYPES = {
    "x": float, "y": float, "z": float, "radius": float,
    "xmin": float, "zmin": float, "xmax": float, "zmax": float,
    "offset": int, "limit": int, "scene_offset": int, "native_offset": int,
    "dependency_depth": int, "search": str, "target": str, "category": str, "path": str,
    "details": bool, "texture_analysis": bool,
}
REQUIRED = {
    "object": ("target",), "describe": ("target",), "usages": ("path",),
    "height": ("x", "z"),
}
VALUE_FLAGS = {
    "search": "--search", "offset": "--offset", "limit": "--limit",
    "target": "--target", "x": "--x", "y": "--y", "z": "--z", "radius": "--radius",
    "scene_offset": "--scene-offset", "native_offset": "--native-offset",
    "dependency_depth": "--dependency-depth", "category": "--category",
    "path": "--path", "xmin": "--xmin", "xmax": "--xmax", "zmin": "--zmin", "zmax": "--zmax",
}


def python_path() -> Path:
    venv = STATE / "venv/bin/python"
    return venv if venv.is_file() else Path(sys.executable)


def cmd(argv, timeout=20):
    return subprocess.run(list(map(str, argv)), cwd=ROOT, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
                          check=False)


def safely_trim(text, limit=900):
    return text if len(text) <= limit else text[:limit] + "… [string truncated]"


def limited(node, max_list, max_dict, depth=0):
    """Keep reports valid JSON and mark lost pagination explicitly."""
    if depth >= 12:
        return "[nested data omitted]"
    if isinstance(node, list):
        # Three-dimensional vectors, RGBA colors, quaternions and world-axis
        # scales must retain ALL numeric components. Truncating [x,y,z] to
        # [x,y,omitted] makes spatial evidence misleading and unusable.
        if len(node) <= 4 and all(isinstance(v, (int, float, bool)) for v in node):
            return node[:]
        items = [limited(x, max_list, max_dict, depth + 1) for x in node[:max_list]]
        if len(node) > max_list:
            items.append({"_omitted_items": len(node) - max_list,
                          "_reason": "Use narrower radius or next offset"})
        return items
    if isinstance(node, dict):
        out = {}
        for k, value in list(node.items())[:max_dict]:
            out[str(k)] = limited(value, max_list, max_dict, depth + 1)
        if len(node) > max_dict:
            out["_omitted_fields"] = len(node) - max_dict
        return out
    if isinstance(node, str):
        return safely_trim(node, 500)
    return node


def report(data):
    for list_cap, dict_cap in ((12, 65), (8, 42), (5, 30), (3, 18), (2, 12), (1, 8)):
        filtered = limited(data, list_cap, dict_cap)
        value = json.dumps(filtered, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(value) <= MAX_JSON:
            return value
    summary = {"status": data.get("status", "partial"), "command": data.get("command"),
               "warning": "Result too large for issue output; use a smaller page/area",
               "result_top_keys": list(data.get("result", {}).keys())[:35]
               if isinstance(data.get("result"), dict) else []}
    return json.dumps(summary, ensure_ascii=False)


def unity_inventory():
    candidates = [
        Path("/opt/unity/Editor/Unity"), Path("/opt/unity/Hub/Editor"),
        Path("/home/codespace/Unity/Hub/Editor"), Path("/usr/local/bin/Unity"),
    ]
    configured = os.environ.get("UNITY_EDITOR_PATH", "")
    if configured:
        candidates.insert(0, Path(configured))
    found = [str(x) for x in candidates if x.is_file()]
    known_exes = {x: shutil.which(x) for x in ("Unity", "unityhub", "unity-hub")}
    installed = [x for x, y in known_exes.items() if y]
    return {"project_version": (ROOT / "ProjectSettings/ProjectVersion.txt").read_text().strip()
            if (ROOT / "ProjectSettings/ProjectVersion.txt").is_file() else "unavailable",
            "configured_path": configured or None,
            "found_binary_paths": found, "found_path_executables": installed,
            "editor_ready": bool(found or installed),
            "search_scope": "Known paths and PATH only; not a complete filesystem scan",
            "render_or_physics_verified": False}


def doctor():
    py = python_path()
    dependency_code = (
        "import importlib.util,json; "
        "print(json.dumps({n:importlib.util.find_spec(n) is not None "
        "for n in ('numpy','yaml','PIL','UnityPy','assimp_py')}))"
    )
    p = cmd([py, "-c", dependency_code])
    deps = json.loads(p.stdout) if p.returncode == 0 else {"error": safely_trim(p.stderr)}
    status = cmd(["git", "status", "--short", "--branch"], timeout=45)
    disk = shutil.disk_usage(ROOT)
    return {
        "status": "ready_for_readonly_queries" if deps.get("numpy") and deps.get("yaml")
                  else "python_dependencies_missing",
        "repository": str(ROOT),
        "python_executable": str(py),
        "dependencies": deps,
        "unity": unity_inventory(),
        "disk_free_gb": round(disk.free / 1e9, 2),
        "git_status": safely_trim(status.stdout or status.stderr, 2000),
        "transport": "Owner-controlled GitHub Issue #37; worker must be running",
        "warning": "Do not infer successful Unity rendering from serialized inspections",
    }


def parse():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["doctor", "unity", *COMMANDS])
    for name, type_ in TYPES.items():
        if type_ is bool:
            p.add_argument("--" + name.replace("_", "-"), action="store_true", default=False)
        else:
            p.add_argument("--" + name.replace("_", "-"), type=type_, default=None)
    args = p.parse_args()
    supplied = {k: v for k, v in vars(args).items()
                if k != "command" and v is not None and v is not False}
    if args.command in ("doctor", "unity") and supplied:
        p.error("This command does not take flags")
    allowed = set(COMMANDS.get(args.command, ()))
    if set(supplied) - allowed:
        p.error("Unsupported flags for selected read-only sensor")
    for field in REQUIRED.get(args.command, ()):
        if field not in supplied:
            p.error("--" + field.replace("_", "-") + " is required")
    if args.command in ("site", "inspect") and "target" not in supplied:
        if not {"x", "z"} <= set(supplied):
            p.error("Provide --target or both --x and --z")
    for key, v in supplied.items():
        if isinstance(v, float) and (not math.isfinite(v) or abs(v) > 10000):
            p.error(key + " must be a finite coordinate")
        if key in ("offset", "scene_offset", "native_offset", "dependency_depth") and v < 0:
            p.error(key + " must not be negative")
    if "limit" in supplied and not 1 <= supplied["limit"] <= 30:
        p.error("limit must be 1..30 for issue output; use pagination")
    if "radius" in supplied and not 1 <= supplied["radius"] <= 300:
        p.error("radius must be 1..300 metres")
    if "category" in supplied and supplied["category"] not in (
            "tree", "rock", "shrub", "unresolved"):
        p.error("invalid terrain category")
    if "path" in supplied and (not supplied["path"].startswith(
            ("Assets/", "Packages/", "ProjectSettings/"))
            or ".." in Path(supplied["path"]).parts):
        p.error("path must be inside a project asset/config directory")
    return args, supplied


def main():
    args, supplied = parse()
    if not ROOT.is_dir():
        print(report({"status": "error", "error": "Codespace checkout missing"}))
        return 2
    if args.command == "doctor":
        print(report(doctor()))
        return 0
    if args.command == "unity":
        print(report({"status": "ok", "command": "unity", "result": unity_inventory()}))
        return 0
    py = python_path()
    argv = [str(py), str(ROOT / "Tools/World/world.py"), args.command]
    for k, v in supplied.items():
        if k in ("details", "texture_analysis"):
            if v:
                argv.append("--" + k.replace("_", "-"))
        else:
            argv.extend([VALUE_FLAGS[k], str(v)])
    try:
        executed = cmd(argv, timeout=135)
    except subprocess.TimeoutExpired:
        print(report({"status": "error", "command": args.command,
                      "error": "Read-only world inspection timed out (135s)"}))
        return 2
    if executed.returncode:
        print(report({"status": "error", "command": args.command,
                      "exit_code": executed.returncode,
                      "error": safely_trim(executed.stderr or executed.stdout, 2800),
                      "hint": "Run doctor; install missing dependencies or fetch actual Git LFS assets"}))
        return executed.returncode
    try:
        doc = json.loads(executed.stdout)
    except json.JSONDecodeError:
        print(report({"status": "error", "command": args.command,
                      "error": "World sensor returned non-JSON output"}))
        return 2
    result = doc.get("result", doc)
    if args.command == "site" and isinstance(result, dict):
        site = dict(result.get("site") or {})
        # The site itself may carry a 500+ file hash inventory. Send the
        # stable fingerprint digest instead, retaining enough room for
        # neighbouring buildings, trees, distances and material evidence.
        site.pop("source_fingerprint", None)
        summary = {"site": site,
                   "inspection_coverage": (result.get("inspection") or {}).get("coverage"),
                   "unresolved_prefabs": (result.get("inspection") or {}).get(
                       "unresolved_serialized_prefab_instances")}
    else:
        summary = result
    fingerprint = doc.get("source_fingerprint")
    if isinstance(fingerprint, dict):
        fingerprint = {"sha256": fingerprint.get("sha256"),
                       "files_count": len(fingerprint.get("files") or [])}
    print(report({"status": "ok", "command": args.command, "query": supplied,
                  "source_fingerprint": fingerprint,
                  "result": summary,
                  "caution": "Read-only saved-file evidence; not Unity runtime/capture"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
