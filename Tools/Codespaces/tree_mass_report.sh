#!/usr/bin/env bash
# Read-only, bounded classification of the last private Unity tree bake run.
set -Eeuo pipefail
python3 - <<'PY'
import json,pathlib,re
p=pathlib.Path("/tmp/aaris-codespaces/tree-mass/mass-report.json")
if not p.is_file():
    print("tree_mass_report=not_created")
else:
    try:
        d=json.loads(p.read_text())
        state=str(d.get("status","UNKNOWN"))
        reason=str(d.get("reason","UNKNOWN"))
        if not re.fullmatch(r"[A-Za-z0-9_]{1,96}",reason):
            reason="REDACTED"
        if state not in {"passed","failed"}:state="UNKNOWN"
        records=d.get("records",[])
        print("tree_mass_report="+state)
        print("reason="+reason)
        print("species="+str(min(6,len(records))))
        print("generated_assets="+str(min(18,int(d.get("meshAssets",0)))))
    except (ValueError,OSError,TypeError):
        print("tree_mass_report=invalid")
PY
