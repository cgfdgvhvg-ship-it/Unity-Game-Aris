#!/usr/bin/env python3
"""Codespace-side OAuth; URL is intercepted privately by the Actions controller."""
import os, sys, re, time, queue, threading, subprocess, shutil, pwd, tempfile
from pathlib import Path
from urllib.parse import urlsplit
CLI_DIR=Path.home()/".local/share/aaris-unity-cli"
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
def find_cli(candidates):
    # Path.is_file raises PermissionError on some Python/Linux combinations
    # when the SSH user's inherited HOME points to root-owned directories.
    for candidate in candidates:
        try:
            if candidate.is_file() and os.access(candidate,os.X_OK):
                return str(candidate)
        except OSError:
            continue
    return shutil.which("unity")

def choose_writable_home():
    # A GitHub Codespace SSH session may report HOME=/root even though the
    # actual SSH user cannot write to that directory. Use passwd's UID home.
    candidates=[Path(pwd.getpwuid(os.geteuid()).pw_dir),
                Path.home(),Path("/home/vscode"),Path("/home/codespace"),
                Path("/tmp")/("aaris-unity-home-"+str(os.geteuid()))]
    seen=set()
    for home in candidates:
        if str(home) in seen: continue
        seen.add(str(home))
        try:
            home.mkdir(parents=True,exist_ok=True)
            state=home/".local/share/aaris-unity-cli"
            state.mkdir(parents=True,exist_ok=True)
            marker=state/(".aaris-write-test-"+str(os.getpid()))
            with marker.open("wb") as check: check.write(b"ok")
            marker.unlink()
            os.chmod(state,0o700)
            if str(home).startswith("/tmp/"):
                print("UNITY_STATE_HOME_TEMPORARY",flush=True)
            else:
                print("UNITY_STATE_HOME_PERSISTENT",flush=True)
            return home,state
        except OSError:
            continue
    print("UNITY_STATE_DIRECTORY_UNWRITABLE",flush=True)
    return None,None

def main():
    global CLI_DIR
    os.umask(0o077)
    user_home,state=choose_writable_home()
    if state is None: return 16
    CLI_DIR=state
    candidates=[state/"bin/unity",user_home/".local/bin/unity"]+PATHS
    print("UNITY_CLI_DISCOVERY_START",flush=True)
    cli=find_cli(candidates)
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
                         "HOME":str(user_home),
                         "UNITY_CLI_HOME":str(CLI_DIR),"DO_NOT_TRACK":"1"}
            # Keep installer output in an unlinked private file; never surface
            # its URLs, emails or arbitrary messages on the public GitHub Issue.
            with tempfile.TemporaryFile() as private_log:
                setup=subprocess.run(["bash",str(script)],env=install_env,
                                     stdout=private_log,stderr=subprocess.STDOUT,
                                     timeout=200,check=False)
                if setup.returncode:
                    private_log.seek(0)
                    raw=private_log.read(125000).decode("utf-8","replace").lower()
                    checks=(
                        ("ACCESS_POLICY",r"access denied|access policy|blocked by|http 403|forbidden"),
                        ("PERMISSION",r"permission denied|operation not permitted|cannot create directory"),
                        ("MISSING_TOOL",r"command not found|unzip: not found|tar: not found|jq: not found"),
                        ("UNSUPPORTED_GLIBC",r"glibc|unsupported operating system|unsupported platform"),
                        ("NETWORK",r"could not resolve|certificate|connection failed|timeout|curl:|wget:"),
                        ("DISK_FULL",r"no space left|out of disk|disk full"),
                        ("SCRIPT_FORMAT",r"<!doctype|<html|syntax error near unexpected token|not a shell script"),
                    )
                    category=next((name for name,pattern in checks if re.search(pattern,raw)),"UNCLASSIFIED")
                    print("UNITY_CLI_INSTALL_CATEGORY_"+category,flush=True)
                    print("UNITY_CLI_INSTALL_FAILED",flush=True)
                    return 11
        except (OSError,subprocess.TimeoutExpired):
            print("UNITY_CLI_BOOTSTRAP_ERROR",flush=True);return 11
        finally:
            try: script.unlink(missing_ok=True)
            except OSError: pass
        cli=find_cli(candidates)
        if not cli:
            print("UNITY_CLI_BINARY_NOT_FOUND",flush=True);return 11
    print("UNITY_CLI_READY",flush=True)
    env={k:v for k,v in os.environ.items() if k not in ("UNITY_PASSWORD","UNITY_SERVICE_ACCOUNT_ID","UNITY_SERVICE_ACCOUNT_SECRET")}
    env["HOME"]=str(user_home);env["UNITY_CLI_HOME"]=str(CLI_DIR);env["DO_NOT_TRACK"]="1"
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
