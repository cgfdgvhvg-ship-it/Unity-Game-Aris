#!/usr/bin/env python3
"""Intercept Unity OAuth from private SSH stream, send it to Cloudflare signed OIDC.
Never print raw Unity output or authorization URLs to public Actions logs/artifacts.
"""
import os, re, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"Tools/CI"))
from private_unity_approval_publish import publish, allowed_url
SAFE={
 "UNITY_AUTH_ALREADY_VALID","UNITY_AUTH_STARTED","UNITY_AUTH_VERIFIED",
 "UNITY_AUTH_NOT_COMPLETED","UNITY_LICENSE_ALREADY_ACTIVE",
 "UNITY_PERSONAL_ACTIVATION_START","UNITY_PERSONAL_ACTIVATION_ERROR",
 "UNITY_PERSONAL_NOT_ACTIVE_HUB_MAY_BE_REQUIRED",
 "UNITY_PERSONAL_LICENSE_VERIFIED","UNITY_CLI_MISSING_RUN_CS_INSTALL_FIRST"}
def sanitize(line,run_id):
    line=line.strip()
    if line.startswith("AARIS_AUTH_LINK="):
        url=line[len("AARIS_AUTH_LINK="):]
        if not allowed_url(url): return "UNITY_AUTH_LINK_INVALID"
        try:
            publish(url,run_id)
            return "UNITY_PRIVATE_APPROVAL_LINK_READY"
        except Exception:
            return "UNITY_PRIVATE_APPROVAL_RELAY_FAILED"
    return line if line in SAFE else "UNITY_PROGRESS_REDACTED"
def run(codespace):
    if not re.fullmatch(r"[A-Za-z0-9-]{3,120}",codespace): return 2
    run_id=os.environ.get("GITHUB_RUN_ID","")
    if not re.fullmatch(r"[0-9]{6,18}",run_id): return 2
    path=ROOT/"Tools/Codespaces/mobile_license.py"
    with path.open("rb") as source:
        p=subprocess.Popen(["gh","codespace","ssh","-c",codespace,"--","python3 -u -"],
                           stdin=source,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                           text=True,encoding="utf-8",errors="replace",bufsize=1)
        link_sent=False
        for line in p.stdout:
            result=sanitize(line,run_id)
            print(result,flush=True)
            if result=="UNITY_PRIVATE_APPROVAL_LINK_READY": link_sent=True
        code=p.wait()
    if code and not link_sent: print("UNITY_AUTH_INCOMPLETE",flush=True)
    return code
if __name__=="__main__":
    if "--selftest" in sys.argv:
        assert sanitize("sensitive oauth token","12345678")=="UNITY_PROGRESS_REDACTED"
        assert sanitize("UNITY_AUTH_STARTED","12345678")=="UNITY_AUTH_STARTED"
        assert sanitize("AARIS_AUTH_LINK=https://evil.invalid/","12345678")=="UNITY_AUTH_LINK_INVALID"
        print("AUTH_BRIDGE_INTERCEPTION_SELFTEST_PASS")
    elif len(sys.argv)==2: raise SystemExit(run(sys.argv[1]))
    else: raise SystemExit(2)
