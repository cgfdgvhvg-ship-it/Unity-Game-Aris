#!/usr/bin/env python3
"""Read-only, sanitized Aaris Turbo connection diagnostics; no tokens/log lines."""
from pathlib import Path
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.request

def main():
    home=Path.home()
    conf=home/".config/aaris-turbo"
    log=conf/"agent.log"
    pidfile=conf/"agent.pid"
    token=conf/"token"
    agent=home/".local/share/aaris-turbo/agent.py"
    print("TURBO_AGENT_FILE_EXISTS="+("yes" if agent.is_file() else "no"))
    print("TURBO_TOKEN_EXISTS="+("yes" if token.is_file() else "no"))
    print("TURBO_TOKEN_PERMISSIONS_SAFE="+("yes" if token.is_file() and not token.stat().st_mode & 0o077 else "no"))
    if pidfile.is_file():
        raw=pidfile.read_text(errors="ignore").strip()
        pid=int(raw) if raw.isdigit() and 0<int(raw)<20000000 else -1
        print("TURBO_PID_ALIVE="+("yes" if pid>0 and Path("/proc/"+str(pid)).exists() else "no"))
    else:
        print("TURBO_PID_ALIVE=unknown")
    try:
        text=log.read_bytes()[-16000:].decode("utf-8","replace")
    except OSError:
        text=""
    classes=list(dict.fromkeys(re.findall(r"AARIS_TURBO_(?:RETRY_[A-Za-z]+|SESSION_REVOKED|AGENT_STARTED)",text)))[:12]
    print("TURBO_LOG_CATEGORIES="+",".join(classes or ["none"]))
    print("TURBO_LOG_BYTES="+str(log.stat().st_size if log.exists() else 0))
    try:
        req=urllib.request.Request("https://aaris-turbo-terminal.aaris-game-control-6f9c.workers.dev/health",headers={"User-Agent":"AarisTurboSafeDiag/1"})
        with urllib.request.urlopen(req,timeout=12) as res:
            d=json.loads(res.read(1024).decode())
            print("TURBO_HEALTH_HTTP="+str(res.status))
            print("TURBO_HEALTH_VALID="+("yes" if d.get("status")=="ready" else "no"))
    except urllib.error.HTTPError as e:
        print("TURBO_HEALTH_HTTP="+str(e.code))
    except urllib.error.URLError as e:
        print("TURBO_HEALTH_NETWORK_CLASS="+type(e.reason).__name__)
    except (OSError,ValueError) as e:
        print("TURBO_HEALTH_ERROR_CLASS="+type(e).__name__)
    print("TURBO_DIAG_SAFE_COMPLETE")
if __name__=="__main__":
    main()
