#!/usr/bin/env python3
"""Validate exact-path Codespace gameplay package; optionally publish a review branch.

Never touches the Codespace working tree. Fails closed on upstream changes, bad
LFS pointers or untrusted archive members. Only runner-local Git is modified.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(os.environ["GITHUB_WORKSPACE"])
BRANCH = "feat/finish-existing-humanoid-gloo-20261110"
PREFIXES = ("Assets/AarisWorld/Editor/AarisCharacterImport.cs",
            "Assets/AarisWorld/Scripts/AarisBattleActions.cs",
            "Assets/AarisWorld/Scripts/AarisCharacterVisual.cs",
            "Assets/AarisWorld/Scripts/AarisOfflineGlooWall.cs",
            "Assets/AarisWorld/Scripts/AarisOfflineTacticalHUD.cs",
            "Assets/Resources/AarisCharacters/Primary/Animations/clip-sources.json",
            "Assets/Resources/AarisCharacters/Primary/asset-source.json")
ANIMS = ("crouch","crouch_walk","punch","run","walk")
ALLOWED = set(PREFIXES) | {
    "Assets/Resources/AarisCharacters/Primary/Animations/"+n+".fbx"+s
    for n in ANIMS for s in ("",".meta")
}

def command(*args, timeout=300, check=True):
    p=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     timeout=timeout,env={**os.environ,"GIT_TERMINAL_PROMPT":"0"})
    if p.returncode and check:
        raise RuntimeError("GIT_OR_TEST_COMMAND_FAILED")
    return p

def git(*args,check=True):
    return command("git",*args,check=check).stdout.decode("utf-8","replace").strip()

def abort(code):
    print("AARIS_GAMEPLAY_"+code, flush=True)
    raise SystemExit(1)

def prepare(path):
    try:
        with tarfile.open(path,"r:gz") as tf:
            members=tf.getmembers()
            names=[m.name for m in members]
            if (not 2<=len(names)<=18 or len(set(names))!=len(names)
                    or not all(m.isfile() and 0<m.size<28*1024*1024 for m in members)
                    or "manifest.json" not in names):
                abort("PACKAGE_MEMBERS_INVALID")
            manifest=json.load(tf.extractfile("manifest.json"))
            entries=manifest.get("files",[])
            if (manifest.get("kind")!="aaris_live_gameplay_snapshot_v1"
                    or not isinstance(entries,list) or not 1<=len(entries)<=17
                    or manifest.get("changedCount")!=len(entries)
                    or not re.fullmatch("[0-9a-f]{40}",manifest.get("sourceHead",""))):
                abort("MANIFEST_INVALID")
            paths=[e.get("path") for e in entries]
            if (len(set(paths))!=len(paths) or not set(paths)<=ALLOWED
                    or set(names)!={"manifest.json"}|{"files/"+p for p in paths}):
                abort("PACKAGE_PATH_SCOPE_INVALID")
            blob={}
            total=0
            for item in entries:
                name=item["path"]
                raw=tf.extractfile("files/"+name).read()
                total+=len(raw)
                if (total>85*1024*1024 or len(raw)!=item["bytes"]
                    or hashlib.sha256(raw).hexdigest()!=item["sha256"]
                    or not re.fullmatch("[0-9a-f]{40}",item["sourceIndexBlob"])):
                    abort("PACKAGE_HASH_MISMATCH")
                if name.endswith(".fbx") and raw.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    abort("FBX_POINTER_NOT_ASSET")
                blob[name]=raw
    except (OSError,KeyError,ValueError,TypeError,tarfile.TarError):
        abort("PACKAGE_CANNOT_VALIDATE")
    return manifest,blob

def main():
    if len(sys.argv)!=3 or sys.argv[2] not in ("audit","publish"):
        abort("INVALID_USAGE")
    archive=Path(sys.argv[1])
    data, blobs=prepare(archive)
    source=data["sourceHead"]
    target=git("rev-parse","HEAD")
    if git("rev-parse","--is-shallow-repository")=="true":
        git("fetch","--unshallow","origin")
    else:
        git("fetch","origin","main")
    try:
        git("cat-file","-e",source+"^{commit}")
    except RuntimeError:
        abort("SOURCE_COMMIT_NOT_FOUND")
    conflicts=[]
    report=[]
    for e in data["files"]:
        p=e["path"]
        old=git("rev-parse",source+":"+p,check=False)
        now=git("rev-parse",target+":"+p,check=False)
        if old!=e["sourceIndexBlob"] or not old or not now:
            abort("SOURCE_INDEX_MISMATCH")
        # Deliberately refuse to overwrite any independently changed main file.
        if old!=now:
            conflicts.append(p)
        attrs=git("check-attr","filter","--",p)
        lfs=attrs.endswith(": lfs")
        if lfs!=bool(e["lfs"]):
            abort("LFS_ATTRIBUTE_MISMATCH")
        report.append({"path":p,"bytes":e["bytes"],"sha256":e["sha256"],
                       "lfs":lfs,"upstreamConflict":old!=now})
    output=ROOT/"codespace-results"
    output.mkdir(exist_ok=True)
    (output/"gameplay-review.json").write_text(json.dumps({
        "status":"conflicts" if conflicts else "ready",
        "sourceHead":source,"mainHead":target,
        "count":len(report),"files":report,"conflicts":conflicts},indent=2)+"\n")
    print("AARIS_GAMEPLAY_PACKAGE_HASHES_VERIFIED")
    print("gameplay_files_checked="+str(len(report)))
    print("gameplay_conflicts="+str(len(conflicts)))
    if conflicts:
        print("AARIS_GAMEPLAY_UPSTREAM_CONFLICT_REVIEW_REQUIRED")
        if sys.argv[2]=="publish":
            abort("PUBLISH_BLOCKED_BY_MAIN_CHANGES")
        return
    if sys.argv[2]=="audit":
        print("AARIS_GAMEPLAY_AUDIT_READ_ONLY_PASS")
        return
    if git("ls-remote","--heads","origin",BRANCH):
        abort("BRANCH_ALREADY_EXISTS")
    git("config","user.name","Aaris Gameplay Reviewer")
    git("config","user.email","aaris-gameplay@users.noreply.github.com")
    git("lfs","install","--local")
    git("switch","-c",BRANCH)
    for p,raw in blobs.items():
        dest=ROOT/p
        if dest.is_symlink() or not dest.parent.exists():
            abort("DESTINATION_INVALID")
        dest.write_bytes(raw)
    git("add","--",*blobs.keys())
    staged=[p for p in git("diff","--cached","--name-only").splitlines() if p]
    if not staged or not set(staged)<=set(blobs):
        abort("STAGED_FILE_SCOPE_INVALID")
    if command("git","diff","--cached","--check",check=False).returncode:
        abort("STAGED_DIFF_WHITESPACE_ERROR")
    git("commit","-m","feat(gameplay): preserve existing Codespace Humanoid and Gloo Wall edits")
    # A new LFS commit is usable only when original hashed binary payloads
    # are uploaded before the branch ref; never rewrite source LFS pointers.
    for p in staged:
        if not p.endswith(".fbx") or not git("check-attr","filter","--",p).endswith(": lfs"):
            continue
        pointer=git("show","HEAD:"+p)
        match=re.search(r"^oid sha256:([0-9a-f]{64})$",pointer,re.M)
        if not match or match.group(1)!=hashlib.sha256(blobs[p]).hexdigest():
            abort("LFS_POINTER_CONTENT_MISMATCH")
        command("git","lfs","push","--object-id","origin",match.group(1),timeout=380)
    git("push","origin","HEAD:refs/heads/"+BRANCH)
    print("AARIS_GAMEPLAY_REVIEW_BRANCH_PUBLISHED")
    print("gameplay_published_files="+str(len(staged)))
    print("gameplay_review_branch="+BRANCH)
    print("gameplay_commit="+git("rev-parse","HEAD"))

if __name__=="__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired):
        abort("UNVERIFIED_ACTION_FAILED")
