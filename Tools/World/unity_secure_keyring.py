#!/usr/bin/env python3
"""Protected, restart-repairable Secret Service for Unity CLI on a Codespace.

Do not upload credentials or keyring data to GitHub. Private state stays in
Codespace home (0700 directory; 0600 unlock key), never in the game checkout.
"""
from __future__ import annotations
import fcntl, json, os, secrets, shutil, socket, stat, subprocess, sys, time
from pathlib import Path

PRIVATE = Path.home() / ".local/share/aaris-unity-keyring-runtime"
SECRET = PRIVATE / ".unlock-key"
BUS = PRIVATE / "session-bus.sock"
LOCK = PRIVATE / ".lock"
STAGE = Path("/workspaces/.aaris-world-bridge/ondemand")
STATE = STAGE / "unity-secure-keyring-status.json"
LOG = STAGE / "unity-secure-keyring-setup.log"
REQUIRED = ("dbus-daemon", "dbus-send", "gnome-keyring-daemon", "secret-tool")
PACKAGES = ("gnome-keyring", "libsecret-tools", "dbus-x11")

def save(state, **extra):
    STAGE.mkdir(parents=True, exist_ok=True)
    file = STATE.with_suffix(".next")
    if file.is_symlink(): raise RuntimeError("unsafe status path")
    with file.open("w") as f:
        os.chmod(file, 0o600)
        json.dump({"state":state,"at":int(time.time()), **extra},f)
    os.replace(file, STATE)

def environment():
    env=os.environ.copy()
    env["DBUS_SESSION_BUS_ADDRESS"]="unix:path="+str(BUS)
    return env

def command(args, *, timeout=15, env=None, stdin=None):
    return subprocess.run(args, input=stdin, capture_output=True, env=env,
                          timeout=timeout, check=False)

def is_bus_ready():
    if not BUS.exists() or BUS.is_symlink(): return False
    try:
        p=command(["dbus-send","--session","--type=method_call",
                   "--dest=org.freedesktop.DBus","/org/freedesktop/DBus",
                   "org.freedesktop.DBus.ListNames"],env=environment(),timeout=8)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired): return False

def secret_service_ready():
    if not is_bus_ready():return False
    try:
        p=command(["dbus-send","--session","--print-reply","--type=method_call",
                   "--dest=org.freedesktop.DBus","/org/freedesktop/DBus",
                   "org.freedesktop.DBus.NameHasOwner",
                   "string:org.freedesktop.secrets"],env=environment(),timeout=8)
        return p.returncode == 0 and b"boolean true" in p.stdout
    except (OSError,subprocess.TimeoutExpired):return False

def worker_running():
    for p in Path("/proc").iterdir():
        if not p.name.isdigit(): continue
        try:
            a=(p/"cmdline").read_bytes().decode("utf-8","replace")
            if "unity_secure_keyring.py" in a and "--worker" in a: return True
        except OSError: pass
    return False

def status():
    s={}
    if STATE.is_file() and not STATE.is_symlink() and STATE.stat().st_size<3000:
        try:s=json.loads(STATE.read_text())
        except (OSError,ValueError):pass
    return {"packages":{x:bool(shutil.which(x)) for x in REQUIRED},
            "bus_available":is_bus_ready(),
            "secret_service_available":secret_service_ready(),
            "unlock_secret_present":SECRET.is_file() and not SECRET.is_symlink(),
            "worker_running":worker_running(),
            "last_state":s.get("state","not_started"),
            "last_error":s.get("error"),
            "credentials_not_in_repository":True}

def initialize_service():
    if not all(shutil.which(p) for p in REQUIRED):
        raise RuntimeError("keyring packages not installed")
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    if PRIVATE.is_symlink():raise RuntimeError("unsafe private credentials directory")
    PRIVATE.chmod(0o700)
    if not SECRET.exists():
        # Never replace a pre-existing keyring with an unknown password.
        keyring_dir=Path.home()/".local/share/keyrings"
        if keyring_dir.is_dir() and any(keyring_dir.iterdir()):
            raise RuntimeError("existing keyring requires its original unlock password")
        with SECRET.open("x") as file:
            os.chmod(SECRET,0o600)
            file.write(secrets.token_urlsafe(40))
    if not SECRET.is_file() or SECRET.is_symlink():
        raise RuntimeError("unsafe unlock key")
    if (SECRET.stat().st_mode & 0o077): SECRET.chmod(0o600)
    if not is_bus_ready():
        if BUS.exists() or BUS.is_symlink():
            if BUS.is_symlink() or not stat.S_ISSOCK(BUS.lstat().st_mode):
                raise RuntimeError("unsafe stale dbus path")
            BUS.unlink()   # stale socket from Codespace restart; never remove other files
        p=command(["dbus-daemon","--session","--fork",
                   "--address=unix:path="+str(BUS),
                   "--print-address=1"],timeout=15)
        if p.returncode: raise RuntimeError("private D-Bus session failed")
    if not is_bus_ready(): raise RuntimeError("private D-Bus not reachable")
    # Even when D-Bus advertises the service, its login collection can
    # remain locked until a real unlock is performed.
    password=SECRET.read_bytes().strip()+b"\n"
    p=command(["gnome-keyring-daemon","--components=secrets","--unlock"],
              timeout=35,env=environment(),stdin=password)
    if p.returncode and not secret_service_ready():
        raise RuntimeError("keyring unlock daemon failed")
    for _ in range(36):
        if secret_service_ready():break
        time.sleep(0.5)
    if not secret_service_ready():raise RuntimeError("GNOME Secret Service not ready after startup")
    # End-to-end store/read/delete of a harmless random probe, never an account token.
    probe=secrets.token_hex(20)
    args=["aaris-unity-keyring-test","verification"]
    env=environment()
    s=command(["secret-tool","store","--label=Temporary Unity Keyring Probe",*args],
              env=env,timeout=20,stdin=probe.encode())
    if s.returncode:raise RuntimeError("keyring probe store failed")
    try:
        r=command(["secret-tool","lookup",*args],env=env,timeout=20)
        if r.returncode or r.stdout.strip()!=probe.encode():
            raise RuntimeError("keyring probe readback failed")
    finally:
        command(["secret-tool","clear",*args],env=env,timeout=20)
    return True

def worker():
    STAGE.mkdir(parents=True,exist_ok=True)
    try:
        if not all(shutil.which(p) for p in REQUIRED):
            save("installing_packages")
            env=os.environ.copy()
            env["DEBIAN_FRONTEND"]="noninteractive"
            with LOG.open("a") as log:
                p=subprocess.run(["sudo","-n","apt-get","install","-y","-qq",
                                  "--no-install-recommends",*PACKAGES],
                       env=env,stdin=subprocess.DEVNULL,
                       stdout=log,stderr=log,timeout=1200,check=False)
            if p.returncode:raise RuntimeError("apt keyring install failed: "+str(p.returncode))
        PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
        with LOCK.open("a+") as lk:
            os.chmod(LOCK,0o600)
            fcntl.flock(lk.fileno(),fcntl.LOCK_EX)
            save("initializing_secret_service")
            initialize_service()
            save("ready")
    except Exception as e:
        save("failed",error=type(e).__name__+": "+str(e)[:220])

def start():
    if secret_service_ready() and status()["last_state"]=="ready":return {"status":"already_ready", **status()}
    if worker_running():return {"status":"already_running", **status()}
    STAGE.mkdir(parents=True,exist_ok=True)
    with LOG.open("a") as log:
        p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--worker"],
                 stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    return {"status":"started","pid":p.pid, **status()}

if __name__=="__main__":
    if sys.argv[1:]==["--worker"]:worker()
    elif sys.argv[1:]==["--start"]: print(json.dumps(start()))
    elif sys.argv[1:]==["--status"]:print(json.dumps(status()))
    else:raise SystemExit("use --start or --status")
