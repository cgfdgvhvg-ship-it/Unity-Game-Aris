#!/usr/bin/env python3
"""Codespace-side OAuth; URL is intercepted privately by the Actions controller."""
import os, sys, re, time, queue, threading, subprocess, shutil
from pathlib import Path
from urllib.parse import urlsplit
CLI_DIR=Path("/workspaces/.aaris-unity-cli")
PATHS=[CLI_DIR/"bin/unity",
       Path.home()/".local/bin/unity", Path.home()/".unity/bin/unity",
       Path("/tmp/aaris-unity-runtime/cli/bin/unity"),
       Path("/root/.local/bin/unity"), Path("/home/vscode/.local/bin/unity")]
URL_RE=re.compile(r"auth_url=(https?://[^\s\"'\\]+)|https://[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]+")
def valid(url):
    try:
        p=urlsplit(url); h=(p.hostname or "").lower()
        return p.scheme=="https" and not p.username and not p.password and len(url)<4000 and any(h==s or h.endswith("."+s) for s in ("unity.com","unity3d.com"))
    except ValueError: return False
def extract(line):
    for m in URL_RE.finditer(line):
        u=(m.group(1) or m.group(0)).rstrip("'\"]},)")
        if valid(u): return u
    return None
def check(cli,env,what):
    try:
        p=subprocess.run([cli,what,"status","--format","json","--non-interactive"],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=40)
        return p.returncode==0
    except (OSError,subprocess.TimeoutExpired): return False
def login(cli,env):
    if check(cli,env,"auth"):
        print("UNITY_AUTH_ALREADY_VALID",flush=True);return True
    print("UNITY_AUTH_STARTED",flush=True)
    p=subprocess.Popen([cli,"auth","login","--format","json"],env=env,text=True,encoding="utf-8",errors="replace",stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=1)
    q=queue.Queue()
    def reader():
        try:
            for line in p.stdout: q.put(line)
        finally: q.put(None)
    threading.Thread(target=reader,daemon=True).start()
    sent=set(); deadline=time.monotonic()+420
    try:
        while time.monotonic()<deadline:
            try: line=q.get(timeout=1)
            except queue.Empty:
                if p.poll() is not None: break
                continue
            if line is None: break
            url=extract(line)
            if url and url not in sent:
                sent.add(url)
                print("AARIS_AUTH_LINK="+url,flush=True)
            # NEVER echo any other raw Unity CLI output, emails or tokens.
    finally:
        if p.poll() is None:
            p.terminate()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill()
    if check(cli,env,"auth"):
        print("UNITY_AUTH_VERIFIED",flush=True);return True
    print("UNITY_AUTH_NOT_COMPLETED",flush=True);return False
def main():
    os.umask(0o077)
    CLI_DIR.mkdir(parents=True,exist_ok=True)
    cli=next((str(x) for x in PATHS if x.is_file() and os.access(x,os.X_OK)),shutil.which("unity"))
    if not cli:
        print("UNITY_CLI_BOOTSTRAPPING",flush=True)
        # Unity's current installer installs to ~/.local/bin on Linux, NOT
        # $UNITY_CLI_HOME/bin. Keep CLI auth state on persistent /workspaces.
        folder=Path("/tmp/aaris-codespaces")
        folder.mkdir(parents=True,exist_ok=True)
        script=folder/"unity-cli-official-install.sh"
        try:
            got=subprocess.run(["curl","-fsSL","--retry","2",
                                "--connect-timeout","30","--max-time","150",
                                "https://unity.com/install.sh","-o",str(script)],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                               timeout=165,check=False)
            if got.returncode:
                print("UNITY_CLI_DOWNLOAD_FAILED",flush=True);return 11
            install_env={**os.environ,"UNITY_CLI_CHANNEL":"beta",
                         "UNITY_CLI_HOME":str(CLI_DIR),"DO_NOT_TRACK":"1"}
            setup=subprocess.run(["bash",str(script)],env=install_env,
                                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                 timeout=200,check=False)
            if setup.returncode:
                print("UNITY_CLI_INSTALL_FAILED",flush=True);return 11
        except (OSError,subprocess.TimeoutExpired):
            print("UNITY_CLI_BOOTSTRAP_ERROR",flush=True);return 11
        finally:
            try: script.unlink(missing_ok=True)
            except OSError: pass
        cli=next((str(x) for x in PATHS if x.is_file() and os.access(x,os.X_OK)),shutil.which("unity"))
        if not cli:
            print("UNITY_CLI_BINARY_NOT_FOUND",flush=True);return 11
    print("UNITY_CLI_READY",flush=True)
    env={k:v for k,v in os.environ.items() if k not in ("UNITY_PASSWORD","UNITY_SERVICE_ACCOUNT_ID","UNITY_SERVICE_ACCOUNT_SECRET")}
    env["UNITY_CLI_HOME"]=str(CLI_DIR);env["DO_NOT_TRACK"]="1"
    if not login(cli,env): return 12
    if check(cli,env,"license"):
        print("UNITY_LICENSE_ALREADY_ACTIVE",flush=True);return 0
    print("UNITY_PERSONAL_ACTIVATION_START",flush=True)
    try:
        p=subprocess.run([cli,"license","activate","--personal","--accept-eula","--non-interactive"],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=200)
    except (OSError,subprocess.TimeoutExpired):
        print("UNITY_PERSONAL_ACTIVATION_ERROR");return 13
    if p.returncode!=0 or not check(cli,env,"license"):
        print("UNITY_PERSONAL_NOT_ACTIVE_HUB_MAY_BE_REQUIRED");return 14
    print("UNITY_PERSONAL_LICENSE_VERIFIED",flush=True);return 0
if __name__=="__main__":
    if "--selftest" in sys.argv:
        assert valid("https://id.unity.com/login?x=1") and not valid("https://id.unity.com.evil.tld/")
        assert extract('auth_url=https://id.unity.com/login?x=1')=="https://id.unity.com/login?x=1"
        print("MOBILE_UNITY_AUTH_SELFTEST_PASS")
    else: raise SystemExit(main())
