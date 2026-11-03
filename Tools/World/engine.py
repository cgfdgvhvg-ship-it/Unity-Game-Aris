"""Launch the installed Unity editor in a disposable copy; never borrow an open project."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from patching import apply_yaml, atomic_write, plan
from unity_data import SCENE, World, WorldError, digest, pointer, safe_path


def capabilities(root):
    root = Path(root).resolve()
    executable = os.environ.get("UNITY_EDITOR_PATH", "")
    missing = [p.relative_to(root).as_posix() for p in (Path(root)/"Assets").rglob("*")
               if p.is_file() and pointer(p)]
    inventory = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "Assets"], capture_output=True, check=False)
    tracked = inventory.stdout.decode().split("\0") if inventory.returncode == 0 else []
    absent = [p for p in tracked if p and not (root/p).is_file()]
    inventory_ok = len(tracked) > 1
    available = bool(executable and Path(executable).is_file())
    return {"editor_available": available, "editor_path_configured": bool(executable),
            "lfs_pointer_count": len(missing), "missing_sample": missing[:12],
            "tracked_inventory_available": inventory_ok, "absent_tracked_count": len(absent),
            "ready": available and not missing and inventory_ok and not absent,
            "requires": "Installed/licensed project-matching Unity, complete git lfs pull, isolated project import. A GitHub connection alone supplies neither an editor nor a runner."}


def run(root, request, patch=None, write=False, capture_dir=None):
    root = Path(root).resolve()
    cap = capabilities(root)
    if not cap["ready"]:
        raise WorldError("Unity engine is unavailable or LFS checkout is incomplete: " + json.dumps(cap))
    action = request.get("command")
    if action not in ("export", "probe", "capture", "apply"):
        raise WorldError("Unsupported Unity command")
    patch_report, outputs = (plan(root, patch) if patch else (None, {}))
    if action == "apply" and (not patch or not write):
        raise WorldError("Unity apply requires a validated patch and --write")
    allowed = set(outputs)
    if patch_report and patch_report["native_operations"]:
        allowed.update(t["asset"]["path"] for t in World(root).terrains())
    with tempfile.TemporaryDirectory(prefix="aaris-unity-", dir=os.environ.get("AARIS_WORLD_TEMP")) as temp:
        temp = Path(temp)
        project = temp/"project"
        for folder in ("Assets", "Packages", "ProjectSettings"):
            shutil.copytree(root/folder, project/folder)
        # YAML edits use the same guarded, identity-preserving Python implementation in the copy.
        if outputs:
            yaml_patch = {**patch, "operations": [o for o in patch["operations"] if o["op"] != "terrain_brush"]}
            if yaml_patch["operations"]:
                apply_yaml(project, yaml_patch, True)
        req = {**request, "scene": SCENE}
        if patch_report:
            req["brushes"] = [{"x": o["center_xz"][0], "z": o["center_xz"][1],
                              "radius": o["radius_m"], "delta": o["delta_m"]} for o in patch_report["native_operations"]]
        req_path, response = temp/"request.json", temp/"response.json"
        req["capturePath"] = str(temp/"capture.png")
        req_path.write_text(json.dumps(req))
        env = dict(os.environ, AARIS_WORLD_REQUEST=str(req_path), AARIS_WORLD_RESPONSE=str(response))
        args = [os.environ["UNITY_EDITOR_PATH"], "-batchmode", "-quit", "-projectPath", str(project),
                "-executeMethod", "Aaris.WorldAutomation.WorldBridge.Run", "-logFile", str(temp/"unity.log")]
        if action != "capture":
            args.insert(1, "-nographics")
        proc = None
        previous_handler = signal.getsignal(signal.SIGTERM)
        def cancelled(signum, frame):
            raise WorldError("Unity query cancelled; terminating the isolated editor and removing its project")
        signal.signal(signal.SIGTERM, cancelled)
        try:
            proc = subprocess.Popen(args, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                code = proc.wait(timeout=1800)
            except subprocess.TimeoutExpired as e:
                raise WorldError("Unity import/query exceeded 30 minutes; temporary project removed") from e
        finally:
            if proc is not None and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            signal.signal(signal.SIGTERM, previous_handler)
        if code or not response.is_file():
            log = (temp/"unity.log").read_text(errors="replace")[-12000:] if (temp/"unity.log").exists() else "No editor log"
            raise WorldError(f"Unity failed (exit {code}); {log}")
        result = json.loads(response.read_text())
        if result.get("status") != "ok":
            raise WorldError("Unity rejected request: " + json.dumps(result))
        if action == "apply":
            originals = {p: (root/p).read_bytes() for p in allowed}
            for p, expected in patch["expected_files"].items():
                if digest(safe_path(root, p)) != expected:
                    raise WorldError("Original checkout changed during Unity run; no files copied back")
            if patch_report["native_operations"]:
                from terrain import NativeTerrain
                seams = NativeTerrain(World(project)).seams()
                if any(s["max_delta_m"] > .05 for s in seams):
                    raise WorldError("Unity result has a terrain seam >5cm; no files copied back")
                result["seam_verification"] = seams
            try:
                for p in sorted(allowed):
                    atomic_write(root/p, (project/p).read_bytes())
            except BaseException:
                for p, data in originals.items():
                    atomic_write(root/p, data)
                raise
            result["written_files"] = {p: digest(root/p) for p in sorted(allowed)}
            result["historical_layout_reports"] = "May be stale. Regenerate/review before merge; this tool does not forge authoring reports."
        if action == "capture":
            if not capture_dir:
                raise WorldError("Capture requires an explicit output directory")
            out = Path(capture_dir)
            out.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp/"capture.png", out/"capture.png")
            result["capture"] = str(out/"capture.png")
        result["temporary_project_deleted_on_return"] = True
        source = World(root)
        source.terrains()
        result["source_fingerprint"] = source.fingerprint()
        return result
