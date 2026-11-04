#!/usr/bin/env python3
"""Safe Unity + Git LFS preflight for AI-controlled Codespaces.

Default is read-only: never fetches LFS, changes the Git checkout, or launches
Unity. Explicit --hydrate-missing only fetches small missing clean LFS assets
after strict disk and source-of-truth checks. This does NOT install Unity Editor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

EXPECTED_EDITOR = "6000.3.26f1"
DEFAULT_EDITOR = Path("/home/codespace/Unity/Hub/Editor/6000.3.26f1/Editor/Unity")
CORE_FILES = (
    "ProjectSettings/ProjectVersion.txt",
    "Packages/manifest.json",
    "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity",
)
LFS_LINE = re.compile(r"^([0-9a-f]{64})\s+[*-]\s+(.+)$")
POINTER = re.compile(
    rb"^version https://git-lfs.github.com/spec/v1\n"
    rb"oid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?", re.M
)
MIN_FREE = 8 * 1024 ** 3
MAX_FETCH = 512 * 1024 ** 2
MAX_FILES = 12


class SafetyError(RuntimeError):
    pass


def git(project: Path, *args: str, timeout: int = 40) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=project, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, check=False,
    )
    if result.returncode:
        raise SafetyError(
            "Git failed: " + " ".join(args[:2]) + ": " +
            result.stderr.decode("utf-8", "replace")[-220:]
        )
    return result.stdout


def protected_paths(project: Path) -> set[str]:
    dirty = git(project, "diff", "--name-only", "-z", "HEAD", "--")
    untracked = git(project, "ls-files", "--others", "--exclude-standard", "-z")
    return {
        value.decode("utf-8", "surrogateescape")
        for value in (dirty + untracked).split(b"\0") if value
    }


def list_lfs(project: Path) -> list[tuple[str, str]]:
    output = git(project, "lfs", "ls-files", "--long", timeout=55)
    result = []
    for line in output.decode("utf-8", "surrogateescape").splitlines():
        found = LFS_LINE.fullmatch(line)
        if not found:
            raise SafetyError("Unrecognized git lfs inventory; refusing fetch")
        name, oid = found.group(2), found.group(1)
        path = Path(name)
        if not name.startswith("Assets/") or path.is_absolute() or ".." in path.parts:
            raise SafetyError("Unexpected Git LFS path; refusing fetch")
        result.append((name, oid))
    if not result:
        raise SafetyError("No Git LFS records; refusing to interpret empty list as synchronized")
    return result


def classify_assets(
    project: Path, entries: list[tuple[str, str]], protected: set[str]
) -> dict:
    status = {"present": 0, "missing": [], "pointers": [],
              "protected": [], "unsafe": []}
    for name, _ in entries:
        path = project / name
        if name in protected:
            status["protected"].append(name)
        elif path.is_symlink():
            status["unsafe"].append(name)
        elif not path.is_file():
            status["missing"].append(name)
        else:
            with path.open("rb") as reader:
                if reader.read(48).startswith(b"version https://git-lfs.github.com/spec/v1"):
                    status["pointers"].append(name)
                else:
                    status["present"] += 1
    return status


def pointer_metadata(project: Path, name: str, oid: str) -> int:
    pointer = git(project, "cat-file", "blob", "HEAD:" + name, timeout=20)
    match = POINTER.match(pointer)
    if not match or match.group(1).decode("ascii") != oid:
        raise SafetyError("Refusing to fetch nonmatching Git LFS pointer: " + name)
    return int(match.group(2))


def hydration_plan(
    project: Path, entries: list[tuple[str, str]], status: dict, free: int
) -> dict:
    targets = set(status["missing"] + status["pointers"])
    selected = [(name, oid) for name, oid in entries if name in targets]
    if status["unsafe"]:
        return {"allowed": False, "reason": "symlinked LFS files present"}
    if len(selected) > MAX_FILES:
        return {"allowed": False, "reason": "too many missing files; manual review"}
    if free < MIN_FREE:
        return {"allowed": False, "reason": "less than 8 GiB persistent disk free"}
    estimated = 0
    try:
        for name, oid in selected:
            estimated += pointer_metadata(project, name, oid)
    except SafetyError as exc:
        return {"allowed": False, "reason": str(exc)}
    if estimated > MAX_FETCH:
        return {"allowed": False, "reason": "LFS fetch size exceeds 512 MiB budget"}
    if free - estimated * 2 < MIN_FREE:
        return {"allowed": False, "reason": "insufficient additional disk headroom"}
    return {"allowed": True, "files": [n for n, _ in selected],
            "estimated_bytes": estimated}


def read_project_version(project: Path) -> str | None:
    path = project / CORE_FILES[0]
    if not path.is_file() or path.is_symlink():
        return None
    match = re.search(
        r"^m_EditorVersion:\s*(\S+)", path.read_text(errors="replace"), re.M
    )
    return match.group(1) if match else None


def run_preflight(
    project: Path, editor: Path, *, hydrate: bool = False
) -> dict:
    if not project.is_dir() or project.is_symlink():
        raise SafetyError("Project path missing or unsafe")
    version = read_project_version(project)
    protected = protected_paths(project)
    entries = list_lfs(project)
    state = classify_assets(project, entries, protected)
    disk = shutil.disk_usage(project)
    core = {
        file: ((project / file).is_file() and not (project / file).is_symlink())
        for file in CORE_FILES
    }
    editor_present = editor.is_file() and not editor.is_symlink()
    report = {
        "project": str(project), "editor": str(editor),
        "editor_present": editor_present,
        "project_version": version,
        "expected_version": EXPECTED_EDITOR,
        "version_matches": version == EXPECTED_EDITOR,
        "core_files_present": core,
        "lfs_total": len(entries), "lfs_present": state["present"],
        "lfs_missing": state["missing"], "lfs_pointers": state["pointers"],
        "lfs_protected": state["protected"], "lfs_unsafe": state["unsafe"],
        "dirty_or_untracked_count": len(protected),
        "persistent_free_gib": round(disk.free / 2 ** 30, 3),
        "assets_unchanged": True,
        "unity_import_started": False,
        "download_attempted": False,
    }
    if version != EXPECTED_EDITOR or not all(core.values()):
        report["status"] = "blocked_project_core"
        return report
    if not editor_present:
        report["status"] = "blocked_editor_not_installed"
        return report
    if state["unsafe"]:
        report["status"] = "blocked_unsafe_symlink"
        return report
    if not state["missing"] and not state["pointers"]:
        report["status"] = "lfs_already_present_no_download"
        return report
    plan = hydration_plan(project, entries, state, disk.free)
    report["hydration"] = plan
    if not hydrate:
        report["status"] = "missing_lfs_dry_run_only"
        return report
    if not plan["allowed"]:
        report["status"] = "blocked_hydration_guard"
        return report
    # Hydrate ONLY clean, missing tracked paths from current HEAD, never
    # run global git lfs pull or reset/checkout over owner's modified work.
    oids = dict(entries)
    report["download_attempted"] = True
    confirmed = []
    for name in plan["files"]:
        git(project, "lfs", "pull", "--include=" + name, "--exclude=", timeout=180)
        target = project / name
        if target.is_symlink() or not target.is_file():
            raise SafetyError("LFS checkout did not create expected file: " + name)
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != oids[name]:
            raise SafetyError("Hydrated LFS SHA-256 mismatch: " + name)
        confirmed.append(name)
    report["hydrated_and_sha_verified"] = confirmed
    report["status"] = "targeted_lfs_hydration_verified"
    report["assets_unchanged"] = not bool(confirmed)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument("--editor", type=Path,
                        default=Path(os.environ.get("AARIS_UNITY_EDITOR", str(DEFAULT_EDITOR))))
    parser.add_argument("--hydrate-missing", action="store_true",
                        help="Explicitly fetch only guarded, missing LFS files")
    args = parser.parse_args(argv)
    try:
        report = run_preflight(args.project, args.editor, hydrate=args.hydrate_missing)
    except (SafetyError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in (
        "lfs_already_present_no_download", "targeted_lfs_hydration_verified"
    ) else 3


if __name__ == "__main__":
    sys.exit(main())
