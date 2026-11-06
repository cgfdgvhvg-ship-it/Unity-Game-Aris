#!/usr/bin/env python3
"""One-time Unity CLI and private OAuth bootstrap; no Unity project edits.
Personal EULA acceptance and account login remain user-controlled.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path("/workspaces/.aaris-world-bridge/ondemand")
CLI=Path.home()/".local/bin/unity"
INSTALLER_URL="https://public-cdn.cloud.unity3d.com/hub/prod/cli/install.sh"
INSTALL_SCRIPT=ROOT/"unity-cli-official-install.sh"
LOG=ROOT/"unity-cli-auth-install.log"
AUTH_LOG=ROOT/"unity-cli-login-private.log"
STATE=ROOT/"unity-cli-auth-state.json"


def record(status, **kw):
    ROOT.mkdir(parents=True,exist_ok=True)
    payload={"state":status,"timestamp":int(time.time()),**kw}
    tmp=ROOT/"unity-cli-auth-state.tmp"
    tmp.write_text(json.dumps(payload),encoding="utf-8")
    tmp.chmod(0o600)
    os.replace(tmp,STATE)


def running(flag):
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():continue
        try:
            s=(p/"cmdline").read_bytes().decode("utf-8","replace")
            if "unity_cli_auth_bootstrap.py" in s and flag in s:return True
        except OSError:continue
    return False


def cli_path():
    if CLI.is_file() and os.access(CLI,os.X_OK):return CLI
    candidate=shutil.which("unity")
    return Path(candidate) if candidate else None


def run_quiet(argv, timeout=20):
    try:
        p=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=timeout,check=False)
        return p.returncode
    except (OSError,subprocess.TimeoutExpired):
        return 127


def safe_url():
    if not AUTH_LOG.is_file() or AUTH_LOG.is_symlink():return None
    data=AUTH_LOG.read_text(errors="replace")[-14000:]
    candidates=re.findall(r'https://[^\\s"\\\\<>]+',data)
    for match in candidates:
        url=match.strip("'),;")
        host=urlparse(url).hostname or ""
        if host=="unity.com" or host.endswith(".unity.com") or host=="unity3d.com" or host.endswith(".unity3d.com"):
            return url[:1800]
    return None


def status():
    binpath=cli_path()
    state={}
    if STATE.is_file() and not STATE.is_symlink() and STATE.stat().st_size<3000:
        try:state=json.loads(STATE.read_text())
        except (OSError,ValueError):pass
    result={"unity_cli_installed":bool(binpath),"installer_running":running("--install-worker"),
            "oauth_worker_running":running("--login-worker"),
            "last_state":state.get("state","not_started"),
            "last_error":state.get("error")}
    if binpath:
        result["authenticated"]=run_quiet([str(binpath),"auth","status","--format","json"],timeout=12)==0
        result["personal_license_active"]=run_quiet([str(binpath),"license","status","--format","json"],timeout=14)==0
        # OAuth URL is intentionally returned only for an explicit status read.
        result["sign_in_url"]=safe_url() if not result["authenticated"] else None
    return result


def worker_install():
    try:
        ROOT.mkdir(parents=True,exist_ok=True)
        if INSTALL_SCRIPT.is_symlink():raise RuntimeError("unsafe installer symlink")
        record("downloading_official_unity_cli")
        r=subprocess.run(["curl","-fsSL","--max-time","90",INSTALLER_URL,"-o",str(INSTALL_SCRIPT)],
              stdin=subprocess.DEVNULL,capture_output=True,timeout=115,check=False)
        if r.returncode or not INSTALL_SCRIPT.is_file() or not 500<INSTALL_SCRIPT.stat().st_size<400000:
            raise RuntimeError("official Unity CLI download failed")
        INSTALL_SCRIPT.chmod(0o600)
        env=os.environ.copy();env["UNITY_CLI_CHANNEL"]="beta";env["HOME"]=str(Path.home())
        record("installing_official_unity_cli")
        with LOG.open("a",encoding="utf-8") as output:
            p=subprocess.run(["bash",str(INSTALL_SCRIPT)],env=env,stdin=subprocess.DEVNULL,
                             stdout=output,stderr=output,timeout=900,check=False)
        if p.returncode or cli_path() is None:raise RuntimeError("Unity CLI install failed; exit "+str(p.returncode))
        record("cli_installed")
    except Exception as e:record("failed",error=type(e).__name__+": "+str(e)[:250])


def worker_login():
    try:
        tool=cli_path()
        if tool is None:raise RuntimeError("Unity CLI missing")
        record("awaiting_unity_id_oauth")
        # The standalone Unity CLI prints the headless auth URL to a private log.
        with AUTH_LOG.open("a",encoding="utf-8") as output:
            os.chmod(AUTH_LOG,0o600)
            env=os.environ.copy();env.pop("DISPLAY",None)
            p=subprocess.run([str(tool),"auth","login","--non-interactive","--format","json"],
                        env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=output,timeout=900,check=False)
        record("authenticated" if p.returncode==0 else "oauth_unfinished",
               error=None if p.returncode==0 else "Unity ID sign-in not completed")
    except Exception as e:record("oauth_failed",error=type(e).__name__+": "+str(e)[:250])


def launch(which):
    ROOT.mkdir(parents=True,exist_ok=True)
    if which=="--install-start" and cli_path():
        return {"status":"already_installed",**status()}
    if which=="--login-start" and not cli_path():
        return {"status":"cli_missing",**status()}
    flag="--install-worker" if which=="--install-start" else "--login-worker"
    if running(flag):return {"status":"already_running",**status()}
    target=LOG if which=="--install-start" else AUTH_LOG
    with target.open("a",encoding="utf-8") as output:
        os.chmod(target,0o600)
        p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),flag],
              stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True)
    return {"status":"started","pid":p.pid,**status()}


if __name__=="__main__":
    if sys.argv[1:]==["--install-worker"]:worker_install()
    elif sys.argv[1:]==["--login-worker"]:worker_login()
    elif sys.argv[1:]==["--status"]:print(json.dumps(status()))
    elif sys.argv[1:] in (["--install-start"],["--login-start"]):
        print(json.dumps(launch(sys.argv[1])))
    else:raise SystemExit("Expected --install-start, --login-start, --status or worker mode")
