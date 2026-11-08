#!/usr/bin/env python3
"""Owner-only Codespaces monthly compute accounting; safe bounded text output.

Uses the PAT already configured for the reviewed GitHub Codespaces controller.
Reads billing report via GitHub API; never exposes token, raw response,
arbitrary API error body, account email, or private repository names.
Run this on the GitHub Actions runner, not inside the Codespace (which would
needlessly consume compute quota or wake a stopped environment).
"""
import datetime
import json
import re
import subprocess
import sys


def api(path):
    try:
        proc = subprocess.run(
            ["gh", "api", "--method", "GET", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=40, check=False, text=True,
        )
        if proc.returncode:
            return None
        doc = json.loads(proc.stdout)
        return doc if isinstance(doc, dict) else None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


def numeric(row):
    for key in ("grossQuantity", "quantity"):
        val = row.get(key)
        if isinstance(val, (float, int)) and not isinstance(val, bool) and 0 <= val < 1e9:
            return float(val)
    return None


def core_hours(row):
    """Only count usage with unambiguous dimensions, never infer from dollar cost."""
    quantity = numeric(row)
    if quantity is None:
        return None
    unit = str(row.get("unitType", "")).lower().strip().replace("_", "-")
    sku = str(row.get("sku", "")).lower()
    # Some billing reports already express core-hours rather than VM-hours.
    if unit in ("core-hours", "core-hours-month", "corehours", "core-hour"):
        return quantity
    if unit not in ("minutes", "minute", "hours", "hour"):
        return None
    match = re.search(r"(?<!\d)(2|4|8|16|32)\s*[- ]?\s*(?:cores?|vcpus?|cpus?)\b", sku)
    if match is None:
        match = re.search(r"(?:cores?|vcpus?|cpus?)\s*[- ]?\s*(2|4|8|16|32)\b", sku)
    if match is None:
        return None
    core_count = int(match.group(1))
    return quantity * core_count / (60 if unit in ("minutes", "minute") else 1)


def report(doc, plan):
    items = doc.get("usageItems")
    if not isinstance(items, list):
        print("CODESPACES_BILLING_FORMAT_UNKNOWN")
        return
    compute = []
    storage = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        product = str(item.get("product", "")).lower()
        sku = str(item.get("sku", "")).lower()
        if "codespace" not in product and "codespace" not in sku:
            continue
        if "storage" in sku or "gb-month" in str(item.get("unitType", "")).lower():
            storage += 1
        else:
            compute.append(item)
    if not compute:
        # 0 entries can mean no compute this month, but the provider's report
        # might omit or aggregate all-zero line items. Do not overclaim.
        print("CODESPACES_COMPUTE_LINES=0")
        print("CODESPACES_HOURS_STATUS=NO_COMPUTE_LINE")
        return
    values = [core_hours(item) for item in compute]
    print("CODESPACES_COMPUTE_LINES=" + str(len(compute)))
    print("CODESPACES_STORAGE_LINES=" + str(storage))
    if any(value is None for value in values):
        print("CODESPACES_HOURS_STATUS=UNIT_UNRECOGNIZED")
        return
    used = round(sum(values), 3)
    print(f"CODESPACES_USED_CORE_HOURS={used:.3f}")
    if plan in ("free", "pro"):
        allowance = 120 if plan == "free" else 180
        print("CODESPACES_PLAN=" + plan.upper())
        print("CODESPACES_INCLUDED_CORE_HOURS=" + str(allowance))
        print("CODESPACES_REMAINING_CORE_HOURS=" + f"{max(0, allowance-used):.3f}")
        print("CODESPACES_REMAINING_4CORE_HOURS=" + f"{max(0, allowance-used)/4:.3f}")
    else:
        print("CODESPACES_PLAN=UNVERIFIED")
        print(f"CODESPACES_FREE_REMAINING_CORE_HOURS={max(0, 120-used):.3f}")
        print(f"CODESPACES_PRO_REMAINING_CORE_HOURS={max(0, 180-used):.3f}")
    print("CODESPACES_BILLING_REPORT=SUCCESS")


def selftest():
    assert core_hours({"sku": "Codespaces Compute - 4 core", "unitType": "hours", "grossQuantity": 2.5}) == 10.0
    assert core_hours({"sku": "Codespaces - 8-core", "unitType": "minutes", "quantity": 60}) == 8.0
    assert core_hours({"sku": "Codespaces compute", "unitType": "core-hours", "grossQuantity": 23}) == 23.0
    assert core_hours({"sku": "Codespaces compute", "unitType": "hours", "quantity": 7}) is None
    assert core_hours({"sku": "Codespaces storage", "unitType": "GB-month", "quantity": 11}) is None
    print("CODESPACES_QUOTA_SELFTEST_PASSED")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    print("CODESPACES_BILLING_PERIOD=" + now.strftime("%Y-%m"))
    user = api("/user")
    if user is None or not isinstance(user.get("login"), str):
        print("CODESPACES_ACCOUNT_AUTH_UNAVAILABLE")
        return
    login = user["login"]
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", login):
        print("CODESPACES_ACCOUNT_INVALID")
        return
    plan = user.get("plan") or {}
    plan_name = str(plan.get("name", "")).lower() if isinstance(plan, dict) else ""
    # GitHub's enhanced billing GET endpoints require user Plan(read) permission.
    root = f"/users/{login}/settings/billing/usage"
    query = f"?year={now.year}&month={now.month}"
    doc = api(root + query)
    if doc is None or not isinstance(doc.get("usageItems"), list):
        doc = api(root + "/summary" + query)
    if doc is None:
        print("CODESPACES_BILLING_REPORT=DENIED_OR_UNAVAILABLE")
        print("CODESPACES_HOURS_STATUS=UNKNOWN")
        print("CODESPACES_BILLING_PORTAL=REQUIRED")
        return
    report(doc, plan_name)


if __name__ == "__main__":
    main()
