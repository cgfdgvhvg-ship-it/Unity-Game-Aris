"""Expire only completed AI query runs; never touch source, releases or build/PR checks."""
import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone

WORKFLOWS = {"world-query.yml": "World query", "world-engine-query.yml": "World engine query"}


def expired(run, filename, now):
    if filename not in WORKFLOWS or run.get("path") != ".github/workflows/"+filename:
        return False
    if run.get("status") != "completed" or run.get("event") != "workflow_dispatch":
        return False
    m = re.fullmatch(re.escape(WORKFLOWS[filename])+r" TTL=(1|2|6|24)h", run.get("display_title", ""))
    if not m:
        return False
    updated = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
    return now >= updated+timedelta(hours=int(m[1]))


def api(path, method="GET"):
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid repository")
    req = urllib.request.Request("https://api.github.com/repos/"+repo+path, method=method,
        headers={"Authorization": "Bearer "+os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
        return json.loads(data) if data else None


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--delete-expired", action="store_true")
    args = p.parse_args(); now = datetime.now(timezone.utc); candidates = []
    # Collect first, delete second so pagination is not shifted by our deletions.
    for filename in WORKFLOWS:
        for page in range(1, 21):
            rows = api(f"/actions/workflows/{filename}/runs?event=workflow_dispatch&per_page=100&page={page}")["workflow_runs"]
            candidates.extend(r for r in rows if expired(r, filename, now))
            if len(rows) < 100: break
    for run in candidates:
        if args.delete_expired:
            api(f"/actions/runs/{int(run['id'])}", "DELETE")
    print(json.dumps({"expired_query_runs": len(candidates), "deleted": args.delete_expired,
                      "scope": list(WORKFLOWS), "note": "Source scripts, assets and other workflows untouched"}))


if __name__ == "__main__": main()
