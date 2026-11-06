#!/usr/bin/env python3
"""Externally hosted GitHub Actions -> user Codespace, no issue-comment inbox.

The GITHUB_TOKEN cannot start a user's personal Codespace. Keep a separate
Codespaces-scoped credential in repository Actions secret AARIS_CODESPACE_TOKEN.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY = "sundamunda289-art/Unity-Game-Aris"
OWNER = "sundamunda289-art"
BRANCH = "ai/codespace-jobs"
CODESPACE = "redesigned-space-train-gxp5jwvq94wg2wvw6"
QUEUE = ".aaris/jobs/"
ID_RE = re.compile(r"[a-z][a-z0-9-]{3,55}\Z")
API = f"https://api.github.com/user/codespaces/{CODESPACE}"
MAX_OUTPUT = 18000

# Every core source read is pinned to the expected full HEAD supplied by the AI.
# GitHub Actions verifies that this SHA is the actual main ref at fetch time.
# The Unity destination remains a guarded disposable scratch copy.
MAIN_TREE_ROOT = "Assets/TerrainDemoScene_URP/Prefabs/Trees/"
MAIN_SHADER_MATERIALS = tuple(
    MAIN_TREE_ROOT + folder + "/Materials/" + name + ".mat"
    for folder, names in (
        ("Conifer", ("Conifer_Branches", "Conifer_Billboard")),
        ("Cypress", ("Cypress_Forest_Desktop", "Cypress_Forest_Desktop_Billboard")),
        *((f"Pines/Pine_{letter}", (f"Pine_{letter}", f"Pine_{letter}_Billboard"))
          for letter in "ABCD"),
    ) for name in names
)
MAIN_TREE_PREFABS = tuple(
    MAIN_TREE_ROOT + stem + ".prefab"
    for stem in ("Conifer/Conifer", "Cypress/Cypress_Forest_Desktop",
                 *(f"Pines/Pine_{letter}/Pine_{letter}" for letter in "ABCD"))
)
MAIN_RUNTIME_FILES = ("Assets/AarisWorld/Scripts/AarisThirdPersonPlayer.cs",)
MAIN_EDITOR_CHECKS = (
    "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity",
    "ProjectSettings/QualitySettings.asset",
    "ProjectSettings/GraphicsSettings.asset",
    "Packages/manifest.json",
)
MAIN_CORE_PATHS = MAIN_SHADER_MATERIALS + MAIN_TREE_PREFABS + MAIN_RUNTIME_FILES




class JobError(Exception):
    pass


def validate_job(data: dict, *, expected_file: str | None = None) -> dict:
    if not isinstance(data, dict) or set(data) != {"id", "operation", "args"}:
        raise JobError("job requires exactly id, operation and args")
    ident = data["id"]
    op = data["operation"]
    if not isinstance(ident, str) or not ID_RE.fullmatch(ident):
        raise JobError("invalid job id")
    if op not in {"unity_software_graphics_start", "unity_software_graphics_status", "unity_virtual_gui_restart_after_license", "unity_cli_license_activate", "unity_keyring_setup", "unity_keyring_status", "unity_cli_install_start", "unity_cli_login_start", "unity_cli_auth_status", "unity_desktop_deps_start", "unity_desktop_deps_status", "unity_recovery_diagnostics", "unity_tmp_install_start", "unity_tmp_install_status", "codespace_machine_upgrade", "diagnose", "desktop_xterm", "desktop_diagnose", "unity_gui", "unity_diagnostics", "desktop_tools", "desktop_snapshot", "unity_terms_accept", "unity_low_disk_stop", "unity_low_disk_pause", "unity_resume_paused", "codespace_machines", "system_storage_audit", "runtime_mount_probe", "safe_archives_audit", "safe_archives_cleanup", "unity_lfs_preflight", "unity_scratch_reconcile", "unity_tree_v2_preview", "unity_forest_stage", "unity_forest_x11_probe", "unity_forest_editor_refresh", "unity_forest_menu_snapshot", "unity_forest_recompile", "unity_forest_crash_report", "unity_forest_one_shot_plan", "unity_forest_one_shot_apply", "unity_forest_baseline_probe", "unity_forest_treeonly_prepare", "unity_forest_treeonly_tune", "unity_map_camera_capture", "unity_render_backend_probe", "unity_shader_ab_preflight", "unity_shader_ab_apply", "unity_shader_ab_restore", "unity_main_core_sync", "unity_house_gallery_start", "unity_house_gallery_export", "unity_house_gallery_diagnose", "unity_house_gallery_refresh", "unity_house_bridge_gallery_start", "unity_house_bridge_gallery_export", "unity_house_bridge_gallery_partial_export", "unity_house_bridge_gallery_diagnose", "unity_house_helper_quarantine", "unity_sync_auth", "unity_sync_status", "unity_sync_arm", "unity_sync_dry_run", "unity_sync_save_session", "unity_sync_watch_start", "unity_session_status", "unity_session_stop_simulation", "unity_session_checkpoint", "unity_session_recover", "unity_batch_launch", "unity_batch_status", "unity_virtual_gui_launch", "unity_virtual_gui_status", "unity_gui_house_search", "unity_sceneview_prepare", "unity_sceneview_refresh", "unity_virtual_live", "unity_virtual_result", "unity_virtual_frame", "unity_live", "unity_result", "unity_frame", "world_site", "storage_audit", "lfs_verify_chunk", "prune_caches", "unity_version", "world_doctor", "terminal_readonly"}:
        raise JobError("unsupported operation")
    args = data["args"]
    if not isinstance(args, list) or len(args) > 16 or any(
        not isinstance(a, str) or not (0 < len(a) < 500) for a in args
    ):
        raise JobError("args must be short strings")
    if op in {"unity_live", "unity_virtual_live"}:
        if len(args) != 1:
            raise JobError("unity_live requires one short JSON request")
        try:
            from Tools.World.ai_codespace_executor import validate_live_payload
            validate_live_payload(json.loads(args[0]))
        except ImportError:
            # Queue source layout doesn't have Tools as a Python package in
            # every legacy checkout; remote executor validates independently.
            if not args[0].startswith("{") or len(args[0]) > 500:
                raise JobError("invalid Unity live request")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise JobError("invalid live Unity request: " + str(exc)[:160])
    elif op in {"unity_result", "unity_frame", "unity_virtual_result", "unity_virtual_frame"}:
        if len(args) != 1 or not ID_RE.fullmatch(args[0]):
            raise JobError("expected one previously issued Unity job ID")
    elif op == "world_site":
        import math
        if len(args)!=3:
            raise JobError("world_site requires x z radius")
        try:
            x,z,radius=map(float,args)
        except ValueError:
            raise JobError("invalid world_site coordinates")
        if not all(math.isfinite(v) for v in (x,z,radius)) or max(abs(x),abs(z))>10000 or not 1<=radius<=150:
            raise JobError("world_site coordinates outside inspected bounds")
    elif op == "unity_map_camera_capture":
        if len(args)!=1 or args[0] not in {"forest-west","forest-south","mountain-east"}:
            raise JobError("Unity capture requires a reviewed real map camera zone")
    elif op == "unity_forest_one_shot_apply":
        if (len(args)!=2 or args[0] not in {"1_1","1_2","2_1","2_2"} or
            not re.fullmatch(r"[a-f0-9]{64}",args[1])):
            raise JobError("Forest one-shot apply requires one allowed tile ID and exact SHA256")
    elif op == "unity_house_bridge_gallery_diagnose":
        if len(args)!=1 or not ID_RE.fullmatch(args[0]):
            raise JobError("Native house photo diagnosis needs exact survey ID")
    elif op in {"unity_house_bridge_gallery_export","unity_house_bridge_gallery_partial_export"}:
        if len(args)!=1 or not ID_RE.fullmatch(args[0]):
            raise JobError("Bridge gallery export needs exact previous survey ID")
    elif op == "unity_house_gallery_diagnose":
        if len(args)!=1 or not ID_RE.fullmatch(args[0]):
            raise JobError("House gallery diagnosis requires prior job ID")
    elif op == "unity_house_gallery_export":
        if len(args)!=1 or not ID_RE.fullmatch(args[0]):
            raise JobError("Photo gallery export requires exact prior job ID")
    elif op == "lfs_verify_chunk":
        if len(args) != 1 or not re.fullmatch(r"(?:0|[1-9][0-9]{0,4})", args[0]):
            raise JobError("lfs_verify_chunk requires one numeric cursor")
    elif op == "unity_main_core_sync":
        if len(args) != 1 or not re.fullmatch(r"[0-9a-f]{40}", args[0]):
            raise JobError("unity_main_core_sync requires reviewed exact main HEAD SHA")
    elif op != "terminal_readonly" and args:
        raise JobError("this operation takes no arguments")
    if op == "terminal_readonly":
        validate_readonly_argv(args)
    if expected_file is not None and expected_file != f"{QUEUE}{ident}.json":
        raise JobError("filename/job id mismatch")
    return data


def validate_readonly_argv(args: list[str]):
    if not args:
        raise JobError("missing terminal command")
    command = args[0]
    allowed = {"pwd", "df", "free", "ps", "stat", "ls", "du", "glxinfo", "pgrep"}
    if command not in allowed:
        raise JobError("terminal_readonly supports only fixed diagnostic commands")
    if any(a.startswith("-") and ("exec" in a or "delete" in a) for a in args[1:]):
        raise JobError("option not supported")
    if any(a.startswith("/") and not (a.startswith("/workspaces/") or a.startswith("/home/codespace/")) for a in args[1:]):
        raise JobError("only workspace and Codespace home file paths are allowed")
    if any(a in {";", "&&", "|", ">", "<", "`", "$("} for a in args[1:]):
        raise JobError("shell syntax not supported")


def select_job(event: dict, workspace: Path, sha: str):
    if event.get("ref") != f"refs/heads/{BRANCH}":
        raise JobError("job must come from the dedicated queue branch")
    if event.get("repository", {}).get("full_name") != REPOSITORY:
        raise JobError("wrong repository")
    if event.get("sender", {}).get("login", "").casefold() != OWNER.casefold():
        raise JobError("job must be submitted by Codespace owner")
    head = event.get("head_commit") or {}
    if event.get("after") != sha or (head.get("id") not in (None, sha)):
        raise JobError("push commit and checked-out HEAD do not match")
    # GitHub Actions push payloads omit added/modified/removed arrays.
    # Inspect the actual checked-out Git commit rather than trusting webhook metadata.
    diff = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", sha],
        cwd=workspace, text=True, capture_output=True, timeout=20, check=False,
    )
    if diff.returncode != 0:
        raise JobError("cannot inspect job commit diff: " + diff.stderr[-300:])
    changes = [line.split("\t", 1) for line in diff.stdout.splitlines()]
    if len(changes) != 1 or len(changes[0]) != 2 or changes[0][0] != "A":
        raise JobError("submit exactly one newly added job file, no other changes")
    path = changes[0][1]
    if not isinstance(path, str) or not re.fullmatch(r"\.aaris/jobs/[a-z][a-z0-9-]{3,55}\.json", path):
        raise JobError("new file must be a queue JSON job")
    file = workspace / path
    if not file.is_file() or file.is_symlink() or file.stat().st_size > 4096:
        raise JobError("job is missing, too large or symlinked")
    return validate_job(json.loads(file.read_text(encoding="utf-8")), expected_file=path)


def github_api(method, token, suffix="", *, payload=None, timeout=30):
    req = Request(API + suffix, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Aaris-Codespace-OnDemand/1.0",
    }, data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except HTTPError as exc:
        err = exc.read(500).decode("utf-8", "replace")
        raise JobError(f"Codespaces API {method} status={exc.code}: {err}") from None
    except URLError as exc:
        raise JobError(f"Codespaces API unreachable: {exc.reason}") from None


def start_and_wait(token: str, *, sleep=time.sleep, get=github_api, attempts=30):
    """Cloudflare alone starts/stops the Codespace. SSH transport only checks state."""
    info = get("GET", token)
    if info.get("name") != CODESPACE or info.get("repository", {}).get("full_name") != REPOSITORY:
        raise JobError("Codespace identity/repository mismatch: refusing another Codespace")
    state = info.get("state", "Unknown")
    if state in {"Shutdown", "Stopped", "ShuttingDown"}:
        raise JobError("Codespace is stopped: request Cloudflare lifecycle start before queuing SSH commands")
    if state in {"Unavailable", "Deleted", "Deleting", "Archived", "Failed"}:
        raise JobError(f"Codespace lifecycle state is {state}")
    for i in range(attempts):
        info = get("GET", token)
        state = info.get("state")
        print(f"AARIS: Codespace state {state} (poll {i + 1}/{attempts})", flush=True)
        if state in {"Available", "Running"}:
            return
        if state in {"Shutdown", "Stopped", "ShuttingDown", "Unavailable", "Deleted", "Deleting", "Archived", "Failed"}:
            raise JobError(f"Codespace not ready: {state}; Cloudflare controls lifecycle")
        sleep(5)
    raise JobError("Codespace did not become ready; check Cloudflare status, billing or quota")


def invoke(args, *, env, timeout=90, attempts=3):
    last = None
    for i in range(attempts):
        try:
            r = subprocess.run(args, capture_output=True, text=True, env=env,
                               timeout=timeout, check=False, stdin=subprocess.DEVNULL)
            if r.returncode == 0:
                return r
            last = f"exit {r.returncode}: {(r.stderr or r.stdout)[-1100:]}"
        except subprocess.TimeoutExpired:
            last = f"command timed out ({timeout} s)"
        if i + 1 < attempts:
            print(f"AARIS: remote connection retry {i + 2}/{attempts}", flush=True)
            time.sleep(4)
    raise JobError(f"Remote transfer/SSH failed: {last}")


def execute_remote(job: dict, token: str, workspace: Path, result_file: Path, *, runner=invoke):
    result_file.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    cs = CODESPACE
    remote = "/workspaces/.aaris-world-bridge/ondemand"
    local_script = workspace / "Tools/World/ai_codespace_executor.py"
    if not local_script.is_file():
        raise JobError("remote executor source missing")
    local_job = workspace / QUEUE / (job["id"] + ".json")
    runner(["gh", "codespace", "ssh", "-c", cs, "--", f"mkdir -p {remote}"], env=env, timeout=70)
    runner(["gh", "codespace", "cp", "-e", "-c", cs, str(local_script), f"remote:{remote}/ai_codespace_executor.py"], env=env, timeout=90)
    runner(["gh", "codespace", "cp", "-e", "-c", cs, str(local_job), f"remote:{remote}/{job['id']}.json"], env=env, timeout=90)
    if job["operation"] in {"unity_cli_install_start","unity_cli_login_start","unity_cli_auth_status","unity_cli_license_activate","unity_virtual_gui_restart_after_license","unity_keyring_setup","unity_keyring_status"}:
        secure = workspace / "Tools/World/unity_secure_keyring.py"
        if not secure.is_file() or secure.is_symlink():
            raise JobError("Reviewed Unity Secret Service bootstrap missing")
        runner(["gh","codespace","cp","-e","-c",cs,str(secure),
                f"remote:{remote}/unity_secure_keyring.py"],env=env,timeout=95)
    if job["operation"] in {"unity_cli_install_start","unity_cli_login_start","unity_cli_auth_status","unity_cli_license_activate","unity_virtual_gui_restart_after_license"}:
        source = workspace / "Tools/World/unity_cli_auth_bootstrap.py"
        if not source.is_file() or source.is_symlink():
            raise JobError("Approved official Unity CLI auth bootstrap missing")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/unity_cli_auth_bootstrap.py"],env=env,timeout=95)
    if job["operation"] in {"unity_tmp_install_start","unity_tmp_install_status","unity_desktop_deps_start","unity_desktop_deps_status","unity_software_graphics_start","unity_software_graphics_status"}:
        source = workspace / "Tools/World/unity_tmp_editor_installer.py"
        if not source.is_file() or source.is_symlink():
            raise JobError("Pinned Unity temporary editor installer missing")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/unity_tmp_editor_installer.py"],env=env,timeout=105)
    if job["operation"] == "unity_house_gallery_start":
        # Editor-only source is staged outside the owner's original Git checkout.
        helper=workspace/"Tools/World/AarisHousePhotoSurvey.cs"
        if not helper.is_file() or helper.is_symlink():
            raise JobError("Reviewed Unity house gallery authoring source unavailable")
        runner(["gh","codespace","cp","-e","-c",cs,str(helper),
                f"remote:{remote}/AarisHousePhotoSurvey.cs"],env=env,timeout=105)
    if job["operation"] == "unity_main_core_sync":
        # Source is frozen by exact commit and an allowlisted path list, fetched
        # only in the GitHub Actions ephemeral checkout, not the owner's worktree.
        import tarfile
        import hashlib
        import io
        import tempfile
        # One scoped, ephemeral GitHub read-credential adapter for every AI.
        # Never reuse the Codespaces lifecycle token for repository git access.
        from ai_master_github_auth import checked_fetch_main, MasterAuthError
        try:
            checked_fetch_main(workspace, job["args"][0])
        except MasterAuthError as exc:
            raise JobError(str(exc)) from None
        def source_data(path):
            result=subprocess.run(
                ["git","show",job["args"][0]+":"+path],cwd=workspace,
                capture_output=True,timeout=22,check=False)
            if result.returncode or len(result.stdout)>8*1024*1024:
                raise JobError("Reviewed source file missing/oversized: "+path)
            return result.stdout
        paths = MAIN_CORE_PATHS + MAIN_EDITOR_CHECKS
        manifest = {"commit":job["args"][0],"files":{},"checks":{}}
        archive = Path(tempfile.gettempdir()) / ("aaris-verified-core-"+job["id"]+".tar")
        if archive.exists() or archive.is_symlink():
            raise JobError("Existing verified core bundle")
        with tarfile.open(archive,"w") as pack:
            for path in paths:
                buf=source_data(path)
                digest=hashlib.sha256(buf).hexdigest()
                if path in MAIN_CORE_PATHS:
                    manifest["files"][path]=digest
                    info=tarfile.TarInfo("source/"+path)
                    info.size=len(buf)
                    info.mode=0o600
                    pack.addfile(info,io.BytesIO(buf))
                else:
                    manifest["checks"][path]=digest
            info=tarfile.TarInfo("manifest.json")
            content=json.dumps(manifest,sort_keys=True).encode()
            info.size=len(content)
            info.mode=0o600
            pack.addfile(info,io.BytesIO(content))
        if archive.stat().st_size > 8*1024*1024:
            raise JobError("Unexpectedly large reviewed source bundle")
        runner(["gh","codespace","cp","-e","-c",cs,str(archive),
                f"remote:{remote}/main-core-{job['id']}.tar"],env=env,timeout=115)
        archive.unlink()
    if job["operation"] == "unity_batch_launch":
        source = workspace / "Tools/World/AarisBatchProbe.cs"
        if not source.is_file():
            raise JobError("Reviewed headless Scene audit C# script not available")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/AarisBatchProbe.cs"],env=env,timeout=90)
    if job["operation"] == "unity_session_recover":
        probe = workspace / "Tools/World/AarisBatchProbe.cs"
        if not probe.is_file():
            raise JobError("Reviewed native Unity Editor scene probe not found")
        runner(["gh","codespace","cp","-e","-c",cs,str(probe),
                f"remote:{remote}/AarisBatchProbe.cs"],env=env,timeout=90)
    if job["operation"] in {"unity_session_status","unity_session_stop_simulation","unity_session_checkpoint","unity_session_recover"}:
        source = workspace / "Tools/World/unity_session_checkpoint.py"
        if not source.is_file():
            raise JobError("Approved Unity restart checkpoint script missing")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/unity_session_checkpoint.py"],env=env,timeout=90)
    if job["operation"] in {"unity_sync_auth","unity_sync_status",
                            "unity_sync_arm","unity_sync_dry_run",
                            "unity_sync_watch_start"}:
        source = workspace / "Tools/World/unity_batched_autosync.py"
        if not source.is_file():
            raise JobError("Reviewed Unity batching source missing")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/unity_batched_autosync.py"],env=env,timeout=90)
    if job["operation"] == "unity_forest_stage":
        # Approved one-time native forest authoring utilities go into staging;
        # the remote executor may touch only the disposable Unity scratch copy.
        approved=[
            ("Tools/World/AarisForestCoreAuthoring.cs","AarisForestCoreAuthoring.cs"),
            ("Assets/AarisWorld/Editor/AarisLiveEditorBridge.cs","AarisLiveEditorBridge.cs"),
        ]
        for relative,leaf in approved:
            source=workspace/relative
            if not source.is_file() or source.is_symlink():
                raise JobError("Reviewed native forest staging source unavailable")
            runner(["gh","codespace","cp","-e","-c",cs,str(source),
                    f"remote:{remote}/{leaf}"],env=env,timeout=100)
    if job["operation"] == "unity_map_camera_capture":
        source=workspace/"Tools/World/AarisMapCameraOneShot.cs"
        if not source.is_file() or source.is_symlink():
            raise JobError("Reviewed scratch-only Unity camera source missing")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/AarisMapCameraOneShot.cs"],env=env,timeout=105)
    if job["operation"] == "unity_forest_treeonly_tune":
        source=workspace/"Tools/World/AarisForestCoreAuthoring.cs"
        if not source.is_file() or source.is_symlink():
            raise JobError("Reviewed tree-only width tuning C# missing")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/AarisForestCoreAuthoring.cs"],env=env,timeout=100)
    if job["operation"] == "unity_forest_treeonly_prepare":
        for rel, name in (
            ("Tools/World/AarisForestCoreAuthoring.cs","AarisForestCoreAuthoring.cs"),
            ("Tools/World/AarisForestOneShot.cs","AarisForestOneShot.cs"),
        ):
            source=workspace/rel
            if not source.is_file() or source.is_symlink():
                raise JobError("Reviewed tree-only Unity authoring source missing")
            runner(["gh","codespace","cp","-e","-c",cs,str(source),
                    f"remote:{remote}/{name}"],env=env,timeout=105)
    if job["operation"] in {"unity_forest_one_shot_plan","unity_forest_one_shot_apply"}:
        source=workspace/"Tools/World/AarisForestOneShot.cs"
        if not source.is_file() or source.is_symlink():
            raise JobError("Reviewed scratch-only Unity one-shot authoring source not found")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/AarisForestOneShot.cs"],env=env,timeout=110)
    if job["operation"] == "unity_tree_v2_preview":
        source = workspace / "Tools/World/unity_tree_v2_preview.py"
        if not source.is_file() or source.is_symlink():
            raise JobError("Reviewed v2 SpeedTree scratch-only source stage missing")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/unity_tree_v2_preview.py"],env=env,timeout=110)
    if job["operation"] == "unity_scratch_reconcile":
        source = workspace / "Tools/World/unity_scratch_reconcile.py"
        if not source.is_file():
            raise JobError("Reviewed scratch reconciliation helper missing")
        runner(["gh","codespace","cp","-e","-c",cs,str(source),
                f"remote:{remote}/unity_scratch_reconcile.py"],env=env,timeout=90)
    if job["operation"] == "unity_lfs_preflight":
        source = workspace / "Tools/World/unity_lfs_preflight.py"
        if not source.is_file():
            raise JobError("Reviewed read-only LFS preflight missing from queue branch")
        runner(["gh", "codespace", "cp", "-e", "-c", cs, str(source),
                f"remote:{remote}/unity_lfs_preflight.py"], env=env, timeout=90)
    if job["operation"] in {"world_site", "world_doctor"}:
        # Stage the reviewed sensor outside the owner's dirty checkout. The
        # live worktree may be on an older branch missing this file.
        source = workspace / "Tools/World/ai_world_observe.py"
        if not source.is_file():
            raise JobError("Read-only world sensor missing from trusted queue branch")
        runner(["gh", "codespace", "cp", "-e", "-c", cs, str(source),
                f"remote:{remote}/ai_world_observe.py"], env=env, timeout=90)
    if job["operation"] in {"unity_gui", "unity_live", "unity_result"}:
        # Trusted reviewed bridge sources are transferred to a staging folder,
        # never to the owner's dirty Unity project by GitHub CLI directly.
        for leaf in ("AarisLiveEditorBridge.cs", "AarisLiveEditorBridge.cs.meta"):
            source = workspace / "Assets/AarisWorld/Editor" / leaf
            if not source.is_file():
                raise JobError("Native Unity editor bridge missing from checked-out job source")
            runner(["gh","codespace","cp","-e","-c",cs,str(source),f"remote:{remote}/{leaf}"],
                   env=env, timeout=90)
    proc = runner(["gh", "codespace", "ssh", "-c", cs, "--",
                   f"python3 {remote}/ai_codespace_executor.py {remote}/{job['id']}.json"],
                  env=env, timeout=125, attempts=1)
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, TypeError):
        raise JobError("remote executor returned invalid JSON")
    if not isinstance(result, dict) or result.get("id") != job["id"] or result.get("operation") != job["operation"]:
        raise JobError("remote result identity mismatch")
    if result.get("ok") and job["operation"] in {"unity_frame", "unity_virtual_frame", "desktop_snapshot", "unity_map_camera_capture"}:
        # Screenshot stays out of Git history. Copy to short-lived Actions artifact;
        # remove original only after secure remote copy and size check.
        frame_id=job["id"] if job["operation"] in {"desktop_snapshot","unity_map_camera_capture"} else job["args"][0]
        remote_frame=(f"/tmp/aaris-unity-batch/control/frames/{frame_id}.jpg"
                      if job["operation"] in {"unity_virtual_frame","unity_map_camera_capture"}
                      else f"/home/codespace/.aaris-desktop/frames/{frame_id}.jpg")
        local_frame=result_file.parent/(frame_id+".jpg")
        runner(["gh","codespace","cp","-e","-c",cs,f"remote:{remote_frame}",str(local_frame)],
               env=env,timeout=90)
        info=json.loads(result.get("stdout","{}"))
        if not local_frame.is_file() or local_frame.stat().st_size!=info.get("bytes"):
            raise JobError("Unity screenshot transfer size check failed; retaining source")
        runner(["gh","codespace","ssh","-c",cs,"--",f"rm -f -- {remote_frame}"],env=env,timeout=65)
        print("AARIS_FRAME_STAGED=",frame_id,local_frame.stat().st_size,flush=True)
    if result.get("ok") and job["operation"] in {"unity_house_bridge_gallery_export",
                                                     "unity_house_bridge_gallery_partial_export"}:
        name=job["args"][0]
        import hashlib
        archive_name = name + ("-partial" if job["operation"].endswith("_partial_export") else "")
        remote_zip=f"/tmp/aaris-unity-batch/control/house-exports/{archive_name}.zip"
        local_zip=result_file.parent/(archive_name+".zip")
        runner(["gh","codespace","cp","-e","-c",cs,f"remote:{remote_zip}",str(local_zip)],
                env=env,timeout=120)
        info=json.loads(result.get("stdout","{}"))
        if (not local_zip.is_file() or
                local_zip.stat().st_size!=info.get("bytes") or
                hashlib.sha256(local_zip.read_bytes()).hexdigest()!=info.get("sha256")):
            raise JobError("Bridge house gallery ZIP transfer checksum mismatch")
        print("AARIS_NATIVE_HOUSE_GALLERY_STAGED",name,local_zip.stat().st_size,flush=True)
    if result.get("ok") and job["operation"] == "unity_house_gallery_export":
        # The validated archive is temporarily copied to a one-day Actions
        # artifact; neither JPEG nor metadata are committed to the game repo.
        name=job["args"][0]
        remote_zip=f"/tmp/aaris-unity-batch/control/house-exports/{name}.zip"
        local_zip=result_file.parent/(name+".zip")
        runner(["gh","codespace","cp","-e","-c",cs,f"remote:{remote_zip}",
                str(local_zip)],env=env,timeout=120)
        import hashlib
        info=json.loads(result.get("stdout","{}"))
        if (not local_zip.is_file() or
                local_zip.stat().st_size!=info.get("bytes") or
                hashlib.sha256(local_zip.read_bytes()).hexdigest()!=info.get("sha256")):
            raise JobError("House gallery ZIP transfer hash mismatch")
        print("AARIS_HOUSE_GALLERY_STAGED",name,local_zip.stat().st_size,flush=True)
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("AARIS_RESULT_JSON=" + json.dumps(result, ensure_ascii=False)[:MAX_OUTPUT], flush=True)
    if not result.get("ok"):
        raise JobError("remote operation reported failure (see result artifact)")


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--event", type=Path, required=True)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--result-dir", type=Path, required=True)
    args = p.parse_args(argv)
    job = None
    result = args.result_dir / "failure.json"
    try:
        event = json.loads(args.event.read_text())
        job = select_job(event, args.workspace, args.sha)
        result = args.result_dir / (job["id"] + ".json")
        token = os.getenv("AARIS_CODESPACE_TOKEN", "")
        if not token:
            raise JobError("SETUP_REQUIRED: add repository Actions secret AARIS_CODESPACE_TOKEN; it requires Codespaces lifecycle admin write, Codespaces read and permission for gh codespace ssh")
        if job["operation"] in {"codespace_machines", "codespace_machine_upgrade"}:
            # Only the existing named Codespace; no other machine is modified.
            current = github_api("GET", token)
            if (current.get("name") != CODESPACE or current.get("repository", {}).get("full_name") != REPOSITORY):
                raise JobError("Codespace identity mismatch before machine inspection")
            info = github_api("GET", token, "/machines")
            options = info.get("machines", []) if isinstance(info, dict) else []
            safe = [{"name": m.get("name"), "display_name": m.get("display_name"),
                     "cpus": m.get("cpus"), "memory_in_bytes": m.get("memory_in_bytes"),
                     "storage_in_bytes": m.get("storage_in_bytes")}
                    for m in options if isinstance(m, dict)]
            current_machine = current.get("machine") or {}
            outcome = {"machines":safe,"current_machine":{
                "name":current_machine.get("name"),"cpus":current_machine.get("cpus"),
                "memory_in_bytes":current_machine.get("memory_in_bytes"),
                "storage_in_bytes":current_machine.get("storage_in_bytes")},
                "codespace_state":current.get("state")}
            if job["operation"] == "codespace_machine_upgrade":
                target = next((m for m in safe if m["name"] == "standardLinux32gb"), None)
                if target is None or int(target.get("storage_in_bytes") or 0) < int(current_machine.get("storage_in_bytes") or 0):
                    raise JobError("Available 4-core upgrade missing or would shrink persistent disk")
                if current_machine.get("name") == target["name"]:
                    outcome["change"] = "already_on_highest_offered_ram"
                else:
                    # Only an explicit owner job may change billable machine type.
                    # GitHub applies same-storage changes at the next Codespace restart.
                    updated = github_api("PATCH", token, payload={"machine":"standardLinux32gb"})
                    outcome["change"] = "machine_update_requested"
                    outcome["requested_machine"] = "standardLinux32gb"
                    outcome["api_machine_name"] = (updated.get("machine") or {}).get("name")
                    outcome["requires_restart"] = True
            response = {"id":job["id"],"operation":job["operation"],"ok":True,
                        "exit_code":0,"stdout":json.dumps(outcome),"stderr":""}
            result.parent.mkdir(parents=True,exist_ok=True)
            result.write_text(json.dumps(response,ensure_ascii=False,indent=2))
            print("AARIS_RESULT_JSON="+json.dumps(response),flush=True)
            return 0
        start_and_wait(token)
        execute_remote(job, token, args.workspace, result)
        print("AARIS_JOB_COMPLETE", job["id"], flush=True)
        return 0
    except (JobError, ValueError, OSError, json.JSONDecodeError) as exc:
        args.result_dir.mkdir(parents=True, exist_ok=True)
        safe = str(exc)
        # No exceptions should echo tokens, but never store accidental contents.
        token = os.getenv("AARIS_CODESPACE_TOKEN", "")
        if token:
            safe = safe.replace(token, "[REDACTED]")
        failure = {"id": job["id"] if job else None, "ok": False, "error": safe}
        result.write_text(json.dumps(failure, ensure_ascii=False, indent=2))
        print("AARIS_JOB_ERROR=" + safe, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())