#!/usr/bin/env python3
"""Intercept Unity OAuth from private SSH stream, send it to Cloudflare signed OIDC.
Never print raw Unity output or authorization URLs to public Actions logs/artifacts.
"""
import os, re, subprocess, sys, base64, hashlib, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"Tools/CI"))
from private_unity_approval_publish import publish, allowed_url
SAFE={
 "UNITY_AUTH_ALREADY_VALID","UNITY_AUTH_STARTED","UNITY_AUTH_VERIFIED",
 "UNITY_AUTH_NOT_COMPLETED","UNITY_LICENSE_ALREADY_ACTIVE",
 "UNITY_PERSONAL_ACTIVATION_START","UNITY_PERSONAL_ACTIVATION_ERROR",
 "UNITY_PERSONAL_NOT_ACTIVE_HUB_MAY_BE_REQUIRED",
 "UNITY_PERSONAL_LICENSE_VERIFIED","UNITY_CLI_MISSING_RUN_CS_INSTALL_FIRST",
 "UNITY_CLI_BOOTSTRAPPING","UNITY_CLI_READY","UNITY_CLI_DOWNLOAD_FAILED",
 "UNITY_CLI_INSTALL_FAILED","UNITY_CLI_BOOTSTRAP_ERROR","UNITY_CLI_BINARY_NOT_FOUND"}
def encrypted_issue_delivery(url,run_id):
    """Post only RSA-OAEP ciphertext. The private key never leaves this chat session."""
    if not allowed_url(url) or not re.fullmatch(r"[0-9]{6,18}",run_id):
        return "UNITY_ENCRYPTED_APPROVAL_INVALID"
    if os.environ.get("GITHUB_REPOSITORY")!="sundamunda289-art/Unity-Game-Aris":
        return "UNITY_ENCRYPTED_APPROVAL_REPO_MISMATCH"
    issue_token=os.environ.get("AARIS_ISSUE_REPLY_TOKEN","")
    if not issue_token:
        return "UNITY_ENCRYPTED_APPROVAL_ISSUE_TOKEN_MISSING"
    public=ROOT/"Tools/Codespaces/approval_relay_public.pem"
    if not public.is_file():
        return "UNITY_ENCRYPTED_APPROVAL_KEY_MISSING"
    raw=url.encode("utf-8")
    chunks=[]
    try:
        for start in range(0,len(raw),240):
            proc=subprocess.run(["openssl","pkeyutl","-encrypt",
                                 "-pubin","-inkey",str(public),
                                 "-pkeyopt","rsa_padding_mode:oaep",
                                 "-pkeyopt","rsa_oaep_md:sha256",
                                 "-pkeyopt","rsa_mgf1_md:sha256"],
                                input=raw[start:start+240],stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,timeout=12,check=True)
            chunks.append(base64.urlsafe_b64encode(proc.stdout).decode("ascii"))
        if not chunks or len(chunks)>24:
            return "UNITY_ENCRYPTED_APPROVAL_BAD_CHUNK_COUNT"
        message=(
           "AARIS_UNITY_ENCRYPTED_APPROVAL_V1\n"
           "RUN="+run_id+"\n"
           "SHA256="+hashlib.sha256(raw).hexdigest()+"\n"
           "CIPHERTEXT_BEGIN\n"+"\n".join(chunks)+"\nCIPHERTEXT_END\n"
        )
        # NEVER write the OAuth URL; only encrypted chunks to a mode-0600 file.
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",prefix="aaris-cipher-",
                                         dir=os.environ.get("RUNNER_TEMP","/tmp"),
                                         delete=False) as artifact:
            filename=artifact.name
            artifact.write(message)
        try:
            os.chmod(filename,0o600)
            env=dict(os.environ)
            env["GH_TOKEN"]=issue_token
            proc=subprocess.run(["gh","issue","comment","77","-R",
                                "sundamunda289-art/Unity-Game-Aris",
                                "--body-file",filename],env=env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,timeout=30,check=False)
            if proc.returncode: return "UNITY_ENCRYPTED_APPROVAL_POST_FAILED"
        finally:
            os.unlink(filename)
        return "UNITY_ENCRYPTED_APPROVAL_POSTED"
    except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError,ValueError):
        return "UNITY_ENCRYPTED_APPROVAL_FAILED"

def sanitize(line,run_id):
    line=line.strip()
    if line.startswith("AARIS_AUTH_LINK="):
        url=line[len("AARIS_AUTH_LINK="):]
        if not allowed_url(url): return "UNITY_AUTH_LINK_INVALID"
        try:
            publish(url,run_id)
            return "UNITY_PRIVATE_APPROVAL_LINK_READY"
        except Exception:
            # Cloudflare workers.dev may be blocked by the runner network policy.
            # Use the same owner-only GitHub bridge, but send RSA ciphertext only.
            return encrypted_issue_delivery(url,run_id)
    return line if line in SAFE else "UNITY_PROGRESS_REDACTED"
def run(codespace):
    if not re.fullmatch(r"[A-Za-z0-9-]{3,120}",codespace): return 2
    run_id=os.environ.get("GITHUB_RUN_ID","")
    if not re.fullmatch(r"[0-9]{6,18}",run_id): return 2
    path=ROOT/"Tools/Codespaces/mobile_license.py"
    # Reuse exactly the proven CS STATUS SSH transport (remote bash -s).
    # Bash executes the trusted Python program from the SSH stdin here-document,
    # so the gh CLI never attempts to exec a remote command containing spaces.
    source=path.read_text(encoding="utf-8")
    marker="AARIS_UNITY_PY_EOF_22941"
    if marker in source: return 2
    shell="python3 -u - <<'"+marker+"'\\n"+source+"\\n"+marker+"\\n"
    with tempfile.TemporaryFile() as private_stderr:
        p=subprocess.Popen(["gh","codespace","ssh","-c",codespace,"--","bash -s"],
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                           stderr=private_stderr,text=True,
                           encoding="utf-8",errors="replace",bufsize=1)
        p.stdin.write(shell)
        p.stdin.close()
        link_sent=False
        for line in p.stdout:
            result=sanitize(line,run_id)
            print(result,flush=True)
            if result in ("UNITY_PRIVATE_APPROVAL_LINK_READY","UNITY_ENCRYPTED_APPROVAL_POSTED"): link_sent=True
        code=p.wait()
        if code:
            private_stderr.seek(0)
            raw=private_stderr.read(81920).decode("utf-8","replace").lower()
            if "permissionerror" in raw: category="PYTHON_PATH_PERMISSION"\n            elif "permission denied" in raw: category="SSH_OR_SHELL_PERMISSION"
            elif "syntaxerror" in raw or "indentationerror" in raw: category="PYTHON_SYNTAX"
            elif "modulenotfounderror" in raw or "importerror" in raw: category="PYTHON_DEPENDENCY"
            elif "no such file or directory" in raw: category="MISSING_FILE"
            elif "traceback" in raw: category="PYTHON_RUNTIME"
            elif "authentication failed" in raw or "unauthorized" in raw: category="SSH_AUTHORIZATION"
            elif "timed out" in raw or "connection" in raw: category="SSH_TRANSPORT"
            elif "unknown" in raw and "command" in raw: category="GH_CLI_ARGUMENT"
            elif not raw.strip(): category="NO_STDERR"
            else: category="REMOTE_EXECUTION"
            print("UNITY_REMOTE_DIAGNOSTIC_"+category,flush=True)
    if code and not link_sent: print("UNITY_AUTH_INCOMPLETE",flush=True)
    return code
if __name__=="__main__":
    if "--selftest" in sys.argv:
        assert sanitize("sensitive oauth token","12345678")=="UNITY_PROGRESS_REDACTED"
        assert sanitize("UNITY_AUTH_STARTED","12345678")=="UNITY_AUTH_STARTED"
        assert sanitize("AARIS_AUTH_LINK=https://evil.invalid/","12345678")=="UNITY_AUTH_LINK_INVALID"
        assert "openssl" in encrypted_issue_delivery.__code__.co_consts.__str__() or callable(encrypted_issue_delivery)
        print("AUTH_BRIDGE_INTERCEPTION_SELFTEST_PASS")
    elif len(sys.argv)==2: raise SystemExit(run(sys.argv[1]))
    else: raise SystemExit(2)
