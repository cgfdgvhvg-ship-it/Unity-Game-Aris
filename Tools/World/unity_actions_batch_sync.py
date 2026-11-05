#!/usr/bin/env python3
"""Owner-only GitHub Actions writer for validated Unity TMP edit batches.

Runs on GitHub-hosted ephemeral runner with GITHUB_TOKEN(contents:write),
not inside the Codespace that has NO Git push credential.
It NEVER modifies original /workspaces Unity files, never commits .meta,
never submits entire Unity Library or frames, and never automatically merges.
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
import tarfile
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
import unity_batched_autosync as sync

OWNER="Aaris-khan-don"
REPO=sync.REPO
CS="musical-carnival-jjxp9r6vw45wfjgvg"
TMP_REMOTE="/tmp/aaris-unity-batch/sync-export"
STAGED_REMOTE="/workspaces/.aaris-world-bridge/ondemand/unity_batched_autosync.py"
ALLOWED_EVENT_OP="unity_sync_save_session"


class RunnerError(Exception):
    pass


def call(cmd,*,token=None,timeout=120,check=True):
    env=os.environ.copy()
    env["GIT_TERMINAL_PROMPT"]="0"
    if token is not None:
        env["GH_TOKEN"]=token
    try:
        p=subprocess.run(cmd,env=env,stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RunnerError("Codespace/GitHub operation timed out or was unavailable") from exc
    if check and p.returncode:
        # Never disclose credential helper output, tokens or GH URLs.
        raise RunnerError("GitHub operation failed: "+cmd[0])
    return p


def choose_mode(event,event_name,workspace):
    if event_name in ("schedule","workflow_dispatch"):
        return "scheduled"
    if event_name!="push":
        return "skip"
    if event.get("ref")!="refs/heads/ai/codespace-jobs":
        return "skip"
    if event.get("repository",{}).get("full_name")!=REPO:
        raise RunnerError("Repository mismatch")
    if event.get("sender",{}).get("login","").casefold()!=OWNER.casefold():
        raise RunnerError("Only owner can submit Unity Git LFS Sync jobs")
    paths=[]
    head=event.get("head_commit") or {}
    for field in ("added","modified","removed"):
        paths.extend(head.get(field) or [])
    selected=[n for n in paths if re.fullmatch(r"\.aaris/jobs/[a-z][a-z0-9-]{3,55}\.json",n)]
    if len(selected)!=1 or len(paths)!=1:
        return "skip"
    job=json.loads((workspace/selected[0]).read_text())
    if (not isinstance(job,dict) or job.get("id")!=Path(selected[0]).stem or
        job.get("operation")!=ALLOWED_EVENT_OP or job.get("args")!=[]):
        return "skip"
    return "manual"


def codespace_running(token):
    p=call(["gh","api","/user/codespaces/"+CS],token=token,timeout=40)
    data=json.loads(p.stdout)
    return data.get("state") in ("Available","Active")


def package_from_codespace(token,workspace,force):
    # Ensure reviewed source is staged outside the user's dirty Git checkout.
    source=workspace/"Tools/World/unity_batched_autosync.py"
    if not source.is_file():
        raise RunnerError("Reviewed Unity Sync source unavailable")
    call(["gh","codespace","cp","-e","-c",CS,str(source),
          "remote:"+STAGED_REMOTE],token=token,timeout=90)
    cmd=["gh","codespace","ssh","-c",CS,"--",
         "python3 "+STAGED_REMOTE+" export"+(" --force" if force else "")]
    p=call(cmd,token=token,timeout=150)
    try:
        answer=json.loads(p.stdout.decode("utf-8","replace").strip().splitlines()[-1])
    except (ValueError,IndexError) as exc:
        raise RunnerError("Invalid readback from native Unity autosync exporter") from exc
    if answer.get("status")!="ready_for_actions_upload":
        return answer,None
    for path in (answer.get("manifest"),answer.get("tar")):
        if not isinstance(path,str) or not re.fullmatch(
            r"/tmp/aaris-unity-batch/sync-export/batch-[a-f0-9]{14}\.(?:tar|json)",path
        ):
            raise RunnerError("Unexpected Codespace export path")
    temp=Path(tempfile.mkdtemp(prefix="unity-verified-actions-"))
    try:
        for path in (answer["manifest"],answer["tar"]):
            call(["gh","codespace","cp","-e","-c",CS,
                  "remote:"+path,str(temp/Path(path).name)],token=token,timeout=300)
        return answer,temp
    except Exception:
        shutil.rmtree(temp,ignore_errors=True)
        raise


def verified_manifest(export,folder):
    file=folder/Path(export["manifest"]).name
    bundle=folder/Path(export["tar"]).name
    if file.is_symlink() or not file.is_file() or file.stat().st_size>18000:
        raise RunnerError("Invalid file manifest")
    data=json.loads(file.read_text())
    if data.get("schema")!=1 or data.get("repo")!=REPO:
        raise RunnerError("Unexpected Unity transfer schema/repository")
    branch=data.get("branch")
    if branch is not None and (
        not isinstance(branch,str) or
        not re.fullmatch(r"ai/unity-batched-[A-Za-z0-9-]+",branch)
    ):
        raise RunnerError("Untrusted Git branch in Unity manifest")
    if not isinstance(data.get("scratch_identity"),str):
        raise RunnerError("Transfer source session missing")
    entries=data.get("files")
    if not isinstance(entries,list) or not (1<=len(entries)<=sync.MAX_FILES):
        raise RunnerError("Invalid Unity changedAsset count")
    paths=[]
    total=0
    for item in entries:
        if not isinstance(item,dict):
            raise RunnerError("Invalid Unity manifest asset")
        name=sync.relative_asset(item.get("path"))
        if name in paths:
            raise RunnerError("Duplicate asset in Unity transfer")
        paths.append(name)
        length=item.get("bytes")
        if isinstance(length,bool) or not isinstance(length,int) or not (0<length<=sync.MAX_BYTES):
            raise RunnerError("Invalid Unity native asset size")
        total+=length
        for key in ("sha256","original_sha256","meta_sha256"):
            if not isinstance(item.get(key),str) or not re.fullmatch(r"[a-f0-9]{64}",item[key]):
                raise RunnerError("Invalid SHA-256 in Unity transfer")
        previous=item.get("previously_pushed_sha256")
        if previous is not None and (
            not isinstance(previous,str) or
            not re.fullmatch(r"[a-f0-9]{64}",previous)
        ):
            raise RunnerError("Invalid previously pushed SHA-256")
    if total>sync.MAX_BYTES:
        raise RunnerError("Unexpected Unity batch byte count")
    if bundle.is_symlink() or not bundle.is_file() or (
        bundle.stat().st_size>sync.MAX_BYTES+20*1024**2):
        raise RunnerError("Unity transfer tar unsafe or too large")
    return data,bundle


def write_git_batch(data,bundle,github_token):
    files=data["files"]
    file_names=[x["path"] for x in files]
    with tempfile.TemporaryDirectory(prefix="aaris-actions-lfs-git-") as temp:
        # gh CLI credential helper receives the short-lived repo-scoped
        # GitHub Actions token only via environment, NOT CodeSpace disk.
        call(["gh","auth","setup-git"],token=github_token,timeout=30)
        checkout=Path(temp)/"repo"
        state={"branch":data.get("branch")}
        try:
            branch=sync.clone_branch(checkout,state,file_names)
        except sync.SyncError as exc:
            raise RunnerError("Git clone or review branch unavailable") from exc
        try:
            with tarfile.open(bundle,"r") as archive:
                members=archive.getmembers()
                names={m.name for m in members}
                if names!=set(file_names) or len(members)!=len(file_names):
                    raise RunnerError("Unexpected content in Unity TAR archive")
                for item in files:
                    name=item["path"]
                    member=archive.getmember(name)
                    if not member.isfile() or member.size!=item["bytes"]:
                        raise RunnerError("Unsafe changedAsset TAR member")
                    expected=item.get("previously_pushed_sha256") or item["original_sha256"]
                    remote=sync.command(["git","-C",str(checkout),"show",
                                         "HEAD:"+name],timeout=100).stdout
                    if not sync.match_remote_blob(remote,expected):
                        raise RunnerError("Remote branch changed or base file conflicts")
                    meta=sync.command(["git","-C",str(checkout),"show",
                                       "HEAD:"+name+".meta"],timeout=60).stdout
                    if hashlib.sha256(meta).hexdigest()!=item["meta_sha256"]:
                        raise RunnerError("Original Unity GUID metadata conflict")
                    out=checkout/name
                    out.parent.mkdir(parents=True,exist_ok=True)
                    content=archive.extractfile(member)
                    if content is None:
                        raise RunnerError("Unity TAR member unavailable")
                    digest=hashlib.sha256()
                    with out.open("wb") as destination:
                        while True:
                            chunk=content.read(1024*1024)
                            if not chunk:break
                            destination.write(chunk)
                            digest.update(chunk)
                    if digest.hexdigest()!=item["sha256"]:
                        raise RunnerError("Unity saved core asset SHA-256 mismatch")
            sync.command(["git","-C",str(checkout),"config","user.name",
                          "Aaris Unity AI Session"])
            sync.command(["git","-C",str(checkout),"config","user.email",
                          "aaris-unity-ai@users.noreply.github.com"])
            sync.command(["git","-C",str(checkout),"lfs","install","--local"])
            sync.command(["git","-C",str(checkout),"add","--",*file_names])
            staged=sync.command(["git","-C",str(checkout),"diff","--cached",
                                 "--name-only","-z"]).stdout
            changed={x.decode("utf-8","replace") for x in staged.split(b"\0") if x}
            if not changed or not changed.issubset(set(file_names)):
                raise RunnerError("Unexpected staged Unity file or no real change")
            for item in files:
                if item["path"] not in changed:
                    continue
                a=sync.command(["git","-C",str(checkout),"check-attr","filter",
                                "--",item["path"]]).stdout
                if b": lfs" in a:
                    p=sync.command(["git","-C",str(checkout),"show",":"+item["path"]]).stdout
                    m=sync.POINTER.match(p)
                    if not m or m.group(1).decode()!=item["sha256"]:
                        raise RunnerError("Git LFS index pointer differs from Unity file")
            sync.command(["git","-C",str(checkout),"diff","--cached","--check"])
            sync.command(["git","-C",str(checkout),"commit","-m",
                          "Unity AI verified batch: "+str(len(changed))+" map assets"])
            sync.command(["git","-C",str(checkout),"lfs","push","origin",branch],timeout=300)
            sync.command(["git","-C",str(checkout),"push","origin",
                          "HEAD:refs/heads/"+branch],timeout=300)
            commit=sync.command(["git","-C",str(checkout),"rev-parse","HEAD"]).stdout.decode().strip()
            remote=sync.command(["git","-C",str(checkout),"ls-remote","origin",
                                 "refs/heads/"+branch]).stdout.decode()
            if not remote.startswith(commit+"\t"):
                raise RunnerError("Remote Git ref readback mismatch")
        except sync.SyncError as exc:
            raise RunnerError("Git LFS upload blocked by conflict or missing credential") from exc
    return {"schema":1,"repo":REPO,"branch":branch,"commit":commit,
            "scratch_identity":data["scratch_identity"],
            "pushed":{a["path"]:a["sha256"] for a in files}}


def acknowledge(token,receipt,folder):
    outfile=folder/"sync-receipt.json"
    outfile.write_text(json.dumps(receipt,indent=2))
    destination=TMP_REMOTE+"/sync-receipt.json"
    call(["gh","codespace","cp","-e","-c",CS,str(outfile),
          "remote:"+destination],token=token,timeout=110)
    command="python3 "+STAGED_REMOTE+" ack --receipt "+destination
    response=call(["gh","codespace","ssh","-c",CS,"--",command],token=token,timeout=85)
    try:
        status=json.loads(response.stdout.decode().strip().splitlines()[-1])
    except (ValueError,IndexError) as exc:
        raise RunnerError("Git pushed but Codespace receipt could not be validated") from exc
    if status.get("status")!="actions_remote_verified_and_acknowledged":
        raise RunnerError("Git branch uploaded but session acknowledgement failed")
    return status


def pull_request(github_token,branch):
    env=os.environ.copy()
    env["GH_TOKEN"]=github_token
    view=subprocess.run(["gh","pr","view",branch,"-R",REPO,"--json","url",
                         "--jq",".url"],env=env,text=True,capture_output=True,timeout=40)
    if view.returncode==0 and view.stdout.strip().startswith("https://"):
        return view.stdout.strip()
    new=subprocess.run(["gh","pr","create","-R",REPO,"--head",branch,
                        "--base","main","--title","Unity AI map edits — verified batch session",
                        "--body","Generated from native Unity Editor-saved source assets. "
                        "Changes are batched after idle or explicit Save Session, "
                        "SHA-256-validated, with original working tree untouched. "
                        "Review before merge."],env=env,text=True,
                       capture_output=True,timeout=65)
    return new.stdout.strip() if new.returncode==0 and new.stdout.strip().startswith("https://") else None


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--event",required=True,type=Path)
    p.add_argument("--event-name",required=True)
    p.add_argument("--workspace",required=True,type=Path)
    a=p.parse_args(argv)
    folder=None
    try:
        event=json.loads(a.event.read_text()) if a.event.is_file() else {}
        mode=choose_mode(event,a.event_name,a.workspace)
        if mode=="skip":
            head=event.get("head_commit") or {}
            changes=[p for key in ("added","modified","removed")
                     for p in (head.get(key) or [])]
            print(json.dumps({"status":"skipped_non_save_job",
                              "event_name":a.event_name,
                              "event_ref":event.get("ref"),
                              "event_sender":(event.get("sender") or {}).get("login"),
                              "changed_job_paths":[x for x in changes
                                                   if x.startswith(".aaris/jobs/")][:3],
                              "changed_count":len(changes)}))
            return 0
        owner_token=os.getenv("AARIS_CODESPACE_TOKEN","")
        git_token=os.getenv("GITHUB_TOKEN","")
        if not owner_token or not git_token:
            raise RunnerError("GitHub Actions sync permissions/secrets not configured")
        if not codespace_running(owner_token):
            print(json.dumps({"status":"codespace_stopped_no_tmp_to_sync"}))
            return 0
        export,folder=package_from_codespace(owner_token,a.workspace,mode=="manual")
        if folder is None:
            print(json.dumps(export))
            return 0
        data,bundle=verified_manifest(export,folder)
        receipt=write_git_batch(data,bundle,git_token)
        ack=acknowledge(owner_token,receipt,folder)
        pr=pull_request(git_token,receipt["branch"])
        print(json.dumps({"status":"verified_github_batch_saved",
                          "branch":receipt["branch"],
                          "commit":receipt["commit"],"count":len(receipt["pushed"]),
                          "review_url":pr,"codespace_acknowledged":True,
                          "original_unmodified":True}))
        return 0
    except (RunnerError,sync.SyncError,OSError,ValueError,tarfile.TarError) as exc:
        print(json.dumps({"status":"blocked_no_false_success",
                          "reason":str(exc)[:300],
                          "original_unmodified":True}))
        return 1
    finally:
        if folder is not None:
            shutil.rmtree(folder,ignore_errors=True)


if __name__=="__main__":
    sys.exit(main())
