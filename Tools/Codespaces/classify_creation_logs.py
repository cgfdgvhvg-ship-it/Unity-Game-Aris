#!/usr/bin/env python3
"""Privacy-preserving classification of Codespace creation logs.

Never emit arbitrary log lines, URLs, auth tokens, emails, repo data, or paths.
The raw log stays on the ephemeral GitHub Actions runner and is deleted.
"""
from pathlib import Path
import re
import sys

def classify(raw: str) -> dict[str, str]:
    s = raw[-400000:].lower()
    categories = (
      ("POST_CREATE_APT", r"(apt-get|dpkg|apt )[\s\S]{0,140}(failed|error|not found)"),
      ("POST_CREATE", r"(postcreatecommand|post-create)[\s\S]{0,120}(failed|error|exit code)"),
      ("POST_START", r"(poststartcommand|post-start)[\s\S]{0,120}(failed|error|exit code)"),
      ("IMAGE_PULL", r"(pull|manifest|image)[\s\S]{0,100}(denied|failed|not found|unauthorized)"),
      ("SSH_SERVER", r"(sshd|openssh-server|ssh server)[\s\S]{0,120}(failed|error|not found|refused)"),
      ("PERMISSION", r"permission denied|operation not permitted"),
      ("NETWORK", r"timeout|timed out|connection reset|could not resolve|tls handshake"),
      ("STORAGE", r"no space left|disk full|insufficient disk"),
      ("CONTAINER", r"(container|devcontainer)[\s\S]{0,120}(failed|error|exited)"),
    )
    reason = next((code for code,pattern in categories if re.search(pattern,s)),"NO_CLASSIFIED_FAILURE")
    return {
        "creation_log_bytes": str(len(raw.encode("utf-8","replace"))),
        "creation_log_errors": str(min(len(re.findall(r"\berror\b",s)),9999)),
        "creation_log_failures": str(min(len(re.findall(r"\bfailed\b",s)),9999)),
        "create_error_type": reason,
        "os_image_ubuntu_mentioned": "yes" if "ubuntu-22.04" in s else "no",
        "os_image_alpine_mentioned": "yes" if "alpine" in s else "no",
        "ssh_server_mentioned": "yes" if re.search(r"sshd|openssh|ssh server",s) else "no",
        "post_create_mentioned": "yes" if re.search(r"postcreate|post-create",s) else "no",
        "post_start_mentioned": "yes" if re.search(r"poststart|post-start",s) else "no",
    }

def main() -> int:
    if len(sys.argv)==2 and sys.argv[1]=="--selftest":
        sample="ubuntu-22.04 postCreateCommand apt-get install failed: not found"
        v=classify(sample)
        assert v["create_error_type"] in ("POST_CREATE_APT","POST_CREATE")
        assert v["os_image_ubuntu_mentioned"]=="yes"
        assert all(re.fullmatch(r"[a-zA-Z0-9_.-]+",x) for x in v.values())
        print("CREATION_LOG_PRIVACY_TEST_PASS")
        return 0
    if len(sys.argv)!=2: return 2
    try:
        with Path(sys.argv[1]).open("rb") as f:
            f.seek(0,2)
            size=f.tell()
            f.seek(max(0,size-400000))
            raw=f.read(400000).decode("utf-8","replace")
    except OSError:
        print("AARIS_CREATION_LOG_READ_FAILED")
        return 3
    print("AARIS_CODESPACE_CREATION_LOG_CLASSIFIED")
    for k,v in classify(raw).items():
        print(k+"="+v)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
