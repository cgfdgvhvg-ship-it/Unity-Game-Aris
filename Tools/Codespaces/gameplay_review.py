#!/usr/bin/env python3
"""Read-only, exact-path snapshot of unfinished Humanoid/Gloo work in the owner Codespace.

Executed over the existing GitHub Actions -> gh codespace SSH allowlisted bridge.
Does not alter, reset, save, or synchronize the live Unity working tree.
"""
import hashlib
import io
import json
import pathlib
import re
import subprocess
import sys
import tarfile

ROOT = pathlib.Path("/workspaces/Unity-Game-Aris")
DEST = pathlib.Path("/tmp/aaris-codespaces/gameplay-review")
FILES = (
    "Assets/AarisWorld/Editor/AarisCharacterImport.cs",
    "Assets/AarisWorld/Scripts/AarisBattleActions.cs",
    "Assets/AarisWorld/Scripts/AarisCharacterVisual.cs",
    "Assets/AarisWorld/Scripts/AarisOfflineGlooWall.cs",
    "Assets/AarisWorld/Scripts/AarisOfflineTacticalHUD.cs",
    "Assets/Resources/AarisCharacters/Primary/Animations/clip-sources.json",
    "Assets/Resources/AarisCharacters/Primary/asset-source.json",
    "Assets/Resources/AarisCharacters/Primary/Animations/crouch.fbx",
    "Assets/Resources/AarisCharacters/Primary/Animations/crouch.fbx.meta",
    "Assets/Resources/AarisCharacters/Primary/Animations/crouch_walk.fbx",
    "Assets/Resources/AarisCharacters/Primary/Animations/crouch_walk.fbx.meta",
    "Assets/Resources/AarisCharacters/Primary/Animations/punch.fbx",
    "Assets/Resources/AarisCharacters/Primary/Animations/punch.fbx.meta",
    "Assets/Resources/AarisCharacters/Primary/Animations/run.fbx",
    "Assets/Resources/AarisCharacters/Primary/Animations/run.fbx.meta",
    "Assets/Resources/AarisCharacters/Primary/Animations/walk.fbx",
    "Assets/Resources/AarisCharacters/Primary/Animations/walk.fbx.meta",
)
SECRET_RE = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----|github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|sk-[A-Za-z0-9]{25,}")

def git(*args):
    return subprocess.check_output(("git", "-C", str(ROOT), *args),
        stderr=subprocess.DEVNULL, timeout=35).decode("utf-8", "replace").strip()

def require(cond, label):
    if not cond:
        print("AARIS_GAMEPLAY_REVIEW_" + label)
        raise SystemExit(2)

def add_bytes(tf, name, raw):
    info = tarfile.TarInfo(name)
    info.size = len(raw)
    info.mode = 0o600
    info.mtime = 0
    tf.addfile(info, io.BytesIO(raw))

def main():
    require((ROOT / ".git").exists(), "SOURCE_UNAVAILABLE")
    require(git("rev-parse", "--is-inside-work-tree") == "true", "INVALID_REPOSITORY")
    src = git("rev-parse", "HEAD")
    require(bool(re.fullmatch("[0-9a-f]{40}", src)), "INVALID_HEAD")
    changed = set(git("diff", "--name-only", "HEAD", "--", *FILES).splitlines())
    require(bool(changed) and changed.issubset(set(FILES)), "NO_MATCHING_CHANGES")
    entries = []
    total = 0
    for path in FILES:
        if path not in changed:
            continue
        full = ROOT / path
        require(full.is_file() and not full.is_symlink(), "UNSAFE_SOURCE_FILE")
        require(full.stat().st_size < 28 * 1024 * 1024, "SOURCE_TOO_LARGE")
        raw = full.read_bytes()
        total += len(raw)
        require(total < 85 * 1024 * 1024, "PACKAGE_TOO_LARGE")
        require(not (raw.startswith(b"version https://git-lfs.github.com/spec/v1") and
                     path.endswith(".fbx")), "LFS_POINTER_NOT_ANIMATION")
        if path.endswith((".cs", ".json", ".meta")):
            require(SECRET_RE.search(raw) is None, "SECRET_GUARD")
        entries.append({"path":path,"sha256":hashlib.sha256(raw).hexdigest(),
                        "bytes":len(raw),"lfs":git("check-attr","filter","--",path).endswith(": lfs"),
                        "sourceIndexBlob":git("rev-parse", "HEAD:"+path)})
    require(any(x["path"].endswith(".cs") for x in entries), "NO_SCRIPT_CHANGES")
    # The scope is deliberately small: unrelated native trees, sky, terrain, props,
    # 793 LFS source assets, and Editor settings remain untouched.
    manifest = {"kind":"aaris_live_gameplay_snapshot_v1",
                "sourceHead":src,
                "files":entries,
                "changedCount":len(entries)}
    DEST.mkdir(parents=True, exist_ok=True)
    target = DEST / "source.tar.gz"
    with tarfile.open(target, "w:gz") as tar:
        add_bytes(tar,"manifest.json",(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode())
        for e in entries:
            path = e["path"]
            raw = (ROOT/path).read_bytes()
            require(len(raw)==e["bytes"] and
                    hashlib.sha256(raw).hexdigest()==e["sha256"], "SOURCE_CHANGED_DURING_CAPTURE")
            add_bytes(tar,"files/"+path,raw)
    require(target.stat().st_size < 85*1024*1024, "ARCHIVE_TOO_LARGE")
    print("AARIS_GAMEPLAY_SNAPSHOT_READ_ONLY")
    print("gameplay_changed_files="+str(len(entries)))
    print("gameplay_lfs_files="+str(sum(x["lfs"] for x in entries)))
    print("gameplay_archive_bytes="+str(target.stat().st_size))
    print("gameplay_source_head="+src)
    print("AARIS_GAMEPLAY_SOURCE_WORKTREE_PRESERVED")

if __name__=="__main__":
    main()
