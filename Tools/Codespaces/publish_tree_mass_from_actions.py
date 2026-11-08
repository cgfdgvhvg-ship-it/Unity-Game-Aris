#!/usr/bin/env python3
"""Publish only reviewed native SpeedTree bake from the existing Codespace.

The runner receives an allowlisted manifest and tar archive over authenticated
gh codespace ssh, verifies every byte, stages generated .asset files through
Git LFS and pushes a review branch. Never pushes the owner's dirty workspace.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

REPO = "sundamunda289-art/Unity-Game-Aris"
BRANCH = "feat/native-tree-mass-generated-20261108"
GEN = "Assets/AarisWorld/Generated/TreeMass/"
PREFIX = "Assets/TerrainDemoScene_URP/Prefabs/Trees/"
PREFABS = [
    PREFIX+"Conifer/Conifer.prefab",
    PREFIX+"Cypress/Cypress_Forest_Desktop.prefab",
    *[PREFIX+f"Pines/{s}/{s}.prefab" for s in
      ("Pine_A","Pine_B","Pine_C","Pine_D")],
]
MESHES = [GEN+f"{s}_LOD{lod}.asset" for s in
          ("Conifer","Cypress","Pine_A","Pine_B","Pine_C","Pine_D")
          for lod in (0,1,2)]
OTHER = ["Assets/AarisWorld/Generated.meta",
         "Assets/AarisWorld/Generated/TreeMass.meta"]
EXPECTED = sorted(set(PREFABS+OTHER+MESHES+[m+".meta" for m in MESHES]))
assert len(EXPECTED)==44

def run(*argv: str, timeout: int = 300) -> str:
    return subprocess.run(argv,check=True,text=True,capture_output=True,
                          timeout=timeout).stdout.strip()

def fail(reason: str):
    raise RuntimeError(reason)

def main(archive: Path, report: Path):
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        fail("TREE_PUBLISH_REPO_NOT_AUTHORIZED")
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        fail("TREE_PUBLISH_NONMAIN_EVENT")
    if not archive.is_file() or archive.stat().st_size>250_000_000:
        fail("TREE_PUBLISH_PACKAGE_MISSING_OR_OVERSIZED")
    cwd=Path.cwd().resolve()
    with tarfile.open(archive,"r:gz") as tf:
        members=tf.getmembers()
        if not members or any(not v.isfile() or v.name.startswith("/")
                              or ".." in Path(v.name).parts for v in members):
            fail("TREE_PUBLISH_ARCHIVE_UNSAFE")
        names=[m.name for m in members]
        if sorted(names)!=sorted(EXPECTED+["mass-manifest.json"]):
            fail("TREE_PUBLISH_UNEXPECTED_FILE_MANIFEST")
        if sum(v.size for v in members)>240_000_000:
            fail("TREE_PUBLISH_UNCOMPRESSED_ASSETS_OVER_BUDGET")
        meta=tf.extractfile("mass-manifest.json")
        if meta is None:fail("TREE_PUBLISH_MANIFEST_MISSING")
        manifest=json.load(meta)
        if manifest.get("kind")!="aaris_tree_mass_native_editor_bake" or \
           manifest.get("count")!=44 or \
           not re.fullmatch(r"[0-9a-f]{40}",manifest.get("sourceSha","")):
            fail("TREE_PUBLISH_MANIFEST_INVALID")
        records=manifest.get("files",[])
        if sorted(rec.get("path","") for rec in records)!=EXPECTED:
            fail("TREE_PUBLISH_MANIFEST_PATH_MISMATCH")
        contents={}
        for record in records:
            path=record["path"]; member=tf.extractfile(path)
            if member is None:fail("TREE_PUBLISH_MISSING_PAYLOAD")
            raw=member.read()
            if len(raw)!=record["bytes"] or \
               hashlib.sha256(raw).hexdigest()!=record["sha256"]:
                fail("TREE_PUBLISH_CHECKSUM_MISMATCH")
            if path.endswith(".prefab") and \
               (not raw.startswith(b"%YAML") or b"m_Mesh: " not in raw):
                fail("TREE_PUBLISH_PREFAB_NOT_UNITY_YAML")
            if path.endswith(".asset") and \
               (len(raw)<512 or raw[:80].startswith(b"version https://git-lfs.github.com")):
                fail("TREE_PUBLISH_MESH_ASSET_UNHYDRATED")
            contents[path]=raw

    run("git","fetch","--quiet","origin","main",timeout=120)
    head=run("git","rev-parse","origin/main")
    if not re.fullmatch(r"[0-9a-f]{40}",head):
        fail("TREE_PUBLISH_UNVERIFIED_MAIN")
    if run("git","ls-remote","--heads","origin",BRANCH):
        fail("TREE_PUBLISH_REVIEW_BRANCH_ALREADY_EXISTS")
    # GitHub checkout can expose a few historic LFS-tracked non-pointer
    # files as modified. Never reset them; the staged-files allowlist is the
    # final guard against leaking unrelated changes into the review commit.
    initial=subprocess.run(["git","status","--porcelain=v1","-z"],
                           check=True,capture_output=True).stdout
    for entry in initial.decode("utf-8","surrogateescape").split("\0"):
        if not entry:continue
        if len(entry)<4:
            fail("TREE_PUBLISH_RUNNER_STATUS_INVALID")
        if entry[:2]=="??":
            if entry[3:]=="codespace-results/":
                continue  # bounded Actions upload outputs, never staged
            fail("TREE_PUBLISH_RUNNER_UNTRACKED_FILE")
        attr=run("git","check-attr","filter","--",entry[3:])
        if not attr.endswith(": filter: lfs"):
            fail("TREE_PUBLISH_RUNNER_NONLFS_MODIFIED")
    run("git","checkout","-b",BRANCH,"origin/main")
    run("git","lfs","install","--local")
    for path in MESHES:
        run("git","lfs","track","--filename",path)
    for path,raw in contents.items():
        dest=(cwd/path).resolve()
        if not dest.is_relative_to(cwd):
            fail("TREE_PUBLISH_PATH_ESCAPE")
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(raw)
    run("git","add","--",".gitattributes",*EXPECTED,timeout=180)
    staged=run("git","diff","--cached","--name-only").splitlines()
    if sorted(staged)!=sorted(EXPECTED+[".gitattributes"]):
        fail("TREE_PUBLISH_STAGED_FILE_SET_MISMATCH")
    for path in MESHES:
        blob=subprocess.run(["git","show",":"+path],capture_output=True,
                            check=True,timeout=90).stdout
        if not blob.startswith(b"version https://git-lfs.github.com/spec/v1"):
            fail("TREE_PUBLISH_MESH_NOT_LFS_POINTER")
    for prefab in PREFABS:
        if prefab not in staged:fail("TREE_PUBLISH_PREFAB_NOT_MODIFIED")
    run("git","config","user.name","github-actions[bot]")
    run("git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com")
    run("git","commit","-m","Bake realistic mobile SpeedTree trunk and foliage meshes (18 LFS assets)",timeout=240)
    new_commit=run("git","rev-parse","HEAD")
    run("git","push","origin","HEAD:refs/heads/"+BRANCH,timeout=1200)
    # Confirm objects are on LFS remote; original historical objects remain.
    run("git","lfs","push","origin",BRANCH,timeout=1200)
    lfs=run("git","lfs","ls-files")
    if any(Path(p).name not in lfs for p in MESHES):
        # Exact HEAD pointer verification above is authoritative; report this
        # as an integrity issue instead of silently claiming success.
        fail("TREE_PUBLISH_LFS_LIST_INCOMPLETE")
    report.write_text(json.dumps({
        "status":"passed","branch":BRANCH,"commit":new_commit,
        "sourceSha":manifest["sourceSha"],
        "meshAssets":18,"nativePrefabs":6,"allFiles":len(EXPECTED),
        "lfsCommitVerified":True
    },indent=2))
    print("AARIS_TREE_MASS_GIT_LFS_REVIEW_BRANCH_PUBLISHED")
    print("mesh_assets=18")
    print("original_terrain_scene_preserved=yes")

if __name__=="__main__":
    try: main(Path(sys.argv[1]),Path(sys.argv[2]))
    except Exception as exc:
        # Error categories only, no credential-bearing command output.
        print("AARIS_TREE_MASS_PUBLISH_FAILED:"+str(exc).splitlines()[0][:120])
        raise SystemExit(1)
