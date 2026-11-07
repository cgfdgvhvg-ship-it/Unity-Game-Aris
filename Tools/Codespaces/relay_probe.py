#!/usr/bin/env python3
"""Private OIDC preflight. Reports only boolean identity checks and HTTP status.
Never prints JWT, access token, user email, OAuth URL, or raw HTTP body.
"""
import base64, json, os, sys
from urllib import request
from urllib.error import HTTPError, URLError
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"CI"))
from private_unity_approval_publish import oidc_token, WORKER

def main():
    try:
        jwt=oidc_token()
        payload=jwt.split(".")[1]
        raw=base64.urlsafe_b64decode(payload+"="*(-len(payload)%4))
        claims=json.loads(raw)
    except Exception:
        print("OIDC_MINT_FAILED")
        return 3
    repo="sundamunda289-art/Unity-Game-Aris"
    checks={
      "REPOSITORY":str(claims.get("repository"))==repo,
      "REPOSITORY_ID":str(claims.get("repository_id"))=="1443109769",
      "ACTOR_ID":str(claims.get("actor_id"))=="353065137",
      "WORKFLOW":str(claims.get("workflow_ref"))==repo+"/.github/workflows/aaris-codespaces-control.yml@refs/heads/main",
      "REF":str(claims.get("ref"))=="refs/heads/main",
      "EVENT":str(claims.get("event_name")) in ("issue_comment","workflow_dispatch"),
      "RUN_ID":str(claims.get("run_id"))==os.getenv("GITHUB_RUN_ID"),
      "AUDIENCE":str(claims.get("aud"))==WORKER,
      "ISSUER":str(claims.get("iss"))=="https://token.actions.githubusercontent.com",
    }
    for key,good in checks.items():
        print("OIDC_"+key+"_PASS" if good else "OIDC_"+key+"_FAIL")
    url=WORKER.rsplit("/",1)[0]+"/probe"
    req=request.Request(url,method="POST",data=b"",headers={"Authorization":"Bearer "+jwt,"Accept":"application/json"})
    try:
        with request.urlopen(req,timeout=30) as res:
            status=res.status
            obj=json.loads(res.read(2048))
            ok=status==200 and obj.get("accepted") is True
            print("RELAY_PROBE_PASS" if ok else "RELAY_PROBE_RESPONSE_UNEXPECTED")
            return 0 if ok else 4
    except HTTPError as e:
        if e.code in (400,401,403,404,413,429,500,503):
            print("RELAY_PROBE_HTTP_"+str(e.code))
        else:
            print("RELAY_PROBE_HTTP_OTHER")
        # Diagnose the transport layer without leaking a JWT, account, or body.
        content_type=(e.headers.get("Content-Type") or "").lower()
        server=(e.headers.get("Server") or "").lower()
        if "json" in content_type: print("RELAY_RESPONSE_JSON")
        elif "html" in content_type: print("RELAY_RESPONSE_HTML")
        else: print("RELAY_RESPONSE_OTHER_CONTENT_TYPE")
        if "cloudflare" in server: print("RELAY_SERVER_CLOUDFLARE")
        try:
            payload=e.read(2048)
            obj=json.loads(payload)
            if isinstance(obj,dict):
                category=obj.get("category","")
                if category in {"TOKEN_LENGTH","TOKEN_FORMAT","HEADER","AUDIENCE_ISSUER","TOKEN_TIME","CLAIMS","JWKS_NETWORK","JWKS_KEY","SIGNATURE","UNCLASSIFIED"}:
                    print("RELAY_REJECT_STAGE_"+category)
                elif obj.get("error")=="github_workflow_identity_rejected":
                    print("RELAY_REJECT_OLD_WORKER_VERSION")
                elif obj.get("error")=="identity_rejected":
                    print("RELAY_REJECT_NO_CATEGORY")
                elif isinstance(obj.get("errors"),list):
                    print("RELAY_RESPONSE_CLOUDFLARE_API_ENVELOPE")
                elif obj.get("error") in {"forbidden","access_denied","authentication_required","unauthorized"}:
                    print("RELAY_RESPONSE_ACCESS_LAYER")
                else: print("RELAY_JSON_WITHOUT_DIAGNOSTIC")
        except (ValueError,OSError):
            if "html" in content_type: print("RELAY_HTML_EDGE_BLOCK")
            else: print("RELAY_RESPONSE_NOT_JSON")
        return 5
    except (URLError,OSError,ValueError):
        print("RELAY_PROBE_NETWORK_ERROR")
        return 6
if __name__=="__main__":
    raise SystemExit(main())
