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
    # Compare three safe requests to identify provider/edge 403 vs Worker 401.
    # The real token never appears in output, exceptions or GitHub logs.
    machine=sys.argv[1] if len(sys.argv)>1 else ""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{2,119}",machine) and token.is_file():
        url="https://aaris-turbo-terminal.aaris-game-control-6f9c.workers.dev/agent/"+machine+"/ping"
        credential=token.read_text(encoding="ascii").strip()
        probes=[
            ("AUTH_REAL",{"Authorization":"Bearer "+credential}),
            ("AUTH_DUMMY",{"Authorization":"Bearer invalid"}),
            ("CUSTOM_DUMMY",{"X-Aaris-Agent-Token":"invalid"}),
        ]
        for label,headers in probes:
            request=urllib.request.Request(url,data=b"{}",method="POST",
                headers={"Content-Type":"application/json",**headers})
            try:
                with urllib.request.urlopen(request,timeout=12) as res:
                    print("TURBO_"+label+"_HTTP="+str(res.status))
                    print("TURBO_"+label+"_JSON="+("yes" if "application/json" in
                        res.headers.get("content-type","").lower() else "no"))
            except urllib.error.HTTPError as exc:
                print("TURBO_"+label+"_HTTP="+str(exc.code))
                print("TURBO_"+label+"_JSON="+("yes" if "application/json" in
                    exc.headers.get("content-type","").lower() else "no"))
                print("TURBO_"+label+"_CHALLENGE="+("yes" if exc.headers.get("cf-mitigated","")=="challenge" else "no"))
            except urllib.error.URLError as exc:
                print("TURBO_"+label+"_NETWORK_CLASS="+type(exc.reason).__name__)
    # Distinguish a blocked POST method from a blocked /agent route.
    base="https://aaris-turbo-terminal.aaris-game-control-6f9c.workers.dev"
    route="/agent/"+machine+"/ping" if machine else "/agent/test-only/ping"
    tests=[
        ("HEALTH_POST","/health","POST"),
        ("AGENT_GET",route,"GET"),
        ("MISSING_GET","/invalid-safe-probe","GET"),
        ("MISSING_POST","/invalid-safe-probe","POST"),
    ]
    for label,path,method in tests:
        req=urllib.request.Request(base+path,
            data=b"{}" if method=="POST" else None,method=method,
            headers={"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=8) as res:
                print("TURBO_"+label+"_HTTP="+str(res.status))
                print("TURBO_"+label+"_SERVER="+re.sub(r"[^a-z]", "",res.headers.get("server","unknown").lower())[:32])
        except urllib.error.HTTPError as exc:
            print("TURBO_"+label+"_HTTP="+str(exc.code))
            print("TURBO_"+label+"_SERVER="+re.sub(r"[^a-z]","",exc.headers.get("server","unknown").lower())[:32])
        except urllib.error.URLError as exc:
            print("TURBO_"+label+"_NETWORK_CLASS="+type(exc.reason).__name__)

    # Safe GET /health probes: never print credentials, response bodies or URLs.
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{2,119}",machine) and token.is_file():
        private=token.read_text(encoding="ascii").strip()
        combos=[
            ("OP_ONLY",{"X-Aaris-Op":"ping"}),
            ("MACHINE_ONLY",{"X-Aaris-Machine":machine}),
            ("TOKEN_DUMMY",{"X-Aaris-Token":"0"*64}),
            ("TOKEN_REAL",{"X-Aaris-Token":private}),
            ("OP_MACHINE",{"X-Aaris-Op":"ping","X-Aaris-Machine":machine}),
            ("OP_MACHINE_DUMMY",{"X-Aaris-Op":"ping","X-Aaris-Machine":machine,"X-Aaris-Token":"0"*64,"X-Aaris-Payload":"e30"}),
            ("OP_MACHINE_REAL",{"X-Aaris-Op":"ping","X-Aaris-Machine":machine,"X-Aaris-Token":private,"X-Aaris-Payload":"e30"}),
            ("AGENT_HEADER",{"X-Aaris-Op":"ping","X-Aaris-Machine":machine,"X-Aaris-Token":private,"X-Aaris-Payload":"e30","User-Agent":"Mozilla/5.0"}),
        ]
        for label,headers in combos:
            req=urllib.request.Request(base+"/health",method="GET",headers=headers)
            try:
                with urllib.request.urlopen(req,timeout=8) as response:
                    status=response.status
                    mime=response.headers.get("content-type","")
                    response.read(64)
            except urllib.error.HTTPError as exc:
                status=exc.code
                mime=exc.headers.get("content-type","")
            except urllib.error.URLError:
                status=0; mime=""
            print("TURBO_PROBE_"+label+"_HTTP="+str(status))
            print("TURBO_PROBE_"+label+"_JSON="+("yes" if "application/json" in mime.lower() else "no"))
    print("TURBO_DIAG_SAFE_COMPLETE")
if __name__=="__main__":
    main()
